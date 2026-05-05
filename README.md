# URL to PDF / Markdown

Convert any web page — including paywalled articles — to a **PDF** or **Markdown** file for use in AI workflows (custom GPTs, RAG pipelines, NotebookLM, and similar tools).

## Setup

**Prerequisites:** Python 3.10+ and Node.js 20+

```bash
pip install -r requirements.txt
playwright install chromium
npm ci
```

## Web UI

Run the FastAPI backend:

```bash
python Code/server.py
```

In a second terminal, run the Next.js frontend:

```bash
npm run dev
```

Open `http://localhost:3000` in your browser. The frontend proxies `/api/*` requests to `http://127.0.0.1:8000` by default. To point the UI at a different backend, set `BACKEND_URL` before starting Next.js.

Paste URLs, choose a format, optionally name the collection, and convert. Saved jobs appear in My Collection and are persisted under `output/_meta/`. Logs are written to `logs/server.log` and `logs/jobs.log`; both are cleared on each backend restart.

## Quick start (CLI)

```bash
# Single URL → PDF (default)
python Code/cli.py https://example.com/article

# Single URL → Markdown
python Code/cli.py https://example.com/article --format md

# Group outputs by topic into output/My_Collection/
python Code/cli.py https://example.com/article --format md --collection "My Collection"

# Batch: process all URLs in a text file
python Code/cli.py --batch urls.txt --format md --collection "Salesforce Course"

# Merge all PDFs in a collection into one file
python Code/combine_pdfs.py output/Salesforce_Course
```

## Batch file format

Plain text file, one URL per line. Lines starting with `#` and blank lines are ignored.

```
# Salesforce CRM Analytics — Bindings
https://help.salesforce.com/s/articleView?id=sf.bi_setup.htm
https://help.salesforce.com/s/articleView?id=sf.bi_embed.htm
```

Run it:

```bash
python Code/cli.py --batch urls.txt --format md --collection "Salesforce CRM"
```

All outputs land in `output/Salesforce_CRM/`. Feed that folder to your agent or upload the combined PDF to a custom GPT.

## All flags

| Flag | Description |
|---|---|
| `--format pdf\|md` | Output format (default: `pdf`) |
| `--collection NAME` | Group outputs into `output/NAME/` subfolder |
| `--batch FILE` | Process all URLs in a text file |
| `--output-dir DIR` | Override output root (default: `output/`) |
| `--no-headless` | Show browser window — useful for debugging |
| `--no-extension` | Skip the paywall-removal Chrome extension |
| `--no-images` | Block images for faster loading |
| `--freedium` | Route Medium.com articles through Freedium proxy |

## Combining PDFs

```bash
python Code/combine_pdfs.py output/My_Collection                      # → combined.pdf
python Code/combine_pdfs.py output/My_Collection True                 # recursive
python Code/combine_pdfs.py output/My_Collection False my_output.pdf  # custom name
```

## Troubleshooting

If a page fails to convert, a debug screenshot is saved in `logs/debug_screenshots/` with a timestamped, URL-based filename. Run with `--no-headless` to watch the browser in real time, or try `--freedium` for Medium.com articles.

## Improving the converter with Claude Code

This repository ships a Claude Code skill — **`fix-conversion-failures`** — that helps diagnose and fix URLs that fail to convert. If you use Claude Code, the skill activates automatically whenever a conversion fails or you describe a scraping problem. It reads the logs and debug screenshots, classifies the failure (paywall, cookie banner, timeout, content check too strict, …), and proposes a targeted fix before touching any file.

To use it, open this repository in Claude Code and describe what's failing — or just paste a URL that doesn't work. Claude will take it from there.

**If the skill leads you to a fix that improves scraping for a site others are likely to hit**, please fork the repository and open a pull request with the change. Fixes to `COOKIE_SELECTORS`, `_remove_paywalls()`, and the content-check thresholds in `Code/converter.py` are the most common improvements and are easy to review.
