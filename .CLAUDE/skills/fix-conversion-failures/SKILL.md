---
name: fix-conversion-failures
description: Diagnose and fix URL conversion failures in the URL-to-PDF project. Use this skill whenever a URL fails to convert, when server.log or jobs.log shows errors, when the user says "this URL fails" or "the converter isn't working", or when you notice failure patterns while reading logs — even if the user hasn't explicitly asked for a fix. Also activate proactively when you spot repeated failures across multiple URLs. Always invoke before making any change to Code/converter.py or Code/output.py.
---

# Fix Conversion Failures

You're helping diagnose and fix conversion failures in this URL-to-PDF project. The workflow adapts depending on whether you're acting proactively (you already see the issue) or reactively (the user brought it to you).

**Never edit any file before the user has explicitly approved the proposed change.**

---

## Two Modes

### Proactive mode — you already see a failure in context

Lead with your diagnosis: "I can see that `<url>` failed because `<reason>`. Here's what I'd fix: `<one-sentence plan>`."  
Then ask: "Should I go ahead, or is there something else to focus on first?"

Don't ask questions whose answers you already have.

### Reactive mode — the user brought the problem to you

Ask a short, focused set of questions before reading anything:

- **What failed?** Which URL(s), or what did they observe?
- **New or recurring?** New = maybe a recent code change; recurring = the site may have changed.
- **Should you read the most recent logs**, or does the user have specific output to share?

If the user has already pasted log output or an error trace, skip the questions and use that as the primary source.

---

## Step 1 — Gather Evidence

Read in order, stopping as soon as you have enough to classify the failure.

### `logs/jobs.log`
Lines look like:
```
2026-04-24 17:54:43  STARTED   <job-id>  "My collection"  3 URL(s)  format=markdown
    ✓  filename.md  (42.3 KB)  https://example.com/article
    ✗  https://failing.com/page  —  Could not load page content.
```
Use this to identify which URLs failed and the first line of their error.

### `logs/server.log`
ERROR entries are wrapped in a bordered block:
```
────────────────────────────────────────────────────────────────────────────────
  ERROR  2026-04-24 17:54:58  [converter]
────────────────────────────────────────────────────────────────────────────────

  Load failed for https://... — browser did not launch, no screenshot available

────────────────────────────────────────────────────────────────────────────────
```
Scan for these blocks — they contain the full exception and the specific step that failed.

### `logs/debug_screenshots/`
Files are named `YYYYMMDD_HHMMSS_microseconds_<sanitized-url>.png`. List the most recent ones for failed URLs. Read the screenshot image directly — it shows exactly what the browser saw at the moment of failure (paywall, cookie banner, empty page, etc.).

### `Code/converter.py` and `Code/output.py`
Read `converter.py` in full before proposing any change. Read `output.py` if the error occurred after a successful page load (i.e., during save).

If multiple failures are visible, ask the user which one(s) to focus on.

---

## Step 2 — Diagnose

Tell the user:

- **What failed** — which URL, which step in the process
- **Why it failed** — which category below and the specific evidence
- **What you plan to change** — one sentence

Wait for confirmation before writing a fix.

### Failure categories

| Category | Key signals |
|---|---|
| **Browser launch failure** | "browser did not launch, no screenshot available" — Chromium crashed before opening a page |
| **Content check too strict** | Screenshot shows a real loaded page, but `check_content_sufficient` returned False |
| **Page load / network timeout** | `TimeoutError` or `networkidle` timeout in the error block |
| **Paywall not bypassed** | Screenshot shows a paywall, login wall, or blurred/truncated article body |
| **Cookie banner blocking** | Screenshot shows an unclicked cookie dialog covering the page content |
| **AMP fallback also failed** | server.log shows both normal-load and AMP-load warnings before the final error |
| **Output generation error** | server.log shows `Loaded … via … mode` (page loaded fine) but `save_pdf` or `save_markdown` then raised an exception |
| **No category matches** | Paste the raw error block here and triage together before proceeding |

---

## Step 3 — Propose the Fix

Show the exact change — before/after diff or the specific lines to add. Keep fixes as narrow as possible.

### Content check too strict
Lower `MIN_BODY_TEXT_LENGTH`, `MIN_CONTENT_LENGTH`, or `MIN_PARAGRAPH_COUNT` in the constants block at the top of `converter.py`. Safe floor values: `MIN_BODY_TEXT_LENGTH` no lower than ~500, `MIN_CONTENT_LENGTH` no lower than ~2000, `MIN_PARAGRAPH_COUNT` no lower than 2.

**Regression risk:** lowering these thresholds means near-empty or error pages on *other* sites may start "succeeding" and producing near-empty output files. Mention this trade-off to the user when recommending a threshold change.

### Missing cookie selector
Read the debug screenshot — it shows the cookie dialog. Identify the button text, ID, or data attribute visible in the image, then add the appropriate selector to `COOKIE_SELECTORS` in `converter.py`. Playwright selector formats: `"button:has-text('Accept')"`, `"#cookie-accept"`, `"[data-testid='accept-all']"`.

### Paywall not bypassed
Read the debug screenshot to identify the CSS class or element wrapping the paywall overlay. Extend the JS in `_remove_paywalls()` with a targeted `querySelectorAll` for that selector:
```js
document.querySelectorAll('.specific-paywall-class').forEach(el => el.remove());
```
For Medium.com articles specifically, check/extend the `is_medium` branch. If JS removal keeps failing, consider enabling Freedium (see below).

### AMP fallback also failed
This means both the normal load and the AMP URL returned insufficient content. Options in order of invasiveness:
1. Check whether an AMP URL actually exists for this domain (some sites don't have one)
2. Lower the AMP-specific threshold: `check_content_sufficient(page, min_paragraphs=0)` is already the AMP call — if it's still failing, the page is genuinely near-empty
3. Add a domain-specific conditional in `_try_load` to skip the content check for this site

### Page load / network timeout
Increase `PAGE_LOAD_TIMEOUT_MS` or `NETWORK_IDLE_TIMEOUT_MS` in the constants block. Alternatively, catch the `networkidle` timeout separately in `_try_load` and continue rather than abort — some sites never fully reach network idle.

### Output generation error
The page loaded successfully but saving failed. Check which function raised the exception (`save_pdf` or `save_markdown` in `Code/output.py`). Common causes:
- `save_markdown`: `page.evaluate()` returned empty string — the `article`/`main`/`body` selector found nothing. Fix: broaden the selector or fall back to `document.documentElement.innerHTML`.
- `save_pdf`: Playwright `page.pdf()` failed — usually a permissions or path issue, rarely a Playwright bug.

### Freedium as a fallback (Medium and heavy paywalls)
If paywall bypass consistently fails for a site, `use_freedium=True` in `LoadOptions` routes the request through `https://freedium.cfd/<url>`. This is already wired up in `converter.py`. For the web UI, it can be enabled by setting `use_freedium=True` in `_convert_one_sync` for specific domains — propose this as a last resort after JS-based removal has been tried.

### `--no-extension` for isolating the Chrome extension
If the failure mode is unclear, suggest the user retry with `--no-extension` (CLI) or toggle "Strip navigation & ads" off in the web UI. This bypasses the paywall-removal Chrome extension entirely, which helps determine whether the extension is causing the problem.

**Wait for explicit approval before touching any file.**

---

## Step 4 — Apply and Verify

Once approved:

1. Apply the edit to `Code/converter.py` or `Code/output.py`
2. Run `pytest tests/ -v` — all tests use mocked Playwright pages, so passing confirms Python logic is intact but **does not prove the real browser fix works**
3. Tell the user: "restart the server (`python Code/server.py`) and retry `<url>` to verify the real fix"
4. If root cause is still uncertain, suggest `python Code/cli.py "<url>" --no-headless` to watch the browser in real time

---

## Hard Constraints

- **Never modify `sanitize_filename`** — it returns a stem without extension by design; the suffix is added by callers
- **All tunable values must stay as named module-level constants** at the top of `converter.py`, never inline magic numbers
- **Never change the `uuid`-based `user_data_dir` pattern** — required for concurrent conversions; sharing a Chromium profile directory causes `TargetClosedError`
- **Prefer the narrowest fix** — one constant, one selector, one JS line — not a restructure of `_try_load` or `open_page`
- **If root cause is genuinely uncertain, say so** — don't guess; suggest `--no-headless` and ask the user to retry manually
