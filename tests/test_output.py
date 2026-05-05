from unittest.mock import MagicMock, patch
from pathlib import Path

from pypdf import PdfWriter

from output import save_pdf, save_markdown, merge_pdfs, concat_markdown


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


def test_save_pdf_default_page_size_is_a4(tmp_path):
    page = MagicMock()
    save_pdf(page, tmp_path / "out.pdf")
    _, kwargs = page.pdf.call_args
    assert kwargs["format"] == "A4"


def test_save_pdf_custom_page_size(tmp_path):
    page = MagicMock()
    save_pdf(page, tmp_path / "out.pdf", page_size="Letter")
    _, kwargs = page.pdf.call_args
    assert kwargs["format"] == "Letter"


def test_save_markdown_strips_images_by_default(tmp_path):
    page = MagicMock()
    page.evaluate.return_value = '<img src="photo.jpg"><p>Body text</p>'
    out = tmp_path / "out.md"
    save_markdown(page, out)
    assert "photo.jpg" not in out.read_text(encoding="utf-8")


def test_save_markdown_includes_images_when_requested(tmp_path):
    page = MagicMock()
    page.evaluate.return_value = '<img src="photo.jpg" alt="Photo"><p>Body text</p>'
    out = tmp_path / "out.md"
    save_markdown(page, out, include_images=True)
    assert "photo.jpg" in out.read_text(encoding="utf-8")


def test_save_markdown_warns_on_empty_content(tmp_path):
    page = MagicMock()
    page.evaluate.return_value = ""
    out = tmp_path / "empty.md"
    with patch("output.logger") as mock_logger:
        save_markdown(page, out)
    mock_logger.warning.assert_called_once()
    assert out.exists()


def _write_minimal_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as f:
        writer.write(f)


def test_merge_pdfs_returns_zero_when_all_succeed(tmp_path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    _write_minimal_pdf(a)
    _write_minimal_pdf(b)
    out = tmp_path / "merged.pdf"
    skipped = merge_pdfs([a, b], out)
    assert skipped == 0
    assert out.exists() and out.stat().st_size > 0


def test_merge_pdfs_counts_skipped_on_bad_input(tmp_path):
    good = tmp_path / "good.pdf"
    _write_minimal_pdf(good)
    missing = tmp_path / "nope.pdf"
    out = tmp_path / "merged.pdf"
    skipped = merge_pdfs([good, missing], out)
    assert skipped == 1
    assert out.exists()


def test_merge_pdfs_creates_parent_dir(tmp_path):
    a = tmp_path / "a.pdf"
    _write_minimal_pdf(a)
    out = tmp_path / "nested" / "merged.pdf"
    merge_pdfs([a], out)
    assert out.exists()


def test_concat_markdown_emits_toc_and_anchors(tmp_path):
    f1 = tmp_path / "one.md"
    f1.write_text("Body one.", encoding="utf-8")
    f2 = tmp_path / "two.md"
    f2.write_text("Body two.", encoding="utf-8")
    items = [
        {"title": "First page", "url": "https://x/1", "file": str(f1)},
        {"title": "Second page", "url": "https://x/2", "file": str(f2)},
    ]
    out = tmp_path / "merged.md"
    skipped = concat_markdown(items, out)
    text = out.read_text(encoding="utf-8")
    assert skipped == 0
    assert "# Contents" in text
    assert "(#first-page)" in text and "(#second-page)" in text
    assert '<a id="first-page"></a>' in text
    assert "Body one." in text and "Body two." in text


def test_concat_markdown_dedupes_duplicate_anchors(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("body", encoding="utf-8")
    items = [
        {"title": "Same", "url": "https://x/1", "file": str(f)},
        {"title": "Same", "url": "https://x/2", "file": str(f)},
        {"title": "Same", "url": "https://x/3", "file": str(f)},
    ]
    out = tmp_path / "merged.md"
    concat_markdown(items, out)
    text = out.read_text(encoding="utf-8")
    assert '<a id="same"></a>' in text
    assert '<a id="same-2"></a>' in text
    assert '<a id="same-3"></a>' in text


def test_concat_markdown_skips_unreadable_files(tmp_path):
    good = tmp_path / "good.md"
    good.write_text("ok", encoding="utf-8")
    items = [
        {"title": "Good", "url": "u1", "file": str(good)},
        {"title": "Missing", "url": "u2", "file": str(tmp_path / "absent.md")},
    ]
    out = tmp_path / "merged.md"
    skipped = concat_markdown(items, out)
    assert skipped == 1
    text = out.read_text(encoding="utf-8")
    assert "Good" in text
    # Missing file's anchor still appears in TOC, but no body section is emitted
    assert text.count("<a id=") == 1


def test_concat_markdown_handles_missing_title(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("body", encoding="utf-8")
    items = [{"url": "https://example.com/article", "file": str(f)}]
    out = tmp_path / "merged.md"
    concat_markdown(items, out)
    text = out.read_text(encoding="utf-8")
    assert "https://example.com/article" in text
