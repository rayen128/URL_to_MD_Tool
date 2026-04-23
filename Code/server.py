import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
import io
import json
import webbrowser
import zipfile
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
CONCURRENCY = 3

app = FastAPI()
_executor = ThreadPoolExecutor(max_workers=CONCURRENCY)


class ConvertRequest(BaseModel):
    urls: list[str]
    format: str = "pdf"
    collection: str = ""
    options: dict = {}


@app.post("/api/convert")
async def post_convert(body: ConvertRequest):
    job = store.create(
        urls=body.urls,
        fmt=body.format,
        name=body.collection,
        options=body.options,
    )
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
    sem = asyncio.Semaphore(CONCURRENCY)
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

    await asyncio.gather(
        *[process_item(item) for item in job["items"]],
        return_exceptions=True,
    )
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
    store.push_event(job["id"], {"type": "status", "url_id": item["id"], "status": "working"})

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
        store.push_event(job["id"], {
            "type": "status", "url_id": item["id"], "status": "done",
            "title": title, "size": item["size"], "filename": item["filename"],
        })
    except Exception as e:
        item["status"] = "error"
        item["error"] = str(e)
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
            Path(item["file"]).unlink(missing_ok=True)
    return {"ok": True}


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="static")


if __name__ == "__main__":
    webbrowser.open("http://localhost:8000")
    uvicorn.run("server:app", host="127.0.0.1", port=8000)
