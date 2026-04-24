from unittest.mock import MagicMock
from rules import check_content, _check_html_length, _check_paragraph_count, _check_body_text


def test_check_html_length_passes_on_long_html():
    page = MagicMock()
    page.content.return_value = "x" * 15_000
    ok, reason = _check_html_length(page)
    assert ok is True
    assert reason is None


def test_check_html_length_fails_with_reason():
    page = MagicMock()
    page.content.return_value = "x" * 100
    ok, reason = _check_html_length(page)
    assert ok is False
    assert "100" in reason
    assert "10,000" in reason


def test_check_paragraph_count_passes():
    page = MagicMock()
    page.locator.return_value.count.return_value = 10
    ok, reason = _check_paragraph_count(page)
    assert ok is True
    assert reason is None


def test_check_paragraph_count_fails_with_reason():
    page = MagicMock()
    page.locator.return_value.count.return_value = 2
    ok, reason = _check_paragraph_count(page)
    assert ok is False
    assert "2" in reason


def test_check_paragraph_count_respects_custom_min():
    page = MagicMock()
    page.locator.return_value.count.return_value = 0
    ok, reason = _check_paragraph_count(page, min_paragraphs=0)
    assert ok is False  # 0 > 0 is False; custom min_paragraphs=0 still fails on zero paragraphs


def test_check_body_text_passes():
    page = MagicMock()
    page.evaluate.return_value = 1_000
    ok, reason = _check_body_text(page)
    assert ok is True
    assert reason is None


def test_check_body_text_fails_with_reason():
    page = MagicMock()
    page.evaluate.return_value = 100
    ok, reason = _check_body_text(page)
    assert ok is False
    assert "100" in reason
    assert "500" in reason


def test_check_content_passes_on_html_and_paragraphs():
    page = MagicMock()
    page.content.return_value = "x" * 15_000
    page.locator.return_value.count.return_value = 10
    ok, reason = check_content(page)
    assert ok is True
    assert reason is None


def test_check_content_falls_back_to_body_text():
    page = MagicMock()
    page.content.return_value = "x" * 100
    page.locator.return_value.count.return_value = 2
    page.evaluate.return_value = 1_000
    ok, reason = check_content(page)
    assert ok is True
    assert reason is None


def test_check_content_fails_with_combined_reasons():
    page = MagicMock()
    page.content.return_value = "x" * 100
    page.locator.return_value.count.return_value = 2
    page.evaluate.return_value = 100
    ok, reason = check_content(page)
    assert ok is False
    assert reason is not None
    assert "; " in reason  # multiple failure reasons are joined
    assert "too few article paragraphs" in reason
    assert "body text too short" in reason


def test_check_content_reason_mentions_body_text_count():
    page = MagicMock()
    page.content.return_value = "x" * 100
    page.locator.return_value.count.return_value = 2
    page.evaluate.return_value = 88
    ok, reason = check_content(page)
    assert ok is False
    assert "88" in reason
