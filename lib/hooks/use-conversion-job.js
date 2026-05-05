"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { titleFor } from "@/lib/url";
import { isCancelled } from "@/lib/format";

export function useConversionJob() {
  const [items, setItems] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [format, setFormat] = useState(null);
  const [name, setName] = useState("");
  const streamRef = useRef(null);
  const reconnectAttemptedRef = useRef(false);

  useEffect(() => () => streamRef.current?.close(), []);

  const updateItem = useCallback((id, patch) => {
    setItems((cur) => {
      let changed = false;
      const next = cur.map((i) => {
        if (i.id !== id) return i;
        const merged = { ...i };
        for (const [k, v] of Object.entries(patch)) {
          if (v !== undefined && merged[k] !== v) {
            merged[k] = v;
            changed = true;
          }
        }
        return changed ? merged : i;
      });
      return changed ? next : cur;
    });
  }, []);

  const stats = useMemo(() => {
    const s = { queued: 0, working: 0, done: 0, error: 0, cancelled: 0 };
    items.forEach((i) => {
      if (isCancelled(i)) s.cancelled += 1;
      else if (i.status in s) s[i.status] += 1;
    });
    return s;
  }, [items]);

  const progress = items.length
    ? Math.round(((stats.done + stats.error + stats.cancelled) / items.length) * 100)
    : 0;

  const applyEvent = useCallback((msg) => {
    if (msg.type === "status") {
      updateItem(msg.url_id, {
        status: msg.status,
        title: msg.title,
        size: msg.size,
        filename: msg.filename,
        error: msg.error || null,
      });
    } else if (msg.type === "item_added") {
      setItems((cur) => cur.some((x) => x.id === msg.item.id)
        ? cur
        : [...cur, { ...msg.item, title: titleFor(msg.item.url), size: null, filename: null, error: null }]);
    } else if (msg.type === "cap_reached") {
      toast.warning(`Crawl limit reached at ${msg.max_pages} pages`);
    } else if (msg.type === "done") {
      setIsRunning(false);
      streamRef.current?.close();
      streamRef.current = null;
    }
  }, [updateItem]);

  const openStream = useCallback(function openStreamConnection(id) {
    streamRef.current?.close();
    const es = new EventSource(`/api/jobs/${id}/stream`);
    streamRef.current = es;
    es.onopen = () => { reconnectAttemptedRef.current = false; };
    es.onmessage = (e) => applyEvent(JSON.parse(e.data));
    es.onerror = () => {
      if (es.readyState !== EventSource.CLOSED) return;
      if (!reconnectAttemptedRef.current) {
        reconnectAttemptedRef.current = true;
        toast.info("Reconnecting…");
        setTimeout(() => openStreamConnection(id), 800);
      } else {
        toast.error("Lost connection. Refresh to resume.");
        setIsRunning(false);
      }
    };
  }, [applyEvent]);

  const start = useCallback(async ({ urls, format: fmt, name: jobName, options }) => {
    if (!urls.length || isRunning) return null;
    reconnectAttemptedRef.current = false;
    setIsRunning(true);
    setFormat(fmt);
    setName(jobName || "");
    try {
      const r = await fetch("/api/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls, format: fmt, collection: jobName, options }),
      });
      if (!r.ok) {
        // Surface FastAPI's `detail` field so backend validation errors
        // (e.g. cross-host crawl seeds) reach the user verbatim.
        let detail = "";
        try {
          const body = await r.json();
          if (body && typeof body.detail === "string") detail = body.detail;
        } catch { /* non-JSON; fall back to status-based message */ }
        if (detail) throw new Error(detail);
        if (r.status === 503) throw new Error("Server is busy, retry shortly.");
        if (r.status >= 500) throw new Error("Something went wrong on the server.");
        throw new Error("That request looks invalid.");
      }
      const data = await r.json();
      setJobId(data.job_id);
      setItems((data.items || []).map((i) => ({
        ...i, title: titleFor(i.url), size: null, filename: null, error: null,
      })));
      openStream(data.job_id);
      return data.job_id;
    } catch (e) {
      setIsRunning(false);
      toast.error(`Couldn't save: ${e.message || "unknown error"}`);
      return null;
    }
  }, [isRunning, openStream]);

  const attach = useCallback(async (id) => {
    if (!id) return { ok: false, status: 0 };
    reconnectAttemptedRef.current = false;
    try {
      const r = await fetch(`/api/jobs/${id}`);
      if (!r.ok) return { ok: false, status: r.status };
      const data = await r.json();
      setJobId(data.job_id);
      setFormat(data.format);
      setName(data.name || "");
      setItems((data.items || []).map((i) => ({
        ...i,
        title: i.title || titleFor(i.url),
      })));
      setIsRunning(!!data.isRunning);
      if (data.isRunning) openStream(data.job_id);
      return { ok: true, status: r.status };
    } catch (e) {
      toast.error(`Couldn't open: ${e.message || "unknown error"}`);
      return { ok: false, status: 0 };
    }
  }, [openStream]);

  const stop = useCallback(async () => {
    if (!jobId) return;
    streamRef.current?.close();
    streamRef.current = null;
    try { await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" }); }
    catch { toast.warning("Cancel may not have reached the server."); }
    setIsRunning(false);
    setItems((cur) => cur.map((i) =>
      (i.status === "queued" || i.status === "working")
        ? { ...i, status: "error", error: "Cancelled" }
        : i,
    ));
  }, [jobId]);

  const retryItem = useCallback(async (id) => {
    if (!jobId) return;
    updateItem(id, { status: "working", error: null });
    setIsRunning(true);
    if (!streamRef.current || streamRef.current.readyState === EventSource.CLOSED) openStream(jobId);
    try {
      const r = await fetch(`/api/jobs/${jobId}/retry/${id}`, { method: "POST" });
      if (!r.ok) throw new Error();
    } catch {
      updateItem(id, { status: "error", error: "Retry failed" });
      toast.error("Retry failed");
    }
  }, [jobId, updateItem, openStream]);

  const downloadOne = useCallback((item) => {
    if (!jobId || !item) return;
    window.open(`/api/files/${jobId}/${item.id}`, "_blank");
  }, [jobId]);

  const downloadMerged = useCallback(async () => {
    if (!jobId) return;
    try {
      const res = await fetch(`/api/jobs/${jobId}/merged`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const skipped = parseInt(res.headers.get("X-Merged-Skipped") || "0", 10);
      if (skipped > 0) {
        toast.warning(`${skipped} file${skipped === 1 ? "" : "s"} couldn't be merged. Check the file list for failures.`);
      }
      const fallback = `collection.${format === "pdf" ? "pdf" : "md"}`;
      await _saveBlob(await res.blob(), _filenameFromResponse(res, fallback));
    } catch (e) {
      toast.error(`Couldn't download: ${e.message || "unknown error"}`);
    }
  }, [jobId, format]);

  const downloadZip = useCallback(async () => {
    if (!jobId) return;
    try {
      const res = await fetch(`/api/jobs/${jobId}/zip`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await _saveBlob(await res.blob(), _filenameFromResponse(res, "collection.zip"));
    } catch (e) {
      toast.error(`Couldn't download: ${e.message || "unknown error"}`);
    }
  }, [jobId]);

  const reset = useCallback(() => {
    streamRef.current?.close();
    streamRef.current = null;
    setItems([]);
    setIsRunning(false);
    setJobId(null);
    setFormat(null);
    setName("");
  }, []);

  return {
    items, isRunning, jobId, format, name, stats, progress,
    start, attach, stop, retryItem, reset,
    downloadOne, downloadMerged, downloadZip,
  };
}

function _filenameFromResponse(res, fallback) {
  const cd = res.headers.get("Content-Disposition") || "";
  const m = /filename="?([^"]+)"?/.exec(cd);
  return m ? m[1] : fallback;
}

async function _saveBlob(blob, filename) {
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}
