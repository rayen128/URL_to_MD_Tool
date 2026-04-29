from unittest.mock import MagicMock
from converter import _extract_links, _in_scope


def _make_page(hrefs: list[str], current_url: str = "https://docs.example.com/guide/intro") -> MagicMock:
    page = MagicMock()
    page.url = current_url
    page.evaluate.return_value = hrefs
    return page


HOSTNAME = "docs.example.com"
PREFIXES = ["/guide/"]


# --- _in_scope ---

def test_in_scope_exact_prefix_root():
    assert _in_scope("/guide", ["/guide/"])

def test_in_scope_child_path():
    assert _in_scope("/guide/advanced", ["/guide/"])

def test_in_scope_deeply_nested():
    assert _in_scope("/guide/section/subsection", ["/guide/"])

def test_not_in_scope_different_section():
    assert not _in_scope("/api-reference/method", ["/guide/"])

def test_not_in_scope_prefix_collision():
    # /guide-v2 must NOT match prefix /guide/
    assert not _in_scope("/guide-v2/page", ["/guide/"])

def test_in_scope_multiple_prefixes():
    assert _in_scope("/api/method", ["/guide/", "/api/"])
    assert _in_scope("/guide/intro", ["/guide/", "/api/"])

def test_not_in_scope_no_matching_prefix():
    assert not _in_scope("/other/page", ["/guide/", "/api/"])


# --- _extract_links ---

def test_keeps_same_prefix_link():
    page = _make_page(["https://docs.example.com/guide/advanced"])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == ["https://docs.example.com/guide/advanced"]

def test_drops_different_section_link():
    page = _make_page(["https://docs.example.com/api/method"])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == []

def test_drops_external_domain():
    page = _make_page(["https://external.com/guide/intro"])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == []

def test_drops_fragment_only():
    page = _make_page(["#section-2"])
    page.url = "https://docs.example.com/guide/intro"
    result = _extract_links(page, PREFIXES, HOSTNAME)
    # #section-2 resolves to same page — which is in scope, but fragment is stripped
    # The canonical URL is https://docs.example.com/guide/intro (already visited — no re-add here)
    # It will be returned since _extract_links doesn't know about visited set
    assert result == ["https://docs.example.com/guide/intro"]

def test_strips_trailing_slash_deduplication():
    page = _make_page([
        "https://docs.example.com/guide/about/",
        "https://docs.example.com/guide/about",
    ])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert len(result) == 1
    assert result[0] == "https://docs.example.com/guide/about"

def test_strips_query_string():
    page = _make_page(["https://docs.example.com/guide/page?utm_source=nav&print=1"])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == ["https://docs.example.com/guide/page"]

def test_strips_query_and_fragment():
    page = _make_page(["https://docs.example.com/guide/page?v=2#section"])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == ["https://docs.example.com/guide/page"]

def test_drops_mailto():
    page = _make_page(["mailto:support@example.com"])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == []

def test_drops_tel():
    page = _make_page(["tel:+1234567890"])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == []

def test_drops_javascript():
    page = _make_page(["javascript:void(0)"])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == []

def test_resolves_relative_links():
    # "advanced" relative to /guide/intro resolves to /guide/advanced (sibling)
    page = _make_page(["advanced"], current_url="https://docs.example.com/guide/intro")
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == ["https://docs.example.com/guide/advanced"]

def test_relative_parent_out_of_scope():
    # ../advanced from /guide/intro resolves to /advanced — outside /guide/ prefix
    page = _make_page(["../advanced"], current_url="https://docs.example.com/guide/intro")
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == []

def test_deduplicates_same_url():
    page = _make_page([
        "https://docs.example.com/guide/page",
        "https://docs.example.com/guide/page",
        "/guide/page",
    ])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert len(result) == 1

def test_empty_href_skipped():
    page = _make_page(["", None, "https://docs.example.com/guide/valid"])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == ["https://docs.example.com/guide/valid"]

def test_drops_prefix_collision_link():
    # /guide-v2/page must not be returned when prefix is /guide/
    page = _make_page(["https://docs.example.com/guide-v2/page"])
    result = _extract_links(page, PREFIXES, HOSTNAME)
    assert result == []
