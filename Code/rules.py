from playwright.sync_api import Page

MIN_CONTENT_LENGTH = 10_000
MIN_PARAGRAPH_COUNT = 5
MIN_BODY_TEXT_LENGTH = 500


def _check_html_length(page: Page, min_length: int = MIN_CONTENT_LENGTH) -> tuple[bool, str | None]:
    content = page.content() or ""
    if len(content) > min_length:
        return True, None
    return False, f"HTML too short ({len(content):,} chars, minimum {min_length:,})"


def _check_paragraph_count(page: Page, min_paragraphs: int = MIN_PARAGRAPH_COUNT) -> tuple[bool, str | None]:
    paragraphs = page.locator("article p, section p, div[class*='article'] p").count()
    if paragraphs > min_paragraphs:
        return True, None
    return False, f"too few article paragraphs ({paragraphs}, minimum {min_paragraphs})"


def _check_body_text(page: Page, min_body: int = MIN_BODY_TEXT_LENGTH) -> tuple[bool, str | None]:
    body_text = page.evaluate("() => document.body.innerText.length")
    if body_text > min_body:
        return True, None
    return False, f"body text too short ({body_text:,} chars, minimum {min_body:,})"


def check_content(
    page: Page,
    min_length: int = MIN_CONTENT_LENGTH,
    min_paragraphs: int = MIN_PARAGRAPH_COUNT,
) -> tuple[bool, str | None]:
    """Returns (True, None) if content is sufficient, (False, reason) otherwise."""
    html_ok, html_reason = _check_html_length(page, min_length)
    para_ok, para_reason = _check_paragraph_count(page, min_paragraphs)
    if html_ok and para_ok:
        return True, None

    body_ok, body_reason = _check_body_text(page)
    if body_ok:
        return True, None

    reasons = [r for r in [html_reason, para_reason, body_reason] if r]
    return False, "; ".join(reasons)
