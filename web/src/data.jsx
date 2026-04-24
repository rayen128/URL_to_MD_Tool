// Browser-side URL display helpers

const DOMAIN_NICE = {
  "nu.nl": "NU.nl",
  "tweakers.net": "Tweakers",
  "nrc.nl": "NRC",
  "fd.nl": "Het Financieele Dagblad",
  "rijksoverheid.nl": "Rijksoverheid",
  "computable.nl": "Computable",
  "protinus.nl": "Protinus IT",
  "emerce.nl": "Emerce",
  "agconnect.nl": "AG Connect",
  "parlement.com": "Parlement.com",
  "github.com": "GitHub",
  "stackoverflow.com": "Stack Overflow",
  "wikipedia.org": "Wikipedia",
  "arxiv.org": "arXiv",
  "anthropic.com": "Anthropic",
  "openai.com": "OpenAI",
};

// Deterministic pseudo-title based on URL path
function titleFor(url) {
  try {
    const u = new URL(url);
    const domain = u.hostname.replace(/^www\./, "");
    const nice = DOMAIN_NICE[domain] || domain.split(".")[0].replace(/^\w/, c => c.toUpperCase());
    const path = u.pathname.replace(/^\//, "").replace(/\/$/, "");
    if (!path) return `${nice} — Homepage`;
    const slug = path.split("/").pop() || path;
    const words = slug.replace(/\.html?$/, "").replace(/[-_]/g, " ");
    const titled = words.split(" ").filter(Boolean).slice(0, 8)
      .map(w => /^[a-z]/i.test(w) ? w[0].toUpperCase() + w.slice(1) : w)
      .join(" ");
    return titled || `${nice} article`;
  } catch {
    return "Untitled page";
  }
}

function domainFor(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return "invalid"; }
}

function faviconFor(url) {
  try {
    const u = new URL(url);
    return `https://www.google.com/s2/favicons?domain=${u.hostname}&sz=64`;
  } catch { return null; }
}

function fmtSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes/1024).toFixed(1)} KB`;
  return `${(bytes/(1024*1024)).toFixed(2)} MB`;
}

function fmtTimeAgo(ts) {
  const diff = Date.now() - ts;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hr ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d} day${d>1?"s":""} ago`;
  const date = new Date(ts);
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function niceDate(ts) {
  return new Date(ts).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric"
  });
}

window.ProtinusData = {
  titleFor, domainFor, faviconFor, fmtSize, fmtTimeAgo, niceDate,
};
