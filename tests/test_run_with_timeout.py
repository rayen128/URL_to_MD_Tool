import asyncio
import json
import time

import pytest

import jobs as jobs_module
import server
from jobs import JobStore


@pytest.fixture
def fresh_store(monkeypatch):
    s = JobStore()
    monkeypatch.setattr(server, "store", s)
    return s


def _make_item(job_id: str, url: str = "https://example.com") -> dict:
    return {
        "id": "u-0", "url": url, "domain": "example.com", "favicon": "",
        "status": "queued", "title": None, "file": None, "size": None,
        "filename": None, "error": None,
    }


@pytest.mark.asyncio
async def test_run_with_timeout_returns_result_when_fast(fresh_store, monkeypatch):
    job = fresh_store.create(urls=["https://x"], fmt="pdf", name="t", options={})
    item = job["items"][0]

    def fake_convert(j, i):
        return ["https://discovered"]

    monkeypatch.setattr(server, "_convert_one_sync", fake_convert)
    loop = asyncio.get_running_loop()
    result = await server._run_with_timeout(loop, job, item)
    assert result == ["https://discovered"]
    assert item["status"] != "error"


@pytest.mark.asyncio
async def test_run_with_timeout_marks_error_on_timeout(fresh_store, monkeypatch):
    job = fresh_store.create(urls=["https://x"], fmt="pdf", name="t", options={})
    item = job["items"][0]

    def slow_convert(j, i):
        time.sleep(2.0)
        return []

    monkeypatch.setattr(server, "_convert_one_sync", slow_convert)
    monkeypatch.setattr(server, "ITEM_TIMEOUT", 0.05)
    loop = asyncio.get_running_loop()
    result = await server._run_with_timeout(loop, job, item)
    assert result == []
    assert item["status"] == "error"
    assert "longer than" in item["error"].lower()
    persisted = json.loads((jobs_module.META_DIR / f"{job['id']}.json").read_text(encoding="utf-8"))
    assert persisted["items"][0]["status"] == "error"
    assert "longer than" in persisted["items"][0]["error"].lower()


@pytest.mark.asyncio
async def test_run_with_timeout_pushes_status_event(fresh_store, monkeypatch):
    job = fresh_store.create(urls=["https://x"], fmt="pdf", name="t", options={})
    item = job["items"][0]

    def slow_convert(j, i):
        time.sleep(2.0)
        return []

    monkeypatch.setattr(server, "_convert_one_sync", slow_convert)
    monkeypatch.setattr(server, "ITEM_TIMEOUT", 0.05)
    loop = asyncio.get_running_loop()
    await server._run_with_timeout(loop, job, item)
    event = await asyncio.wait_for(fresh_store.get_event(job["id"]), timeout=1.0)
    assert event["type"] == "status"
    assert event["status"] == "error"
    assert event["url_id"] == item["id"]
