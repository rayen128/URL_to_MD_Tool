# URL to PDF — Application Overview

This document explains every part of this application from top to bottom.
It assumes you know basic Python but have never worked with React or web APIs.

---

## Table of Contents

1. [What does this application do?](#1-what-does-this-application-do)
2. [How to run it](#2-how-to-run-it)
3. [High-level architecture](#3-high-level-architecture)
4. [Backend — Python](#4-backend--python)
   - [server.py — the web server](#serverpy--the-web-server)
   - [jobs.py — tracking conversions in memory](#jobspy--tracking-conversions-in-memory)
   - [converter.py — loading pages in a real browser](#converterpy--loading-pages-in-a-real-browser)
   - [output.py — turning pages into files](#outputpy--turning-pages-into-files)
   - [cli.py — command-line interface](#clipy--command-line-interface)
   - [combine_pdfs.py — merging PDF files](#combine_pdfspy--merging-pdf-files)
5. [Frontend — React](#5-frontend--react)
   - [What is React? (very short primer)](#what-is-react-very-short-primer)
   - [index.html — the starting point](#indexhtml--the-starting-point)
   - [App.jsx — the outer shell](#appjsx--the-outer-shell)
   - [Converter.jsx — the main screen](#converterjsx--the-main-screen)
   - [OutputPanel.jsx — live results](#outputpaneljsx--live-results)
   - [Collections.jsx — history](#collectionsjsx--history)
   - [data.jsx — shared helper functions](#datajsx--shared-helper-functions)
   - [icons.jsx — SVG icons](#iconsjsx--svg-icons)
   - [styles.css — visual design](#stylescss--visual-design)
6. [How frontend and backend communicate](#6-how-frontend-and-backend-communicate)
   - [Regular API calls (fetch)](#regular-api-calls-fetch)
   - [Real-time updates (Server-Sent Events)](#real-time-updates-server-sent-events)
7. [Complete data flow: URL → file](#7-complete-data-flow-url--file)
8. [The paywall-removal extension](#8-the-paywall-removal-extension)
9. [Tests](#9-tests)
10. [Glossary of key terms](#10-glossary-of-key-terms)

---

## 1. What does this application do?

You paste one or more URLs (web page addresses) into a form and the app converts each page into either:

- A **PDF** file (looks like a printed version of the page), or
- A **Markdown** file (plain text that captures the article content).

The main reason this exists is to feed web content into AI tools (custom GPTs, RAG pipelines, NotebookLM). It also tries to bypass paywalls — subscription walls that hide article content behind a "please subscribe" screen.

You can use it in two ways:

| Mode | How |
|------|-----|
| **Web UI** | Open `http://localhost:8000` in a browser, paste URLs, click Convert |
| **Command line** | `python Code/cli.py "https://example.com/article"` |

---

## 2. How to run it

```bash
# 1. Activate the Python virtual environment
source .venv/Scripts/activate       # Windows Git Bash

# 2. Install dependencies (first time only)
pip install -r requirements.txt
playwright install chromium          # Downloads the Chromium browser

# 3. Start the server — this also opens the browser automatically
python Code/server.py
```

The server starts at `http://localhost:8000`. Press `Ctrl+C` to stop it.

---

## 3. High-level architecture

Here is how all the pieces fit together:

```
┌─────────────────────────────────────────┐
│            Your web browser             │
│     (React app served from /web)        │
│                                         │
│  Converter tab  │  Collections tab      │
└────────┬────────┴──────────┬────────────┘
         │ HTTP requests      │ SSE stream
         ▼                    ▼
┌─────────────────────────────────────────┐
│         server.py  (FastAPI)            │
│                                         │
│  POST /api/convert  →  create job       │
│  GET  /api/jobs/{id}/stream  →  events  │
│  GET  /api/files/{id}/{urlId}  → file   │
│  GET  /api/jobs/{id}/zip  →  zip file   │
└────────────────┬────────────────────────┘
                 │ spawns threads
         ┌───────┴───────┐
         ▼               ▼
   ┌──────────┐    ┌──────────┐
   │converter │    │ output   │
   │    .py   │    │   .py    │
   │(Playwright│   │(PDF/MD   │
   │ browser) │    │ writer)  │
   └──────────┘    └──────────┘
                 │
                 ▼
         output/[collection]/
           article.pdf  or  article.md
```

**In plain English:**

1. The browser shows you a React UI that was served from the `web/` folder.
2. When you click "Convert", the UI sends the URLs to the Python server.
3. The server opens a real Chromium browser (via Playwright) for each URL, loads the page, removes paywalls, then saves the result as a PDF or Markdown file.
4. While this is happening, the server streams live status updates back to your browser so you see each URL change from "Queued" → "Working" → "Done".
5. When done, you click "Download" to get the file.

---

## 4. Backend — Python

The backend lives in `Code/`. It is a Python web server with six files.

---

### `server.py` — the web server

**File:** `Code/server.py`

This is the entry point. Run it to start everything.

It uses **FastAPI** — a Python library for building web APIs. Think of FastAPI as a way to write functions that respond to HTTP requests (like visiting a URL in a browser or sending data from a form).

#### What FastAPI does

Every function decorated with `@app.get(...)` or `@app.post(...)` becomes an HTTP endpoint — a URL your browser can call.

```python
@app.post("/api/convert")
async def post_convert(body: ConvertRequest):
    # This runs when the browser POSTs to /api/convert
    ...
```

#### Key constants (top of file)

| Constant | Value | Meaning |
|----------|-------|---------|
| `WEB_DIR` | `web/` | Where the React files live (served as static files) |
| `OUTPUT_ROOT` | `output/` | Where converted files are saved |
| `LOG_DIR` | `logs/` | Where log files go |
| `CONCURRENCY` | `3` | How many URLs are processed at the same time |

#### The API endpoints

| Endpoint | Method | What it does |
|----------|--------|--------------|
| `/api/convert` | POST | Start converting a list of URLs. Returns a `job_id`. |
| `/api/collections` | GET | List all past conversion jobs |
| `/api/collections/{job_id}` | DELETE | Delete a job and its files |
| `/api/jobs/{job_id}/stream` | GET | Stream live status updates (SSE) |
| `/api/jobs/{job_id}/cancel` | POST | Cancel an in-progress job |
| `/api/jobs/{job_id}/retry/{url_id}` | POST | Retry one failed URL |
| `/api/files/{job_id}/{url_id}` | GET | Download a single converted file |
| `/api/jobs/{job_id}/zip` | GET | Download all done files as a ZIP |
| `/` | GET | Serve the React web UI |

#### How conversion works inside the server

When the browser calls `POST /api/convert`, the server:

1. Calls `store.create(...)` to register the job in memory (see `jobs.py`).
2. Launches `_run_job()` as a **background task** (so the response returns immediately — the browser doesn't wait for all URLs to convert).
3. Returns `{job_id, items}` to the browser straight away.

`_run_job()` then processes up to 3 URLs at the same time (controlled by `_semaphore`). For each URL it calls `_convert_one_sync()`, which:

1. Sets the item's status to `"working"` and broadcasts that to any listening browsers.
2. Opens the URL in a real Chromium browser via `open_page()` (from `converter.py`).
3. Saves the result via `save_pdf()` or `save_markdown()` (from `output.py`).
4. Sets the status to `"done"` (or `"error"` on failure) and broadcasts that.

#### Why sync in an async world?

FastAPI is **async** — it can handle many requests at the same time without waiting. Playwright (the browser library) is **sync** — it blocks the thread while it waits for pages to load. To solve this, the server runs Playwright inside a **thread pool** (`_executor`). The async code says "run this blocking function in a thread" using `loop.run_in_executor(...)`.

#### Logging

The server logs to both the console and `logs/server.log`. Errors are formatted as a bordered block so they stand out. Normal INFO/WARNING lines are a single compact line.

---

### `jobs.py` — tracking conversions in memory

**File:** `Code/jobs.py`

This file defines `JobStore` — a simple in-memory database that tracks every conversion job while the server is running. When the server restarts, all jobs are lost (no database file).

#### A "job" represents one conversion request

When you click "Convert 5 URLs", one job is created with 5 items (one per URL).

A job looks like this in memory:

```python
{
    "id": "j-1713950000000-abc123",   # Unique ID (timestamp + random)
    "name": "My Research Pack",        # The collection name you typed
    "format": "pdf",                   # "pdf" or "markdown"
    "created_at": 1713950000000.0,     # When it was created (milliseconds)
    "options": { "images": True, ... },
    "items": [...],                    # List of URL items (see below)
    "cancelled": False,
}
```

Each **item** (one URL) looks like:

```python
{
    "id": "u-0",                       # Position in the job
    "url": "https://example.com",
    "domain": "example.com",
    "favicon": "https://www.google.com/s2/favicons?domain=example.com&sz=64",
    "status": "queued",                # queued → working → done | error
    "title": None,                     # Filled in after conversion
    "file": None,                      # Path to the saved file
    "size": None,                      # File size in bytes
    "filename": None,                  # e.g. "example_com_article.pdf"
    "error": None,                     # Error message if it failed
}
```

#### How live updates reach the browser

The `JobStore` also manages an **event queue** for each job. Think of it as a mailbox: the conversion threads put messages in it, and the SSE stream reads them out and forwards them to the browser.

```
Conversion thread:                SSE stream (server.py):
                                  
store.push_event(job_id, event)   event = await store.get_event(job_id)
  → puts event in queue           → takes event from queue
                                  → sends it to browser
```

`push_event` is thread-safe: it uses `loop.call_soon_threadsafe()` to safely put an event on the queue from a background thread.

---

### `converter.py` — loading pages in a real browser

**File:** `Code/converter.py`

This is the most complex part of the application. It uses **Playwright** to control a real Chromium browser and load web pages.

Why a real browser? Because many modern websites only show their content after running JavaScript — a simple HTTP request (like `requests.get(url)`) would only get the raw HTML skeleton, not the rendered content.

#### `LoadOptions` — configuration for each page load

```python
@dataclass
class LoadOptions:
    headless: bool = True         # True = browser is invisible; False = browser window appears
    use_extension: bool = True    # Whether to load the paywall-removal extension
    block_images: bool = False    # True = don't download images (faster)
    use_freedium: bool = False    # True = route Medium.com via freedium.cfd proxy
```

#### `sanitize_filename(url)` — turning a URL into a filename

URLs contain characters that are illegal in filenames (`/`, `?`, `:`). This function converts a URL like `https://example.com/my-article` into a safe string like `example.com_my-article` (max 120 characters).

Note: it returns just the **stem** without extension. The `.pdf` or `.md` is added in `server.py`.

#### `open_page(url, options)` — the main context manager

This is the heart of `converter.py`. It is a **context manager** (used with `with`):

```python
with open_page("https://example.com", options) as page:
    # `page` is a Playwright Page object — a live browser tab
    save_pdf(page, out_path)
# After the `with` block: browser is closed, temp files cleaned up
```

What happens inside `open_page`:

1. **Sets up the browser:**
   - Launches a persistent Chromium context (supports extensions, unlike regular headless mode)
   - Applies a realistic Windows Chrome user agent string (to avoid bot detection)
   - Optionally loads the paywall-removal extension
   - Optionally blocks images/fonts to speed up loading

2. **Calls `_try_load()`** which:
   - Navigates to the URL and waits for the network to go quiet
   - Calls `_accept_cookies()` — clicks the "Accept all" button on cookie banners
   - Calls `_enable_extension()` — clicks the extension's popup button
   - Calls `_remove_paywalls()` — runs JavaScript to hide paywall overlays
   - Calls `_auto_scroll()` — scrolls to the bottom to trigger lazy-loaded content
   - Calls `_remove_paywalls()` again (some paywalls re-appear after scrolling)
   - Calls `check_content_sufficient()` — checks if the page has enough text

3. **AMP fallback:** If content is insufficient, tries the Accelerated Mobile Pages version of the URL (e.g. `url?amp=1` or `url/amp`). AMP pages are simpler and often not paywalled.

4. **Yields the page** to the calling code (server.py), which saves it.

5. **Cleans up:** Closes the browser and deletes the `playwright-user-data/` temp directory.

#### Paywall removal strategy

The function `_remove_paywalls()` runs JavaScript inside the browser page to:

- Delete DOM elements whose CSS class names contain words like "paywall", "meter", "lock", "overlay"
- Remove `blur` CSS filters that blur the article text
- Restore `overflow: auto` on the body (paywall sites often set `overflow: hidden` to prevent scrolling)
- For Medium.com specifically: also sets `localStorage['mediumUnlimited'] = 'true'`

---

### `output.py` — turning pages into files

**File:** `Code/output.py`

Once `converter.py` has a loaded page, `output.py` saves it.

#### `save_pdf(page, path, page_size="A4")`

1. Tells the browser to switch to **print media** mode (so print stylesheets apply)
2. Calls `page.pdf()` with A4 (or Letter) dimensions and 10mm margins
3. Writes the PDF to `path`

#### `save_markdown(page, path, include_images=False)`

1. Uses JavaScript (`page.evaluate(...)`) to extract the HTML of the main content: first tries `<article>`, then `<main>`, then falls back to `<body>`
2. Passes that HTML to the `html2text` library, which converts it to Markdown
3. `html2text` is configured to: preserve links, skip images (unless `include_images=True`), not wrap long lines
4. Writes the Markdown text to `path`

---

### `cli.py` — command-line interface

**File:** `Code/cli.py`

A standalone script that does the same conversion as the web UI, but from the terminal. Useful for scripting and batch processing.

```bash
# Convert one URL to PDF
python Code/cli.py "https://example.com/article"

# Convert to Markdown, put in a named folder
python Code/cli.py "https://example.com/article" --format md --collection "Research"

# Batch mode: read URLs from a text file
python Code/cli.py --batch urls.txt --format pdf --collection "Reports"
```

**Batch file format** (`urls.txt`):

```
# Lines starting with # are comments and are ignored
https://site-a.com/page-1
https://site-b.com/page-2

https://site-c.com/page-3
```

`resolve_output_path()` computes where to save each file:
- No collection: `output/example.com_article.pdf`
- With collection "My Reports": `output/My_Reports/example.com_article.pdf`

---

### `combine_pdfs.py` — merging PDF files

**File:** `Code/combine_pdfs.py`

A standalone utility that merges multiple PDF files in a folder into one. It does not depend on any other file in this project.

```bash
# Merge all PDFs in a folder
python Code/combine_pdfs.py output/My_Collection

# Merge recursively (including subfolders)
python Code/combine_pdfs.py output/My_Collection True

# Custom output filename
python Code/combine_pdfs.py output/My_Collection False "merged_report.pdf"
```

It uses `pypdf.PdfWriter` internally. Files are sorted alphabetically. If a `combined.pdf` already exists in the folder, it is skipped to avoid merging the output into itself.

---

## 5. Frontend — React

The frontend lives in `web/`. It provides the visual interface you see in the browser.

---

### What is React? (very short primer)

React is a JavaScript library for building user interfaces. The key idea is **components** — reusable building blocks. Each component is a function that returns HTML-like code (called JSX) describing what to display.

```jsx
function Greeting({ name }) {
    return <h1>Hello, {name}!</h1>;
}
```

Components can have **state** — data that, when it changes, causes the component to redraw automatically. You declare state with `useState`:

```jsx
const [count, setCount] = useState(0);  // count starts at 0
// When you call setCount(1), React redraws the component with count = 1
```

React normally requires a build step (running `npm build`) to convert JSX into regular JavaScript the browser understands. **This project skips that.** Instead, `index.html` loads React and a JSX transpiler (Babel) directly from a CDN. The browser converts JSX on the fly. This makes setup simpler but is slower than a proper build — fine for a local tool.

---

### `index.html` — the starting point

**File:** `web/index.html`

This is what the browser loads first. It does three things:

1. Loads the CSS stylesheet (`styles.css`)
2. Loads React, ReactDOM, and Babel from `unpkg.com` (a CDN)
3. Loads all the JSX component files in order — order matters because later files use components defined in earlier ones

```html
<div id="root"></div>   <!-- React renders everything into this div -->

<script type="text/babel" src="src/icons.jsx"></script>
<script type="text/babel" src="src/data.jsx"></script>
<script type="text/babel" src="src/OutputPanel.jsx"></script>
<script type="text/babel" src="src/Collections.jsx"></script>
<script type="text/babel" src="src/Converter.jsx"></script>
<script type="text/babel" src="src/App.jsx"></script>   <!-- last, uses all of the above -->
```

The very last line of `App.jsx` mounts React:

```javascript
ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
```

This tells React: "render the `App` component inside the `<div id="root">` element."

---

### `App.jsx` — the outer shell

**File:** `web/src/App.jsx`

`App` is the root component — everything else is nested inside it. It owns the top-level state:

| State variable | Type | Purpose |
|---------------|------|---------|
| `tab` | `"converter"` or `"collections"` | Which tab is visible |
| `collections` | array | All past conversion jobs (fetched from server on load) |
| `toastMsg` | string or null | Short notification message shown briefly |
| `tweaks` | object | Visual preferences: accent colour, dark mode, compact density |
| `settings` | object | Conversion options: include images, reader mode, page size, filename pattern |

**What it renders:**

```
<div class="app">
  <header class="topbar">          ← Navy top bar with logo, tabs, user avatar
  <main>
    <Converter .../>               ← when tab === "converter"
    or
    <Collections .../>             ← when tab === "collections"
  </main>
  <div class="toast">...</div>     ← brief notification (if toastMsg is set)
  <TweaksPanel .../>               ← settings overlay (if tweakOn is true)
```

**Tab navigation:** Clicking "Converter" or "My Collections" in the top bar calls `setTab(...)`, which changes `tab` state, which makes React re-render and show the corresponding component.

**Collections loading:** On startup, `App` fetches `/api/collections` and stores the result. This is how the "My Collections" tab shows your history from the current server session.

**Tweaks panel:** Lets you switch accent colour (green / navy / orange / indigo), enable compact density, or enable dark mode. These choices are applied by adding CSS classes to `<body>` and setting CSS custom properties on `<html>`.

---

### `Converter.jsx` — the main screen

**File:** `web/src/Converter.jsx`

This is the most complex frontend component. It handles the entire conversion workflow.

#### Layout

The screen is split into two columns:

```
┌──────────────────────┬───────────────────────────┐
│  LEFT PANEL          │  RIGHT PANEL              │
│                      │                           │
│  Textarea for URLs   │  OutputPanel              │
│  Format selector     │  (live results appear     │
│  Collection name     │   here as URLs convert)   │
│  Options             │                           │
│  [Convert X URLs]    │                           │
└──────────────────────┴───────────────────────────┘
```

#### State

| Variable | Purpose |
|----------|---------|
| `text` | Raw text in the URL textarea |
| `format` | `"pdf"` or `"markdown"` |
| `name` | Collection name the user typed |
| `items` | Array of conversion results for the current job |
| `isRunning` | True while a job is in progress |
| `isDone` | True when the job has finished |
| `jobId` | ID of the current job (from the server) |
| `esRef` | Reference to the open SSE connection |

#### Derived values (computed from state, not stored)

`useMemo` computes these every time relevant state changes:

- `parsedUrls` — the textarea text split by newlines, trimmed, deduplicated
- `validUrls` — only those that are valid URLs (checked with `new URL()`)
- `invalidCount` — count of lines that look like text but aren't URLs
- `canConvert` — `validUrls.length > 0 && !isRunning`
- `stats` — counts of queued / working / done / error items
- `progress` — percentage complete

#### Key actions

**`loadSample()`** — Fills the textarea with 3 example URLs and sets a default collection name. Purely client-side.

**`startConversion()`** — The main action. Steps:

1. Sends a POST request to `/api/convert` with the URLs, format, collection name, and options.
2. Receives `{job_id, items}` back from the server immediately.
3. Sets `items` state so the right panel shows all URLs as "Queued".
4. Opens a **Server-Sent Events** (SSE) stream to `/api/jobs/{job_id}/stream`.
5. For each event received on the stream:
   - If `type === "status"`: find the item by `url_id` and update it (status, title, size, filename, or error).
   - If `type === "done"`: close the stream, mark `isDone = true`.

**`retryOne(id)`** — Sends `POST /api/jobs/{jobId}/retry/{id}`. The server re-runs the conversion for that one URL.

**`downloadOne(item)`** — Opens `/api/files/{jobId}/{item.id}` in a new browser tab. The browser prompts the user to save the file.

**`downloadAll()`** — Opens `/api/jobs/{jobId}/zip`. Downloads a ZIP of all completed files. Also adds the collection to the "My Collections" tab.

**`cancelRun()`** — Sends `POST /api/jobs/{jobId}/cancel`. Marks all in-progress items as cancelled.

**`clearAll()`** — Closes the SSE connection and resets all state to empty.

#### Options panel

A collapsible panel (click "Options" to open) with:
- **Include images** toggle — whether to include images in Markdown output
- **Strip nav & ads (reader mode)** toggle — whether to use the paywall-removal extension
- **Page size** selector — A4 or Letter (PDF only)
- **Filename pattern** — a template like `{date}-{domain}-{title}` (currently displayed but not yet used server-side)

---

### `OutputPanel.jsx` — live results

**File:** `web/src/OutputPanel.jsx`

Receives the list of conversion items as a **prop** (data passed down from `Converter.jsx`) and displays them.

#### What it shows

- **Empty state:** An illustration and instructions when no job has been started yet.
- **Progress bar + status text:** Shows "Converting... 3/10", "Conversion complete", etc.
- **List of items:** One row per URL.

#### Each row (`ListRow` component)

```
[favicon]  Page Title                         [status chip]  [size]  [action]
           example.com · example.com_article.pdf
```

- **Favicon:** The website's small icon. Falls back to a coloured circle with the domain's first letter if it can't load.
- **Title:** The page title extracted after conversion.
- **Status chip:** Coloured badge — grey (Queued), blue animated (Working), green (Done), red (Failed).
- **File size:** Human-readable (e.g. "245 KB").
- **Action buttons:** Download (when done), Retry (when failed), or a disabled clock icon (when queued/working). Plus a trash icon to remove the row from the UI.

---

### `Collections.jsx` — history

**File:** `web/src/Collections.jsx`

Shows all past conversion jobs in a grid of cards. Data comes from `App.jsx` which loaded it from `/api/collections` on startup.

#### Features

- **Search bar** — filters cards by collection name
- **Sort** — by most recent, name (A–Z), or size (URL count)
- **Cards** — each card shows:
  - Collection name
  - Metadata: "5 files · 1 failed · 2 hours ago"
  - Format badge (PDF or MD)
  - Stack of up to 4 favicons from the URLs
  - Download ZIP button
  - Delete button

Clicking the delete button calls `onDelete(job.id)` (defined in `App.jsx`), which sends `DELETE /api/collections/{id}` and removes the card from the list.

---

### `data.jsx` — shared helper functions

**File:** `web/src/data.jsx`

Utility functions used across multiple components. They are attached to the global `window.ProtinusData` object so any component can call them.

| Function | What it does |
|----------|-------------|
| `titleFor(url)` | Derives a human-readable title from the URL path, e.g. "GitHub — my-article" |
| `domainFor(url)` | Extracts the domain, removes "www.", e.g. "example.com" |
| `faviconFor(url)` | Returns a Google Favicons URL for the domain |
| `fmtSize(bytes)` | Formats bytes as "512 B", "1.5 KB", "2.3 MB" |
| `fmtTimeAgo(timestamp)` | Formats a timestamp as "just now", "5 min ago", "2 hours ago", "3 days ago" |
| `niceDate(timestamp)` | Formats as "24 Apr 2024" |

It also contains a `DOMAIN_NICE` map that maps domains like `"github.com"` to nicer display names like `"GitHub"`.

---

### `icons.jsx` — SVG icons

**File:** `web/src/icons.jsx`

Defines all the icons used in the UI as React components. Each icon is an SVG that accepts a `size` prop.

```jsx
<Icon.Download size={16}/>   // renders a download arrow icon at 16×16 pixels
<Icon.Trash size={14}/>      // renders a trash can icon at 14×14 pixels
```

Available icons: `X`, `Check`, `Download`, `Archive`, `Refresh`, `Clock`, `Trash`, `Search`, `Folder`, `Settings`, `ChevronRight`, `FilePdf`, `FileText`, `Sparkles`, `Paste`.

`LogoMark` renders the Protinus logo (navy rectangle with a green accent bar).

---

### `styles.css` — visual design

**File:** `web/styles.css`

One large CSS file that handles all visual styling. Key design choices:

- **Font:** Figtree (loaded from Google Fonts)
- **Colour system:** CSS custom properties (`--green`, `--navy`, etc.) so the accent colour can be changed by updating one variable
- **Accent themes:** `body` class does not change; instead, `App.jsx` sets `--green`/`--green-2`/`--green-soft` variables on `<html>` based on the chosen accent colour
- **Dark mode:** Activated by adding the `dark` class to `<body>`; overrides background and text colours
- **Compact density:** Activated by adding the `dense` class to `<body>`; reduces padding/row heights
- **Canvas background:** Off-white (`#F6F4EF`) gives a warm, paper-like feel

---

## 6. How frontend and backend communicate

### Regular API calls (fetch)

The frontend uses the browser's built-in `fetch()` function to send HTTP requests to the server.

**Example — starting a conversion:**

```javascript
// Frontend (Converter.jsx)
const resp = await fetch('/api/convert', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        urls: ["https://example.com"],
        format: "pdf",
        collection: "My Pack",
        options: { images: true, reader: true, pageSize: "A4" }
    })
});
const data = await resp.json();
// data = { job_id: "j-...", items: [...] }
```

**Example — deleting a collection:**

```javascript
fetch(`/api/collections/${id}`, { method: 'DELETE' });
```

The URL path starts with `/api/`, which tells the server to handle it as a data endpoint (not serve an HTML file).

---

### Real-time updates (Server-Sent Events)

**The problem:** Conversion takes 10–30 seconds per URL. The browser can't just wait for one big response — the user would see nothing until everything finished.

**The solution:** Server-Sent Events (SSE). After starting a job, the browser opens a persistent HTTP connection to the server. The server keeps that connection open and pushes a new message each time something changes. The browser receives each message and updates the UI instantly.

This is one-directional: server → browser only (unlike WebSockets, which go both ways).

**How it works:**

```
Browser                          Server
  |                                |
  |--- GET /api/jobs/{id}/stream -->|
  |<-- data: {"type":"status",...} -|   URL 1 starts working
  |<-- data: {"type":"status",...} -|   URL 2 starts working
  |<-- data: {"type":"status",...} -|   URL 1 done
  |<-- data: {"type":"status",...} -|   URL 3 starts working
  |<-- data: {"type":"status",...} -|   URL 2 failed
  |<-- data: {"type":"done"}       -|   Job finished
  |--- closes connection -----------|
```

**Frontend code (Converter.jsx):**

```javascript
const es = new EventSource(`/api/jobs/${jobId}/stream`);

es.onmessage = (e) => {
    const event = JSON.parse(e.data);
    if (event.type === "status") {
        // Update the matching item in the `items` array
        setItems(prev => prev.map(item =>
            item.id === event.url_id ? { ...item, ...event } : item
        ));
    }
    if (event.type === "done") {
        es.close();      // Close the connection
        setIsDone(true);
    }
};
```

**Server code (server.py):**

The server's SSE endpoint is a generator function that yields events one at a time. It first replays the current state of all non-queued items (so if you reconnect after a network blip, you catch up), then waits for new events from the job's queue.

Every 15 seconds it sends a "keepalive" comment to prevent the connection from timing out on intermediate proxies.

---

## 7. Complete data flow: URL → file

Here is the full journey of a single URL through the system:

```
1. USER
   Pastes "https://example.com/article" into the textarea
   Clicks "Convert 1 URL"
   
2. BROWSER (Converter.jsx)
   Calls POST /api/convert with:
     { urls: ["https://example.com/article"], format: "pdf", collection: "My Pack" }

3. SERVER (server.py — post_convert)
   Calls store.create() → creates job "j-1234567-abc123"
   Returns { job_id: "j-1234567-abc123", items: [{id: "u-0", status: "queued", ...}] }
   Launches _run_job() in the background (doesn't wait for it)

4. BROWSER (Converter.jsx)
   Receives job_id immediately
   Sets items state → UI shows "https://example.com/article" as "Queued"
   Opens EventSource to /api/jobs/j-1234567-abc123/stream

5. SERVER (server.py — _run_job → _convert_one_sync)
   Thread picks up the item
   Sets status → "working"
   Pushes event: { type: "status", url_id: "u-0", status: "working" }

6. BROWSER
   Receives event via SSE
   Updates UI → status chip changes to "Working" (blue animated dot)

7. SERVER (converter.py — open_page)
   Launches Chromium browser (invisible)
   Navigates to "https://example.com/article"
   Waits for page to fully load
   Clicks cookie banner if present
   Loads paywall-removal extension
   Runs JavaScript to remove paywall elements
   Scrolls to bottom to trigger lazy loading
   Checks content is sufficient (10KB+ or 5+ paragraphs)
   Yields the ready page

8. SERVER (output.py — save_pdf)
   Switches browser to print mode
   Generates PDF → output/My_Pack/example.com_article.pdf
   File is ~200 KB

9. SERVER (server.py — _convert_one_sync)
   Sets status → "done"
   Pushes event: { type: "status", url_id: "u-0", status: "done",
                   title: "Example Article", size: 204800, filename: "example.com_article.pdf" }

10. BROWSER
    Receives event via SSE
    Updates UI → status chip changes to "Done" (green), title appears, size shown
    Download button appears

11. SERVER
    Pushes event: { type: "done" }  ← all URLs finished

12. BROWSER
    Receives "done" event
    Closes SSE connection
    Shows "Conversion complete"

13. USER
    Clicks "Download"
    Browser opens GET /api/files/j-1234567-abc123/u-0
    File is downloaded to user's Downloads folder
```

---

## 8. The paywall-removal extension

**Directory:** `Code/remove_paywall_extension/`

This is an unpacked Chrome extension (Manifest V3) loaded into the Playwright browser.

**What it does:** When its popup button is clicked, it redirects the current tab to `https://removepaywalls.com/{original_url}` — a third-party service that fetches paywalled articles through various means.

**How it's used in the app:** `_enable_extension()` in `converter.py` opens the extension's popup page and programmatically clicks its button. This triggers the redirect.

**It's a fallback** — the primary paywall removal is JavaScript injection (`_remove_paywalls()`), which runs in all cases. The extension is an extra attempt that runs only if `use_extension=True`.

If the extension isn't installed or its popup fails to load, the conversion continues without it. The try/except in `_enable_extension()` ensures a failure here doesn't abort the whole conversion.

---

## 9. Tests

**Directory:** `tests/`

Tests use **pytest** and mock the Playwright browser — no real browser is launched. `tests/conftest.py` adds `Code/` to Python's module search path so test files can `import converter` directly.

| File | Tests | What it covers |
|------|-------|----------------|
| `test_converter.py` | 5 | `sanitize_filename`, `LoadOptions` defaults, `check_content_sufficient` |
| `test_jobs.py` | 11 | Creating/getting/deleting jobs, event queue, `_domain`, `_favicon` helpers |
| `test_output.py` | 11 | `save_pdf`, `save_markdown`, directory creation, image handling |
| `test_cli.py` | 8 | `resolve_output_path`, batch file parsing |
| `test_server.py` | 25 | All API endpoints, conversion sync, cancellation, retry, file download, ZIP |

```bash
# Run all tests
pytest tests/ -v

# Run one file
pytest tests/test_server.py -v
```

---

## 10. Glossary of key terms

| Term | Meaning |
|------|---------|
| **FastAPI** | Python library for building web APIs. Converts Python functions into HTTP endpoints. |
| **Uvicorn** | The server that runs FastAPI. Handles incoming HTTP connections. |
| **Playwright** | Library that controls a real browser (Chromium) programmatically from Python. |
| **Chromium** | The open-source browser engine used by Chrome and Edge. Playwright uses it in "headless" (invisible) mode. |
| **Headless** | Running a browser without showing a window on screen. Faster and suitable for automation. |
| **React** | JavaScript library for building UIs out of reusable components. Each component re-renders automatically when its state changes. |
| **JSX** | A syntax extension for JavaScript that lets you write HTML-like code inside .js/.jsx files. Babel converts it to regular JavaScript. |
| **State (React)** | Data stored inside a component. Changing state causes React to redraw that component. |
| **Props (React)** | Data passed from a parent component to a child component. Read-only in the child. |
| **useMemo** | A React hook that caches a computed value and only recalculates it when its dependencies change. |
| **useRef** | A React hook that stores a value that persists across renders but doesn't cause re-renders when changed. Used here to hold the EventSource connection. |
| **SSE (Server-Sent Events)** | A browser API for receiving a stream of events from a server over a persistent HTTP connection. One-way: server → browser. |
| **EventSource** | The browser object you create to open an SSE connection. |
| **CDN** | Content Delivery Network. A server (like unpkg.com) that hosts JavaScript/CSS libraries so you can load them directly in HTML without installing them. |
| **Context manager** | A Python `with` block. The code inside `open_page()` runs setup on entry and cleanup on exit. |
| **Thread pool** | A set of background threads that run blocking code without freezing the async event loop. |
| **Async / await** | Python (and JavaScript) syntax for writing non-blocking code. `await` pauses a function until a result is ready, without blocking other code from running. |
| **AMP** | Accelerated Mobile Pages. A stripped-down HTML format used by news sites for fast mobile loading. Often not paywalled. |
| **Paywall** | A website feature that hides article content unless you have a subscription. |
| **Favicon** | The small icon that appears in browser tabs next to a page title. |
| **Markdown** | A plain text format where `# Heading` becomes a heading, `**bold**` becomes bold, etc. Widely used in AI tools. |
| **ZIP** | A compressed archive file that bundles multiple files into one. |
| **HTTP methods** | GET (read data), POST (send data / create), DELETE (remove). |
| **Job** | One conversion request. Contains one or more items (URLs). Lives in memory until the server restarts. |
| **Item** | One URL within a job. Has a status: queued → working → done or error. |
