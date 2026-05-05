import asyncio
import json
import logging
import posixpath
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger("jobs")

# Disk persistence: one JSON file per job. Lives next to the converted outputs
# so a single OUTPUT_ROOT wipe clears everything in step. Asyncio.Queue and
# event-loop refs are not persisted — they're rebuilt lazily on first SSE.
META_DIR = Path(__file__).parent.parent / "output" / "_meta"

# Keys that survive across restarts. Anything else (cancelled flag, merged_dirty,
# in-flight events) is intentionally dropped — restart is a clean slate for runtime state.
_PERSIST_KEYS = {
    "id", "name", "format", "created_at", "options", "items",
    "recursive", "max_pages", "seed_hostname", "seed_path_prefixes", "cap_reached",
}


def _seed_prefix(url: str) -> str:
    """
    Extract the seed path prefix from a URL.

    For a path ending with `/` (directory URL): use the path as-is with trailing `/`
    For a path NOT ending with `/` (file-like URL): use the parent directory with trailing `/`
    Special case: if result is `/`, keep it as `/`

    Examples:
    - /guide/intro → /guide/
    - /guide/ → /guide/
    - / → /
    """
    path = urlparse(url).path

    if path.endswith("/"):
        # Directory URL: rstrip("/") and add back "/"
        stripped = path.rstrip("/")
        result = stripped or "/"
        if result != "/":
            result = result + "/"
        return result
    else:
        # File-like URL: use parent directory
        parent = posixpath.dirname(path)
        if parent == "":
            parent = "/"
        if parent != "/":
            parent = parent + "/"
        return parent


def _canonical_url(url: str) -> str:
    """Strip query string, fragment, and trailing path slash — matches _extract_links normalisation."""
    p = urlparse(url)
    path = p.path.rstrip("/") or "/"
    return f"{p.scheme}://{p.netloc}{path}"


class JobStore:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._loops: dict[str, asyncio.AbstractEventLoop] = {}

    def create(
        self,
        urls: list[str],
        fmt: str,
        name: str,
        options: dict,
        recursive: bool = False,
        max_pages: int = 100,
    ) -> dict:
        # If recursive mode, validate all URLs share the same hostname
        if recursive:
            hostnames = {urlparse(u).hostname for u in urls}
            if len(hostnames) != 1:
                raise ValueError("All seed URLs must share the same hostname")
            job_seed_hostname = next(iter(hostnames))

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

        # Add recursive mode fields
        if recursive:
            job["recursive"] = True
            job["max_pages"] = max_pages
            job["seed_hostname"] = job_seed_hostname
            job["seed_path_prefixes"] = [_seed_prefix(url) for url in urls]
            job["visited"] = {_canonical_url(u) for u in urls}
            job["cap_reached"] = False

        self._jobs[job_id] = job
        self._queues[job_id] = asyncio.Queue()
        try:
            self._loops[job_id] = asyncio.get_running_loop()
        except RuntimeError:
            self._loops[job_id] = None
        self.persist(job_id)
        return job

    def get(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    def delete(self, job_id: str) -> dict | None:
        self._queues.pop(job_id, None)
        self._loops.pop(job_id, None)
        (META_DIR / f"{job_id}.json").unlink(missing_ok=True)
        return self._jobs.pop(job_id, None)

    def persist(self, job_id: str) -> None:
        """Snapshot a job's persistable state to disk. Called on create, on item
        completion, and on rename. Best-effort — disk failures are logged, never raised."""
        job = self._jobs.get(job_id)
        if job is None:
            return
        META_DIR.mkdir(parents=True, exist_ok=True)
        snapshot = {k: job[k] for k in _PERSIST_KEYS if k in job}
        # `visited` is a set; JSON-serialise as a list and rebuild on hydrate.
        if "visited" in job:
            snapshot["visited"] = sorted(job["visited"])
        try:
            (META_DIR / f"{job_id}.json").write_text(json.dumps(snapshot), encoding="utf-8")
        except OSError as e:
            logger.warning("persist(%s) failed: %s", job_id, e)

    def hydrate(self) -> None:
        """Load persisted jobs from META_DIR into memory. Idempotent: existing
        in-memory jobs win over disk (so a hot reload doesn't clobber live state)."""
        if not META_DIR.exists():
            return
        for f in META_DIR.iterdir():
            if not f.is_file() or f.suffix != ".json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("hydrate: skipping %s (%s)", f.name, e)
                continue
            job_id = data.get("id")
            if not job_id or job_id in self._jobs:
                continue
            if "visited" in data:
                data["visited"] = set(data["visited"])
            data.setdefault("cancelled", False)
            cleaned = False
            for item in data.get("items", []):
                if item.get("status") in ("queued", "working"):
                    item["status"] = "error"
                    item["error"] = "Interrupted"
                    cleaned = True
            self._jobs[job_id] = data
            self._queues[job_id] = asyncio.Queue()
            self._loops[job_id] = None
            # Persist cleaned state so we don't re-flip the same items every restart.
            if cleaned:
                self.persist(job_id)

    def list_all(self) -> list[dict]:
        return sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)

    def push_event(self, job_id: str, event: dict) -> None:
        q = self._queues.get(job_id)
        if q is not None:
            loop = self._loops.get(job_id)
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(q.put_nowait, event)
            else:
                q.put_nowait(event)

    async def get_event(self, job_id: str) -> dict | None:
        q = self._queues.get(job_id)
        if q is None:
            return None
        return await q.get()

    def add_item(self, job_id: str, url: str) -> dict | None:
        """
        Add a new URL to a recursive job.

        Returns None if:
        - job_id not found
        - job is not recursive
        - url already in visited
        - max_pages cap reached

        Returns the new item dict if successful.
        """
        job = self.get(job_id)
        if job is None:
            return None
        if not job.get("recursive"):
            return None

        # Check if URL already visited
        if url in job["visited"]:
            return None

        # Check if at cap
        if len(job["items"]) >= job["max_pages"]:
            if not job["cap_reached"]:
                job["cap_reached"] = True
            return None

        # Create the new item
        item = {
            "id": f"u-{len(job['items'])}",
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

        # Add to job
        job["items"].append(item)
        job["visited"].add(url)

        return item


def _domain(url: str) -> str:
    try:
        host = urlparse(url).hostname or "unknown"
        return host.removeprefix("www.")
    except Exception:
        return "unknown"


def _favicon(url: str) -> str:
    try:
        host = urlparse(url).hostname
        if not host:
            return ""
        return f"https://www.google.com/s2/favicons?domain={host}&sz=64"
    except Exception:
        return ""


store = JobStore()
