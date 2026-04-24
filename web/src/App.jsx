const { useState: useStateA, useEffect: useEffectA, useRef: useRefA } = React;

function TweaksPanel({ tweaks, setTweaks, onClose }) {
  const accents = [
    { id: "green", color: "#1A7F3C", label: "Protinus green" },
    { id: "navy", color: "#0E1E3F", label: "Deep navy" },
    { id: "orange", color: "#F08A4B", label: "Warm orange" },
    { id: "indigo", color: "#4F46E5", label: "Indigo" },
  ];
  return (
    <div className="tweaks-panel">
      <div className="tweaks-head">
        <span>⚙ Tweaks</span>
        <button className="icon-btn" style={{color:"#fff", width:24, height:24}} onClick={onClose}>
          <Icon.X size={14}/>
        </button>
      </div>
      <div className="tweaks-body">
        <div className="opt-row">
          <div className="opt-label"><span>Accent color</span></div>
          <div className="color-chips">
            {accents.map(a => (
              <button key={a.id}
                className={`color-chip ${tweaks.accent === a.id ? "on" : ""}`}
                title={a.label}
                style={{background: a.color}}
                onClick={() => setTweaks(t => ({...t, accent: a.id}))}/>
            ))}
          </div>
        </div>
        <div className="opt-row">
          <div className="opt-label"><span>Compact density</span><small>Tighter rows & padding</small></div>
          <div className={`switch ${tweaks.dense ? "on" : ""}`} onClick={() => setTweaks(t => ({...t, dense: !t.dense}))}/>
        </div>
        <div className="opt-row">
          <div className="opt-label"><span>Dark mode</span></div>
          <div className={`switch ${tweaks.dark ? "on" : ""}`} onClick={() => setTweaks(t => ({...t, dark: !t.dark}))}/>
        </div>
      </div>
    </div>
  );
}

function App() {
  const [tab, setTab] = useStateA("converter");
  const [collections, setCollections] = useStateA([]);
  const [toastMsg, setToastMsg] = useStateA(null);
  const [tweakOn, setTweakOn] = useStateA(false);
  const [tweaks, setTweaks] = useStateA(
    /*EDITMODE-BEGIN*/{
      "accent": "green",
      "dense": false,
      "dark": false
    }/*EDITMODE-END*/
  );

  const [settings, setSettings] = useStateA({
    images: true,
    reader: true,
    pageSize: "A4",
    filenamePattern: "{date}-{domain}-{title}",
  });

  // Apply accent & density to body
  useEffectA(() => {
    const root = document.documentElement;
    const map = {
      green: ["#1A7F3C", "#156931", "#E6F2EA"],
      navy: ["#0E1E3F", "#132756", "#E1E6F1"],
      orange: ["#F08A4B", "#E77A37", "#FEF0E3"],
      indigo: ["#4F46E5", "#3F38BD", "#EAE8FB"],
    };
    const [a, a2, soft] = map[tweaks.accent] || map.green;
    root.style.setProperty("--green", a);
    root.style.setProperty("--green-2", a2);
    root.style.setProperty("--green-soft", soft);

    document.body.classList.toggle("dense", tweaks.dense);
    document.body.classList.toggle("dark", tweaks.dark);
  }, [tweaks]);

  useEffectA(() => {
    fetch('/api/collections')
      .then(r => r.json())
      .then(data => setCollections(data))
      .catch(() => {});
  }, []);

  // Tweaks host protocol
  useEffectA(() => {
    const handler = (e) => {
      if (e.data?.type === "__activate_edit_mode") setTweakOn(true);
      if (e.data?.type === "__deactivate_edit_mode") setTweakOn(false);
    };
    window.addEventListener("message", handler);
    try { window.parent.postMessage({type: "__edit_mode_available"}, "*"); } catch {}
    return () => window.removeEventListener("message", handler);
  }, []);

  // Persist tweak changes
  useEffectA(() => {
    try { window.parent.postMessage({type:"__edit_mode_set_keys", edits: tweaks}, "*"); } catch {}
  }, [tweaks]);

  const toast = (msg) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 2400);
  };

  const addCollection = (payload) => {
    setCollections(cs => [{ createdAt: Date.now(), ...payload }, ...cs]);
  };

  const deleteCollection = (id) => {
    fetch(`/api/collections/${id}`, { method: 'DELETE' }).catch(() => {});
    setCollections(cs => cs.filter(c => c.id !== id));
    toast("Collection deleted");
  };

  const openCollection = (c) => {
    toast(`Opening "${c.name}"…`);
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <LogoMark/>
            <span className="logo-text">Protinus<em>ETA</em></span>
          </div>
          <span className="product-pill">URL Converter</span>

          <nav className="tabs" role="tablist">
            <button
              className={tab === "converter" ? "active" : ""}
              onClick={() => setTab("converter")}
              role="tab"
              data-screen-label="Converter">
              Converter
            </button>
            <button
              className={tab === "collections" ? "active" : ""}
              onClick={() => setTab("collections")}
              role="tab"
              data-screen-label="My Collections">
              My Collections
              <span className="count">{collections.length}</span>
            </button>
          </nav>

          <div className="topbar-spacer"/>
          <div className="top-user">
            <span>Tessa van der Berg</span>
            <div className="avatar">TB</div>
          </div>
        </div>
      </header>

      <main data-screen-label={tab === "converter" ? "Converter" : "Collections"}>
        {tab === "converter" ? (
          <Converter
            onCreateCollection={addCollection}
            toast={toast}
            settings={settings}
            setSettings={setSettings}
          />
        ) : (
          <Collections
            collections={collections}
            onOpen={openCollection}
            onDelete={deleteCollection}
            toast={toast}
          />
        )}
      </main>

      {toastMsg && <div className="toast"><Icon.Check size={14}/>{toastMsg}</div>}
      {tweakOn && <TweaksPanel tweaks={tweaks} setTweaks={setTweaks} onClose={() => setTweakOn(false)}/>}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
