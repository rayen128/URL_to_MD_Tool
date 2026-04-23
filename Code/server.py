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
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(CONCURRENCY)
    return _semaphore


def _convert_one_sync(job: dict, item: dict) -> None:
    pass


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
