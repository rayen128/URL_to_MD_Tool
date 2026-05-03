const { useState: useStateOP } = React;

function OutputPanel({ items, stats, progress, isRunning, isDone, isCrawling, name, format, onRetry, onRemove, onDownloadOne, onDownloadAll }) {
  const { fmtSize } = window.ProtinusData;
  if (!items.length) return <EmptyOutput />;

  const formatLabel = format === "pdf" ? "PDF" : "Markdown";
  const extLabel = format === "pdf" ? ".pdf" : ".md";
  const doneCount = stats.done;

  return (
    <>
      <div className="output-head">
        <h2>
          <Icon.Folder size={16} />
          <span className="collection-name">{name || "Untitled collection"}</span>
          <span className={`chip ${format === "pdf" ? "fmt-pdf" : "fmt-md"}`} style={{marginLeft:4}}>
            {formatLabel}
          </span>
        </h2>
        <div className="output-actions">
          <button
            className="btn btn-primary"
            disabled={doneCount === 0 || isRunning}
            onClick={onDownloadAll}>
            <Icon.Archive size={14}/>
            Download all ({doneCount})
          </button>
        </div>
      </div>

      <div className="progress-wrap">
        <div className="progress-row">
          <strong style={{fontSize:13, color:"var(--ink)"}}>
            {isRunning
              ? `${isCrawling ? "Crawling" : "Converting"}… ${stats.done + stats.error} / ${items.length}`
              : isDone
                ? stats.error > 0
                  ? `Finished with ${stats.error} error${stats.error>1?"s":""}`
                  : "Conversion complete"
                : "Ready"}
          </strong>
          <div className="progress-counts">
            {stats.queued > 0 && <span className="pc pc-queued"><span className="pc-dot"/> {stats.queued} queued</span>}
            {stats.working > 0 && <span className="pc pc-working"><span className="pc-dot"/> {stats.working} working</span>}
            {stats.done > 0 && <span className="pc pc-done"><span className="pc-dot"/> {stats.done} done</span>}
            {stats.error > 0 && <span className="pc pc-error"><span className="pc-dot"/> {stats.error} failed</span>}
          </div>
        </div>
        <div className="progress-bar">
          <div className="fill" style={{width: `${progress}%`}}/>
        </div>
      </div>

      <div className="list">
        {items.map(item => (
          <ListRow
            key={item.id}
            item={item}
            extLabel={extLabel}
            onRetry={() => onRetry(item.id)}
            onRemove={() => onRemove(item.id)}
            onDownload={() => onDownloadOne(item)}
          />
        ))}
      </div>
    </>
  );
}

function ListRow({ item, extLabel, onRetry, onRemove, onDownload }) {
  const { fmtSize } = window.ProtinusData;
  const [imgError, setImgError] = useStateOP(false);
  const initial = item.domain.replace(/\..*/, "").slice(0, 1).toUpperCase() || "?";
  const filename = item.title.replace(/[^\w\s-]/g, "").replace(/\s+/g, "-").toLowerCase().slice(0, 40) + extLabel;

  return (
    <div className="list-row">
      <div className="favicon">
        {!imgError && item.favicon
          ? <img src={item.favicon} alt="" onError={() => setImgError(true)}/>
          : <span>{initial}</span>}
      </div>
      <div className="row-main">
        <div className="row-title" title={item.title}>{item.title}</div>
        <div className="row-sub" title={item.url}>
          <span className="domain">{item.domain}</span>
          <span className="sep">·</span>
          <span>{filename}</span>
          {item.error && <>
            <span className="sep">·</span>
            <span style={{color:"var(--danger)"}}>{item.error}</span>
          </>}
        </div>
      </div>
      <StatusChip status={item.status}/>
      <div className="size">{item.size != null ? fmtSize(item.size) : "—"}</div>
      <div className="row-action">
        {item.status === "done" && (
          <button className="icon-btn" title="Download" onClick={onDownload}>
            <Icon.Download size={15}/>
          </button>
        )}
        {item.status === "error" && (
          <button className="icon-btn" title="Retry" onClick={onRetry}>
            <Icon.Refresh size={15}/>
          </button>
        )}
        {(item.status === "queued" || item.status === "working") && (
          <button className="icon-btn" disabled title="In progress">
            <Icon.Clock size={15}/>
          </button>
        )}
        <button className="icon-btn danger" title="Remove" onClick={onRemove}>
          <Icon.Trash size={14}/>
        </button>
      </div>
    </div>
  );
}

function StatusChip({ status }) {
  const map = {
    queued:  { label: "Queued",  cls: "chip-queued" },
    working: { label: "Working", cls: "chip-working" },
    done:    { label: "Done",    cls: "chip-done" },
    error:   { label: "Failed",  cls: "chip-error" },
  };
  const m = map[status];
  return <span className={`chip ${m.cls}`}><span className="dot"/>{m.label}</span>;
}

function EmptyOutput() {
  return (
    <div className="empty">
      <div className="empty-ill">
        <svg viewBox="0 0 180 120" width="180" height="120" aria-hidden="true">
          {/* dot grid echo */}
          {Array.from({length: 10}).flatMap((_, y) =>
            Array.from({length: 16}).map((_, x) => (
              <circle key={`${x}-${y}`} cx={x * 11 + 6} cy={y * 11 + 6} r="1.2" fill="#D6D1C3" opacity={0.5 + (Math.sin(x * 0.4 + y * 0.3) * 0.25)}/>
            ))
          )}
          {/* folder */}
          <g transform="translate(56 36)">
            <rect x="0" y="6" width="68" height="48" rx="6" fill="#F1EEE6" stroke="#D6D1C3"/>
            <path d="M0 10c0-3 2-4 4-4h14l4 6h44c3 0 6 2 6 6v4H0z" fill="#0E1E3F"/>
            <rect x="6" y="22" width="56" height="28" rx="4" fill="#fff" stroke="#D6D1C3"/>
            <rect x="10" y="28" width="34" height="3" rx="1.5" fill="#E5E1D8"/>
            <rect x="10" y="34" width="26" height="3" rx="1.5" fill="#E5E1D8"/>
            <rect x="10" y="40" width="30" height="3" rx="1.5" fill="#1A7F3C" opacity="0.5"/>
          </g>
        </svg>
      </div>
      <h3>No collection yet</h3>
      <p>Paste a few URLs on the left, pick a format, and hit <strong>Convert</strong>. Your collection will appear here.</p>
    </div>
  );
}

window.OutputPanel = OutputPanel;
