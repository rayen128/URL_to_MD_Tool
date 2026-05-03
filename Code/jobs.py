import asyncio
import posixpath
import time
import uuid
from urllib.parse import urlparse


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
        return job

    def get(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    def delete(self, job_id: str) -> dict | None:
        self._queues.pop(job_id, None)
        self._loops.pop(job_id, None)
        return self._jobs.pop(job_id, None)

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
