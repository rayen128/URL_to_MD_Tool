import asyncio
import pytest
from jobs import JobStore, _domain, _favicon

SEED = "https://docs.example.com/guide/intro"
SEED_DIR = "https://docs.example.com/guide/"
SEED2 = "https://docs.example.com/api/method"
DIFF_DOMAIN = "https://other.com/guide/intro"


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


# --- Recursive mode tests ---

def test_create_non_recursive_has_no_crawl_fields():
    store = JobStore()
    job = store.create(["https://example.com"], "pdf", "Test", {})
    assert not job.get("recursive")
    assert "visited" not in job
    assert "seed_path_prefixes" not in job


def test_create_recursive_sets_recursive_flag():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True)
    assert job["recursive"] is True


def test_create_recursive_default_max_pages():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True)
    assert job["max_pages"] == 100


def test_create_recursive_custom_max_pages():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True, max_pages=25)
    assert job["max_pages"] == 25


def test_create_recursive_seed_hostname():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True)
    assert job["seed_hostname"] == "docs.example.com"


def test_create_recursive_prefix_from_file_path():
    # /guide/intro → parent dir → /guide/
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True)
    assert job["seed_path_prefixes"] == ["/guide/"]


def test_create_recursive_prefix_from_directory_path():
    # /guide/ → /guide/
    store = JobStore()
    job = store.create([SEED_DIR], "pdf", "Test", {}, recursive=True)
    assert job["seed_path_prefixes"] == ["/guide/"]


def test_create_recursive_visited_prepopulated():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True)
    # Visited stores canonical form (no trailing slash, no query/fragment)
    assert "https://docs.example.com/guide/intro" in job["visited"]


def test_create_recursive_visited_normalises_trailing_slash():
    # Seed with trailing slash must be stored canonically so _extract_links dedup works
    store = JobStore()
    job = store.create([SEED_DIR], "pdf", "Test", {}, recursive=True)
    assert "https://docs.example.com/guide" in job["visited"]
    assert SEED_DIR not in job["visited"]


def test_create_recursive_cap_reached_false():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True)
    assert job["cap_reached"] is False


def test_create_recursive_multiple_seeds_same_host():
    store = JobStore()
    job = store.create([SEED, SEED2], "pdf", "Test", {}, recursive=True)
    assert job["seed_hostname"] == "docs.example.com"
    assert "/guide/" in job["seed_path_prefixes"]
    assert "/api/" in job["seed_path_prefixes"]
    assert len(job["seed_path_prefixes"]) == 2


def test_create_recursive_mixed_hosts_raises():
    store = JobStore()
    with pytest.raises(ValueError, match="hostname"):
        store.create([SEED, DIFF_DOMAIN], "pdf", "Test", {}, recursive=True)


# --- add_item ---

def test_add_item_adds_new_url():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True)
    new_url = "https://docs.example.com/guide/advanced"
    item = store.add_item(job["id"], new_url)
    assert item is not None
    assert item["url"] == new_url
    assert item["status"] == "queued"
    assert len(job["items"]) == 2


def test_add_item_marks_url_visited():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True)
    new_url = "https://docs.example.com/guide/advanced"
    store.add_item(job["id"], new_url)
    assert new_url in job["visited"]


def test_add_item_duplicate_returns_none():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True)
    result = store.add_item(job["id"], SEED)  # SEED already in visited
    assert result is None


def test_add_item_returns_correct_shape():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True)
    item = store.add_item(job["id"], "https://docs.example.com/guide/page")
    assert "id" in item
    assert "url" in item
    assert "domain" in item
    assert "favicon" in item
    assert item["status"] == "queued"
    assert item["title"] is None
    assert item["file"] is None
    assert item["size"] is None
    assert item["filename"] is None
    assert item["error"] is None


def test_add_item_at_cap_returns_none():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True, max_pages=1)
    result = store.add_item(job["id"], "https://docs.example.com/guide/advanced")
    assert result is None


def test_add_item_at_cap_sets_cap_reached():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True, max_pages=1)
    store.add_item(job["id"], "https://docs.example.com/guide/advanced")
    assert job["cap_reached"] is True


def test_add_item_cap_reached_set_only_once():
    store = JobStore()
    job = store.create([SEED], "pdf", "Test", {}, recursive=True, max_pages=1)
    store.add_item(job["id"], "https://docs.example.com/guide/page1")
    store.add_item(job["id"], "https://docs.example.com/guide/page2")
    # Still True, not toggled back
    assert job["cap_reached"] is True


def test_add_item_invalid_job_id_returns_none():
    store = JobStore()
    result = store.add_item("nonexistent-id", "https://example.com/page")
    assert result is None


def test_add_item_on_non_recursive_job_returns_none():
    store = JobStore()
    job = store.create(["https://example.com"], "pdf", "Test", {})
    result = store.add_item(job["id"], "https://example.com/page")
    assert result is None
