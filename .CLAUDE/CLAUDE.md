# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate virtual environment
source .venv/Scripts/activate   # Windows Git Bash
# or
.venv\Scripts\activate          # Windows CMD/PowerShell

# Convert a URL to PDF
python Code/url_to_pdf.py "https://example.com/article"
python Code/url_to_pdf.py "https://example.com/article" "output.pdf"

# Key flags
--no-headless      # Show browser window (useful for debugging)
--no-extension     # Skip Chrome paywall-removal extension
--no-images        # Block images for faster loading
--freedium         # Route Medium.com articles through Freedium proxy

# Combine PDFs in a directory
python Code/combine_pdfs.py "/path/to/pdfs"
python Code/combine_pdfs.py "/path/to/pdfs" True          # recursive
python Code/combine_pdfs.py "/path/to/pdfs" False "out.pdf"  # custom output name
```

## Architecture

### `url_to_pdf.py` — main conversion script

Launches a persistent Playwright Chromium instance (user data stored in `playwright-user-data/`) with anti-bot detection measures (custom User-Agent, disabled automation flags). The conversion pipeline:

1. **Load page** — waits for `networkidle`, then auto-scrolls to trigger lazy-loaded content.
2. **Bypass paywalls** — three layered strategies run in order:
   - Inject JavaScript to remove paywall overlay elements and unlock CSS `overflow: hidden`.
   - Click cookie consent buttons via a hardcoded CSS selector list.
   - Medium.com-specific logic that surgically removes the metered paywall DOM nodes.
3. **Validate content** — aborts and falls back to the AMP version (`/amp` suffix) if the extracted text is under 10,000 characters or fewer than 5 paragraphs.
4. **Generate PDF** — switches Playwright to print-media emulation and renders A4 with 10 mm margins.

On failure, debug screenshots are written to `debug_failed_load.png` and `debug_final.png`.

### `combine_pdfs.py` — batch PDF merger

Scans a directory (optionally recursive) for `.pdf` files, sorts them by filename, and merges them with `pypdf.PdfWriter`. The output file is automatically excluded from the input list to avoid self-inclusion.

### `remove_paywall_extension/` — Chrome extension

Manifest V3 extension loaded unpacked into the Playwright browser context. When triggered, it redirects the active tab through `removepaywalls.com`. It is an optional layer; `--no-extension` skips loading it.

## Key Dependencies

| Package | Purpose |
|---|---|
| `playwright` | Headless Chromium automation |
| `pypdf` | PDF merging in `combine_pdfs.py` |
| `beautifulsoup4` | HTML parsing for content validation |
| `python-dotenv` | (available, not currently used) |

Install Playwright browsers after installing the package:
```bash
playwright install chromium
```
