const { useState: useStateC } = React;

function Collections({ collections, onOpen, onDelete, toast }) {
  const { fmtTimeAgo, niceDate, domainFor, faviconFor } = window.ProtinusData;
  const [query, setQuery] = useStateC("");
  const [sort, setSort] = useStateC("recent");

  const filtered = collections
    .filter(c => !query || c.name.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => {
      if (sort === "recent") return b.createdAt - a.createdAt;
      if (sort === "name") return a.name.localeCompare(b.name);
      if (sort === "size") return b.urls.length - a.urls.length;
      return 0;
    });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>My Collections</h1>
          <p>Every collection you've converted, ready to re-download or reopen.</p>
        </div>
        <div style={{display:"flex", gap:10, alignItems:"center"}}>
          <div style={{position:"relative"}}>
            <Icon.Search size={14} style={{position:"absolute", left:10, top:"50%", transform:"translateY(-50%)", color:"var(--muted)"}}/>
            <input
              className="text-input"
              placeholder="Search collections"
              value={query}
              onChange={e => setQuery(e.target.value)}
              style={{paddingLeft:30, width:240}}
            />
          </div>
          <div className="mini-seg">
            {[["recent","Recent"],["name","Name"],["size","Size"]].map(([k,l]) => (
              <button key={k} className={sort === k ? "on" : ""} onClick={() => setSort(k)}>{l}</button>
            ))}
          </div>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="card" style={{padding:"64px 40px", textAlign:"center"}}>
          <div style={{fontSize:15, fontWeight:600, color:"var(--ink)", marginBottom:6}}>No collections found</div>
          <div style={{fontSize:13, color:"var(--muted)"}}>
            {query ? "Try a different search term." : "Create your first collection from the Converter tab."}
          </div>
        </div>
      ) : (
        <div className="collections-grid">
          {filtered.map(c => (
            <CollectionCard
              key={c.id}
              collection={c}
              onOpen={() => onOpen(c)}
              onDelete={() => onDelete(c.id)}
              toast={toast}
            />
          ))}
        </div>
      )}
    </>
  );
}

function CollectionCard({ collection, onOpen, onDelete, toast }) {
  const { fmtTimeAgo, domainFor, faviconFor, niceDate } = window.ProtinusData;
  const urls = collection.urls;
  const shown = urls.slice(0, 4);
  const extra = Math.max(0, urls.length - shown.length);
  const isPdf = collection.format === "pdf";

  return (
    <div className="coll-card" onClick={onOpen}>
      <div className="coll-card-head">
        <div style={{minWidth:0, flex:1}}>
          <h3 style={{overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}}>{collection.name}</h3>
          <div className="meta">
            {collection.done} file{collection.done!==1?"s":""}
            {collection.errors > 0 && <span style={{color:"var(--danger)"}}> · {collection.errors} failed</span>}
            <span style={{opacity:0.5, margin:"0 6px"}}>·</span>
            {fmtTimeAgo(collection.createdAt)}
          </div>
        </div>
        <span className={`fmt-badge ${isPdf ? "fmt-pdf" : "fmt-md"}`}>
          {isPdf ? "PDF" : "MD"}
        </span>
      </div>

      <div className="stack">
        {shown.map((u, i) => {
          const d = domainFor(u);
          return <Favi key={i} url={u} domain={d}/>;
        })}
        {extra > 0 && <span className="more">+{extra} more</span>}
      </div>

      <div className="coll-card-foot" onClick={e => e.stopPropagation()}>
        <button className="btn btn-primary" onClick={() => { window.location.href = `/api/jobs/${collection.id}/zip`; }}>
          <Icon.Download size={13}/> Download
        </button>
        <button className="btn btn-ghost" title="Delete" onClick={onDelete}
          style={{flex:"0 0 auto", width:36, padding:0}}>
          <Icon.Trash size={13}/>
        </button>
      </div>
    </div>
  );
}

function Favi({ url, domain }) {
  const [err, setErr] = useStateC(false);
  const { faviconFor } = window.ProtinusData;
  const src = faviconFor(url);
  return (
    <span className="fav" title={domain}>
      {!err && src ? <img src={src} alt="" onError={() => setErr(true)}/> : (domain[0] || "?").toUpperCase()}
    </span>
  );
}

window.Collections = Collections;
