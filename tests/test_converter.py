from unittest.mock import MagicMock
from converter import sanitize_filename, LoadOptions


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


def test_sanitize_filename_with_normalized_https_url():
    result = sanitize_filename("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert result == "www.youtube.com_watch"
    assert result.startswith("www.youtube.com")

