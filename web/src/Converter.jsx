const { useState, useEffect, useRef, useMemo, useCallback } = React;

function Converter({ collection, onCreateCollection, toast, settings, setSettings }) {
  const [text, setText] = useState("");
  const [format, setFormat] = useState("pdf"); // 'pdf' | 'markdown'
  const [name, setName] = useState("");
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [items, setItems] = useState([]); // {id, url, title, domain, status, size, error}
  const [isRunning, setIsRunning] = useState(false);
  const [isDone, setIsDone] = useState(false);
  const [jobId, setJobId] = useState(null);
  const esRef = useRef(null);
  const { titleFor, domainFor, faviconFor, fmtSize } = window.ProtinusData;

  // Parse textarea into valid URL lines (ignore empty; also strip duplicates)
  const parsedUrls = useMemo(() => {
    const seen = new Set();
    return text.split(/\r?\n/).map(l => l.trim()).filter(l => {
      if (!l) return false;
      if (seen.has(l)) return false;
      seen.add(l);
      return true;
    });
  }, [text]);

  const validUrls = useMemo(() =>
    parsedUrls.filter(u => { try { new URL(u); return true; } catch { return false; } })
  , [parsedUrls]);

  const invalidCount = parsedUrls.length - validUrls.length;

  const canConvert = validUrls.length > 0 && !isRunning;

  const stats = useMemo(() => {
    const s = { queued: 0, working: 0, done: 0, error: 0 };
    items.forEach(i => s[i.status]++);
    return s;
  }, [items]);

  const progress = items.length
    ? Math.round(((stats.done + stats.error) / items.length) * 100)
    : 0;

  // ===== Actions =====
  const handlePaste = async () => {
    try {
      const t = await navigator.clipboard.readText();
      setText(prev => prev ? prev.replace(/\s*$/, "") + "\n" + t : t);
      toast("Pasted from clipboard");
    } catch {
      toast("Clipboard not available");
    }
  };

  const loadSample = () => {
    const sample = [
      "https://www.protinus.nl/over-ons",
      "https://www.rijksoverheid.nl/onderwerpen/europese-aanbestedingen",
      "https://www.computable.nl/artikel/nieuws/cloud",
      "https://www.tweakers.net/reviews/enterprise-hardware",
      "https://fd.nl/bedrijfsleven/tech",
      "https://www.pianoo.nl/nl/regelgeving/aanbestedingswet",
      "https://broken.example.invalid/page",
    ].join("\n");
    setText(sample);
    if (!name) setName("Research pack " + new Date().toLocaleDateString("en-GB", { day:"numeric", month:"short"}));
  };

  const clearAll = () => {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    setText("");
    setItems([]);
    setIsDone(false);
    setJobId(null);
  };

  const startConversion = async () => {
    setIsRunning(true);
    setIsDone(false);
    try {
      const resp = await fetch('/api/convert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          urls: validUrls,
          format,
          collection: name || '',
          options: { images: settings.images, reader: settings.reader, pageSize: settings.pageSize },
        }),
      });
      if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
      const { job_id, items: serverItems } = await resp.json();
      setJobId(job_id);
      setItems(serverItems.map(si => ({
        ...si,
        title: titleFor(si.url),
        size: null,
        error: null,
      })));

      if (esRef.current) esRef.current.close();
      const es = new EventSource(`/api/jobs/${job_id}/stream`);
      esRef.current = es;
      es.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === 'status') {
          setItems(curr => curr.map(i =>
            i.id === data.url_id
              ? {
                  ...i,
                  status: data.status,
                  title: data.title || i.title,
                  size: data.size != null ? data.size : i.size,
                  filename: data.filename || i.filename,
                  error: data.error || null,
                }
              : i
          ));
        }
        if (data.type === 'done') {
          setIsRunning(false);
          setIsDone(true);
        }
      };
      es.onerror = () => { setIsRunning(false); };
    } catch (err) {
      setIsRunning(false);
      toast('Conversion failed: ' + err.message);
    }
  };

  const retryOne = async (id) => {
    if (!jobId) return;
    setItems(curr => curr.map(i => i.id === id ? { ...i, status: 'working', error: null } : i));
    setIsRunning(true);
    setIsDone(false);
    if (!esRef.current || esRef.current.readyState === EventSource.CLOSED) {
      const es = new EventSource(`/api/jobs/${jobId}/stream`);
      esRef.current = es;
      es.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.type === 'status') {
          setItems(curr => curr.map(i =>
            i.id === data.url_id
              ? {
                  ...i,
                  status: data.status,
                  title: data.title || i.title,
                  size: data.size != null ? data.size : i.size,
                  filename: data.filename || i.filename,
                  error: data.error || null,
                }
              : i
          ));
        }
        if (data.type === 'done') { setIsRunning(false); setIsDone(true); }
      };
    }
    await fetch(`/api/jobs/${jobId}/retry/${id}`, { method: 'POST' }).catch(() => {});
  };

  const removeItem = (id) => setItems(curr => curr.filter(i => i.id !== id));

  const downloadOne = (item) => {
    if (!jobId) return;
    window.open(`/api/files/${jobId}/${item.id}`, '_blank');
  };

  const downloadAll = () => {
    if (!jobId) return;
    window.location.href = `/api/jobs/${jobId}/zip`;
    onCreateCollection({
      id: jobId,
      name: name || `Untitled — ${new Date().toLocaleDateString('en-GB')}`,
      format,
      createdAt: Date.now(),
      urls: items.map(i => i.url),
      done: items.filter(i => i.status === 'done').length,
      errors: items.filter(i => i.status === 'error').length,
    });
  };

  const cancelRun = async () => {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
    if (jobId) {
      await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' }).catch(() => {});
    }
    setIsRunning(false);
    setItems(curr => curr.map(i =>
      (i.status === 'queued' || i.status === 'working')
        ? { ...i, status: 'error', error: 'Cancelled' }
        : i
    ));
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Convert URLs to a collection</h1>
          <p>Paste a list of links, choose a format, and Protinus will bundle everything into a single downloadable collection.</p>
        </div>
      </div>

      <div className="converter">
        {/* LEFT — input */}
        <div className="card">
          <div className="card-head">
            <h2><span className="step">1</span> Paste URLs</h2>
            <span className="hint">
              {validUrls.length} valid
              {invalidCount > 0 && <span style={{color:"var(--danger)", marginLeft:6}}>· {invalidCount} invalid</span>}
            </span>
          </div>
          <div className="card-body">
            <div className="url-input-wrap">
              <textarea
                className="url-input"
                placeholder={"https://example.com/article-1\nhttps://example.com/article-2\nhttps://example.com/article-3\n\n…one URL per line"}
                value={text}
                onChange={e => setText(e.target.value)}
                spellCheck={false}
              />
              <div className="url-input-footer">
                <span>One URL per line</span>
                <button className="btn btn-subtle pill" onClick={loadSample} style={{padding:"4px 10px", fontSize:12, borderRadius:6}}>
                  <Icon.Sparkles size={12}/> Load sample
                </button>
              </div>
            </div>

            <div className="input-actions">
              <button className="btn btn-ghost" onClick={handlePaste}>
                <Icon.Paste size={14}/> Paste
              </button>
              <button className="btn btn-ghost" onClick={clearAll} disabled={!text && !items.length}>
                <Icon.X size={14}/> Clear
              </button>
            </div>

            {/* Step 2 — format */}
            <div className="field">
              <label className="field-label">Output format</label>
              <div className="segmented">
                <button className={format === "pdf" ? "on" : ""} onClick={() => setFormat("pdf")}>
                  <Icon.FilePdf size={14}/> PDF
                  {format === "pdf" && <span className="chev">.pdf</span>}
                </button>
                <button className={format === "markdown" ? "on" : ""} onClick={() => setFormat("markdown")}>
                  <Icon.FileText size={14}/> Markdown
                  {format === "markdown" && <span className="chev">.md</span>}
                </button>
              </div>
            </div>

            {/* Step 3 — name */}
            <div className="field">
              <label className="field-label">Collection name</label>
              <input
                className="text-input"
                placeholder="e.g. Compliance research — Q2"
                value={name}
                onChange={e => setName(e.target.value)}
              />
            </div>

            {/* Options */}
            <div className="options">
              <button className="options-head" onClick={() => setOptionsOpen(o => !o)}>
                <span style={{display:"flex", alignItems:"center", gap:8}}>
                  <Icon.Settings size={14}/> Options
                </span>
                <span style={{transform: optionsOpen ? "rotate(90deg)" : "none", transition:"transform 150ms"}}>
                  <Icon.ChevronRight size={14}/>
                </span>
              </button>
              {optionsOpen && (
                <div className="options-body">
                  <div className="opt-row">
                    <div className="opt-label">
                      <span>Include images</span>
                      <small>Embeds article images in output</small>
                    </div>
                    <div
                      className={`switch ${settings.images ? "on" : ""}`}
                      onClick={() => setSettings(s => ({...s, images: !s.images}))}
                    />
                  </div>
                  <div className="opt-row">
                    <div className="opt-label">
                      <span>Strip navigation & ads</span>
                      <small>Reader-mode cleanup</small>
                    </div>
                    <div
                      className={`switch ${settings.reader ? "on" : ""}`}
                      onClick={() => setSettings(s => ({...s, reader: !s.reader}))}
                    />
                  </div>
                  {format === "pdf" && (
                    <div className="opt-row">
                      <div className="opt-label">
                        <span>Page size</span>
                      </div>
                      <div className="mini-seg">
                        {["A4", "Letter"].map(p => (
                          <button key={p}
                            className={settings.pageSize === p ? "on" : ""}
                            onClick={() => setSettings(s => ({...s, pageSize: p}))}>{p}</button>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="opt-row">
                    <div className="opt-label">
                      <span>Filename pattern</span>
                      <small>{"{date}"} {"{domain}"} {"{title}"}</small>
                    </div>
                    <input
                      className="mini-input"
                      value={settings.filenamePattern}
                      onChange={e => setSettings(s => ({...s, filenamePattern: e.target.value}))}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* CTA */}
            <div className="cta-row">
              {!isRunning ? (
                <button className="btn btn-primary btn-lg btn-block" disabled={!canConvert} onClick={startConversion}>
                  <Icon.Sparkles size={15}/>
                  {items.length > 0 && isDone ? "Convert again" : `Convert ${validUrls.length || ""} URL${validUrls.length===1?"":"s"}`.trim()}
                </button>
              ) : (
                <button className="btn btn-ghost btn-lg btn-block" onClick={cancelRun}>
                  <Icon.X size={15}/> Cancel
                </button>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT — output */}
        <div className="card output-card">
          <OutputPanel
            items={items}
            stats={stats}
            progress={progress}
            isRunning={isRunning}
            isDone={isDone}
            name={name}
            format={format}
            onRetry={retryOne}
            onRemove={removeItem}
            onDownloadOne={downloadOne}
            onDownloadAll={downloadAll}
          />
        </div>
      </div>
    </>
  );
}

window.Converter = Converter;
