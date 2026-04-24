import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
from datetime import datetime
import io
import json
import logging
import shutil
import webbrowser
import zipfile
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from converter import LoadOptions, open_page, sanitize_filename
from output import save_pdf, save_markdown
from jobs import store

WEB_DIR = Path(__file__).parent.parent / "web"
OUTPUT_ROOT = Path(__file__).parent.parent / "output"
LOG_DIR = Path(__file__).parent.parent / "logs"
CONCURRENCY = 3

LOG_DIR.mkdir(exist_ok=True)

if not getattr(sys, "_server_logs_cleared", False):
    for _f in [LOG_DIR / "server.log", LOG_DIR / "jobs.log"]:
        if _f.exists():
            _f.write_text("", encoding="utf-8")
    _screenshots_dir = LOG_DIR / "debug_screenshots"
    if _screenshots_dir.exists():
        for _f in _screenshots_dir.iterdir():
            if _f.is_file():
                _f.unlink(missing_ok=True)
    sys._server_logs_cleared = True


class _Formatter(logging.Formatter):
    """Single-line for INFO/WARNING; bordered block with full traceback for ERROR+."""
    _RULE = "─" * 80
    _NORMAL = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    def format(self, record: logging.LogRecord) -> str:
        if record.levelno < logging.ERROR:
            return self._NORMAL.format(record)

        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        parts = [
            "",
            self._RULE,
            f"  {record.levelname}  {timestamp}  [{record.name}]",
            self._RULE,
            "",
            f"  {record.getMessage()}",
        ]
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            parts.append("")
            for line in record.exc_text.splitlines():
                parts.append(f"  {line}")
        parts += ["", self._RULE, ""]
        return "\n".join(parts)


_fmt = _Formatter()
_file_handler = RotatingFileHandler(
    LOG_DIR / "server.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
_file_handler.setFormatter(_fmt)
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_fmt)

logging.basicConfig(level=logging.INFO, handlers=[
                    _file_handler, _stream_handler])
logging.getLogger("uvicorn.access").handlers = [_file_handler, _stream_handler]
logging.getLogger("uvicorn.access").propagate = False

logger = logging.getLogger("server")

jobs_logger = logging.getLogger("jobs")
jobs_logger.setLevel(logging.INFO)
jobs_logger.propagate = False
if not jobs_logger.handlers:
    _jobs_file_handler = RotatingFileHandler(
        LOG_DIR / "jobs.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    _jobs_file_handler.setFormatter(logging.Formatter("%(message)s"))
    jobs_logger.addHandler(_jobs_file_handler)

app = FastAPI()
_executor = ThreadPoolExecutor(max_workers=CONCURRENCY)
_semaphore = asyncio.Semaphore(CONCURRENCY)


class ConvertRequest(BaseModel):
    urls: list[str]
    format: str = "pdf"
    collection: str = ""
    options: dict = {}


def _log_job_start(job: dict) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    name = f'"{job["name"]}"' if job["name"] else "(unnamed)"
    line = f'{ts}  STARTED   {job["id"]}  {name}  {len(job["items"])} URL(s)  format={job["format"]}'
    jobs_logger.info(line)


def _log_job_finish(job: dict) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    name = f'"{job["name"]}"' if job["name"] else "(unnamed)"
    done = sum(1 for i in job["items"] if i["status"] == "done")
    errors = sum(1 for i in job["items"] if i["status"] == "error")
    header = f'{ts}  FINISHED  {job["id"]}  {name}  {done} done, {errors} error(s)'
    lines = [header]
    for item in job["items"]:
        if item["status"] == "done":
            size_kb = f'{item["size"] / 1024:.1f} KB' if item["size"] else "?"
            lines.append(
                f'    ✓  {item["filename"]}  ({size_kb})  {item["url"]}')
        else:
            error = (item.get("error") or "unknown error").splitlines()[0]
            lines.append(f'    ✗  {item["url"]}  —  {error}')
    lines.append("")
    jobs_logger.info("\n".join(lines))


@app.post("/api/convert")
async def post_convert(body: ConvertRequest):
    job = store.create(
        urls=body.urls,
        fmt=body.format,
        name=body.collection,
        options=body.options,
    )
    logger.info("Job %s started — %d URL(s), format=%s, collection=%r",
                job["id"], len(body.urls), body.format, body.collection or "(none)")
    _log_job_start(job)
    asyncio.create_task(_run_job(job))
    return {
        "job_id": job["id"],
        "items": [
            {
                "id": item["id"],
                "url": item["url"],
                "domain": item["domain"],
                "favicon": item["favicon"],
                "status": item["status"],
            }
            for item in job["items"]
        ],
    }


async def _run_job(job: dict) -> None:
    sem = _semaphore
    loop = asyncio.get_running_loop()

    async def process_item(item: dict) -> None:
        async with sem:
            if job["cancelled"]:
                item["status"] = "error"
                item["error"] = "Cancelled"
                store.push_event(job["id"], {
                    "type": "status", "url_id": item["id"],
                    "status": "error", "error": "Cancelled",
                })
                return
            await loop.run_in_executor(_executor, _convert_one_sync, job, item)

    results = await asyncio.gather(
        *[process_item(item) for item in job["items"]],
        return_exceptions=True,
    )
    for exc in results:
        if isinstance(exc, Exception):
            logger.error("Unexpected error in job %s worker",
                         job["id"], exc_info=exc)
    done = sum(1 for i in job["items"] if i["status"] == "done")
    errors = sum(1 for i in job["items"] if i["status"] == "error")
    logger.info("Job %s finished — %d done, %d error(s)",
                job["id"], done, errors)
    _log_job_finish(job)
    store.push_event(job["id"], {"type": "done"})


def _convert_one_sync(job: dict, item: dict) -> None:
    if job["cancelled"]:
        item["status"] = "error"
        item["error"] = "Cancelled"
        store.push_event(job["id"], {
            "type": "status", "url_id": item["id"],
            "status": "error", "error": "Cancelled",
        })
        return

    item["status"] = "working"
    logger.info("[%s] Converting %s", job["id"], item["url"])
    store.push_event(job["id"], {"type": "status",
                     "url_id": item["id"], "status": "working"})

    opts = job["options"]
    options = LoadOptions(
        headless=True,
        use_extension=opts.get("reader", True),
        block_images=not opts.get("images", True),
        use_freedium=False,
    )
    page_size = opts.get("pageSize", "A4")
    include_images = opts.get("images", True)
    fmt = job["format"]
    coll = job["name"].replace(" ", "_") if job["name"] else None
    out_dir = OUTPUT_ROOT / coll if coll else OUTPUT_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize_filename(item["url"])
    suffix = ".pdf" if fmt == "pdf" else ".md"
    out_path = out_dir / (stem + suffix)

    try:
        with open_page(item["url"], options) as page:
            title = page.title() or stem
            if fmt == "pdf":
                save_pdf(page, out_path, page_size=page_size)
            else:
                save_markdown(page, out_path, include_images=include_images)
        item["status"] = "done"
        item["title"] = title
        item["file"] = str(out_path)
        item["size"] = out_path.stat().st_size
        item["filename"] = stem + suffix
        logger.info("[%s] Done: %s → %s (%.1f KB)",
                    job["id"], item["url"], item["filename"], item["size"] / 1024)
        store.push_event(job["id"], {
            "type": "status", "url_id": item["id"], "status": "done",
            "title": title, "size": item["size"], "filename": item["filename"],
        })
    except Exception as e:
        item["status"] = "error"
        item["error"] = str(e)
        logger.error("[%s] Failed: %s — %s", job["id"],
                     item["url"], e, exc_info=True)
        store.push_event(job["id"], {
            "type": "status", "url_id": item["id"],
            "status": "error", "error": str(e),
        })


@app.get("/api/collections")
async def get_collections():
    return [
        {
            "id": j["id"],
            "name": j["name"],
            "format": j["format"],
            "createdAt": j["created_at"],
            "urls": [i["url"] for i in j["items"]],
            "done": sum(1 for i in j["items"] if i["status"] == "done"),
            "errors": sum(1 for i in j["items"] if i["status"] == "error"),
        }
        for j in store.list_all()
    ]


@app.delete("/api/collections/{job_id}")
async def delete_collection(job_id: str):
    job = store.delete(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    for item in job["items"]:
        if item["file"]:
            p = Path(item["file"]).resolve()
            if p.is_relative_to(OUTPUT_ROOT.resolve()):
                p.unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def generator():
        # Replay current non-queued state for reconnects
        for item in job["items"]:
            if item["status"] != "queued":
                event: dict = {
                    "type": "status",
                    "url_id": item["id"],
                    "status": item["status"],
                }
                if item["status"] == "done":
                    event.update({
                        "title": item["title"],
                        "size": item["size"],
                        "filename": item["filename"],
                    })
                elif item["status"] == "error":
                    event["error"] = item["error"]
                yield {"data": json.dumps(event)}

        # Stream live updates; break on done so orphaned connections close
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(store.get_event(job_id), timeout=15.0)
                if event is None:
                    break
                yield {"data": json.dumps(event)}
                if event.get("type") == "done":
                    break
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    break
                yield {"comment": "keepalive"}

    return EventSourceResponse(generator())


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job["cancelled"] = True
    for item in job["items"]:
        if item["status"] in ("queued", "working"):
            item["status"] = "error"
            item["error"] = "Cancelled"
            store.push_event(job_id, {
                "type": "status", "url_id": item["id"],
                "status": "error", "error": "Cancelled",
            })
    store.push_event(job_id, {"type": "done"})
    return {"ok": True}


@app.post("/api/jobs/{job_id}/retry/{url_id}")
async def retry_item(job_id: str, url_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    item = next((i for i in job["items"] if i["id"] == url_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    item["status"] = "queued"
    item["error"] = None
    loop = asyncio.get_running_loop()
    sem = _semaphore

    async def _do_retry():
        job["cancelled"] = False
        async with sem:
            await loop.run_in_executor(_executor, _convert_one_sync, job, item)
        if not any(i["status"] in ("queued", "working") for i in job["items"]):
            store.push_event(job_id, {"type": "done"})

    asyncio.create_task(_do_retry())
    return {"ok": True}


@app.get("/api/files/{job_id}/{url_id}")
async def download_file(job_id: str, url_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    item = next((i for i in job["items"] if i["id"] == url_id), None)
    if item is None or item["status"] != "done" or not item["file"]:
        raise HTTPException(status_code=404, detail="File not ready")
    p = Path(item["file"]).resolve()
    if not p.is_relative_to(OUTPUT_ROOT.resolve()):
        raise HTTPException(status_code=403, detail="Forbidden")
    return FileResponse(
        path=str(p),
        filename=item["filename"],
        media_type="application/octet-stream",
    )


@app.get("/api/jobs/{job_id}/zip")
async def download_zip(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    done = [i for i in job["items"] if i["status"] == "done" and i["file"]]
    if not done:
        raise HTTPException(status_code=404, detail="No completed files")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in done:
            zf.write(str(item["file"]), arcname=item["filename"])
    buf.seek(0)
    raw_name = (job["name"].replace(" ", "_") or "collection") + ".zip"
    zip_name = raw_name.replace('"', "").replace("\\", "")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="static")


if __name__ == "__main__":
    webbrowser.open("http://localhost:8000")
    uvicorn.run("server:app", host="127.0.0.1", port=8000)
