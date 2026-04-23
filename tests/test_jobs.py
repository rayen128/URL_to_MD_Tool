import asyncio
from jobs import JobStore, _domain, _favicon


def make_store():
    return JobStore()


def test_create_returns_job_with_correct_shape():
    s = make_store()
    job = s.create(urls=["https://example.com/page"], fmt="pdf", name="My Docs", options={})
    assert job["id"].startswith("j-")
    assert job["name"] == "My Docs"
    assert job["format"] == "pdf"
    assert job["cancelled"] is False
    assert len(job["items"]) == 1


def test_create_item_has_expected_fields():
    s = make_store()
    job = s.create(urls=["https://www.example.com/page"], fmt="pdf", name="", options={})
    item = job["items"][0]
    assert item["id"] == "u-0"
    assert item["url"] == "https://www.example.com/page"
    assert item["domain"] == "example.com"
    assert "example.com" in item["favicon"]
    assert item["status"] == "queued"
    assert item["file"] is None


def test_get_returns_same_job_object():
    s = make_store()
    job = s.create(urls=["https://a.com"], fmt="pdf", name="", options={})
    assert s.get(job["id"]) is job


def test_get_returns_none_for_unknown():
    s = make_store()
    assert s.get("no-such-id") is None


def test_delete_removes_job():
    s = make_store()
    job = s.create(urls=["https://a.com"], fmt="pdf", name="", options={})
    removed = s.delete(job["id"])
    assert removed is job
    assert s.get(job["id"]) is None


def test_delete_returns_none_for_unknown():
    s = make_store()
    assert s.delete("no-such-id") is None


def test_list_all_sorted_newest_first():
    s = make_store()
    j1 = s.create(urls=["https://a.com"], fmt="pdf", name="A", options={})
    j2 = s.create(urls=["https://b.com"], fmt="pdf", name="B", options={})
    jobs = s.list_all()
    # j2 created after j1, should come first
    assert jobs[0]["id"] == j2["id"]
    assert jobs[1]["id"] == j1["id"]


def test_push_and_get_event():
    async def _run():
        s = make_store()
        job = s.create(urls=["https://a.com"], fmt="pdf", name="", options={})
        s.push_event(job["id"], {"type": "status", "url_id": "u-0", "status": "done"})
        event = await s.get_event(job["id"])
        assert event["type"] == "status"
        assert event["status"] == "done"

    asyncio.run(_run())


def test_domain_helper():
    assert _domain("https://www.example.com/page") == "example.com"
    assert _domain("not-a-url") == "unknown"


def test_favicon_helper():
    result = _favicon("https://example.com/page")
    assert result.startswith("https://www.google.com/s2/favicons")
    assert "example.com" in result
