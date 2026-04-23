from pathlib import Path

import html2text
from playwright.sync_api import Page


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
    path.write_text(converter.handle(article_html or "").strip(), encoding="utf-8")
