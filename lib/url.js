// Client-side URL normalizer. The backend re-normalizes via Code/helpers.py:normalize_url
// when the job runs, so this is a UX layer (validation, dedup, preview), NOT the
// source of truth. Keep the two normalizers behaviour-aligned for HTTP(S) URLs;
// divergence is acceptable for prose-cleanup (markdown links, wrapper-stripping)
// since those never reach the server. The cleaned URL is what's POSTed.

const HTTP_RE = /^https?:$/;
const INVISIBLE_RE = /[​-‏‪-‮⁠﻿]/g;
const LEADING_NOISE_RE = /^[\s\-–—•*>#·]+/;
const TRAILING_NOISE_CHARS = new Set([" ", "\t", ".", ",", ";", ":", "!", "?", "'", "\"", "»", "›", "]"]);
const WRAP_PAIRS = [
  ["[", "]"], ["(", ")"], ["{", "}"], ["<", ">"],
  ["\"", "\""], ["'", "'"], ["`", "`"],
  ["“", "”"], ["‘", "’"], ["«", "»"],
];

function _tryParse(s) {
  let url = s;
  if (!url) return null;
  if (url.length > 2048) return null;
  if (/\s/.test(url)) return null;

  if (url.startsWith("//")) url = `https:${url}`;
  else if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) url = `https://${url}`;

  let parsed;
  try { parsed = new URL(url); } catch { return null; }
  if (!HTTP_RE.test(parsed.protocol)) return null;
  if (parsed.username || parsed.password) return null;

  const host = parsed.hostname;
  if (!host || /\s/.test(host)) return null;
  if (!host.includes(".") || host.startsWith(".") || host.endsWith(".")) return null;
  const tld = host.split(".").pop();
  if (!tld || tld.length < 2) return null;

  return parsed.href;
}

export function normalizeUrl(value) {
  let url = (value || "").replace(INVISIBLE_RE, "").trim();
  if (!url) return null;

  // Markdown link form. Use lazy match + last `)` so URLs containing `)` survive,
  // e.g. [PDF](https://en.wikipedia.org/wiki/PDF_(file_format))
  const md = url.match(/^\[[^\]]*\]\((.+)\)$/);
  if (md) {
    const inner = md[1].trim();
    const parsed = _tryParse(inner);
    if (parsed) return parsed;
    // Fall through if MD inner doesn't parse; the wrapper-strip below may help.
  }

  url = url.replace(LEADING_NOISE_RE, "").trim();

  // Try parsing as-is first; only strip wrappers / trailing noise if needed.
  // This preserves `)` and quotes when they're legitimately part of the URL.
  let parsed = _tryParse(url);
  if (parsed) return parsed;

  // Try stripping balanced wrapper pairs.
  for (let i = 0; i < 3 && url.length >= 2; i += 1) {
    let stripped = false;
    for (const [open, close] of WRAP_PAIRS) {
      if (url.startsWith(open) && url.endsWith(close)) {
        const candidate = url.slice(open.length, url.length - close.length).trim();
        const tryParsed = _tryParse(candidate);
        if (tryParsed) return tryParsed;
        url = candidate;
        stripped = true;
        break;
      }
    }
    if (!stripped) break;
  }

  // Last resort: peel trailing noise chars one at a time, retry parse each step.
  // Stops as soon as a valid parse is reached, so we don't over-strip a URL
  // whose meaningful suffix was originally already valid.
  while (url.length > 0 && TRAILING_NOISE_CHARS.has(url[url.length - 1])) {
    url = url.slice(0, -1);
    parsed = _tryParse(url);
    if (parsed) return parsed;
  }

  return null;
}

function _dedupKey(href) {
  // Collapse trailing slash + lower-case host so e.g. example.com/foo,
  // EXAMPLE.com/foo, example.com/foo/ all dedup together. Mirrors what
  // jobs.py:_canonical_url does server-side for crawl visited-set.
  try {
    const u = new URL(href);
    const path = u.pathname.replace(/\/+$/, "") || "/";
    return `${u.protocol}//${u.hostname.toLowerCase()}${path}${u.search}${u.hash}`;
  } catch {
    return href;
  }
}

export function validateUrls(text) {
  const lines = (text || "").split(/\r?\n/);
  const seen = new Set();
  const valid = [];
  const invalid = [];
  const duplicates = [];

  lines.forEach((raw, i) => {
    const trimmed = raw.trim();
    if (!trimmed) return;
    const lineNumber = i + 1;
    const normalized = normalizeUrl(trimmed);
    if (!normalized) {
      invalid.push({ line: lineNumber, raw: trimmed });
      return;
    }
    const key = _dedupKey(normalized);
    if (seen.has(key)) {
      duplicates.push({ line: lineNumber, url: normalized });
      return;
    }
    seen.add(key);
    valid.push(normalized);
  });

  return { valid, invalid, duplicates };
}

export function domainFor(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return ""; }
}

export function titleFor(url) {
  try {
    const u = new URL(url);
    const slug = u.pathname.replace(/\/$/, "").split("/").filter(Boolean).pop();
    if (!slug) return domainFor(url);
    return slug.replace(/\.html?$/, "").replace(/[-_]/g, " ").slice(0, 80);
  } catch { return "Untitled"; }
}

export function faviconFor(url) {
  try { return `https://www.google.com/s2/favicons?domain=${new URL(url).hostname}&sz=64`; }
  catch { return null; }
}

export function defaultCollectionName(urls, override, { recursive = false } = {}) {
  if (override) return override;
  const list = Array.isArray(urls) ? urls : [];
  const firstDomain = domainFor(list[0]) || "Untitled";
  if (recursive) return `${firstDomain} crawl`;
  const n = list.length;
  return n === 1 ? firstDomain : `${firstDomain} · ${n} pages`;
}
