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
