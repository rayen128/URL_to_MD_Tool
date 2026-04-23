# Web UI Design Spec — Protinus ETA URL Converter

## Goal

Add a FastAPI web server and React SPA to the existing Python CLI backend so Protinus teammates can convert URLs to PDF/Markdown via a browser UI, without using the command line.

## Context

The Python backend already exists and works:
- `Code/converter.py` — `open_page(url, LoadOptions)` context manager (Playwright)
- `Code/output.py` — `save_pdf()` and `save_markdown()`
- `Code/cli.py` — orchestrates the above

The React SPA design already exists in `design_dump.txt` (from `url-converter/project/`). It uses React 18 + Babel Standalone (CDN-loaded), with JSX files served as static files. It currently uses a simulated backend — we replace that simulation with real API calls.

## Deployment Model

Each teammate runs their own local instance: `python Code/server.py`. No auth, no multi-user concerns, in-memory state only (no database). State is lost on server restart. Files on disk in `output/` survive restart but are not re-listed.

## File Layout

```
Code/
  server.py         ← NEW: FastAPI app, mounts /api + serves web/ as static files
  jobs.py           ← NEW: JobStore — in-memory dict + asyncio.Queue per job
  output.py         ← MODIFIED: add page_size param to save_pdf(); add include_images param to save_markdown()
  converter.py      ← unchanged
  cli.py            ← unchanged
web/
  index.html        ← NEW (missing from design dump): loads React CDN + Babel + JSX files in order
  src/
    icons.jsx       ← NEW (missing from design dump): 14 SVG Icon components + LogoMark SVG
    data.jsx        ← PATCHED: remove SEED_COLLECTIONS, fakeSize, shouldFail; keep helpers
    App.jsx         ← PATCHED: init collections from GET /api/collections; DELETE on remove
    Converter.jsx   ← PATCHED: replace processQueue with real API + SSE
    Collections.jsx ← unchanged
    OutputPanel.jsx ← unchanged
  styles.css        ← unchanged
```

## API

### POST /api/convert

Accepts a batch of URLs and options, creates a job record, starts background processing.

**Request body:**
```json
{
  "urls": ["https://..."],
  "format": "pdf",
  "collection": "My Research",
  "options": {
    "images": true,
    "reader": true,
    "pageSize": "A4"
  }
}
```

**Response:**
```json
{
  "job_id": "j-1745123456789",
  "items": [
    { "id": "u-0", "url": "https://...", "domain": "example.com", "favicon": "https://...", "status": "queued" }
  ]
}
```

`domain` and `favicon` are derived server-side from the URL. The client initialises its item list from this response, augmenting each item with `title: titleFor(url)` (fake slug-based title) until the real title arrives via SSE.

### GET /api/jobs/{job_id}/stream — SSE

Stays open until page unload (FastAPI detects disconnect). Sends events as each URL completes, enabling the retry button to work after the initial conversion finishes.

**Events:**
```
data: {"type": "status", "url_id": "u-0", "status": "working"}
data: {"type": "status", "url_id": "u-0", "status": "done", "title": "Real Page Title", "size": 142300, "filename": "docs_example_com_getting-started.pdf"}
data: {"type": "status", "url_id": "u-0", "status": "error", "error": "Could not load page content"}
data: {"type": "done"}
```

On `done` status event the client updates `item.title` with the real page title from Playwright.

### POST /api/jobs/{job_id}/cancel

Sets a `cancelled` flag on the job. Background workers check this flag before starting each URL. Queued/working items become `error` with message "Cancelled".

### POST /api/jobs/{job_id}/retry/{url_id}

Re-queues the specific item within the same job. Pushes new status events through the still-open SSE stream. The worker checks cancelled flag, acquires semaphore, converts, pushes done/error event.

### GET /api/files/{job_id}/{url_id}

Serves the converted file as an attachment download. Returns 404 if not done yet.

### GET /api/jobs/{job_id}/zip

Builds a ZIP in memory from all `done` files in the job. Returns it as `{collection_name}.zip` (or `collection.zip` if no name). Returns 404 if no done files.

### GET /api/collections

Returns all jobs that have been started (regardless of whether all URLs succeeded), sorted newest first. Populated from the in-memory JobStore. Used by App.jsx on mount and after refresh. A job appears here as soon as `POST /api/convert` is called.

**Response:**
```json
[
  {
    "id": "j-1745...",
    "name": "My Research",
    "format": "pdf",
    "created_at": 1745123456789,
    "urls": ["https://..."],
    "done": 3,
    "errors": 1
  }
]
```

### DELETE /api/collections/{job_id}

Removes job from in-memory store and deletes all output files from disk.

## Backend Architecture

### `jobs.py` — JobStore

Single module-level `JobStore` instance holds all jobs in a dict keyed by `job_id`.

Each job record:
```python
{
  "id": "j-abc",
  "name": "My Research",        # collection name
  "format": "pdf",
  "created_at": 1745...,
  "options": LoadOptions(...),
  "page_size": "A4",
  "cancelled": False,
  "items": [
    {
      "id": "u-0",
      "url": "https://...",
      "domain": "example.com",
      "favicon": "https://...",
      "status": "queued",       # queued | working | done | error
      "title": None,
      "file": None,             # Path to output file, set on done
      "size": None,
      "filename": None,
      "error": None,
    }
  ],
  "queue": asyncio.Queue(),     # receives status-change dicts for SSE
}
```

`JobStore` methods: `create(urls, format, collection, options, page_size) -> job`, `get(job_id) -> job | None`, `delete(job_id) -> None`, `list_all() -> list[job]`.

### `server.py` — FastAPI app

- Mounts `web/` as `StaticFiles` at `/`
- Mounts API routes at `/api`
- `asyncio.Semaphore(3)` limits concurrent Playwright conversions
- On `POST /api/convert`: creates job, fires `asyncio.create_task(_run_job(job))`, returns immediately
- `_run_job(job)`: iterates items, acquires semaphore per URL, calls `_convert_one(job, item)` in `run_in_executor`
- `_convert_one(job, item)`: checks `job["cancelled"]`, calls `open_page()` + `save_pdf()/save_markdown()`, pushes status dict to `job["queue"]`
- SSE endpoint: async generator reads from `job["queue"]`, yields events, exits on `request.is_disconnected()`
- Startup: calls `webbrowser.open("http://localhost:8000")` then runs `uvicorn`

### Options mapping

| UI option | LoadOptions field | output.py |
|---|---|---|
| `images: true` | `block_images=False` | `include_images=True` |
| `images: false` | `block_images=True` | `include_images=False` |
| `reader: true` | `use_extension=True` | — |
| `reader: false` | `use_extension=False` | — |
| `pageSize: "A4"` | — | `save_pdf(page_size="A4")` |
| `pageSize: "Letter"` | — | `save_pdf(page_size="Letter")` |

`use_freedium` and `headless` are not exposed in the UI; they default to `False` and `True` respectively.

## Frontend Patches

### `data.jsx`

Remove: `SEED_COLLECTIONS`, `fakeSize`, `shouldFail`.  
Keep: `titleFor`, `domainFor`, `faviconFor`, `fmtSize`, `fmtTimeAgo`, `niceDate`.  
Update `window.ProtinusData` export to match.

### `App.jsx`

- Change `useStateA(window.ProtinusData.SEED_COLLECTIONS)` → `useStateA([])`
- Add `useEffectA` on mount: `fetch('/api/collections').then(r => r.json()).then(setCollections)`
- Change `deleteCollection`: add `await fetch('/api/collections/'+id, {method:'DELETE'})` before state update
- `addCollection` stays as-is (called from Converter after ZIP download; adds job optimistically to local state so Collections tab updates immediately without a re-fetch)
- Remove `openCollection` toast placeholder (or keep as-is; it's cosmetic)

### `Converter.jsx`

Replace `processQueue` and the simulated `retryOne`/`downloadOne`/`downloadAll` with:

- Add state: `const [jobId, setJobId] = useState(null)` and `const esRef = useRef(null)`
- Remove `fakeSize`, `shouldFail` from destructured `window.ProtinusData`
- `startConversion`: POST `/api/convert` → init items from response → open SSE stream → handle events
- `cancelRun`: POST `/api/jobs/{jobId}/cancel` → close SSE → set cancelled items to error client-side
- `retryOne(id)`: POST `/api/jobs/{jobId}/retry/{id}` → set item back to `working` client-side (SSE pushes real result)
- `downloadOne(item)`: `window.open('/api/files/{jobId}/{item.id}', '_blank')`
- `downloadAll()`: `window.location.href = '/api/jobs/{jobId}/zip'` → then call `onCreateCollection` optimistically

### `index.html`

Loads in order:
1. Google Fonts (Figtree)
2. `styles.css`
3. React 18 UMD + ReactDOM UMD from unpkg CDN
4. Babel Standalone from unpkg CDN
5. `<script type="text/babel">` files in order: `icons.jsx`, `data.jsx`, `OutputPanel.jsx`, `Collections.jsx`, `Converter.jsx`, `App.jsx`
6. Inline mount script: `ReactDOM.createRoot(document.getElementById('root')).render(<App />)`

### `icons.jsx`

Defines a global `Icon` object with function components for each referenced icon: `X`, `Download`, `Archive`, `Refresh`, `Clock`, `Trash`, `Search`, `Folder`, `Settings`, `ChevronRight`, `FilePdf`, `FileText`, `Sparkles`, `Paste`. Each renders a minimal SVG (24×24 viewBox, `currentColor` stroke). Also defines `LogoMark` (Protinus "P" mark in navy/green SVG).

## Dependencies to Add

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
sse-starlette>=1.8.0
```

Add to `requirements.txt`. No new Playwright or Python core deps needed.

## Tests

Existing tests (`tests/`) cover `converter.py`, `output.py`, and `cli.py` and remain unchanged.

New tests (`tests/test_server.py`):
- `test_post_convert_returns_job_id_and_items` — mock `open_page`, verify response shape
- `test_collections_empty_on_start` — GET /api/collections returns []
- `test_delete_collection_removes_job` — create job, delete, verify gone
- `test_cancel_marks_queued_items_error` — create job with 2 items, cancel, verify statuses
- `test_zip_endpoint_returns_zip` — create job with done items, verify ZIP response

Server tests use FastAPI's `TestClient` (synchronous) with mocked `open_page`.

## Start Command

```bash
python Code/server.py
# Opens http://localhost:8000 in default browser
```
