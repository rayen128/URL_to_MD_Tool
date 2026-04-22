from unittest.mock import MagicMock
from output import save_pdf, save_markdown


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
