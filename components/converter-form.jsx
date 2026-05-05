"use client";

/* eslint-disable @next/next/no-img-element */

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import {
  ArrowLeft,
  Clipboard,
  Download,
  FileArchive,
  FileText,
  FileType,
  MoreHorizontal,
  Pencil,
  Play,
  Plus,
  Repeat,
  RotateCcw,
  Search,
  Square,
  Trash2,
  Wand2,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { IconButton } from "@/components/ui/icon-button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Spinner } from "@/components/ui/spinner";
import { ProtinusMark } from "@/components/protinus-mark";
import { domainFor, faviconFor, defaultCollectionName, validateUrls } from "@/lib/url";
import { clampInt } from "@/lib/format";
import { fmtSize, fmtTimeAgo, isCancelled } from "@/lib/format";
import { useConversionJob } from "@/lib/hooks/use-conversion-job";
import { List } from "react-window";

const PASTE_SAMPLE = [
  "https://www.protinus.nl/over-ons",
  "https://en.wikipedia.org/wiki/PDF",
  "https://www.dailydoseofds.com/p/10-must-use-slash-commands-in-claude-code/",
];
const CRAWL_SAMPLE = "https://en.wikipedia.org/wiki/Markdown";


function derivePhase({ isRunning, items, stats }) {
  if (isRunning) return "running";
  if (items.length === 0) return "idle";
  if (stats.cancelled > 0) return "stopped";
  if (stats.done === 0) return "nothing";
  if (stats.error > 0) return "errors";
  return "saved";
}

function deriveHeaderLabel(phase, stats, items, { idle, nothing }) {
  switch (phase) {
    case "idle": return idle;
    case "running": return `Saving ${stats.done + stats.error + stats.cancelled} of ${items.length}…`;
    case "stopped": return stats.done > 0
      ? `Stopped · ${stats.done} saved, ${stats.cancelled} cancelled`
      : `Stopped · ${stats.cancelled} cancelled`;
    case "nothing": return nothing;
    case "errors": return `${stats.done} saved, ${stats.error} failed`;
    case "saved": return `${stats.done} saved`;
    default: return "";
  }
}

function UrlValidityStatus({ validation, hasInput, recursive, crossHostHosts = null }) {
  const valid = validation.valid.length;
  const invalid = validation.invalid;
  const duplicates = validation.duplicates;
  const total = valid + invalid.length + duplicates.length;

  if (total === 0) {
    if (hasInput) return <span>Keep typing…</span>;
    return (
      <span>
        {recursive ? "One starting URL, or several on the same domain" : "Paste one URL per line. Any domains."}
      </span>
    );
  }

  const parts = [];

  if (valid > 0) {
    parts.push(
      <span key="valid">
        <span className="font-medium text-[var(--green-2)]">{valid}</span> valid
      </span>
    );
  } else if (invalid.length > 0 || duplicates.length > 0) {
    parts.push(<span key="none" className="text-[var(--danger)]">No valid URLs</span>);
  }

  if (crossHostHosts) {
    parts.push(
      <Tooltip key="xhost">
        <TooltipTrigger asChild>
          <span className="cursor-help text-[var(--danger)] underline decoration-dotted underline-offset-2">
            crawl seeds must share a domain
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-sm break-words">
          Found {crossHostHosts.length} hosts: {crossHostHosts.join(", ")}
        </TooltipContent>
      </Tooltip>
    );
  }

  if (duplicates.length > 0) {
    const lines = duplicates.map((d) => d.line).join(", ");
    parts.push(
      <Tooltip key="dup">
        <TooltipTrigger asChild>
          <span className="cursor-help text-[var(--muted)] underline decoration-dotted underline-offset-2">
            {duplicates.length} duplicate{duplicates.length === 1 ? "" : "s"}
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-sm break-words">Line{duplicates.length === 1 ? "" : "s"} {lines}</TooltipContent>
      </Tooltip>
    );
  }

  if (invalid.length > 0) {
    const preview = invalid.slice(0, 5).map((x) => `L${x.line}: ${x.raw}`).join("\n");
    const more = invalid.length > 5 ? `\n…and ${invalid.length - 5} more` : "";
    const lines = invalid.map((x) => x.line).join(", ");
    parts.push(
      <Tooltip key="inv">
        <TooltipTrigger asChild>
          <span className="cursor-help text-[var(--danger)] underline decoration-dotted underline-offset-2">
            {invalid.length} invalid (line{invalid.length === 1 ? "" : "s"} {lines})
          </span>
        </TooltipTrigger>
        <TooltipContent className="max-w-sm whitespace-pre-line break-words">
          {preview}{more}
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <span className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5">
      {parts.flatMap((p, i) => (
        i === 0 ? [p] : [<span key={`sep-${i}`} aria-hidden className="opacity-50">·</span>, p]
      ))}
    </span>
  );
}

function TopBarTab({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative inline-flex h-10 items-center gap-1.5 px-1 text-sm font-medium transition-colors after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:rounded-full after:transition-colors ${
        active
          ? "text-white after:bg-[var(--green)]"
          : "text-white/60 hover:text-white after:bg-transparent"
      }`}
    >
      {children}
    </button>
  );
}

function mergeCollections(local, server) {
  // Server is the source of truth for known ids; local entries that the server
  // doesn't have yet (just-added, not yet flushed) are kept and prepended in
  // their existing order. For overlapping ids, take the server payload but
  // preserve local-only fields (e.g. a name being optimistically renamed).
  const serverMap = new Map(server.map((s) => [s.id, s]));
  const merged = server.map((s) => {
    const l = local.find((x) => x.id === s.id);
    return l ? { ...s, ...{ name: l.name ?? s.name } } : s;
  });
  for (let i = local.length - 1; i >= 0; i -= 1) {
    if (!serverMap.has(local[i].id)) merged.unshift(local[i]);
  }
  return merged;
}

export function ConverterForm() {
  const [tab, setTab] = useState("new");
  const [collections, setCollections] = useState([]);

  // Refetch on mount and on every entry to the Library tab. Merge server data
  // by id with local state so optimistic add/rename/delete updates aren't
  // clobbered by a refetch that races them.
  const loadCollections = useCallback(() => {
    fetch("/api/collections")
      .then((r) => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then((server) => setCollections((local) => mergeCollections(local, Array.isArray(server) ? server : [])))
      .catch(() => toast.error("Couldn't load My Collection. Try refreshing."));
  }, []);

  useEffect(() => { loadCollections(); }, [loadCollections]);
  useEffect(() => { if (tab === "library") loadCollections(); }, [tab, loadCollections]);

  function addCollection(payload) {
    setCollections((c) => [payload, ...c.filter((x) => x.id !== payload.id)]);
  }

  function evictCollection(id) {
    setCollections((c) => c.filter((x) => x.id !== id));
  }

  async function deleteCollection(id) {
    const prev = collections;
    setCollections((c) => c.filter((x) => x.id !== id));
    try {
      const r = await fetch(`/api/collections/${id}`, { method: "DELETE" });
      if (!r.ok && r.status !== 404) throw new Error();
      toast.success("Removed from My Collection");
    } catch {
      setCollections(prev);
      toast.error("Delete failed. Try again.");
    }
  }

  async function renameCollection(id, name) {
    const prev = collections;
    setCollections((c) => c.map((x) => x.id === id ? { ...x, name } : x));
    try {
      const r = await fetch(`/api/collections/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!r.ok) throw new Error();
      return true;
    } catch {
      setCollections(prev);
      toast.error("Rename failed. Try again.");
      return false;
    }
  }

  return (
    <div className="min-h-screen bg-[var(--canvas)]">
      <header className="border-b border-white/5 bg-[var(--navy)] text-white">
        <div className="mx-auto flex max-w-[1240px] items-center gap-8 px-7 py-4">
          <button
            type="button"
            onClick={() => setTab("new")}
            aria-label="Go to Scraper"
            className="group flex items-center gap-1.5 rounded-md outline-none transition-opacity hover:opacity-90 focus-visible:ring-2 focus-visible:ring-[var(--green)]/60"
          >
            <ProtinusMark />
            <span className="text-[18px] font-medium tracking-tight leading-none">
              Protinus<span className="font-medium text-[var(--green)]">ETA</span>
            </span>
          </button>
          <nav className="ml-auto flex items-center gap-7">
            <TopBarTab active={tab === "new"} onClick={() => setTab("new")}>
              Scraper
            </TopBarTab>
            <TopBarTab active={tab === "library"} onClick={() => setTab("library")}>
              My Collection
              <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--green)] px-1.5 text-[11px] font-medium text-white">
                {collections.length}
              </span>
            </TopBarTab>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-[1240px] px-7 pt-14 pb-8">
        {tab === "new" ? (
          <NewSave onCreateCollection={addCollection} />
        ) : (
          <Library collections={collections} onDelete={deleteCollection} onRename={renameCollection} onMissing={evictCollection} onGoNew={() => setTab("new")} />
        )}
      </main>
    </div>
  );
}

function NewSave({ onCreateCollection }) {
  const [text, setText] = useState("");
  const [format, setFormat] = useState("markdown");
  const [name, setName] = useState("");
  const [recursive, setRecursive] = useState(false);
  const [maxPages, setMaxPages] = useState(100);
  const [includeImages, setIncludeImages] = useState(true);
  const [pageSize, setPageSize] = useState("A4");
  const [confirmOpen, setConfirmOpen] = useState(false);

  const {
    items, isRunning, jobId, stats, progress,
    start: startJob, stop, retryItem, reset,
    downloadOne, downloadMerged, downloadZip,
  } = useConversionJob();

  const validation = useMemo(() => validateUrls(text), [text]);
  const validUrls = validation.valid;
  const invalidLines = validation.invalid;
  const duplicateCount = validation.duplicates.length;

  // Recursive mode requires all seeds on the same host (backend enforces).
  // Surface the mismatch early so the user fixes it before submit.
  const recursiveHosts = useMemo(() => {
    if (!recursive || validUrls.length < 2) return null;
    const hosts = new Set(validUrls.map((u) => domainFor(u)));
    return hosts.size > 1 ? Array.from(hosts) : null;
  }, [recursive, validUrls]);
  const hasCrossHost = !!recursiveHosts;
  const canSubmit = validUrls.length > 0 && !hasCrossHost;

  const phase = derivePhase({ isRunning, items, stats });
  const headerLabel = deriveHeaderLabel(phase, stats, items, {
    idle: "Ready",
    nothing: "Nothing saved",
  });

  async function start() {
    setConfirmOpen(false);
    await new Promise((r) => requestAnimationFrame(r));
    const displayName = defaultCollectionName(validUrls, name, { recursive });
    const newJobId = await startJob({
      urls: validUrls,
      format,
      name,
      options: { images: includeImages, reader: true, pageSize, recursive, maxPages },
    });
    if (newJobId) {
      onCreateCollection({
        id: newJobId,
        name: displayName,
        format,
        createdAt: Date.now(),
        urls: validUrls,
        done: 0,
        errors: 0,
      });
    }
  }

  function loadSample() {
    setText(recursive ? CRAWL_SAMPLE : PASTE_SAMPLE.join("\n"));
  }

  async function paste() {
    try {
      const t = await navigator.clipboard.readText();
      setText((cur) => (cur ? `${cur.replace(/\s+$/, "")}\n${t}` : t));
    } catch {
      toast.error("Clipboard blocked. Paste with Ctrl+V instead.");
    }
  }

  function clearAll() {
    setText("");
    reset();
  }

  const formatLabel = format === "pdf" ? "PDF" : "Markdown";
  const seedHost = validUrls.length ? domainFor(validUrls[0]) : "";
  const ctaLabel = recursive
    ? `Crawl ${seedHost || "site"} as ${formatLabel}`
    : validUrls.length > 1
      ? `Save ${validUrls.length} as ${formatLabel}`
      : `Save as ${formatLabel}`;

  const dialogTitle = recursive
    ? `Crawl ${seedHost || "site"}${validUrls.length > 1 ? ` (${validUrls.length} seeds)` : ""}`
    : `Save ${validUrls.length} webpage${validUrls.length === 1 ? "" : "s"}`;

  const showOutput = items.length > 0 || isRunning;

  return (
    <>
      <div className="mb-8 text-center">
        <h1 className="text-2xl sm:text-3xl md:text-[30px] lg:text-[34px] font-medium tracking-tight leading-[1.15] text-[var(--navy)]">
          Turn websites into clean <span className="font-medium text-[var(--green)]">Markdown</span> or <span className="font-medium text-[var(--green)]">PDF</span>.
        </h1>
        <p className="mt-2 text-xs md:text-[13px] leading-snug text-[var(--muted)]">
          Paste a list of links or crawl a whole site. Get one merged file, ready to feed an LLM, read offline, or share.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[440px_minmax(0,1fr)]">
      <Card className={`relative flex flex-col overflow-hidden p-5 min-h-[500px] transition-colors ${isRunning ? "border-[var(--green)]" : ""}`}>
        {isRunning && (
          <div className="absolute inset-x-0 top-0 flex items-center justify-center gap-2 bg-[var(--green-soft)] py-1.5 text-xs font-medium text-[var(--green-2)]">
            <Spinner size="xs" /> Saving · settings locked while running
          </div>
        )}
        <fieldset disabled={isRunning} className={`contents ${isRunning ? "[&_*]:cursor-not-allowed" : ""}`}>
          <div className={isRunning ? "opacity-50 transition-opacity pt-6" : "transition-opacity"}>
          <ToggleGroup
            type="single"
            value={recursive ? "crawl" : "paste"}
            onValueChange={(v) => v && setRecursive(v === "crawl")}
            variant="outline"
            spacing="default"
            className="grid w-full grid-cols-2 gap-3"
          >
            <ToggleGroupItem value="paste" className="!h-9 w-full rounded-md text-sm">Paste links</ToggleGroupItem>
            <ToggleGroupItem value="crawl" className="!h-9 w-full rounded-md text-sm">
              <Repeat className="size-4" /> Crawl site
            </ToggleGroupItem>
          </ToggleGroup>

          <div className="relative mt-6">
            <Textarea
              placeholder={recursive
                ? "Starting URL, or several seeds on the same domain\n\nhttps://docs.example.com/guide/\nhttps://docs.example.com/api/"
                : "Paste one URL per line. Any domains.\n\nhttps://example.com/article-1\nhttps://other.com/post"}
              value={text}
              onChange={(e) => setText(e.target.value)}
              spellCheck={false}
              className="min-h-[120px] max-h-[180px] resize-none font-mono text-[13px] pr-20"
            />
            <div className="absolute right-2 top-2 flex gap-1">
              <IconButton tooltip="Paste from clipboard" className="size-7" onClick={paste}>
                <Clipboard className="size-3.5" />
              </IconButton>
              {(text || items.length > 0) && (
                <IconButton tooltip="Clear" className="size-7" onClick={clearAll}>
                  <X className="size-3.5" />
                </IconButton>
              )}
            </div>
          </div>

          <div className="mt-3 flex items-center justify-between text-xs text-[var(--muted)]">
            <UrlValidityStatus
              validation={validation}
              hasInput={text.trim().length > 0}
              recursive={recursive}
              crossHostHosts={recursiveHosts}
            />
            <button type="button" onClick={loadSample} className="inline-flex items-center gap-1 text-[var(--muted)] hover:text-[var(--navy)]">
              <Wand2 className="size-3" /> Load example
            </button>
          </div>

          </div>
        </fieldset>

        <div className="mt-auto pt-6 space-y-3">
          <Label className="text-sm font-medium text-[var(--ink-2)]">Format</Label>
          <ToggleGroup
            type="single"
            value={format}
            onValueChange={(v) => v && setFormat(v)}
            variant="outline"
            spacing="default"
            disabled={isRunning}
            className="grid grid-cols-2 gap-3"
          >
            <ToggleGroupItem value="markdown" className="!h-9 w-full rounded-md px-4 text-sm"><FileText className="size-4" /> Markdown</ToggleGroupItem>
            <ToggleGroupItem value="pdf" className="!h-9 w-full rounded-md px-4 text-sm"><FileType className="size-4" /> PDF</ToggleGroupItem>
          </ToggleGroup>
          {!isRunning ? (
            <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
              <AlertDialogTrigger asChild>
                <Button
                  disabled={!canSubmit}
                  className="!h-11 w-full text-base !font-medium"
                >
                  <Play className="size-4 fill-current" /> {ctaLabel}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent className="!max-w-md">
                <AlertDialogHeader>
                  <div className="flex items-center justify-between gap-3">
                    <AlertDialogTitle className="!text-lg">{dialogTitle}</AlertDialogTitle>
                    <Badge className="bg-[var(--green-soft)] text-[var(--green-2)] font-mono">
                      .{format === "pdf" ? "PDF" : "MD"}
                    </Badge>
                  </div>
                  <AlertDialogDescription className="!text-sm">
                    {recursive
                      ? `Crawl ${domainFor(validUrls[0]) || "the starting URL"} → one merged ${formatLabel} file.`
                      : `${validUrls.length} webpage${validUrls.length === 1 ? "" : "s"} → one merged ${formatLabel} file.`}
                  </AlertDialogDescription>
                </AlertDialogHeader>

                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="dlg-name" className="text-sm font-medium">Name</Label>
                    <Input id="dlg-name" placeholder="e.g. Compliance research Q2" value={name} onChange={(e) => setName(e.target.value)} className="h-9" autoFocus={false} />
                    <p className="text-xs text-[var(--muted)]">Optional. Auto-named if blank.</p>
                  </div>
                  {recursive && (
                    <div className="flex items-center justify-between gap-3">
                      <Label htmlFor="dlg-maxpages" className="text-sm font-normal">Max pages</Label>
                      <Input
                        id="dlg-maxpages"
                        type="number"
                        min="1"
                        max="1000"
                        value={maxPages}
                        onChange={(e) => setMaxPages(clampInt(e.target.value, 1, 1000))}
                        className="h-8 w-24 text-right font-mono"
                      />
                    </div>
                  )}
                  {format === "pdf" && (
                    <>
                      <div className="flex items-center justify-between">
                        <Label htmlFor="dlg-images" className="text-sm font-normal">Include images</Label>
                        <Switch id="dlg-images" checked={includeImages} onCheckedChange={setIncludeImages} />
                      </div>
                      <div className="flex items-center justify-between">
                        <Label className="text-sm font-normal">Page size</Label>
                        <ToggleGroup type="single" value={pageSize} onValueChange={(v) => v && setPageSize(v)} variant="outline" size="sm">
                          <ToggleGroupItem value="A4">A4</ToggleGroupItem>
                          <ToggleGroupItem value="Letter">Letter</ToggleGroupItem>
                        </ToggleGroup>
                      </div>
                    </>
                  )}
                </div>

                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={start} className="!font-medium">
                    <Play className="size-4 fill-current" /> Scrape and save as {formatLabel}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ) : (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" className="!h-11 w-full text-base !font-medium !text-[var(--ink-2)] hover:!text-[var(--danger)] hover:!border-[var(--danger)]/40">
                  <Square className="size-4 fill-current" /> Stop
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent className="!max-w-sm">
                <AlertDialogHeader>
                  <AlertDialogTitle>Cancel saving?</AlertDialogTitle>
                  <AlertDialogDescription>
                    {stats.queued + stats.working > 0
                      ? `${stats.queued + stats.working} webpage${stats.queued + stats.working === 1 ? "" : "s"} won't be saved. The ${stats.done} already saved are still downloadable.`
                      : `${stats.done} saved file${stats.done === 1 ? "" : "s"} are still downloadable.`}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Keep saving</AlertDialogCancel>
                  <AlertDialogAction onClick={stop} variant="destructive" className="!font-medium">
                    <Square className="size-4 fill-current" /> Cancel job
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </Card>

      <Card className="flex flex-col p-0 min-h-[500px]">
        {showOutput ? (
          <OutputBody
            job={{ items, stats, progress, format, isRunning }}
            phase={phase}
            headerLabel={headerLabel}
            onRetry={retryItem}
            onDownloadOne={downloadOne}
            onDownloadMerged={downloadMerged}
            onDownloadZip={downloadZip}
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center px-10 py-16 text-center">
            <FileText className="mb-3 size-8 text-[var(--green-2)] opacity-60" />
            <p className="max-w-[28ch] text-sm text-[var(--muted)]">
              Output appears here.
            </p>
          </div>
        )}
      </Card>
      </div>
    </>
  );
}

function OutputBody({ job, phase, headerLabel, onRetry, onDownloadOne, onDownloadMerged, onDownloadZip }) {
  const { items, stats, progress, format, isRunning } = job;
  const canDownload = stats.done >= 1;
  return (
    <>
      <div className="flex items-center justify-between gap-3 border-b border-[var(--line)] px-6 py-4">
        <div className="text-sm font-medium text-[var(--ink)]">{headerLabel}</div>
        <div className="flex items-center gap-2">
          {onDownloadZip && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  onClick={onDownloadZip}
                  disabled={!canDownload}
                  className="h-10 px-3 font-medium"
                  aria-label="Download as ZIP"
                >
                  <FileArchive className="size-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>ZIP of separate files ({stats.done})</TooltipContent>
            </Tooltip>
          )}
          {phase !== "nothing" && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button onClick={onDownloadMerged} disabled={!canDownload} className="h-10 px-5 font-medium">
                  <Download className="size-4" />
                  {isRunning && stats.done >= 1 ? `Download partial · ${stats.done}` : "Download"}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {canDownload
                  ? `One merged ${format === "pdf" ? "PDF" : "Markdown"} file (${stats.done} webpage${stats.done === 1 ? "" : "s"})`
                  : "Nothing finished yet"}
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>

      <div className="space-y-2 border-b border-[var(--line)] px-6 py-3">
        <Progress value={progress} className="h-1.5" />
        <div className="flex flex-wrap gap-3 text-xs text-[var(--muted)]">
          {stats.queued > 0 && <span>{stats.queued} queued</span>}
          {stats.working > 0 && <span className="flex items-center gap-1"><Spinner size="xs" /> {stats.working} saving</span>}
          {stats.done > 0 && <span className="text-[var(--green-2)]">{stats.done} saved</span>}
          {stats.error > 0 && <span className="text-[var(--danger)]">{stats.error} failed</span>}
          {stats.cancelled > 0 && <span>{stats.cancelled} cancelled</span>}
        </div>
      </div>

      <div className="min-h-0 flex-1" style={{ height: 600 }}>
        <List
          rowCount={items.length}
          rowHeight={64}
          rowComponent={VirtualItemRow}
          rowProps={{ items, format, onRetry, onDownloadOne }}
        />
      </div>
    </>
  );
}

function VirtualItemRow({ index, style, items, format, onRetry, onDownloadOne }) {
  const item = items[index];
  if (!item) return null;
  return <ItemRow style={style} item={item} format={format} onRetry={onRetry} onDownload={onDownloadOne} />;
}

const ItemRow = memo(function ItemRow({ item, format, onRetry, onDownload, style }) {
  const cancelled = isCancelled(item);
  const domain = item.domain || domainFor(item.url);
  const ext = format === "pdf" ? ".pdf" : ".md";
  const fname = item.filename || `${(item.title || "untitled").toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-").slice(0, 40)}${ext}`;

  let badge;
  if (cancelled) badge = <Badge variant="secondary">Cancelled</Badge>;
  else if (item.status === "done") badge = <Badge className="bg-[var(--green-soft)] text-[var(--green-2)]">Saved</Badge>;
  else if (item.status === "error") badge = <Badge variant="destructive">Failed</Badge>;
  else if (item.status === "working") badge = <Badge variant="outline" className="gap-1"><Spinner size="xs" /> Saving</Badge>;
  else badge = <Badge variant="outline">Queued</Badge>;

  const handleRetry = useCallback(() => onRetry(item.id), [onRetry, item.id]);
  const handleDownload = useCallback(() => onDownload(item), [onDownload, item]);

  const spinnerLabel = item.status === "working" ? "Saving…" : "Queued";

  return (
    <div style={style} className="flex items-center gap-3 border-b border-[var(--line)] px-6">
      <img src={faviconFor(item.url)} alt="" className="size-5 rounded-sm" onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-[var(--navy)]" title={item.title}>{item.title || domain}</div>
        <div className="truncate font-mono text-[11px] text-[var(--muted)]" title={item.url}>
          {domain} · {fname}
          {item.error && !cancelled && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="ml-2 cursor-help text-[var(--danger)] underline decoration-dotted underline-offset-2">· {item.error}</span>
              </TooltipTrigger>
              <TooltipContent className="max-w-sm break-words">{item.error}</TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>
      {badge}
      <div className="w-16 text-right font-mono text-[11px] text-[var(--muted)]">{fmtSize(item.size)}</div>
      <div className="flex items-center gap-1">
        {item.status === "done" && (
          <IconButton tooltip="Download this file" onClick={handleDownload}><Download className="size-4" /></IconButton>
        )}
        {item.status === "error" && !cancelled && (
          <IconButton tooltip="Retry" onClick={handleRetry}><RotateCcw className="size-4" /></IconButton>
        )}
        {(item.status === "queued" || item.status === "working") && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="grid size-9 place-items-center text-[var(--muted)]">
                <Spinner />
              </span>
            </TooltipTrigger>
            <TooltipContent>{spinnerLabel}</TooltipContent>
          </Tooltip>
        )}
      </div>
    </div>
  );
});

function FormatBadge({ fmt }) {
  const isPdf = fmt === "pdf";
  return (
    <Badge
      variant="outline"
      className={`shrink-0 font-mono ${isPdf ? "border-[var(--green)]/40 bg-[var(--green-soft)] text-[var(--green-2)]" : "text-[var(--muted)]"}`}
    >
      {isPdf ? "PDF" : "MD"}
    </Badge>
  );
}

function DeleteMenuItem({ name, onConfirm }) {
  const [open, setOpen] = useState(false);
  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <DropdownMenuItem
          variant="destructive"
          onSelect={(e) => { e.preventDefault(); setOpen(true); }}
        >
          <Trash2 className="size-4" /> Delete
        </DropdownMenuItem>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this save?</AlertDialogTitle>
          <AlertDialogDescription>&quot;{name}&quot; and its files will be deleted. This can&apos;t be undone.</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={() => { setOpen(false); onConfirm(); }}>Delete</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function Library({ collections, onDelete, onRename, onMissing, onGoNew }) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState(null);

  const indexed = useMemo(() => collections.map((c) => {
    const urls = c.urls || [];
    const haystack = [
      (c.name || "").toLowerCase(),
      ...urls.map((u) => u.toLowerCase()),
      ...urls.map((u) => domainFor(u).toLowerCase()),
    ].join("\n");
    return { c, haystack };
  }), [collections]);

  const filtered = useMemo(() => {
    if (!query) return collections;
    const q = query.toLowerCase();
    return indexed.filter((x) => x.haystack.includes(q)).map((x) => x.c);
  }, [collections, indexed, query]);

  const selected = selectedId ? collections.find((c) => c.id === selectedId) : null;

  if (selected) {
    return (
      <JobDetailView
        collection={selected}
        onBack={() => setSelectedId(null)}
        onDelete={async (id) => { await onDelete(id); setSelectedId(null); }}
        onRename={onRename}
        onMissing={(id) => {
          onMissing?.(id);
          setSelectedId(null);
          toast.info("That collection no longer exists.");
        }}
      />
    );
  }

  return (
    <>
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
        <h2 className="text-2xl font-medium tracking-tight text-[var(--navy)]">My Collection</h2>
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-[var(--muted)]" />
            <Input
              placeholder="Search name or URL"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-60 pl-8"
            />
          </div>
          <Button onClick={onGoNew} className="h-10 px-4 font-medium">
            <Plus className="size-4" /> New save
          </Button>
        </div>
      </div>

      {filtered.length === 0 ? (
        <Card className="flex flex-col items-center justify-center p-16 text-center">
          <div className="text-base font-medium text-[var(--ink)]">{query ? "No matches" : "Nothing saved yet"}</div>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {query ? "Try a different term." : "Save your first webpage from the Scraper tab."}
          </p>
          {!query && (
            <Button onClick={onGoNew} className="mt-5 h-10 px-5 font-medium">
              <Plus className="size-4" /> New save
            </Button>
          )}
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((c) => (
            <CollectionCard
              key={c.id}
              collection={c}
              onOpen={() => setSelectedId(c.id)}
              onDelete={onDelete}
              onRename={onRename}
            />
          ))}
        </div>
      )}
    </>
  );
}

function JobDetailView({ collection, onBack, onDelete, onRename, onMissing }) {
  const {
    items, isRunning, format, name, stats, progress,
    attach, retryItem, downloadOne, downloadMerged, downloadZip, reset,
  } = useConversionJob();

  useEffect(() => {
    let cancelled = false;
    attach(collection.id).then((res) => {
      if (cancelled || res.ok) return;
      if (res.status === 404 && onMissing) onMissing(collection.id);
      else onBack();
    });
    return () => { cancelled = true; reset(); };
  }, [collection.id, attach, reset, onBack, onMissing]);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(collection.name || "");

  async function commitRename() {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === collection.name) {
      setEditing(false);
      return;
    }
    setEditing(false);
    const ok = await onRename?.(collection.id, trimmed);
    if (ok === false) setEditing(true);
  }

  const phase = derivePhase({ isRunning, items, stats });
  const headerLabel = deriveHeaderLabel(phase, stats, items, {
    idle: "Loading…",
    nothing: stats.cancelled > 0 ? "Stopped before saving anything" : "All pages failed",
  });

  const displayName = collection.name || name || "Untitled";
  const fmt = format || collection.format;

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Button variant="ghost" onClick={onBack} className="h-9 px-2 text-sm font-medium text-[var(--muted)] hover:text-[var(--navy)]">
            <ArrowLeft className="size-4" /> My Collection
          </Button>
          <Separator orientation="vertical" className="!h-6" />
          {editing ? (
            <Input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commitRename}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitRename();
                if (e.key === "Escape") { setDraft(displayName); setEditing(false); }
              }}
              className="h-9 max-w-sm text-xl font-medium text-[var(--navy)]"
            />
          ) : (
            <h2 className="truncate text-xl font-medium tracking-tight text-[var(--navy)]" title={displayName}>
              {displayName}
            </h2>
          )}
          <FormatBadge fmt={fmt} />
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="More actions">
              <MoreHorizontal className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => { setDraft(displayName); setEditing(true); }}>
              <Pencil className="size-4" /> Rename
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DeleteMenuItem name={displayName} onConfirm={() => onDelete(collection.id)} />
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Card className="flex flex-col p-0 min-h-[500px]">
        <OutputBody
          job={{ items, stats, progress, format: fmt, isRunning }}
          phase={phase}
          headerLabel={headerLabel}
          onRetry={retryItem}
          onDownloadOne={downloadOne}
          onDownloadMerged={downloadMerged}
          onDownloadZip={downloadZip}
        />
      </Card>
    </>
  );
}

function CollectionCard({ collection, onOpen, onDelete, onRename }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(collection.name || "");
  const suppressNextClickRef = useRef(false);

  async function commit() {
    const trimmed = draft.trim();
    suppressNextClickRef.current = true;
    if (!trimmed || trimmed === collection.name) {
      setEditing(false);
      return;
    }
    setEditing(false);
    const ok = await onRename?.(collection.id, trimmed);
    if (ok === false) setEditing(true);
  }

  function handleCardClick(e) {
    if (editing) return;
    if (suppressNextClickRef.current) {
      suppressNextClickRef.current = false;
      return;
    }
    if (e.target.closest("button, [role='menuitem'], input, a")) return;
    onOpen();
  }

  function handleCardKey(e) {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onOpen();
    }
  }

  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={handleCardClick}
      onKeyDown={handleCardKey}
      className="group flex cursor-pointer flex-col gap-3 p-5 transition-colors hover:border-[var(--ink-2)] hover:bg-[var(--canvas-2)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--green)]/60"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {editing ? (
            <Input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commit}
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === "Enter") commit();
                if (e.key === "Escape") { setDraft(collection.name || ""); setEditing(false); }
              }}
              className="h-8 text-base font-medium text-[var(--navy)]"
            />
          ) : (
            <h3 className="truncate text-base font-medium text-[var(--navy)]" title={collection.name || "Untitled"}>
              {collection.name || "Untitled"}
            </h3>
          )}
          <div className="mt-1 text-xs text-[var(--muted)]">
            {collection.done} file{collection.done !== 1 ? "s" : ""}
            {collection.errors > 0 && <span className="text-[var(--danger)]"> · {collection.errors} failed</span>}
            <span className="mx-1.5 opacity-50">·</span>
            {fmtTimeAgo(collection.createdAt)}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <FormatBadge fmt={collection.format} />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="More actions"
                className="size-7 text-[var(--muted)] hover:text-[var(--navy)]"
                onClick={(e) => e.stopPropagation()}
              >
                <MoreHorizontal className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
              <DropdownMenuItem onSelect={() => { setDraft(collection.name || ""); setEditing(true); }}>
                <Pencil className="size-4" /> Rename
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DeleteMenuItem name={collection.name || "Untitled"} onConfirm={() => onDelete(collection.id)} />
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      <div className="mt-auto flex items-center justify-end pt-1">
        <span className="text-xs font-medium text-[var(--green-2)] transition-colors group-hover:text-[var(--green)]">
          Open <span aria-hidden>→</span>
        </span>
      </div>
    </Card>
  );
}
