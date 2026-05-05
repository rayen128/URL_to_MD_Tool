import logging
import re
from pathlib import Path

import html2text
from playwright.sync_api import Page
from pypdf import PdfWriter


def _slugify(text: str) -> str:
    return re.sub(r"[^\w]+", "-", (text or "").lower()).strip("-") or "section"

logger = logging.getLogger("output")


def save_pdf(page: Page, path: Path, page_size: str = "A4") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    page.emulate_media(media="print")
    page.pdf(
        path=str(path),
        format=page_size,
        print_background=True,
        margin={"top": "10mm", "right": "10mm", "bottom": "12mm", "left": "10mm"},
    )


def save_markdown(page: Page, path: Path, include_images: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    article_html = page.evaluate(
        "() => { const el = document.querySelector('article')"
        " || document.querySelector('main') || document.body;"
        " return el ? el.innerHTML : ''; }"
    )
    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = not include_images
    converter.body_width = 0
    text = converter.handle(article_html or "").strip()
    if not text:
        logger.warning(
            "save_markdown produced empty output for %s — "
            "no <article>, <main>, or <body> content found",
            path.name,
        )
    path.write_text(text, encoding="utf-8")


def merge_pdfs(paths: list[Path], out: Path) -> int:
    """Merge PDFs into `out`. Returns count of files skipped due to read errors
    so callers can surface the discrepancy instead of silently shipping a short PDF."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    skipped = 0
    for p in paths:
        try:
            writer.append(str(p))
        except Exception as e:
            skipped += 1
            logger.warning("merge_pdfs: skipping %s (%s)", p, e)
    with out.open("wb") as f:
        writer.write(f)
    writer.close()
    return skipped


def concat_markdown(items: list[dict], out: Path) -> int:
    """Concatenate per-item markdown files into one with H1 dividers + TOC.
    Anchors are emitted as explicit <a id="..."></a> tags before each H1 so TOC
    links resolve regardless of the renderer's auto-slug algorithm. Anchors are
    deduped (-2, -3 ...) so collisions don't silently break links.
    Returns count of items skipped due to read errors."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen: dict[str, int] = {}
    anchors: list[str] = []
    for it in items:
        title = (it.get("title") or it.get("url") or "Untitled").strip()
        base = _slugify(title)
        seen[base] = seen.get(base, 0) + 1
        anchors.append(base if seen[base] == 1 else f"{base}-{seen[base]}")

    parts: list[str] = []
    if items:
        toc_lines = [f"- [{(it.get('title') or it.get('url') or 'Untitled').strip()}](#{a})"
                     for it, a in zip(items, anchors)]
        parts.append("# Contents\n\n" + "\n".join(toc_lines))
    skipped = 0
    for it, anchor in zip(items, anchors):
        title = (it.get("title") or it.get("url") or "Untitled").strip()
        url = it.get("url", "")
        try:
            body = Path(it["file"]).read_text(encoding="utf-8")
        except Exception as e:
            skipped += 1
            logger.warning("concat_markdown: couldn't read %s (%s)", it.get("file"), e)
            continue
        parts.append(f'<a id="{anchor}"></a>\n\n# {title}\n\n_Source: <{url}>_\n\n{body}')
    out.write_text("\n\n---\n\n".join(parts), encoding="utf-8")
    return skipped
