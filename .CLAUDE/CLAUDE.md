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

# Start backend API (FastAPI on :8000)
python Code/server.py
# Ctrl+C to stop

# Start frontend (Next.js on :3000) — proxies /api/* to :8000 (see next.config.mjs)
npm install
npm run dev

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
  helpers.py                 # normalize_url(): shared URL normalization for cli.py and server.py
  converter.py               # Playwright browser, paywall bypass, AMP fallback
  rules.py                   # Content-validation (check_content) + site detection (SiteHeuristics, website_heuristics)
  output.py                  # save_pdf, save_markdown, merge_pdfs, concat_markdown
  server.py                  # FastAPI backend: /api/convert, /api/jobs/{id}/{stream,merged,zip}, /api/collections
  jobs.py                    # JobStore: runtime state in memory + JSON snapshots in output/_meta/
  combine_pdfs.py            # Standalone PDF merger (no dependency on other modules)
  remove_paywall_extension/  # Unpacked Chrome extension loaded by Playwright
output/                      # Default output root; subfolders created by --collection
output/_merged/              # Cached merged downloads (one file per job_id)
output/_meta/                # Persisted JobStore snapshots (one JSON per job_id)
tests/                       # pytest unit tests — no real browser required
app/                         # Next.js 16 app router (layout, page, globals)
components/                  # converter-form.jsx + shadcn ui primitives
lib/                         # url, format, hooks/use-conversion-job
```

### `cli.py` — orchestrator

Parses arguments, calls `normalize_url()` from `helpers.py` then `resolve_output_path()` to determine the destination file, then uses `open_page()` from `converter.py` and the appropriate save function from `output.py`. The batch loop isolates per-URL errors so one failure doesn't abort the rest.

### `converter.py` — browser and paywall bypass

Exposes `open_page(url, LoadOptions)` as a `@contextmanager`. Internally:
1. Launches a persistent Chromium context with anti-bot flags and the optional Chrome extension.
2. Loads the page (`domcontentloaded` → `networkidle`), runs cookie acceptance, extension activation, JS paywall removal, and auto-scroll.
3. Falls back to the AMP version if `check_content()` fails.
4. Yields the ready `Page`; cleans up the browser and `playwright-user-data/` directory on exit.

All tunable values (timeouts, scroll settings, User-Agent, extension ID) are module-level constants at the top of the file.

### `output.py` — rendering

- `save_pdf(page, path)` — switches Playwright to print-media emulation and calls `page.pdf()` (A4, 10 mm margins).
- `save_markdown(page, path)` — extracts `<article>` / `<main>` / `<body>` innerHTML via `page.evaluate()`, converts to Markdown with `html2text` (links preserved, images stripped, no line wrapping).

### `combine_pdfs.py` — PDF merger

Standalone script. Scans a directory for `.pdf` files, sorts by filename, merges with `pypdf.PdfWriter`. No dependency on `converter` or `output`.

## Non-obvious implementation notes

- **`open_page` uses a unique `user_data_dir` per call** (`playwright-user-data/<uuid>/`) — Chromium's `launch_persistent_context` only allows one instance per directory, so a shared path causes `TargetClosedError` under concurrent load. The `finally` block cleans up each subdirectory via `shutil.rmtree`.
- **Startup cleanup on Windows/OneDrive: use `.iterdir()` + `.unlink()`, not `shutil.rmtree()`** — `rmtree` on a directory inside an OneDrive-synced path raises `PermissionError: [WinError 5]`. Delete files individually and leave the directory in place.
- **Startup side effects are guarded by `sys._server_logs_cleared`** — `server.py` is imported twice (once as `__main__`, once by uvicorn). This flag ensures log-clearing and directory-wiping run only once per process.
- **`sanitize_filename` returns a stem, not a full filename** — no `.pdf`/`.md` suffix. The suffix is added in `cli.py:resolve_output_path`. Don't add it inside `sanitize_filename`. Stems are truncated at 120 characters.
- **Incomplete URLs are accepted and normalized** — `normalize_url()` in `helpers.py` prepends `https://` to scheme-less inputs (`www.youtube.com` → `https://www.youtube.com`). Both `cli.py` and `server.py` call this before any processing. The hostname must contain a dot; single-label inputs (`hello`) raise `ValueError`.
- **Frontend is Next.js 16 + shadcn (Tailwind v4)** — entry is `app/page.jsx` → `components/converter-form.jsx`. Run `npm run dev` for the dev server. The legacy `web/` Babel-CDN UI was removed in commit 10b363b.
- **Backend timeout leaks intentionally** — `_run_with_timeout` cancels the asyncio future on `ITEM_TIMEOUT`, but the underlying Playwright thread can't be killed. `_executor` is sized at `CONCURRENCY + 2` to absorb leaked slots; `_semaphore` enforces real backpressure at `CONCURRENCY`.
- **Merged downloads are cached per job** — `output/_merged/{job_id}.{ext}`. `job["merged_dirty"]` is set on every successful conversion and on retry; `download_merged` rebuilds when dirty. `_merge_executor` is a separate single-thread pool so merges never block the conversion executor. The `X-Merged-Skipped` response header reports how many files failed to merge.
- **JobStore is partially persisted** — `JobStore.persist` snapshots persistable fields (id, name, format, items, recursive crawl state) to `output/_meta/{job_id}.json` on create / item-success / rename, and unlinks on delete. Runtime-only state (asyncio queues, event-loop refs, the `cancelled` flag, `merged_dirty`) is **not** persisted. On startup, `JobStore.hydrate` loads snapshots and flips any `queued` / `working` items to `error: "Interrupted"` — hydrated jobs are observable (downloadable, renameable) but cannot resume conversion. Hot-reloading the server (`uvicorn --reload`) will trip the hydrate path on every output write — don't enable reload here.
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
