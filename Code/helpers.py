from urllib.parse import urlparse


def normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    elif "://" not in url:
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc or " " in parsed.netloc or "." not in parsed.hostname:
        raise ValueError(f"Cannot normalize to a valid URL: {url!r}")
    return url
