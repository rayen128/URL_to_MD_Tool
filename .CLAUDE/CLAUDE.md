# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate virtual environment
source .venv/Scripts/activate   # Windows Git Bash

# Convert a URL to PDF or Markdown
python Code/cli.py "https://example.com/article"
python Code/cli.py "https://example.com/article" --format md --collection "My Course"

# Batch mode
python Code/cli.py --batch urls.txt --format md --collection "Salesforce Docs"

# Key flags
--format pdf|md    # Output format (default: pdf)
--collection NAME  # Group outputs into output/NAME/
--no-headless      # Show browser window (debugging)
--no-extension     # Skip Chrome paywall-removal extension
--no-images        # Block images for faster loading
--freedium         # Route Medium.com articles through Freedium proxy

# Combine PDFs
python Code/combine_pdfs.py "output/My_Collection"
python Code/combine_pdfs.py "output/My_Collection" True           # recursive
python Code/combine_pdfs.py "output/My_Collection" False "out.pdf"  # custom name

# Start web UI
python Code/server.py
# Opens http://localhost:8000 in the default browser
# Ctrl+C to stop

# Run all unit tests
pytest tests/ -v

# Run a single test file
pytest tests/test_cli.py -v
```

## Architecture

### Module layout

```
Code/
  cli.py                     # Entry point: argparse, batch loop, collection folders
  converter.py               # Playwright browser, paywall bypass, AMP fallback
  output.py                  # save_pdf() and save_markdown()
  combine_pdfs.py            # Standalone PDF merger (no dependency on other modules)
  remove_paywall_extension/  # Unpacked Chrome extension loaded by Playwright
output/                      # Default output root; subfolders created by --collection
tests/                       # pytest unit tests — no real browser required
```

### `cli.py` — orchestrator

Parses arguments, calls `resolve_output_path()` to determine the destination file, then uses `open_page()` from `converter.py` and the appropriate save function from `output.py`. The batch loop isolates per-URL errors so one failure doesn't abort the rest.

### `converter.py` — browser and paywall bypass

Exposes `open_page(url, LoadOptions)` as a `@contextmanager`. Internally:
1. Launches a persistent Chromium context with anti-bot flags and the optional Chrome extension.
2. Loads the page (`domcontentloaded` → `networkidle`), runs cookie acceptance, extension activation, JS paywall removal, and auto-scroll.
3. Falls back to the AMP version if `check_content_sufficient()` fails.
4. Yields the ready `Page`; cleans up the browser and `playwright-user-data/` directory on exit.

All tunable values (timeouts, scroll settings, User-Agent, extension ID) are module-level constants at the top of the file.

### `output.py` — rendering

- `save_pdf(page, path)` — switches Playwright to print-media emulation and calls `page.pdf()` (A4, 10 mm margins).
- `save_markdown(page, path)` — extracts `<article>` / `<main>` / `<body>` innerHTML via `page.evaluate()`, converts to Markdown with `html2text` (links preserved, images stripped, no line wrapping).

### `combine_pdfs.py` — PDF merger

Standalone script. Scans a directory for `.pdf` files, sorts by filename, merges with `pypdf.PdfWriter`. No dependency on `converter` or `output`.

## Non-obvious implementation notes

- **`sanitize_filename` returns a stem, not a full filename** — no `.pdf`/`.md` suffix. The suffix is added in `cli.py:resolve_output_path`. Don't add it inside `sanitize_filename`.
- **All paths in `converter.py` are `Path(__file__).parent.parent`-relative** (project root), not `Path.cwd()`-relative. This matters when the tool is run from a different working directory.
- **`open_page` cleanup is exception-safe** — `context.close()` and `playwright.stop()` are each wrapped in independent try/except blocks so a browser crash doesn't leak the Playwright process.
- **Tests use mocked Playwright pages** — no real browser required. `tests/conftest.py` adds `Code/` to `sys.path` so test files can import `from converter import ...` directly.
- **`url_to_pdf.py` was the old monolithic script — it has been deleted.** `Code/cli.py` is the replacement entry point.

## Key Dependencies

| Package | Purpose |
|---|---|
| `playwright` | Headless Chromium automation |
| `html2text` | HTML → Markdown conversion in `output.py` |
| `pypdf` | PDF merging in `combine_pdfs.py` |

Install Playwright browsers after `pip install -r requirements.txt`:
```bash
playwright install chromium
```
