import asyncio, re, urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

# === CONFIG ===
HUB_URL = "https://www.geeksforgeeks.org/operating-systems/operating-systems/"
OUT_PDF = "GFG_Operating_Systems_Notes.pdf"
MAX_LINKS = 0  # 0 = all collected

# Keep only links under this path prefix (adjust if you change hub/topic)
REQUIRED_PATH_FRAGMENT = "/operating-systems/"

# Exclude these patterns (e.g., quizzes, tags, category pages)
EXCLUDE_PATTERNS = [
    "/quiz/",
    "/tag/",
    "/category/",
    "/author/",
    "#",  # in-page anchors
]

BASE_CSS = r"""
@page { size: A4; margin: 14mm; }

/* 1) Reset & compact defaults */
* { box-sizing: border-box; }
html, body { padding: 0; margin: 0; background: #fff; }
:where(h1,h2,h3,p,ul,ol,pre,table,figure){ margin-block-start: 0; margin-block-end: 0; }
:where(p){ margin: 4px 0; }
:where(ul,ol){ padding-left: 1.2em; margin: 6px 0; }

/* 2) Typography */
body { font-family: -apple-system, system-ui, Segoe UI, Roboto, Ubuntu, Cantarell, "Helvetica Neue", Arial; line-height: 1.35; }
h1,h2,h3 { line-height: 1.25; }
h1 { font-size: 22px; margin: 0 0 10px 0; }
h2 { font-size: 18px; margin: 16px 0 8px 0; }
h3 { font-size: 16px; margin: 12px 0 6px 0; }
p, li { font-size: 12.5px; }

/* 3) Code & tables */
pre, code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; }
pre { font-size: 12px; white-space: pre-wrap; background: #fafafa; border: 1px solid #eee; padding: 8px; border-radius: 6px; page-break-inside: avoid; }
table { width: 100%; border-collapse: collapse; margin: 10px 0; page-break-inside: avoid; }
th, td { border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; word-break: break-word; }

/* 4) Media */
img { max-width: 100%; height: auto; page-break-inside: avoid; }
figure { page-break-inside: avoid; }

/* 5) Page-break rules (no lonely headings) */
h1, h2, h3 { break-after: avoid; }
h1 + p, h2 + p, h3 + p, h1 + ul, h2 + ul, h3 + ul { break-before: avoid; }
.article { page-break-before: always; margin: 0; padding: 0; }
.article:first-of-type { page-break-before: avoid; }
.toc { page-break-after: always; }

/* 6) Hide leftover site chrome if any slipped into extracted HTML */
header, .header, nav, .nav, footer, .footer,
aside, .sidebar, #sidebar,
.comments, .comments-area, #comments, .comment-form, .reply,
.article-tags, .tags, .tag-container, .gfg-tags,
.share, .sharethis-inline-share-buttons, .share-bar, .social,
.gfg-cookie-policy, .gdpr,
.author, .author-info, .author-details, .author-box, .byline, .meta-info,
.improve-article, .feedback-area, .suggest-changes, .vote-wrap, .like-button, .reaction,
.related-posts, .related-articles,
.subscribe, .newsletter,
.ad, [id*="google_ads"], [class*="ads"], [data-ad], .advertisement {
  display: none !important;
}

/* 7) Kill thin “stripe” spacers */
.strip, .spacer, hr { display: none !important; }
div[style*="background"], section[style*="background"] { background: transparent !important; }

/* 8) Links plain */
a { color: inherit; text-decoration: none; }

/* 9) Details expanded look */
details { margin: 8px 0; }
"""


# Selectors we’ll try (GFG has changed layouts over time). First match wins.
ARTICLE_SELECTORS = [
    "article",                 # most modern pages
    ".article--container",     # variant
    ".content",                # fallback
    "main",                    # broad fallback
    "#primary",                # older WP structures
]

def _is_good_link(href: str) -> bool:
    if not href: return False
    if not href.startswith("http"): return False
    if "geeksforgeeks.org" not in href: return False
    if REQUIRED_PATH_FRAGMENT and REQUIRED_PATH_FRAGMENT not in urllib.parse.urlparse(href).path:
        return False
    for bad in EXCLUDE_PATTERNS:
        if bad in href:
            return False
    return True

def _sanitize_filename(s: str) -> str:
    s = re.sub(r"[\\/*?:\"<>|]+", "", s)
    return s.strip()

async def extract_article_html(page) -> tuple[str, str]:
    """Return (title, clean_html) for the main content of a GFG article page."""
    # Title
    title = (await page.title()).strip()
    title = re.sub(r"\s+–\s*GeeksforGeeks.*$", "", title)  # trim site suffix if present
    title = _sanitize_filename(title) or "Untitled"

    # Find a main article container
    handle = None
    for sel in ARTICLE_SELECTORS:
        try:
            h = page.locator(sel).first
            await h.wait_for(state="visible", timeout=5000)
            if await h.count() > 0:
                handle = h
                break
        except Exception:
            continue

    if handle is None:
        # Fallback to body (last resort)
        handle = page.locator("body")

    # Hide site chrome/noise from the DOM we’ll clone
    try:
        await page.evaluate("""
(() => {
  // 1) Remove known chrome / meta / social / feedback / tag boxes
  const kill = sel => document.querySelectorAll(sel).forEach(e => e.remove());
  kill(`
    header, .header, nav, .nav, footer, .footer,
    aside, .sidebar, #sidebar,
    .comments, .comments-area, #comments, .comment-form, .reply,
    .article-tags, .tags, .tag-container, .gfg-tags,
    .share, .sharethis-inline-share-buttons, .share-bar, .social,
    .gfg-cookie-policy, .gdpr,
    .author, .author-info, .author-details, .author-box, .byline, .meta-info,
    .improve-article, .feedback-area, .suggest-changes, .vote-wrap, .like-button, .reaction,
    .related-posts, .related-articles,
    .subscribe, .newsletter,
    .ad, [id*="google_ads"], [class*="ads"], [data-ad], .advertisement
  `);

  // 2) Remove buttons/links by text (Follow, Comment, Like, Report...)
  const killByText = (root, phrases) => {
    root.querySelectorAll('a, button, div, span').forEach(el => {
      const t = (el.innerText || '').trim().toLowerCase();
      if (!t) return;
      if (phrases.some(p => t === p || t.startsWith(p))) el.remove();
    });
  };
  killByText(document, ['comment', 'follow', '+ follow', 'like', 'report', 'improve', 'suggest changes', 'article tags']);

  // 3) Remove <hr> and thin colored strips/spacers w/ background
  document.querySelectorAll('hr').forEach(el => el.remove());
  document.querySelectorAll('div, section, p, span').forEach(el => {
    const cs = getComputedStyle(el);
    const bg = cs.backgroundColor;
    const hasBG = bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent';
    const onlyWhitespace = (el.innerText || '').trim().length === 0 && el.querySelectorAll('img, pre, table, code, ul, ol').length === 0;
    const veryThin = el.offsetHeight > 0 && el.offsetHeight <= 28 && el.offsetWidth >= 200; // kill the green stripe-like blocks
    if ((onlyWhitespace && !el.children.length) || (hasBG && veryThin)) el.remove();
  });

  // 4) Open any <details> so hidden explanations are visible
  document.querySelectorAll('details').forEach(d => d.open = true);

  // 5) Final pass: remove now-empty containers
  document.querySelectorAll('div, section').forEach(el => {
    const txt = (el.innerText || '').trim();
    if (!txt && el.querySelectorAll('img, pre, table, code, ul, ol').length === 0) el.remove();
  });
})();
""")

    except Exception:
        pass

    # Force lazy images to load by scrolling a bit
    try:
        await page.evaluate("""
          let y = 0; const step = 600; 
          const end = Math.min(4000, document.body.scrollHeight);
          const scroller = async () => {
            while (y < end) { window.scrollBy(0, step); y += step; await new Promise(r=>setTimeout(r,100)); }
            window.scrollTo(0,0);
          };
          return scroller();
        """)
        await page.wait_for_timeout(400)  # give images a tick
    except Exception:
        pass

    # Pull innerHTML of the chosen container
    html = await handle.evaluate("el => el.innerHTML")
    # Remove superfluous “read more”, share blocks if any leaked
    html = re.sub(r'<script[\s\S]*?</script>', '', html, flags=re.I)
    html = re.sub(r'<style[\s\S]*?</style>', '', html, flags=re.I)

    # Wrap in minimal article section with a normalized H1
    article_html = f"""
    <section class="article">
      <h1>{title}</h1>
      {html}
    </section>
    """
    return title, article_html

async def fetch_links_from_hub(page, hub_url: str) -> list[str]:
    await page.goto(hub_url, wait_until="domcontentloaded", timeout=180000)

    # Try to accept cookie banners if any
    for sel in ["button:has-text('Accept')", "button:has-text('AGREE')",
                "button:has-text('I Accept')", "[aria-label*='Accept']",
                ".gdpr button", ".fc-cta-consent"]:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=1000):
                await btn.click()
                break
        except Exception:
            pass

    # Collect all anchors inside main/article/content area
    anchors = await page.eval_on_selector_all(
        "main, article, .content, #primary",
        "nodes => Array.from(new Set(nodes.flatMap(n => Array.from(n.querySelectorAll('a')).map(a => a.href))))"
    )
    # Filter/normalize/dedupe while preserving order
    seen = set()
    links = []
    for href in anchors:
        href = href.strip()
        if _is_good_link(href) and href not in seen:
            seen.add(href)
            links.append(href)

    if MAX_LINKS and MAX_LINKS > 0:
        links = links[:MAX_LINKS]
    return links

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Safari/605.1.15"
        )
        page = await context.new_page()

        print("Collecting links from hub…")
        links = await fetch_links_from_hub(page, HUB_URL)
        if not links:
            print("No links found. Check HUB_URL or filters.")
            await context.close(); await browser.close()
            return

        print(f"Found {len(links)} links.")
        articles = []
        toc = []
        idx = 0

        for url in links:
            idx += 1
            print(f"[{idx}/{len(links)}] Fetching: {url}")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=180000)
                title, art_html = await extract_article_html(page)
                articles.append(art_html)
                toc.append(f"<li><a href='#sec-{idx}'>{title}</a></li>")
                # add an anchor id to each section after the fact
                articles[-1] = articles[-1].replace('<section class="article">', f'<section class="article" id="sec-{idx}">', 1)
            except PWTimeoutError:
                print(f"  - timeout, skipping")
            except Exception as e:
                print(f"  - error: {e}, skipping")

        # Build a clean combined HTML document (with a simple TOC)
        joined_articles = "\n".join(articles)
        html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Operating Systems – GeeksforGeeks (Compiled Notes)</title>
  <style>{BASE_CSS}</style>
</head>
<body>
  <section class="toc">
    <h1>Operating Systems – Compiled Notes</h1>
    <p>Source: <a href="{HUB_URL}">{HUB_URL}</a></p>
    <h2>Contents</h2>
    <ol>
      {''.join(toc)}
    </ol>
  </section>

  {joined_articles}
</body>
</html>"""


        # Render this HTML in a fresh page and print to PDF (no header/footer)
        pdf_page = await context.new_page()
        await pdf_page.set_content(html, wait_until="load")
        await pdf_page.pdf(
            path=OUT_PDF,
            format="A4",
            margin={"top": "14mm", "right": "14mm", "bottom": "14mm", "left": "14mm"},
            print_background=True,
            display_header_footer=False
        )
        print(f"\nSaved: {OUT_PDF}")

        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
