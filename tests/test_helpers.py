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


def test_normalize_raises_for_garbage_with_spaces():
    with pytest.raises(ValueError):
        normalize_url("not a url at all")


def test_normalize_raises_for_single_label_hostname():
    with pytest.raises(ValueError):
        normalize_url("hello")


def test_normalize_unwraps_markdown_link():
    assert normalize_url("[Title](https://example.com/x)") == "https://example.com/x"


def test_normalize_unwraps_angle_brackets():
    assert normalize_url("<https://example.com>") == "https://example.com"


def test_normalize_strips_trailing_punctuation():
    assert normalize_url("https://example.com/x.") == "https://example.com/x"
    assert normalize_url("https://example.com/x,") == "https://example.com/x"
    assert normalize_url("https://example.com/x).") == "https://example.com/x"


def test_normalize_rejects_javascript_scheme():
    with pytest.raises(ValueError):
        normalize_url("javascript:alert(1)")


def test_normalize_rejects_ftp_scheme():
    with pytest.raises(ValueError):
        normalize_url("ftp://example.com")


def test_normalize_rejects_file_scheme():
    with pytest.raises(ValueError):
        normalize_url("file:///etc/passwd")


def test_normalize_rejects_userinfo():
    with pytest.raises(ValueError):
        normalize_url("user@example.com")
    with pytest.raises(ValueError):
        normalize_url("https://user:pass@example.com")


def test_normalize_rejects_overlong_url():
    with pytest.raises(ValueError):
        normalize_url("https://example.com/" + "x" * 3000)
