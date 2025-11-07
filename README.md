# GeeksforGeeks PDF Compiler

Python + Playwright script to export GeeksforGeeks pages to clean, print-friendly PDFs.
- `gfg-to-pdf.py`: export one or many URLs (from `urls.txt`) to PDFs
- Optional: merge later using pypdf

## Quick start
pip install playwright
python -m playwright install chromium
python gfg-to-pdf.py

(Place final GFG URLs in urls.txt, one per line.)
