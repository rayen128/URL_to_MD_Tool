import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import server
from server import app, _convert_one_sync
from jobs import JobStore


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    s = JobStore()
    monkeypatch.setattr(server, "store", s)
    return s


def test_collections_empty_on_start(fresh_store):
    with TestClient(app) as client:
        r = client.get("/api/collections")
    assert r.status_code == 200
    assert r.json() == []


def test_collections_returns_started_jobs(fresh_store):
    fresh_store.create(urls=["https://a.com"], fmt="pdf", name="My Docs", options={})
    with TestClient(app) as client:
        r = client.get("/api/collections")
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "My Docs"
    assert data[0]["format"] == "pdf"
    assert data[0]["done"] == 0
    assert data[0]["errors"] == 0
    assert "createdAt" in data[0]


def test_delete_collection_removes_job(fresh_store):
    job = fresh_store.create(urls=["https://a.com"], fmt="pdf", name="X", options={})
    with TestClient(app) as client:
        r = client.delete(f"/api/collections/{job['id']}")
    assert r.status_code == 200
    assert fresh_store.get(job["id"]) is None


def test_delete_collection_returns_404_for_unknown(fresh_store):
    with TestClient(app) as client:
        r = client.delete("/api/collections/no-such-job")
    assert r.status_code == 404


def test_post_convert_returns_job_id_and_items(fresh_store):
    with TestClient(app) as client:
        r = client.post("/api/convert", json={
            "urls": ["https://example.com/a", "https://example.com/b"],
            "format": "pdf",
            "collection": "Test",
            "options": {"images": True, "reader": True, "pageSize": "A4"},
        })
    assert r.status_code == 200
    data = r.json()
    assert "job_id" in data
    assert len(data["items"]) == 2
    assert data["items"][0]["status"] == "queued"
    assert data["items"][0]["domain"] == "example.com"


def test_convert_one_sync_success(fresh_store, tmp_path):
    job = fresh_store.create(
        urls=["https://example.com/page"], fmt="pdf", name="test",
        options={"images": True, "reader": True, "pageSize": "A4"},
    )
    item = job["items"][0]
    mock_page = MagicMock()
    mock_page.title.return_value = "Test Page Title"

    def fake_save_pdf(page, path, page_size="A4"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake pdf content")

    with patch("server.open_page") as mock_open, \
         patch("server.save_pdf", side_effect=fake_save_pdf), \
         patch("server.OUTPUT_ROOT", tmp_path):
        mock_open.return_value.__enter__ = lambda s: mock_page
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        _convert_one_sync(job, item)

    assert item["status"] == "done"
    assert item["title"] == "Test Page Title"
    assert item["size"] > 0
    assert item["filename"].endswith(".pdf")


def test_convert_one_sync_sets_error_on_exception(fresh_store, tmp_path):
    job = fresh_store.create(
        urls=["https://example.com/page"], fmt="pdf", name="",
        options={"images": True, "reader": True, "pageSize": "A4"},
    )
    item = job["items"][0]
    with patch("server.open_page") as mock_open, \
         patch("server.OUTPUT_ROOT", tmp_path):
        mock_open.side_effect = RuntimeError("Could not load page")
        _convert_one_sync(job, item)
    assert item["status"] == "error"
    assert "Could not load page" in item["error"]


def test_convert_one_sync_skips_when_cancelled(fresh_store, tmp_path):
    job = fresh_store.create(
        urls=["https://example.com/page"], fmt="pdf", name="",
        options={"images": True, "reader": True, "pageSize": "A4"},
    )
    job["cancelled"] = True
    item = job["items"][0]
    with patch("server.open_page") as mock_open, \
         patch("server.OUTPUT_ROOT", tmp_path):
        _convert_one_sync(job, item)
        mock_open.assert_not_called()
    assert item["status"] == "error"
    assert item["error"] == "Cancelled"


def test_convert_one_sync_passes_options_correctly(fresh_store, tmp_path):
    job = fresh_store.create(
        urls=["https://example.com/page"], fmt="markdown", name="",
        options={"images": False, "reader": False, "pageSize": "Letter"},
    )
    item = job["items"][0]
    mock_page = MagicMock()
    mock_page.title.return_value = "Page"
    captured = {}

    def fake_save_md(page, path, include_images=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# content", encoding="utf-8")
        captured["include_images"] = include_images

    def fake_open_page(url, options):
        captured["options"] = options
        cm = MagicMock()
        cm.__enter__ = lambda s: mock_page
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    with patch("server.open_page", side_effect=fake_open_page), \
         patch("server.save_markdown", side_effect=fake_save_md), \
         patch("server.OUTPUT_ROOT", tmp_path):
        _convert_one_sync(job, item)

    assert captured["options"].block_images is True
    assert captured["options"].use_extension is False
    assert captured["include_images"] is False


def test_cancel_sets_cancelled_flag(fresh_store):
    job = fresh_store.create(urls=["https://a.com"], fmt="pdf", name="", options={})
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job['id']}/cancel")
    assert r.status_code == 200
    assert job["cancelled"] is True


def test_cancel_marks_queued_items_as_error(fresh_store):
    job = fresh_store.create(
        urls=["https://a.com", "https://b.com"], fmt="pdf", name="", options={}
    )
    with TestClient(app) as client:
        client.post(f"/api/jobs/{job['id']}/cancel")
    assert all(i["status"] == "error" for i in job["items"])
    assert all(i["error"] == "Cancelled" for i in job["items"])


def test_cancel_returns_404_for_unknown(fresh_store):
    with TestClient(app) as client:
        r = client.post("/api/jobs/no-such/cancel")
    assert r.status_code == 404


def test_retry_requeues_item_and_clears_cancelled(fresh_store):
    job = fresh_store.create(urls=["https://a.com"], fmt="pdf", name="", options={})
    item = job["items"][0]
    item["status"] = "error"
    item["error"] = "Previous failure"
    job["cancelled"] = True

    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job['id']}/retry/{item['id']}")

    assert r.status_code == 200
    assert item["status"] == "queued"
    assert item["error"] is None
    assert job["cancelled"] is False


def test_retry_returns_404_for_unknown_job(fresh_store):
    with TestClient(app) as client:
        r = client.post("/api/jobs/no-such/retry/u-0")
    assert r.status_code == 404


def test_stream_returns_404_for_unknown_job(fresh_store):
    with TestClient(app) as client:
        r = client.get("/api/jobs/no-such/stream")
    assert r.status_code == 404
