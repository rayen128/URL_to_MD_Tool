import re
from urllib.parse import urlparse


_TRAILING_PUNCT_RE = re.compile(r"[.,;:!?)\'\"\]]+$")
_MD_LINK_RE = re.compile(r"^\[[^\]]*\]\((.+)\)$")
_ANGLE_WRAP_RE = re.compile(r"^<(.+)>$")
_ALLOWED_SCHEMES = {"http", "https"}
_MAX_URL_LEN = 2048


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("Cannot normalize to a valid URL: empty input")

    md = _MD_LINK_RE.match(url)
    if md:
        url = md.group(1).strip()
    url = _ANGLE_WRAP_RE.sub(r"\1", url).strip()
    url = _TRAILING_PUNCT_RE.sub("", url)

    if not url or len(url) > _MAX_URL_LEN:
        raise ValueError(f"Cannot normalize to a valid URL: {url!r}")

    if url.startswith("//"):
        url = "https:" + url
    elif "://" not in url:
        url = "https://" + url

    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"Cannot normalize to a valid URL: {url!r}")
    if parsed.username or parsed.password:
        raise ValueError(f"Cannot normalize to a valid URL: {url!r}")
    if not parsed.netloc or " " in parsed.netloc:
        raise ValueError(f"Cannot normalize to a valid URL: {url!r}")
    if not parsed.hostname or "." not in parsed.hostname:
        raise ValueError(f"Cannot normalize to a valid URL: {url!r}")
    return url
