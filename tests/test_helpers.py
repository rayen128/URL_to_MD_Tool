import pytest
from helpers import normalize_url


def test_normalize_strips_whitespace():
    assert normalize_url("  https://example.com  ") == "https://example.com"


def test_normalize_protocol_relative():
    assert normalize_url("//example.com/page") == "https://example.com/page"


def test_normalize_adds_https_to_www_domain():
    assert normalize_url("www.youtube.com") == "https://www.youtube.com"


def test_normalize_adds_https_to_bare_domain_with_path():
    assert normalize_url("youtube.com/watch?v=x") == "https://youtube.com/watch?v=x"


def test_normalize_leaves_https_url_unchanged():
    assert normalize_url("https://example.com") == "https://example.com"


def test_normalize_leaves_http_url_unchanged():
    assert normalize_url("http://intranet.local") == "http://intranet.local"


def test_normalize_raises_for_empty_string():
    with pytest.raises(ValueError):
        normalize_url("   ")


def test_normalize_raises_for_scheme_only():
    with pytest.raises(ValueError):
        normalize_url("https://")
