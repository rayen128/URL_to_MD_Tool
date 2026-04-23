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
