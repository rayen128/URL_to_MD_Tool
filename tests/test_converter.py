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
