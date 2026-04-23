import asyncio
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse


class JobStore:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._queues: dict[str, asyncio.Queue] = {}

    def create(self, urls: list[str], fmt: str, name: str, options: dict) -> dict:
        job_id = f"j-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
        items = [
            {
                "id": f"u-{i}",
                "url": url,
                "domain": _domain(url),
                "favicon": _favicon(url),
                "status": "queued",
                "title": None,
                "file": None,
                "size": None,
                "filename": None,
                "error": None,
            }
            for i, url in enumerate(urls)
        ]
        job = {
            "id": job_id,
            "name": name or "",
            "format": fmt,
            "created_at": time.time() * 1000,
            "options": options,
            "items": items,
            "cancelled": False,
        }
        self._jobs[job_id] = job
        self._queues[job_id] = asyncio.Queue()
        return job

    def get(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    def delete(self, job_id: str) -> dict | None:
        self._queues.pop(job_id, None)
        return self._jobs.pop(job_id, None)

    def list_all(self) -> list[dict]:
        return sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)

    def push_event(self, job_id: str, event: dict) -> None:
        q = self._queues.get(job_id)
        if q is not None:
            q.put_nowait(event)

    async def get_event(self, job_id: str) -> dict | None:
        q = self._queues.get(job_id)
        if q is None:
            return None
        return await q.get()


def _domain(url: str) -> str:
    try:
        host = urlparse(url).hostname or "unknown"
        return host.replace("www.", "")
    except Exception:
        return "unknown"


def _favicon(url: str) -> str:
    try:
        host = urlparse(url).hostname
        return f"https://www.google.com/s2/favicons?domain={host}&sz=64"
    except Exception:
        return ""


store = JobStore()
