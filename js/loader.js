/* Loading indicator + data loader.
   - Shows a circular progress ring with a live percentage (INTERMODAL-style "Processing data" card).
   - Over http(s) it measures real bytes received; when the page is opened from a file it counts finished files.
   - window.LoadKit is reused by app.js for on-demand loads (national layer, road detail, county lookup). */
(function () {
  "use strict";
  const C = 2 * Math.PI * 26;                      // ring circumference (r = 26)
  const ring = (id) =>
    '<svg viewBox="0 0 64 64" class="ring" aria-hidden="true"><circle cx="32" cy="32" r="26" class="ring-bg"/>' +
    '<circle cx="32" cy="32" r="26" class="ring-fg" id="' + id + '" stroke-dasharray="' + C.toFixed(1) + '" stroke-dashoffset="' + C.toFixed(1) + '"/></svg>';

  // ---------- big centered card (startup, long jobs) ----------
  const big = document.createElement("div");
  big.className = "loader"; big.setAttribute("role", "status"); big.setAttribute("aria-live", "polite");
  big.innerHTML = '<div class="loader-card"><div class="ring-wrap">' + ring("bigRing") + '<b id="bigPct">0%</b></div>' +
    '<div class="loader-txt"><b id="bigLabel">Loading…</b><span id="bigSub">Please wait</span></div></div>';
  // ---------- small pill in the map corner (background jobs) ----------
  const mini = document.createElement("div");
  mini.className = "mini-loader"; mini.hidden = true; mini.setAttribute("role", "status"); mini.setAttribute("aria-live", "polite");
  mini.innerHTML = '<div class="ring-wrap sm">' + ring("miniRing") + '<b id="miniPct">0%</b></div><span id="miniLabel"></span>';

  function setRing(id, pctId, p) {
    p = Math.max(0, Math.min(1, p || 0));
    const el = document.getElementById(id); if (el) el.setAttribute("stroke-dashoffset", (C * (1 - p)).toFixed(1));
    const t = document.getElementById(pctId); if (t) t.textContent = Math.round(p * 100) + "%";
  }
  const Big = {
    show(label, sub) { big.hidden = false; document.getElementById("bigLabel").textContent = label; document.getElementById("bigSub").textContent = sub || "Please wait"; setRing("bigRing", "bigPct", 0); },
    set(p, sub) { setRing("bigRing", "bigPct", p); if (sub) document.getElementById("bigSub").textContent = sub; },
    hide() { big.hidden = true; },
  };
  // several background jobs can run; the pill shows the most recent one
  const jobs = new Map(); let jobSeq = 0;
  function renderMini() {
    if (!jobs.size) { mini.hidden = true; return; }
    const [, j] = [...jobs.entries()].pop();
    mini.hidden = false; document.getElementById("miniLabel").textContent = j.label + (j.detail ? " · " + j.detail : "");
    setRing("miniRing", "miniPct", j.p);
  }
  const Mini = {
    start(label) { const id = ++jobSeq; jobs.set(id, { label, p: 0, detail: "" }); renderMini();
      return { set(p, detail) { const j = jobs.get(id); if (!j) return; j.p = p; if (detail !== undefined) j.detail = detail; renderMini(); },
               done() { const j = jobs.get(id); if (j) { j.p = 1; renderMini(); } setTimeout(() => { jobs.delete(id); renderMini(); }, 350); } };
    },
  };

  // fetch a URL as text with byte-level progress (falls back to an estimate when Content-Length is missing)
  async function fetchText(url, estBytes, onP) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(url + " → HTTP " + r.status);
    const total = +r.headers.get("content-length") || estBytes || 0;
    if (!r.body || !r.body.getReader) { const t = await r.text(); onP(1); return t; }
    const rd = r.body.getReader(), dec = new TextDecoder(); let got = 0, txt = "";
    for (;;) { const { done, value } = await rd.read(); if (done) break; got += value.length; txt += dec.decode(value, { stream: true }); onP(total ? Math.min(0.99, got / total) : 0.5); }
    txt += dec.decode(); onP(1); return txt;
  }
  // load a JS data file (defines a window.* global). file:// pages use a <script> tag instead of fetch.
  function loadScript(src, estBytes, onP) {
    onP = onP || (() => {});
    if (location.protocol === "file:") {
      return new Promise((res, rej) => { const s = document.createElement("script"); s.src = src; s.onload = () => { onP(1); res(); }; s.onerror = () => rej(new Error("Could not load " + src)); document.head.appendChild(s); });
    }
    return fetchText(src, estBytes, onP).then((t) => { const s = document.createElement("script"); s.text = t + "\n//# sourceURL=" + src; document.head.appendChild(s); });
  }
  window.LoadKit = { Big, Mini, fetchText, loadScript };

  // ---------- startup sequence ----------
  const FILES = [ // approximate sizes are used only when the server does not report Content-Length
    { src: "lib/leaflet/leaflet.js", size: 147552, label: "Map library" },
    { src: "data/hpms.js", size: 433648, label: "Highway network (FHWA HPMS 2024)" },
    { src: "data/data.js", size: 610808, label: "Roadside sites and mileposts" },
  ];
  // js/pages.js switches the simple pages until app.js is ready; here the progress card is shown on the map pages only
  const MAP_VIEWS = ["veg", "plan"];
  let appReady = false; const prog = { p: 0, sub: "Starting" };
  function preView() {
    if (appReady) return;
    if (MAP_VIEWS.includes(location.hash.slice(1))) { Big.show("Processing data…", prog.sub); Big.set(prog.p); } else Big.hide();
  }
  window.addEventListener("hashchange", preView);
  document.addEventListener("DOMContentLoaded", async () => {
    document.body.appendChild(big); (document.getElementById("view-map") || document.body).appendChild(mini);
    big.hidden = true; preView();
    // opened on a simple page: let its images finish first, then fetch the map data in the background
    if (!MAP_VIEWS.includes(location.hash.slice(1)) && document.readyState !== "complete")
      await new Promise((r) => { window.addEventListener("load", r, { once: true }); setTimeout(r, 4000); });
    const total = FILES.reduce((a, f) => a + f.size, 0); let doneBytes = 0;
    const report = (p, sub) => { prog.p = p; prog.sub = sub; Big.set(p, sub); };
    try {
      for (const f of FILES) {
        await loadScript(f.src, f.size, (p) => report((doneBytes + p * f.size) / total, f.label));
        doneBytes += f.size;
      }
      report(1, "Starting the map");
      await loadScript("js/app.js", 60000, () => {});
      appReady = true; if (window.Pages) window.Pages.ready = true;
    } catch (e) {
      Big.show("Loading failed", "Could not load data: " + e.message + ". Check your connection and reload.");
    }
  });
})();
