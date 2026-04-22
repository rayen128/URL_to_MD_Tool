import pytest
from pathlib import Path
from cli import resolve_output_path, parse_batch_file


def test_resolve_output_path_pdf_no_collection(tmp_path):
    path = resolve_output_path("https://example.com/article", "pdf", None, tmp_path)
    assert path.parent == tmp_path
    assert path.suffix == ".pdf"


def test_resolve_output_path_md_no_collection(tmp_path):
    path = resolve_output_path("https://example.com/article", "md", None, tmp_path)
    assert path.suffix == ".md"


def test_resolve_output_path_with_collection(tmp_path):
    path = resolve_output_path("https://example.com/article", "pdf", "My Course", tmp_path)
    assert path.parent == tmp_path / "My_Course"
    assert path.suffix == ".pdf"


def test_resolve_output_path_spaces_become_underscores(tmp_path):
    path = resolve_output_path("https://example.com/a", "md", "Salesforce CRM Docs", tmp_path)
    assert path.parent.name == "Salesforce_CRM_Docs"


def test_resolve_output_path_creates_collection_dir(tmp_path):
    resolve_output_path("https://example.com/a", "pdf", "New Collection", tmp_path)
    assert (tmp_path / "New_Collection").is_dir()


def test_parse_batch_file_returns_urls(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("https://example.com/1\nhttps://example.com/2\n", encoding="utf-8")
    assert parse_batch_file(f) == ["https://example.com/1", "https://example.com/2"]


def test_parse_batch_file_skips_comments_and_blanks(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text(
        "https://example.com/1\n# comment\n\nhttps://example.com/2\n",
        encoding="utf-8",
    )
    assert parse_batch_file(f) == ["https://example.com/1", "https://example.com/2"]


def test_parse_batch_file_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_batch_file(tmp_path / "nonexistent.txt")
