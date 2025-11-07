# 🧩 GeeksforGeeks Notes to PDF Compiler

> Turn entire GeeksforGeeks topic hubs (like *Operating Systems*, *DBMS*, etc.) into one clean, study-ready PDF — automatically.

---

## 🚀 Overview

**GeekPDF** is a Python + Playwright-based script that:
- Crawls any **GeeksforGeeks topic hub page**
- Extracts every **article link** under that topic
- Cleans away ads, comments, author cards, and social clutter
- Compiles all the notes into **one beautifully formatted A4 PDF**

Perfect for quick revision, offline reading, or printing high-quality study notes.

---

## 📦 Features

✅ Automatically finds and visits all sub-topic links under a GFG hub  
✅ Removes comments, “Improve Article”, author boxes, and social widgets  
✅ Uniform typography and minimal white-space for print/PDF  
✅ Supports code blocks, images, and tables  
✅ One-click run — no manual copy-pasting of pages  
✅ Generates **one single combined PDF**

---

## 🛠️ Requirements

- Python **3.9+**
- [Playwright](https://playwright.dev/python/) installed with browser binaries

### Install once:

```bash
pip install playwright
python -m playwright install chromium
```

# ⚙️ Usage
## 1. Clone this repo
```bash
git clone https://github.com/<your-username>/GeekPDF.git
cd GeekPDF
```
## 2. Set the topic hub URL
Open gfg_hub_to_single_pdf.py and edit this line:

```bash
HUB_URL = "https://www.geeksforgeeks.org/operating-systems/operating-systems/"
```
You can replace it with any topic hub — e.g.
"https://www.geeksforgeeks.org/database-management-system-dbms/"

## 3. Run the Script
```bash
python gfg_hub_to_single_pdf.py
```

## 4. Output:

```bash
Collecting links from hub…
Found 26 links.
[1/26] Fetching: https://www.geeksforgeeks.org/.../
...
Saved: GFG_Operating_Systems_Notes.pdf
```
The compiled PDF will appear in the project folder.


