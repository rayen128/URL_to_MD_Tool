import logging
import re
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, Page, BrowserContext

logger = logging.getLogger("converter")

# --- Constants ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
EXTENSION_ID = "ghkdkllgoehcklnpajjjmfoaokabfdfm"
EXTENSION_PATH = Path(__file__).parent / "remove_paywall_extension"
DEBUG_SCREENSHOTS_DIR = Path(__file__).parent.parent / \
    "logs" / "debug_screenshots"
PAGE_LOAD_TIMEOUT_MS = 90_000
NETWORK_IDLE_TIMEOUT_MS = 30_000
COOKIE_TIMEOUT_MS = 5_000
SCROLL_STEP_PX = 2_000
SCROLL_MAX_STEPS = 30
SCROLL_PAUSE_MS = 500
MIN_CONTENT_LENGTH = 10_000
MIN_PARAGRAPH_COUNT = 5
MIN_BODY_TEXT_LENGTH = 2_000

COOKIE_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('I accept')",
    "button:has-text('I Agree')",
    "button:has-text('Agree')",
    "button:has-text('Allow all')",
    "[data-testid='cookie-accept-all']",
    "button:has-text('Alles accepteren')",
    "button:has-text('Accepteren')",
    "button:has-text('Ik accepteer')",
    "button:has-text('Akkoord')",
    "button:has-text('Alle cookies accepteren')",
]


@dataclass
class LoadOptions:
    headless: bool = True
    use_extension: bool = True
    block_images: bool = False
    use_freedium: bool = False


def sanitize_filename(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    base = f"{parsed.netloc}_{path}" if path else parsed.netloc
    base = base.replace("/", "_")
    base = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    return base if base else "page"


def check_content_sufficient(
    page: Page,
    min_length: int = MIN_CONTENT_LENGTH,
    min_paragraphs: int = MIN_PARAGRAPH_COUNT,
) -> bool:
    content = page.content() or ""
    paragraphs = page.locator(
        "article p, section p, div[class*='article'] p").count()
    if len(content) > min_length and paragraphs > min_paragraphs:
        return True
    body_text = page.evaluate("() => document.body.innerText.length")
    return body_text > MIN_BODY_TEXT_LENGTH


def _auto_scroll(page: Page, max_steps: int = SCROLL_MAX_STEPS) -> None:
    last_height = page.evaluate("document.body.scrollHeight")
    steps = 0
    while steps < max_steps:
        page.evaluate(f"window.scrollBy(0, {SCROLL_STEP_PX});")
        page.wait_for_timeout(SCROLL_PAUSE_MS)
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height - last_height < 100:
            break
        last_height = new_height
        steps += 1
    page.evaluate("window.scrollTo(0, 0);")


def _accept_cookies(page: Page) -> None:
    for sel in COOKIE_SELECTORS:
        try:
            btn = page.locator(sel)
            if btn.is_visible(timeout=COOKIE_TIMEOUT_MS):
                btn.first.click()
                page.wait_for_timeout(1000)
                return
        except Exception:
            pass


def _detect_amp_url(page: Page) -> str | None:
    try:
        amp_link = page.locator('link[rel="amphtml"]')
        if amp_link.count() > 0:
            return amp_link.first.get_attribute("href")
    except Exception:
        pass
    return None


def _remove_paywalls(page: Page, is_medium: bool = False) -> None:
    if is_medium:
        js = """() => {
            document.querySelectorAll('div.meteredContent, section[class*="locked"], div.paywall, [class*="paywall"], .meter-banner, .locked-content').forEach(el => {
                el.remove();
            });
            document.body.classList.remove('meter-locked', 'paywall-active');
            document.querySelectorAll('p, h1, h2, img').forEach(el => {
                el.style = 'filter: none !important; visibility: visible !important; opacity: 1 !important;';
            });
            localStorage.setItem('mediumUnlimited', 'true');
        }"""
    else:
        js = """() => {
            document.querySelectorAll('div[class*="paywall"], #paywall, [class*="meter"], [class*="lock"], .overlay, .backdrop').forEach(el => el.remove());
            document.body.style.overflow = 'auto';
            document.documentElement.style.overflow = 'auto';
            document.querySelectorAll('*').forEach(el => {
                if (getComputedStyle(el).filter === 'blur(5px)' || el.classList.contains('blurred'))
                    el.style.filter = 'none';
            });
        }"""
    page.evaluate(js)
    page.wait_for_timeout(2000)


def _enable_extension(context: BrowserContext, page: Page) -> None:
    for attempt in range(3):
        try:
            popup = context.new_page()
            try:
                popup.goto(
                    f"chrome-extension://{EXTENSION_ID}/popup.html", timeout=10_000)
                btn = popup.locator("button, [role='button']")
                if btn.is_visible(timeout=0):
                    btn.first.click()
            finally:
                try:
                    popup.close()
                except Exception:
                    pass
            page.wait_for_load_state(
                "networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
            return
        except Exception as e:
            logger.warning("Extension attempt %d/3 failed: %s", attempt + 1, e)
            page.wait_for_timeout(2000)


def _try_load(
    page: Page,
    context: BrowserContext,
    url: str,
    is_medium: bool,
    use_extension: bool,
) -> tuple[bool, str | None]:
    try:
        page.goto(url, wait_until="domcontentloaded",
                  timeout=PAGE_LOAD_TIMEOUT_MS)
        page.wait_for_load_state(
            "networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
        _accept_cookies(page)
        if use_extension:
            _enable_extension(context, page)
        _remove_paywalls(page, is_medium)
        _auto_scroll(page)
        page.wait_for_timeout(3000)
        _remove_paywalls(page, is_medium)
        if check_content_sufficient(page):
            return True, "normal"
    except Exception as e:
        logger.warning("Normal load failed for %s: %s", url, e)

    amp_url = _detect_amp_url(page)
    if not amp_url:
        for candidate in [f"{url}?amp=1", f"{url}/amp"]:
            try:
                resp = page.goto(candidate, timeout=30_000)
                if resp and resp.status == 200:
                    amp_url = candidate
                    break
            except Exception:
                continue

    if amp_url:
        try:
            page.goto(amp_url, wait_until="networkidle")
            _accept_cookies(page)
            _remove_paywalls(page)
            _auto_scroll(page, max_steps=15)
            if check_content_sufficient(page, min_paragraphs=0):
                return True, "amp"
        except Exception as e:
            logger.warning("AMP fallback failed for %s: %s", url, e)

    return False, None


def _save_debug_screenshot(page, url: str) -> None:
    DEBUG_SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{ts}_{sanitize_filename(url)}.png"
    if page is None:
        logger.error(
            "Load failed for %s — browser did not launch, no screenshot available", url)
        return
    try:
        page.screenshot(path=str(DEBUG_SCREENSHOTS_DIR / filename))
        logger.error(
            "Load failed for %s — screenshot: logs/debug_screenshots/%s", url, filename)
    except Exception as exc:
        logger.error(
            "Load failed for %s — screenshot attempt failed: %s", url, exc)


@contextmanager
def open_page(url: str, options: LoadOptions):
    """
    Context manager: launches Chromium, loads url with paywall bypass, yields the
    ready Page. Cleans up browser and playwright-user-data/ on exit.
    Raises RuntimeError if content cannot be loaded.
    """
    if options.use_freedium:
        url = f"https://freedium.cfd/{url}"
        logger.info("Using Freedium proxy for %s", url)

    is_medium = "medium.com" in urlparse(url).netloc
    parsed = urlparse(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"

    user_data_dir = Path(__file__).parent.parent / \
        "playwright-user-data" / uuid.uuid4().hex
    user_data_dir.mkdir(parents=True, exist_ok=True)

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    use_ext = options.use_extension and EXTENSION_PATH.exists()
    if use_ext:
        launch_args += [
            f"--disable-extensions-except={EXTENSION_PATH}",
            f"--load-extension={EXTENSION_PATH}",
        ]

    playwright = sync_playwright().start()
    context = None
    page = None
    try:
        # Inner try/except covers only the load phase so that exceptions from
        # the caller (save_pdf / save_markdown) after yield do not trigger screenshots.
        try:
            context = playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                channel="chromium",
                headless=options.headless,
                args=launch_args,
                user_agent=USER_AGENT,
                locale="en-US",
                extra_http_headers={"Referer": referer},
                ignore_https_errors=True,
            )
            block_types = ["font", "media"]
            if options.block_images:
                block_types.append("image")
            context.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in block_types
                else route.continue_(),
            )

            page = context.pages[0] if context.pages else context.new_page()
            page.set_viewport_size({"width": 1920, "height": 1080})

            success, mode = _try_load(page, context, url, is_medium, use_ext)
            if not success:
                raise RuntimeError(
                    "Could not load page content. "
                    "See logs/debug_screenshots/ for a screenshot. "
                    "Try --no-extension, --freedium, or --no-headless."
                )
            logger.debug("Loaded %s via %s mode", url, mode)
        except Exception:
            _save_debug_screenshot(page, url)
            raise

        yield page
    finally:
        if context:
            try:
                context.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass
        shutil.rmtree(user_data_dir, ignore_errors=True)
