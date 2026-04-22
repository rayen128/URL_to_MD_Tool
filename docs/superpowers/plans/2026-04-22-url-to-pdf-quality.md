# URL-to-PDF/Markdown Quality Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `url_to_pdf.py` into three focused modules (`converter`, `output`, `cli`), add `--format md`, `--batch`, and `--collection` flags, write a README, and polish the project for Protinus team use.

**Architecture:** `converter.py` owns the Playwright browser and all paywall-bypass logic exposed as an `open_page()` context manager; `output.py` renders PDF or Markdown from a loaded page; `cli.py` is a thin orchestrator that parses args, resolves output paths, and calls both. `url_to_pdf.py` is deleted once `cli.py` is complete.

**Tech Stack:** Python 3.10+, Playwright (browser automation), pypdf (PDF merging), html2text (HTML→Markdown), pytest (unit tests)

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Initialise git repository**

```bash
git init
```

Expected: `Initialized empty Git repository in .../URL_to_PDF/.git/`

- [ ] **Step 2: Write `requirements.txt`**

```
playwright>=1.50.0
pypdf>=4.0.0
html2text>=2020.1.16
```

- [ ] **Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
playwright-user-data/
output/
debug_*.png
```

- [ ] **Step 4: Create `tests/` with `conftest.py`**

`tests/__init__.py` — empty file.

`tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "Code"))
```

- [ ] **Step 5: Install new dependency**

```bash
pip install html2text
```

Expected: `Successfully installed html2text-...`

- [ ] **Step 6: Commit scaffolding**

```bash
git add requirements.txt .gitignore tests/ CLAUDE.md
git commit -m "chore: add project scaffolding, requirements, and tests directory"
```

---

### Task 2: `converter.py` — pure helpers (TDD first)

**Files:**
- Create: `Code/converter.py`
- Create: `tests/test_converter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_converter.py`:

```python
from unittest.mock import MagicMock
from converter import sanitize_filename, check_content_sufficient, LoadOptions


def test_sanitize_filename_basic():
    assert sanitize_filename("https://example.com/some/article") == "example.com_some_article"


def test_sanitize_filename_strips_special_chars():
    result = sanitize_filename("https://example.com/article?id=123&lang=en")
    assert "?" not in result
    assert "&" not in result
    assert "=" not in result


def test_sanitize_filename_truncates_at_120_chars():
    result = sanitize_filename("https://example.com/" + "a" * 200)
    assert len(result) <= 120


def test_load_options_defaults():
    opts = LoadOptions()
    assert opts.headless is True
    assert opts.use_extension is True
    assert opts.block_images is False
    assert opts.use_freedium is False


def test_check_content_sufficient_passes_on_long_html():
    page = MagicMock()
    page.content.return_value = "x" * 15000
    page.locator.return_value.count.return_value = 10
    assert check_content_sufficient(page) is True


def test_check_content_sufficient_falls_back_to_body_text():
    page = MagicMock()
    page.content.return_value = "x" * 100
    page.locator.return_value.count.return_value = 2
    page.evaluate.return_value = 3000  # body innerText.length > 2000
    assert check_content_sufficient(page) is True


def test_check_content_sufficient_fails_on_sparse_page():
    page = MagicMock()
    page.content.return_value = "x" * 100
    page.locator.return_value.count.return_value = 2
    page.evaluate.return_value = 100
    assert check_content_sufficient(page) is False
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_converter.py -v
```

Expected: `ModuleNotFoundError: No module named 'converter'`

- [ ] **Step 3: Create `Code/converter.py` with constants, dataclass, and pure helpers**

```python
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, Page, BrowserContext

# --- Constants ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
EXTENSION_ID = "ghkdkllgoehcklnpajjjmfoaokabfdfm"
EXTENSION_PATH = Path(__file__).parent / "remove_paywall_extension"
PAGE_LOAD_TIMEOUT_MS = 90_000
NETWORK_IDLE_TIMEOUT_MS = 30_000
COOKIE_TIMEOUT_MS = 5_000
SCROLL_STEP_PX = 2_000
SCROLL_MAX_STEPS = 30
SCROLL_PAUSE_MS = 500
MIN_CONTENT_LENGTH = 10_000
MIN_PARAGRAPH_COUNT = 5
MIN_BODY_TEXT_LENGTH = 2_000

COOKIE_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('I accept')",
    "button:has-text('I Agree')",
    "button:has-text('Agree')",
    "button:has-text('Allow all')",
    "[data-testid='cookie-accept-all']",
]


@dataclass
class LoadOptions:
    headless: bool = True
    use_extension: bool = True
    block_images: bool = False
    use_freedium: bool = False


def sanitize_filename(url: str) -> str:
    parsed = urlparse(url)
    base = f"{parsed.netloc}_{parsed.path}".strip("/").replace("/", "_")
    base = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    return base[:120] if base else "page"


def check_content_sufficient(
    page: Page,
    min_length: int = MIN_CONTENT_LENGTH,
    min_paragraphs: int = MIN_PARAGRAPH_COUNT,
) -> bool:
    content = page.content() or ""
    paragraphs = page.locator("article p, section p, div[class*='article'] p").count()
    if len(content) > min_length and paragraphs > min_paragraphs:
        return True
    body_text = page.evaluate("() => document.body.innerText.length")
    return body_text > MIN_BODY_TEXT_LENGTH


def _auto_scroll(page: Page, max_steps: int = SCROLL_MAX_STEPS) -> None:
    last_height = page.evaluate("document.body.scrollHeight")
    steps = 0
    while steps < max_steps:
        page.evaluate(f"window.scrollBy(0, {SCROLL_STEP_PX});")
        page.wait_for_timeout(SCROLL_PAUSE_MS)
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height - last_height < 100:
            break
        last_height = new_height
        steps += 1
    page.evaluate("window.scrollTo(0, 0);")


def _accept_cookies(page: Page) -> None:
    for sel in COOKIE_SELECTORS:
        try:
            btn = page.locator(sel)
            if btn.is_visible(timeout=COOKIE_TIMEOUT_MS):
                btn.first.click()
                page.wait_for_timeout(1000)
                return
        except Exception:
            pass


def _detect_amp_url(page: Page) -> str | None:
    try:
        amp_link = page.locator('link[rel="amphtml"]')
        if amp_link.count() > 0:
            return amp_link.first.get_attribute("href")
    except Exception:
        pass
    return None


def _remove_paywalls(page: Page, is_medium: bool = False) -> None:
    if is_medium:
        js = """() => {
            document.querySelectorAll('div.meteredContent, section[class*="locked"], div.paywall, [class*="paywall"], .meter-banner, .locked-content').forEach(el => {
                el.remove(); el.style.display = 'none';
            });
            document.body.classList.remove('meter-locked', 'paywall-active');
            document.querySelectorAll('p, h1, h2, img').forEach(el => {
                el.style = 'filter: none !important; visibility: visible !important; opacity: 1 !important;';
            });
            localStorage.setItem('mediumUnlimited', 'true');
        }"""
    else:
        js = """() => {
            document.querySelectorAll('div[class*="paywall"], #paywall, [class*="meter"], [class*="lock"], .overlay, .backdrop').forEach(el => el.remove());
            document.body.style.overflow = 'auto';
            document.documentElement.style.overflow = 'auto';
            document.querySelectorAll('*').forEach(el => {
                if (getComputedStyle(el).filter === 'blur(5px)' || el.classList.contains('blurred'))
                    el.style.filter = 'none';
            });
        }"""
    page.evaluate(js)
    page.wait_for_timeout(2000)


def _enable_extension(context: BrowserContext, page: Page) -> None:
    for attempt in range(3):
        try:
            popup = context.new_page()
            popup.goto(f"chrome-extension://{EXTENSION_ID}/popup.html", timeout=10_000)
            btn = popup.locator("button, [role='button']")
            if btn.is_visible():
                btn.first.click()
            popup.close()
            page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
            return
        except Exception as e:
            print(f"  Extension attempt {attempt + 1}/3 failed: {e}")
            page.wait_for_timeout(2000)


def _try_load(
    page: Page,
    context: BrowserContext,
    url: str,
    is_medium: bool,
    use_extension: bool,
) -> tuple[bool, str | None]:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
        _accept_cookies(page)
        if use_extension:
            _enable_extension(context, page)
        _remove_paywalls(page, is_medium)
        _auto_scroll(page)
        page.wait_for_timeout(3000)
        _remove_paywalls(page, is_medium)
        if check_content_sufficient(page):
            return True, "normal"
    except Exception as e:
        print(f"  Normal load failed: {e}")

    amp_url = _detect_amp_url(page)
    if not amp_url:
        for candidate in [f"{url}?amp=1", f"{url}/amp"]:
            try:
                resp = page.goto(candidate, timeout=30_000)
                if resp and resp.status == 200:
                    amp_url = candidate
                    break
            except Exception:
                continue

    if amp_url:
        try:
            page.goto(amp_url, wait_until="networkidle")
            _accept_cookies(page)
            _remove_paywalls(page)
            _auto_scroll(page, max_steps=15)
            if check_content_sufficient(page, min_paragraphs=3):
                return True, "amp"
        except Exception as e:
            print(f"  AMP fallback failed: {e}")

    return False, None


@contextmanager
def open_page(url: str, options: LoadOptions):
    """
    Context manager: launches Chromium, loads url with paywall bypass, yields the
    ready Page. Cleans up browser and playwright-user-data/ on exit.
    Raises RuntimeError if content cannot be loaded.
    """
    if options.use_freedium:
        url = f"https://freedium.cfd/{url}"
        print("  Using Freedium proxy.")

    is_medium = "medium.com" in urlparse(url).netloc
    parsed = urlparse(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"

    user_data_dir = Path.cwd() / "playwright-user-data"
    user_data_dir.mkdir(exist_ok=True)

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    use_ext = options.use_extension and EXTENSION_PATH.exists()
    if use_ext:
        launch_args += [
            f"--disable-extensions-except={EXTENSION_PATH}",
            f"--load-extension={EXTENSION_PATH}",
        ]

    playwright = sync_playwright().start()
    context = None
    try:
        context = playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            channel="chromium",
            headless=options.headless,
            args=launch_args,
            user_agent=USER_AGENT,
            locale="en-US",
            extra_http_headers={"Referer": referer},
            ignore_https_errors=True,
        )
        block_types = ["font", "media"]
        if options.block_images:
            block_types.append("image")
        context.route(
            "**/*",
            lambda route: route.abort()
            if route.request.resource_type in block_types
            else route.continue_(),
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})

        success, mode = _try_load(page, context, url, is_medium, use_ext)
        if not success:
            page.screenshot(path="debug_failed_load.png")
            raise RuntimeError(
                "Could not load page content. Screenshot saved to debug_failed_load.png. "
                "Try --no-extension, --freedium, or --no-headless."
            )
        print(f"  Loaded via {mode} mode.")
        yield page
    finally:
        if context:
            context.close()
        playwright.stop()
        shutil.rmtree(user_data_dir, ignore_errors=True)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_converter.py -v
```

Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add Code/converter.py tests/test_converter.py
git commit -m "feat: add converter.py with browser logic and paywall bypass"
```

---

### Task 3: `output.py` (TDD)

**Files:**
- Create: `Code/output.py`
- Create: `tests/test_output.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_output.py`:

```python
from unittest.mock import MagicMock
from output import save_pdf, save_markdown


def test_save_pdf_calls_emulate_media_and_pdf(tmp_path):
    page = MagicMock()
    save_pdf(page, tmp_path / "out.pdf")
    page.emulate_media.assert_called_once_with(media="print")
    page.pdf.assert_called_once()


def test_save_pdf_creates_nested_parent_dir(tmp_path):
    page = MagicMock()
    out = tmp_path / "nested" / "dir" / "out.pdf"
    save_pdf(page, out)
    assert out.parent.exists()


def test_save_markdown_creates_file(tmp_path):
    page = MagicMock()
    page.evaluate.return_value = "<h1>Hello</h1><p>World paragraph.</p>"
    out = tmp_path / "test.md"
    save_markdown(page, out)
    assert out.exists()


def test_save_markdown_heading_appears_in_output(tmp_path):
    page = MagicMock()
    page.evaluate.return_value = "<h1>Article Title</h1><p>Body text.</p>"
    out = tmp_path / "test.md"
    save_markdown(page, out)
    assert "Article Title" in out.read_text(encoding="utf-8")


def test_save_markdown_creates_nested_parent_dir(tmp_path):
    page = MagicMock()
    page.evaluate.return_value = "<p>Content</p>"
    out = tmp_path / "nested" / "dir" / "test.md"
    save_markdown(page, out)
    assert out.exists()
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_output.py -v
```

Expected: `ModuleNotFoundError: No module named 'output'`

- [ ] **Step 3: Create `Code/output.py`**

```python
from pathlib import Path

import html2text
from playwright.sync_api import Page


def save_pdf(page: Page, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    page.emulate_media(media="print")
    page.pdf(
        path=str(path),
        format="A4",
        print_background=True,
        margin={"top": "10mm", "right": "10mm", "bottom": "12mm", "left": "10mm"},
    )


def save_markdown(page: Page, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    article_html = page.evaluate(
        "() => { const el = document.querySelector('article')"
        " || document.querySelector('main') || document.body;"
        " return el ? el.innerHTML : ''; }"
    )
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0
    path.write_text(converter.handle(article_html or "").strip(), encoding="utf-8")
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_output.py -v
```

Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add Code/output.py tests/test_output.py
git commit -m "feat: add output.py for PDF and Markdown rendering"
```

---

### Task 4: `cli.py` with `--format`, `--batch`, `--collection` (TDD)

**Files:**
- Create: `Code/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cli.py`:

```python
import pytest
from pathlib import Path
from cli import resolve_output_path, parse_batch_file


def test_resolve_output_path_pdf_no_collection(tmp_path):
    path = resolve_output_path("https://example.com/article", "pdf", None, tmp_path)
    assert path.parent == tmp_path
    assert path.suffix == ".pdf"


def test_resolve_output_path_md_no_collection(tmp_path):
    path = resolve_output_path("https://example.com/article", "md", None, tmp_path)
    assert path.suffix == ".md"


def test_resolve_output_path_with_collection(tmp_path):
    path = resolve_output_path("https://example.com/article", "pdf", "My Course", tmp_path)
    assert path.parent == tmp_path / "My_Course"
    assert path.suffix == ".pdf"


def test_resolve_output_path_spaces_become_underscores(tmp_path):
    path = resolve_output_path("https://example.com/a", "md", "Salesforce CRM Docs", tmp_path)
    assert path.parent.name == "Salesforce_CRM_Docs"


def test_resolve_output_path_creates_collection_dir(tmp_path):
    resolve_output_path("https://example.com/a", "pdf", "New Collection", tmp_path)
    assert (tmp_path / "New_Collection").is_dir()


def test_parse_batch_file_returns_urls(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("https://example.com/1\nhttps://example.com/2\n", encoding="utf-8")
    assert parse_batch_file(f) == ["https://example.com/1", "https://example.com/2"]


def test_parse_batch_file_skips_comments_and_blanks(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text(
        "https://example.com/1\n# comment\n\nhttps://example.com/2\n",
        encoding="utf-8",
    )
    assert parse_batch_file(f) == ["https://example.com/1", "https://example.com/2"]


def test_parse_batch_file_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_batch_file(tmp_path / "nonexistent.txt")
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_cli.py -v
```

Expected: `ModuleNotFoundError: No module named 'cli'`

- [ ] **Step 3: Create `Code/cli.py`**

```python
#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from converter import LoadOptions, open_page, sanitize_filename
from output import save_pdf, save_markdown

OUTPUT_ROOT = Path(__file__).parent.parent / "output"


def resolve_output_path(
    url: str, fmt: str, collection: str | None, output_root: Path
) -> Path:
    stem = sanitize_filename(url)
    suffix = ".pdf" if fmt == "pdf" else ".md"
    folder = output_root / collection.replace(" ", "_") if collection else output_root
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (stem + suffix)


def parse_batch_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Batch file not found: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def _process_url(
    url: str,
    fmt: str,
    collection: str | None,
    options: LoadOptions,
    output_root: Path,
) -> None:
    out_path = resolve_output_path(url, fmt, collection, output_root)
    print(f"Converting: {url}")
    print(f"  Output:    {out_path}")
    with open_page(url, options) as page:
        if fmt == "pdf":
            save_pdf(page, out_path)
        else:
            save_markdown(page, out_path)
    print("  Done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert web pages to PDF or Markdown with paywall bypass.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py https://example.com/article
  python cli.py https://example.com/article --format md --collection "My Course"
  python cli.py --batch urls.txt --format md --collection "Salesforce Docs"
        """,
    )
    parser.add_argument("url", nargs="?", help="Single URL to convert")
    parser.add_argument("--batch", metavar="FILE", help="Text file with one URL per line")
    parser.add_argument("--format", choices=["pdf", "md"], default="pdf", help="Output format (default: pdf)")
    parser.add_argument("--collection", metavar="NAME", help="Group outputs into a named subfolder under output/")
    parser.add_argument("--output-dir", metavar="DIR", default=str(OUTPUT_ROOT), help=f"Output root directory (default: {OUTPUT_ROOT})")
    parser.add_argument("--no-headless", dest="headless", action="store_false", default=True, help="Show browser window")
    parser.add_argument("--no-extension", action="store_true", help="Skip paywall-removal Chrome extension")
    parser.add_argument("--no-images", action="store_true", help="Block images for faster loading")
    parser.add_argument("--freedium", action="store_true", help="Route Medium.com articles through Freedium proxy")

    args = parser.parse_args()

    if not args.url and not args.batch:
        parser.error("Provide either a URL or --batch FILE")
    if args.url and args.batch:
        parser.error("Provide either a URL or --batch FILE, not both")

    options = LoadOptions(
        headless=args.headless,
        use_extension=not args.no_extension,
        block_images=args.no_images,
        use_freedium=args.freedium,
    )
    output_root = Path(args.output_dir)

    if args.batch:
        urls = parse_batch_file(Path(args.batch))
        print(f"Batch: {len(urls)} URL(s) to process.")
        errors: list[tuple[str, str]] = []
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}]")
            try:
                _process_url(url, args.format, args.collection, options, output_root)
            except Exception as e:
                print(f"  ERROR: {e}")
                errors.append((url, str(e)))
        if errors:
            print(f"\n{len(errors)} URL(s) failed:")
            for url, err in errors:
                print(f"  {url}: {err}")
            sys.exit(1)
    else:
        _process_url(args.url, args.format, args.collection, options, output_root)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run full test suite — verify everything passes**

```bash
pytest tests/ -v
```

Expected: All 20 tests PASS

- [ ] **Step 5: Commit**

```bash
git add Code/cli.py tests/test_cli.py
git commit -m "feat: add cli.py with --format, --batch, and --collection support"
```

---

### Task 5: Remove `url_to_pdf.py` and smoke test

**Files:**
- Delete: `Code/url_to_pdf.py`

- [ ] **Step 1: Verify `cli.py` `--help` output**

```bash
python Code/cli.py --help
```

Expected: Usage message listing `url`, `--batch`, `--format`, `--collection`, `--output-dir`, `--no-headless`, `--no-extension`, `--no-images`, `--freedium`.

- [ ] **Step 2: Smoke test with a real URL**

```bash
python Code/cli.py "https://help.openai.com/en/articles/6654000" --format pdf --collection "Test"
```

Expected output ends with:
```
  Loaded via normal mode.
  Done.
```
And `output/Test/help.openai.com_en_articles_6654000.pdf` exists.

- [ ] **Step 3: Smoke test Markdown format**

```bash
python Code/cli.py "https://help.openai.com/en/articles/6654000" --format md --collection "Test"
```

Expected: `output/Test/help.openai.com_en_articles_6654000.md` exists and contains readable text.

- [ ] **Step 4: Delete `url_to_pdf.py`**

```bash
git rm Code/url_to_pdf.py
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: replace url_to_pdf.py with cli.py + converter.py + output.py"
```

---

### Task 6: `README.md`

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# URL to PDF / Markdown

Convert any web page — including paywalled articles — to a **PDF** or **Markdown** file for use in AI workflows (custom GPTs, RAG pipelines, NotebookLM, and similar tools).

## Setup

**Prerequisites:** Python 3.10+

```bash
pip install -r requirements.txt
playwright install chromium
```

## Quick start

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

If a page fails to convert, two debug screenshots are saved in the current directory: `debug_failed_load.png` and `debug_final.png`. Run with `--no-headless` to watch the browser in real time, or try `--freedium` for Medium.com articles.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup, usage, and all flags"
```

---

### Task 7: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace `CLAUDE.md` content**

Replace the entire file with:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md to reflect new three-module structure"
```

---

## Self-review

**Spec coverage check:**
- ✅ `requirements.txt` — Task 1
- ✅ `.gitignore` — Task 1
- ✅ `converter.py` with all Playwright/paywall logic — Task 2
- ✅ `output.py` with `save_pdf` and `save_markdown` — Task 3
- ✅ `cli.py` with `--format`, `--batch`, `--collection` — Task 4
- ✅ `url_to_pdf.py` deleted — Task 5
- ✅ Smoke tests for both formats — Task 5
- ✅ `README.md` with setup, flags, batch example, troubleshooting — Task 6
- ✅ `CLAUDE.md` updated — Task 7
- ✅ `combine_pdfs.py` — unchanged, referenced in README and CLAUDE.md

**Type consistency:**
- `sanitize_filename` returns `str` (stem only, no suffix) — suffix added in `resolve_output_path` ✅
- `open_page` is a context manager yielding `Page` — used with `with open_page(...) as page:` in `cli.py` ✅
- `resolve_output_path` returns `Path` — passed to `save_pdf`/`save_markdown` which both accept `Path` ✅
- `parse_batch_file` takes `Path`, returns `list[str]` ✅

**Placeholder scan:** No TBDs, TODOs, or vague steps. All code blocks are complete. ✅
