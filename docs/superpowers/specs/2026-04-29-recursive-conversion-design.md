# Recursive Conversion — Design Spec

**Date:** 2026-04-29  
**Status:** Approved

## Overview

Add recursive (crawl) mode to the URL-to-PDF converter. When enabled, the user provides one or more seed URLs and the tool automatically discovers and converts all linked pages within the same path prefix, up to a configurable page cap. This is intended primarily for documentation sites.

---

## Scope & Constraints

- Crawling is scoped to the **path prefix** of the seed URL. A seed of `https://docs.example.com/guide/intro` only crawls pages whose path starts with `/guide/`.
- Same hostname only — no following links to external domains.
- Default cap of **100 pages**, user-adjustable. Hard stop when cap is reached.
- Non-recursive jobs are **entirely unchanged** — the new code paths only activate when `recursive: true` is set on a job.

---

## 1. Data Model (`jobs.py`)

### New fields on the job dict

| Field | Type | Description |
|---|---|---|
| `recursive` | `bool` | Whether this is a crawl job |
| `max_pages` | `int` | Cap on total pages (default 100) |
| `seed_path_prefixes` | `list[str]` | Path prefixes derived from each seed URL (e.g. `["/guide/"]`), each normalized to strip trailing slash via `rstrip("/") or "/"` applied to the path, then the prefix stored with a trailing `/` to prevent `/guide` matching `/guide-v2` |
| `visited` | `set[str]` | Normalized URLs already queued; used to deduplicate discovered links |

These fields are only present when `recursive=True`. Non-recursive jobs have none of them.

**Multiple seed URLs in recursive mode:** when the user provides more than one URL as seeds, each seed's path prefix is independently valid crawling scope. `seed_path_prefixes` (plural) is stored as a `list[str]`. A discovered link is in-scope if its path starts with ANY of the seed prefixes. This lets users crawl `/guide/` and `/api-reference/` in a single job by pasting both seed URLs.

### New method: `JobStore.add_item(job_id, url) -> dict | None`

- Returns `None` (no-op) if:
  - `url` is already in `job["visited"]`
  - `len(job["items"]) >= job["max_pages"]`
- Otherwise: appends a new item dict to `job["items"]`, adds `url` to `job["visited"]`, returns the item.
- The new item has the same shape as items created by `create()`: `id`, `url`, `domain`, `favicon`, `status="queued"`, and null fields for `title`, `file`, `size`, `filename`, `error`.
- A separate `cap_reached` flag (`job["cap_reached"]: bool`) is set to `True` the first time `add_item` would exceed `max_pages`, so the server can fire the `cap_reached` SSE event exactly once.

### `JobStore.create()` changes

Accepts two new optional kwargs: `recursive: bool = False`, `max_pages: int = 100`. When `recursive=True`, also sets `seed_path_prefixes` (a `list[str]` of each seed URL's path normalized to end with `/`), `seed_hostname` (hostname from the first seed URL — all seeds must share the same hostname; if they don't, `create()` raises `ValueError`), `visited` (pre-populated with all seed URLs), and `cap_reached: False`.

---

## 2. Link Extraction (`converter.py`)

### New function: `_extract_links(page, seed_path_prefixes, seed_hostname) -> list[str]`

Called from `_convert_one_sync` **inside the `with open_page(...) as page:` block**, after saving the file but before the context manager closes the page. Must not be called after the `with` block exits — the page is closed at that point.

Only called when `job["recursive"]` is true and conversion succeeded. On failure, returns `[]` implicitly (link extraction is skipped).

**Logic:**
1. `page.evaluate()` to collect all `<a href>` attribute values from the DOM.
   - *Scope is intentionally limited to `<a href>` elements. `<area href>`, canonical `<link>` tags, and JS-rendered nav menus that don't produce `<a>` tags are out of scope — appropriate for documentation sites, which universally use `<a>` for navigation.*
2. Resolve relative URLs against the page's current URL.
3. Filter — keep only URLs where:
   - Scheme is `http` or `https`
   - Hostname matches `seed_hostname` exactly
   - Path starts with ANY prefix in `seed_path_prefixes`
   - Not a `mailto:`, `tel:`, or `javascript:` link
4. Normalize each URL:
   - Strip query string entirely. *Doc pages are never content-differentiated by query param — query strings on documentation sites are tracking params, view toggles, or analytics markers, not distinct content.*
   - Strip fragment (`#...`).
   - Canonicalize trailing slash: `parsed.path.rstrip("/") or "/"` — `/about/` and `/about` both become `/about`; root `/` stays `/`.
5. Deduplicate using `(hostname, canonical_path)` as key.
6. Return deduplicated list of absolute URLs in canonical form.

**Return value:** `_convert_one_sync` returns `list[str]` directly (changed from `-> None`). The discovered URLs are the return value — not stored in the item dict. All early-return paths (cancelled, invalid URL, conversion failure) return `[]`. The non-recursive `_run_job` path discards the return value unchanged.

---

## 3. Backend Execution Engine (`server.py`)

### `_run_job` — branching on `recursive`

```
if not job["recursive"]:
    # existing asyncio.gather path — unchanged
else:
    # new recursive task-spawning path
```

### Recursive execution pattern

Uses self-spawning coroutines with an `asyncio.Event` for completion detection.

```
active_count = len(seed items)   # starts at number of seed URLs
finished = asyncio.Event()

async def process_one(item):
    nonlocal active_count
    try:
        async with _semaphore:
            new_urls = await loop.run_in_executor(_executor, _convert_one_sync, job, item)
        for url in new_urls:
            new_item = store.add_item(job["id"], url)
            if new_item:
                push item_added SSE event
                active_count += 1          # increment BEFORE scheduling
                create_task(process_one(new_item))
        if store.get(job["id"])["cap_reached"] and not cap_event_fired:
            push cap_reached SSE event
            cap_event_fired = True
    finally:
        active_count -= 1
        if active_count == 0:
            finished.set()

for item in job["items"]:
    create_task(process_one(item))

await finished.wait()
push done SSE event
```

**`active_count` invariant:** always equals the number of live tasks (running + scheduled but not yet started). Increment happens before `create_task`; decrement happens in `finally`. The event loop is single-threaded so there is no race between these operations.

**Concurrency:** the existing `_semaphore` (CONCURRENCY=3) limits simultaneous Playwright browser instances. This is unchanged.

---

## 4. SSE Protocol

Two new event types, both only emitted by recursive jobs.

### `item_added`

Fired when a new URL is discovered and added to the job.

```json
{
  "type": "item_added",
  "item": {
    "id": "u-7",
    "url": "https://docs.example.com/guide/advanced",
    "domain": "docs.example.com",
    "favicon": "https://www.google.com/s2/favicons?domain=docs.example.com&sz=64",
    "status": "queued"
  }
}
```

### `cap_reached`

Fired exactly once when `max_pages` is hit and further discovered URLs are being dropped.

```json
{
  "type": "cap_reached",
  "max_pages": 100
}
```

Existing `status` and `done` events are unchanged.

---

## 5. API Changes (`server.py`)

### `POST /api/convert` — `ConvertRequest` body

`options` dict accepts two new optional fields:

| Field | Type | Default | Description |
|---|---|---|---|
| `recursive` | `bool` | `false` | Enable crawl mode |
| `maxPages` | `int` | `100` | Page cap (only used when `recursive=true`) |

These are read in `post_convert` and passed to `store.create()`.

---

## 6. Frontend (`Converter.jsx`)

### Recursive toggle button

A dedicated **"Recursive Crawl"** toggle button added to the options panel — visually prominent, not buried as a checkbox. When active, the button appears highlighted (same active-state styling as other toggle buttons in the panel). Toggling it on reveals a **"Max pages"** number input directly below, defaulting to `100`.

When recursive mode is on, the textarea placeholder changes to indicate a seed URL is expected (e.g. *"Enter a seed URL to crawl from…"*).

### SSE handler additions

```
case "item_added":
    setItems(prev => [...prev, event.item])
    break

case "cap_reached":
    toast(`Crawl limit reached — stopped at ${event.max_pages} pages`)
    break
```

### Progress display

The progress bar and item count are already derived from `items.length` and per-status counts, so they update automatically as `items` grows.

One addition: when `job["recursive"]` is true and `isRunning` is true, show a **"Crawling…"** label next to the progress bar. This disappears once the job is done.

### Request body

`startConversion` includes the new options:

```json
{
  "urls": ["https://docs.example.com/guide/intro"],
  "format": "pdf",
  "collection": "Salesforce Guide",
  "options": {
    "recursive": true,
    "maxPages": 100,
    "images": true,
    "reader": true,
    "pageSize": "A4"
  }
}
```

---

## 7. Error Handling

- **Failed conversion:** `_extract_links` is not called. The item shows as `error` in the UI. Crawling continues from other items.
- **Cancelled job:** existing cancellation check in `_convert_one_sync` fires before link extraction. No new URLs are added after cancellation.
- **Cap reached:** `store.add_item()` silently drops URLs beyond the cap. The `cap_reached` flag ensures the SSE event fires exactly once.
- **Circular links (A→B→A):** handled by the `visited` set in `JobStore` — any URL already queued is dropped by `add_item`.

---

## 8. Files Changed

| File | Change |
|---|---|
| `Code/jobs.py` | Add `recursive`, `max_pages`, `seed_path_prefixes`, `seed_hostname`, `visited`, `cap_reached` fields to job dict; add `add_item()` method; update `create()` signature |
| `Code/converter.py` | Add `_extract_links(page, seed_path_prefixes, seed_hostname)` function; call it in `_convert_one_sync` when `job["recursive"]` |
| `Code/server.py` | Branch `_run_job` on `recursive`; implement recursive task-spawning path; emit `item_added` and `cap_reached` SSE events |
| `web/src/Converter.jsx` | Add recursive toggle button + max pages input to options panel; handle `item_added` and `cap_reached` SSE events; add "Crawling…" label |

**No other files change.** `output.py`, `rules.py`, `helpers.py`, `cli.py`, `combine_pdfs.py`, and all tests are untouched.
