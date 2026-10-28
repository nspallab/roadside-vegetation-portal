/* Roadside Vegetation Portal: front-end prototype.
   Data comes from data/data.js (window.VEG_DATA). All logic runs in the browser;
   the planning heuristic in section 5 is a stand-in for the future back-end optimizer. */
(function () {
  "use strict";
  const D = window.VEG_DATA;
  if (window.DRONES) D.drones = window.DRONES; // js/pages.js is the source for drone specs
  const AS_OF = new Date(D.meta.as_of + "T12:00:00");
  const $ = (id) => document.getElementById(id);
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n, d = 1) => Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const daysSince = (iso) => Math.round((AS_OF - new Date(iso + "T12:00:00")) / 864e5);

  const CONTROL_TYPES = ["Mowing", "Drone spot spray", "Ground spray (boom truck)", "Brush cutting"];
  const UNIT_COLORS = ["#2a6fdb", "#e0663a", "#14a38b", "#c13b8f", "#7a5af5", "#b08900", "#3d8f3d"];

  /* ---------------------------------------------------------------- 1. map */
  const map = L.map("map", { zoomControl: false, preferCanvas: false }).setView([40.13, -88.24], 11);
  L.control.zoom({ position: "topright" }).addTo(map);
  L.control.scale({ position: "bottomright", imperial: true, metric: false }).addTo(map);
  const wide = () => window.innerWidth > 900;
  const panelMin = () => !!document.querySelector(".float-panel.min:not([hidden])");
  const rightCardOpen = () => ["planOut", "listCard", "drawer"].some((id) => !$(id).hidden);
  const fitPad = () => (wide() ? { paddingTopLeft: [panelMin() ? 20 : 370, panelMin() ? 70 : 20], paddingBottomRight: [rightCardOpen() ? 430 : 60, 20] } : { padding: [10, 10] });
  // Esri basemaps: no API key needed, and they load when the page is opened straight from a file.
  const esri = (path, opts) => L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/" + path + "/MapServer/tile/{z}/{y}/{x}", Object.assign({ maxZoom: 19, maxNativeZoom: 16 }, opts));
  const tiles = {
    streets: L.layerGroup([
      esri("Canvas/World_Light_Gray_Base", { attribution: "Tiles &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors" }),
      esri("Canvas/World_Light_Gray_Reference", {}),
    ]),
    satellite: L.layerGroup([
      esri("World_Imagery", { maxNativeZoom: 19, attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics" }),
      esri("Reference/World_Boundaries_and_Places", {}),
    ]),
  };
  tiles.streets.addTo(map);

  const roadLayer = L.layerGroup().addTo(map);
  const siteLayer = L.layerGroup().addTo(map);
  const activityLayer = L.layerGroup().addTo(map);
  const depotLayer = L.layerGroup().addTo(map);
  const uploadLayer = L.layerGroup().addTo(map);
  const planLayer = L.layerGroup().addTo(map);

  // Highway network: FHWA HPMS 2024, Champaign County, functional class 1-4 (data/hpms.js)
  const FSYS = { 1: ["Interstate", 3.2, 0.85], 2: ["Freeway / expressway", 2.6, 0.8], 3: ["Principal arterial", 2.2, 0.7], 4: ["Minor arterial", 1.4, 0.6] };
  Object.entries(window.HPMS_BG || {}).forEach(([fs, rows]) => {
    const [label, w, op] = FSYS[fs] || ["Road", 1, 0.5];
    rows.forEach(([coords, name, lanes, speed, aadt]) => {
      L.polyline(coords, { color: "#4b5563", weight: w, opacity: op })
        .bindTooltip("<b>" + esc(name || label) + "</b> · " + label + "<br>" + (lanes ? lanes + " lanes · " : "") + (speed ? speed + " mph · " : "") + (aadt ? "AADT " + aadt.toLocaleString("en-US") : ""), { sticky: true })
        .addTo(roadLayer);
    });
  });
  // IDOT mileposts (interstate mile marker signs), shown when zoomed in
  const mpLayer = L.layerGroup();
  (D.mileposts || []).forEach((m) => {
    L.marker(m.ll, { icon: L.divIcon({ className: "", html: '<div class="mp-icon">' + esc(m.mp) + "</div>", iconSize: [26, 16], iconAnchor: [13, 8] }), interactive: true })
      .bindTooltip(esc(m.route) + " milepost " + esc(m.mp) + " (IDOT sign inventory)").addTo(mpLayer);
  });
  const syncMP = () => { if ($("lyrMP").checked && map.getZoom() >= 12) mpLayer.addTo(map); else map.removeLayer(mpLayer); };
  map.on("zoomend", syncMP);
  const addDepotMarker = (d) => L.marker(d.latlng, { icon: L.divIcon({ className: "", html: '<div class="depot-icon' + (d.custom ? " custom" : "") + '">' + d.id + "</div>", iconSize: [26, 26], iconAnchor: [13, 13] }) })
    .bindTooltip(d.name).addTo(depotLayer);
  // Operations Planning shows only the staging areas chosen for the plan; Vegetation Information shows them all
  function renderDepotMarkers() {
    depotLayer.clearLayers();
    D.depots.filter((d) => state.view !== "plan" || (state.depotRows || []).includes(d.id)).forEach(addDepotMarker);
  }

  /* ------------------------------------------------- 2. status + recommendation */
  function thresholds() {
    return {
      density: +$("thDensity").value, height: +$("thHeight").value, age: +$("thAge").value, sight: $("thSight").checked,
      sightH: FIXED.sightH, monFrac: FIXED.monFrac, recent: FIXED.recent,
    };
  }
  // Fixed screening constants (no longer user-adjustable): sight-distance height, monitor share of the cover limit, recent-control window
  const FIXED = { sightH: 12, monFrac: 0.5, recent: 14 };
  function lastControl(s) {
    const c = s.history.filter((e) => CONTROL_TYPES.includes(e.type));
    return c.length ? c[c.length - 1] : null;
  }
  /* Status classification (see docs/frontend_logic.pdf, Section 4).
     Each check gives one result: act, watch, ok (or n/a). The most serious result sets the status:
       act -> Needs control, watch -> Monitor, otherwise No action.
     Exception: a site mowed or sprayed in the last 14 days is No action.
       Weed cover   (weed sites only)  : act if c >= θc, watch if c >= ½θc
       Height                          : act if h >= θh
       Sight distance (sight-line site, rule on): act if h >= 12 in
       Last inspected                  : watch if a > θa                          */
  const RANK = { act: 3, watch: 2, ok: 1, na: 0 };
  function evaluate(s, th) {
    const T = !!s.herbicide, c = s.density_pct, h = s.height_in, a = daysSince(s.last_inspected);
    const lc = lastControl(s), r = lc ? daysSince(lc.date) : Infinity;
    const watchC = Math.round(th.monFrac * th.density);
    const rows = [
      { key: "cover", label: "Weed cover", value: T ? c + "%" : "turf only", limit: "Watch at " + watchC + "%, act at " + th.density + "%",
        res: !T ? "na" : c >= th.density ? "act" : c >= th.monFrac * th.density ? "watch" : "ok", bar: T },
      { key: "height", label: "Height", value: h + " in", limit: "Act at " + th.height + " in", res: h >= th.height ? "act" : "ok" },
      { key: "sight", label: "Sight distance", value: s.sight_concern ? h + " in" : "not a sight-line site",
        limit: th.sight ? "Act at " + th.sightH + " in (sight-line sites only)" : "Rule turned off",
        res: !s.sight_concern || !th.sight ? "na" : h >= th.sightH ? "act" : "ok" },
      { key: "age", label: "Last inspected", value: a + " days ago", limit: "Watch after " + th.age + " days", res: a > th.age ? "watch" : "ok" },
    ];
    const recent = { met: r <= th.recent, text: lc ? "Last treated " + r + " days ago (" + lc.type.toLowerCase() + ")" : "No treatment on record" };
    const worst = rows.reduce((m, k) => (RANK[k.res] > RANK[m] ? k.res : m), "na");
    let status = recent.met ? "good" : worst === "act" ? "control" : worst === "watch" ? "monitor" : "good";
    const why = { cover: (k) => "weed cover " + c + "%", height: () => "height " + h + " in", sight: () => "sight-line site, height " + h + " in", age: () => "inspected " + a + " days ago" };
    const reasons = recent.met ? ["Treated " + r + " days ago"]
      : status === "good" ? ["All checks OK"]
      : rows.filter((k) => k.res === worst).map((k) => why[k.key](k).replace(/^./, (x) => x.toUpperCase()));
    return { status, reasons, rows, recent };
  }
  function recommend(s, ev) {
    if (ev.status === "monitor") return { action: "inspect", why: "Confirm conditions with a scouting flight" };
    if (ev.status !== "control") return null;
    if (!s.herbicide) return { action: "mow", why: "Desirable turf flagged for height or sight distance" };
    if (s.vclass !== "Woody brush" && ["Seed set", "Flowering"].includes(s.stage))
      return { action: "mow", why: "Mow to limit seed spread at " + s.stage.toLowerCase() + "; re-treat regrowth" };
    return { action: "spray", why: "Spot spray " + D.herbicides[s.herbicide].name + " at " + s.stage.toLowerCase() };
  }
  const STATUS = {
    control: { label: "Needs control", v: "--st-control" },
    monitor: { label: "Monitor", v: "--st-monitor" },
    good: { label: "No action", v: "--st-good" },
  };
  const ACTION = {
    spray: { label: "Drone spot spraying", v: "--a-spray" },
    mow: { label: "Mowing", v: "--a-mow" },
    inspect: { label: "Further inspection", v: "--a-inspect" },
  };

  /* --------------------------------------------------------- 3. site styling */
  const VCLASS_COLORS = {
    "Noxious broadleaf": "#c8442b", "Invasive broadleaf": "#e0873a", "Noxious grass": "#a83279",
    "Invasive grass": "#7a5af5", "Woody brush": "#6b4a2a", "Turf grass (desirable)": "#4f9a5e",
  };
  const STAGE_ORDER = ["Rosette", "Fall regrowth", "Vegetative", "Leaf-out", "Bolting", "Boot", "Heading", "Full leaf", "Flowering", "Fruiting", "Seed set", "Dormant"];
  const STAGE_COLORS = ["#1b9e77", "#1b9e77", "#4daf4a", "#4daf4a", "#a6c637", "#a6c637", "#d9c021", "#d9c021", "#f08a24", "#f08a24", "#c8442b", "#8c8c8c"];
  function ramp(t) { // light green -> yellow -> red
    const stops = [[79, 154, 94], [214, 154, 0], [200, 68, 43]];
    t = Math.max(0, Math.min(1, t));
    const i = t < 0.5 ? 0 : 1, f = t < 0.5 ? t * 2 : (t - 0.5) * 2;
    const c = stops[i].map((a, k) => Math.round(a + (stops[i + 1][k] - a) * f));
    return "rgb(" + c.join(",") + ")";
  }
  function siteColor(s) {
    const by = $("colorBy").value;
    if (state.view === "plan" && s._rec) return css(ACTION[s._rec.action].v);
    if (by === "status") return css(STATUS[s._ev.status].v);
    if (by === "vclass") return VCLASS_COLORS[s.vclass];
    if (by === "stage") return STAGE_COLORS[STAGE_ORDER.indexOf(s.stage)] || "#888";
    if (by === "height") return ramp(s.height_in / 60);
    if (by === "density") return s.herbicide ? ramp(s.density_pct / 60) : "#9aa39d";
  }
  /* ---- Representative visuals (A1–A8). Same image for every site of a class / stage.
     Files live in img/vegetation/{class,stage}/<slug>.svg; replace with real photos later. ---- */
  const slug = (t) => t.toLowerCase().replace(/\(.*?\)/g, "").trim().replace(/[^a-z0-9]+/g, "-").replace(/-$/, "");
  const CLASS_IMG = {
    "Noxious broadleaf": "noxious-broadleaf", "Invasive broadleaf": "invasive-broadleaf", "Noxious grass": "noxious-grass",
    "Invasive grass": "invasive-grass", "Woody brush": "woody-brush", "Turf grass (desirable)": "turf",
  };
  /* ---- Representative photos: Wikimedia Commons, open licenses (hotlinked; attribution shown on Home page and in the site card).
     Every class and stage has a photo; the illustration is only a fallback if a photo cannot load. ---- */
  const LIC_URL = {
    "CC BY 2.0": "https://creativecommons.org/licenses/by/2.0/", "CC BY 2.5": "https://creativecommons.org/licenses/by/2.5/",
    "CC BY 3.0 us": "https://creativecommons.org/licenses/by/3.0/us/", "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC BY-SA 2.0": "https://creativecommons.org/licenses/by-sa/2.0/", "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/", "CC0": "https://creativecommons.org/publicdomain/zero/1.0/", "Public domain": "https://creativecommons.org/publicdomain/mark/1.0/",
  };
  const PHOTOS = {
    "class/noxious-broadleaf": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/8/8b/Cirsium_arvense_2025-07-23-4.jpg/960px-Cirsium_arvense_2025-07-23-4.jpg", "Canada thistle (Cirsium arvense)", "Renée Kools", "CC BY 4.0", "https://commons.wikimedia.org/wiki/File:Cirsium_arvense_2025-07-23-4.jpg"],
    "class/invasive-broadleaf": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/0/0f/Pastinaca_sativa_146613743.jpg/960px-Pastinaca_sativa_146613743.jpg", "Wild parsnip (Pastinaca sativa)", "Силаева Татьяна Борисовна", "CC0", "https://commons.wikimedia.org/wiki/File:Pastinaca_sativa_146613743.jpg"],
    "class/noxious-grass": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/6/63/Sorghum_halepense-Sorgho_d%27Alep-20150622.jpg/960px-Sorghum_halepense-Sorgho_d%27Alep-20150622.jpg", "Johnsongrass (Sorghum halepense)", "Daniel Villafruela", "CC BY-SA 4.0", "https://commons.wikimedia.org/wiki/File:Sorghum_halepense-Sorgho_d%27Alep-20150622.jpg"],
    "class/invasive-grass": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/9/97/Phalaris_arundinacea_-_reed_canary_grass_0158.jpg/960px-Phalaris_arundinacea_-_reed_canary_grass_0158.jpg", "Reed canary grass (Phalaris arundinacea)", "R. A. Nonenmacher", "CC BY-SA 4.0", "https://commons.wikimedia.org/wiki/File:Phalaris_arundinacea_-_reed_canary_grass_0158.jpg"],
    "class/woody-brush": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/2/26/Lonicera_maackii_640437988.jpg/960px-Lonicera_maackii_640437988.jpg", "Amur honeysuckle thicket (Lonicera maackii)", "Alex Abair", "CC BY 4.0", "https://commons.wikimedia.org/wiki/File:Lonicera_maackii_640437988.jpg"],
    "class/turf": ["https://upload.wikimedia.org/wikipedia/commons/3/37/Grass_verge_by_the_B7066_-_geograph.org.uk_-_1538953.jpg", "Mowed grass verge beside a road", "Jim Smillie", "CC BY-SA 2.0", "https://commons.wikimedia.org/wiki/File:Grass_verge_by_the_B7066_-_geograph.org.uk_-_1538953.jpg"],
    "stage/rosette": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b2/Cirsium_vulgare_%28Speerdistel%29_-_Noordwijk%2C_South_Holland%2C_NL.jpg/960px-Cirsium_vulgare_%28Speerdistel%29_-_Noordwijk%2C_South_Holland%2C_NL.jpg", "Thistle rosette (Cirsium vulgare)", "Rudolphous", "CC BY-SA 4.0", "https://commons.wikimedia.org/wiki/File:Cirsium_vulgare_(Speerdistel)_-_Noordwijk,_South_Holland,_NL.jpg"],
    "stage/fall-regrowth": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/5/5a/Cirsium_vulgare_at_Jalovec_in_%C4%8C%C3%ADchov%2C_T%C5%99eb%C3%AD%C4%8D_District.jpg/960px-Cirsium_vulgare_at_Jalovec_in_%C4%8C%C3%ADchov%2C_T%C5%99eb%C3%AD%C4%8D_District.jpg", "Thistle regrowth rosette (Cirsium vulgare)", "Jiří Sedláček", "CC BY-SA 4.0", "https://commons.wikimedia.org/wiki/File:Cirsium_vulgare_at_Jalovec_in_%C4%8C%C3%ADchov,_T%C5%99eb%C3%AD%C4%8D_District.jpg"],
    "stage/vegetative": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ee/Phalaris_arundinacea_HojasyTallo_2010-8-29_SierraMadrona.jpg/960px-Phalaris_arundinacea_HojasyTallo_2010-8-29_SierraMadrona.jpg", "Leafy grass stems before heading (Phalaris arundinacea)", "Javier Martín", "Public domain", "https://commons.wikimedia.org/wiki/File:Phalaris_arundinacea_HojasyTallo_2010-8-29_SierraMadrona.jpg"],
    "stage/boot": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/7/7d/Eremopyrum_triticeum_%283735544536%29.jpg/960px-Eremopyrum_triticeum_%283735544536%29.jpg", "Grass head swelling in the leaf sheath (boot stage, Eremopyrum triticeum)", "Matt Lavin", "CC BY-SA 2.0", "https://commons.wikimedia.org/wiki/File:Eremopyrum_triticeum_(3735544536).jpg"],
    "stage/leaf-out": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/9/9c/20150423Euonymus_alatus4.jpg/960px-20150423Euonymus_alatus4.jpg", "Spring leaf-out of an invasive shrub (Euonymus alatus)", "AnRo0002", "CC0", "https://commons.wikimedia.org/wiki/File:20150423Euonymus_alatus4.jpg"],
    "stage/bolting": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/3/36/Starr-040723-0074-Verbascum_thapsus-bolting-Puu_Mali-Hawaii_%2824419153180%29.jpg/960px-Starr-040723-0074-Verbascum_thapsus-bolting-Puu_Mali-Hawaii_%2824419153180%29.jpg", "Bolting common mullein (Verbascum thapsus)", "Forest and Kim Starr", "CC BY 3.0 us", "https://commons.wikimedia.org/wiki/File:Starr-040723-0074-Verbascum_thapsus-bolting-Puu_Mali-Hawaii_(24419153180).jpg"],
    "stage/heading": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/4/4d/Phalaris_arundinacea_%283883207046%29.jpg/960px-Phalaris_arundinacea_%283883207046%29.jpg", "Grass heads emerging (Phalaris arundinacea)", "Matt Lavin", "CC BY-SA 2.0", "https://commons.wikimedia.org/wiki/File:Phalaris_arundinacea_(3883207046).jpg"],
    "stage/full-leaf": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/6/6c/Lonicera_maackii_640437962.jpg/960px-Lonicera_maackii_640437962.jpg", "Amur honeysuckle in full leaf", "Alex Abair", "CC BY 4.0", "https://commons.wikimedia.org/wiki/File:Lonicera_maackii_640437962.jpg"],
    "stage/flowering": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/1/10/Cirsium_arvense_-_p%C3%B5ldohakas.jpg/960px-Cirsium_arvense_-_p%C3%B5ldohakas.jpg", "Flowering Canada thistle", "Ivar Leidus", "CC BY-SA 3.0", "https://commons.wikimedia.org/wiki/File:Cirsium_arvense_-_p%C3%B5ldohakas.jpg"],
    "stage/fruiting": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/6/69/Lonicera_maackii_in_Schenley_Park%2C_Pittsburgh_%2815473295805%29.jpg/960px-Lonicera_maackii_in_Schenley_Park%2C_Pittsburgh_%2815473295805%29.jpg", "Amur honeysuckle fruit", "Britt Reints", "CC BY 2.0", "https://commons.wikimedia.org/wiki/File:Lonicera_maackii_in_Schenley_Park,_Pittsburgh_(15473295805).jpg"],
    "stage/seed-set": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c7/20050716-004-thistle.jpg/960px-20050716-004-thistle.jpg", "Thistle going to seed", "Gary Houston", "CC0", "https://commons.wikimedia.org/wiki/File:20050716-004-thistle.jpg"],
    "stage/dormant": ["https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b3/Thistle_at_winter_in_Gyurmi.jpg/960px-Thistle_at_winter_in_Gyurmi.jpg", "Dormant thistle in winter", "Maximden", "CC0", "https://commons.wikimedia.org/wiki/File:Thistle_at_winter_in_Gyurmi.jpg"],
  };

  const illusSrc = (key) => "img/vegetation/" + key + ".svg";
  // Representative image for a key like "class/turf": photo (with credit + source link) or illustration
  function repImage(key) {
    const ph = PHOTOS[key];
    if (ph) return { src: ph[0], fb: illusSrc(key), title: ph[1], credit: ph[2] + " · " + ph[3], lic: ph[3], page: ph[4], photo: true };
    return { src: illusSrc(key), fb: illusSrc(key), title: ph ? ph[1] : "Illustration", credit: null, page: null, photo: false };
  }
  const classKey = (vclass) => "class/" + CLASS_IMG[vclass];
  const stageKey = (stage) => "stage/" + slug(stage);
  const classImg = (vclass) => repImage(classKey(vclass)).src;
  const stageImg = (stage) => repImage(stageKey(stage)).src;
  // <img> that falls back to the illustration if a photo cannot load; wrapped in a link to the source page for photos
  const imgTag = (r, cls, alt) => '<img class="' + (cls || "") + '" src="' + r.src + '" alt="' + esc(alt || r.title) + '" loading="lazy" onerror="this.onerror=null;this.src=\'' + r.fb + '\'">';
  const linked = (r, inner) => r.page ? '<a href="' + r.page + '" target="_blank" rel="noopener" title="' + esc(r.title + " — " + r.credit + " (open source page)") + '">' + inner + "</a>" : inner;
  const DRIVER_EYE_IN = 42; // AASHTO driver eye height 3.5 ft, used as a visual reference only
  // Height schematic: ruler 0–60 in, plant drawn to h, limit θh and driver-eye reference lines.
  function heightSVG(h, th) {
    const y0 = 82, k = 72 / 60, y = (v) => (y0 - Math.min(v, 64) * k).toFixed(1);
    let blades = "";
    for (let i = 0; i < 18; i++) {
      const x = 46 + i * 3.2, hh = Math.min(h, 64) * (0.78 + 0.22 * Math.sin(i * 1.7) ** 2), lean = (i % 3 - 1) * 4;
      blades += '<path d="M' + x + " " + y0 + " Q" + (x + lean * 0.3) + " " + (y0 - hh * k * 0.6).toFixed(1) + " " + (x + lean) + " " + (y0 - hh * k).toFixed(1) + '" stroke="' + (i % 2 ? "#4f8a3a" : "#6aa84f") + '" stroke-width="1.6" fill="none"/>';
    }
    let ticks = "";
    for (let v = 0; v <= 60; v += 12) ticks += '<line x1="14" x2="20" y1="' + y(v) + '" y2="' + y(v) + '" stroke="#555"/><text x="22" y="' + (+y(v) + 3) + '" font-size="7" fill="#555">' + v + "</text>";
    return '<svg viewBox="0 0 120 90" xmlns="http://www.w3.org/2000/svg"><rect width="120" height="90" fill="#f5f8f3"/>' +
      '<line x1="14" x2="14" y1="' + y(60) + '" y2="' + y0 + '" stroke="#555"/>' + ticks + blades +
      '<rect y="' + y0 + '" width="120" height="8" fill="#b9a27a"/>' +
      '<line x1="34" x2="118" y1="' + y(th.height) + '" y2="' + y(th.height) + '" stroke="#d1432b" stroke-dasharray="4 2"/><text x="118" y="' + (+y(th.height) - 2) + '" font-size="6.5" text-anchor="end" fill="#d1432b">limit ' + th.height + " in</text>" +
      '<line x1="34" x2="118" y1="' + y(DRIVER_EYE_IN) + '" y2="' + y(DRIVER_EYE_IN) + '" stroke="#2a6fdb" stroke-dasharray="2 2"/><text x="118" y="' + (+y(DRIVER_EYE_IN) - 2) + '" font-size="6.5" text-anchor="end" fill="#2a6fdb">driver eye 42 in</text>' +
      '<text x="72" y="' + (+y(h) - 3) + '" font-size="8" font-weight="700" text-anchor="middle" fill="#2b3f5d">' + h + " in</text></svg>";
  }
  // Cover schematic: 10x10 quadrat, c cells filled with the target species (deterministic layout per site).
  function coverSVG(s, th) {
    const c = s.herbicide ? s.density_pct : 0, n = Math.round(c);
    let seed = [...s.id].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) >>> 0, 7);
    const order = [...Array(100).keys()].sort(() => ((seed = (seed * 1103515245 + 12345) >>> 0) / 4294967296) - 0.5);
    const on = new Set(order.slice(0, n));
    let cells = "";
    for (let i = 0; i < 100; i++) cells += '<rect x="' + (8 + (i % 10) * 7.4) + '" y="' + (6 + Math.floor(i / 10) * 7.4) + '" width="6.8" height="6.8" rx="1" fill="' + (on.has(i) ? VCLASS_COLORS[s.vclass] : "#cfe3bf") + '"/>';
    return '<svg viewBox="0 0 120 90" xmlns="http://www.w3.org/2000/svg"><rect width="120" height="90" fill="#f5f8f3"/>' + cells +
      '<text x="88" y="30" font-size="13" font-weight="800" fill="#2b3f5d">' + (s.herbicide ? c + "%" : "—") + "</text>" +
      '<text x="88" y="42" font-size="6.5" fill="#555">' + (s.herbicide ? "target cover" : "turf only") + "</text>" +
      '<text x="88" y="58" font-size="6.5" fill="#d1432b">act at ' + th.density + "%</text></svg>";
  }
  const svgURI = (svg) => "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  // Which visual goes with the current "Color by" mode (A5)
  function visualFor(s, mode) {
    const th = thresholds();
    const fromRep = (r, cap) => ({ src: r.src, fb: r.fb, cap: cap + (r.photo ? " · photo: " + r.credit : " · illustration") });
    if (mode === "stage") return fromRep(repImage(stageKey(s.stage)), "Growth stage: " + s.stage);
    if (mode === "height") { const u = svgURI(heightSVG(s.height_in, th)); return { src: u, fb: u, cap: "Height schematic" }; }
    if (mode === "density") { const u = svgURI(coverSVG(s, th)); return { src: u, fb: u, cap: "Cover schematic (10×10 quadrat)" }; }
    return fromRep(repImage(classKey(s.vclass)), s.vclass);
  }

  function drawLegend() {
    const by = $("colorBy").value, el = $("legend");
    const sw = (c, t, key) => { const r = key ? repImage(key) : null;
      return '<span class="sw">' + (r ? linked(r, imgTag(r, "lg-img", t)) : "") + '<i style="background:' + c + '"></i>' + esc(t) + "</span>"; };
    const numeric = by === "height" || by === "density";
    $("legendBar").hidden = !(numeric && state.view === "veg");
    el.classList.remove("with-img");
    if (state.view === "plan") { el.innerHTML = Object.values(ACTION).map((a) => sw(css(a.v), a.label)).join(""); return; }
    if (by === "status") el.innerHTML = Object.values(STATUS).map((s) => sw(css(s.v), s.label)).join("");
    else if (by === "vclass") { el.innerHTML = Object.entries(VCLASS_COLORS).map(([k, c]) => sw(c, k, classKey(k))).join(""); el.classList.add("with-img"); return; }
    else if (by === "stage") {
      const seen = new Set(D.sites.map((s) => s.stage));
      el.innerHTML = STAGE_ORDER.filter((s) => seen.has(s)).map((s) => sw(STAGE_COLORS[STAGE_ORDER.indexOf(s)], s, stageKey(s))).join("");
      el.classList.add("with-img"); return;
    } else {
      $("lbTop").textContent = "0";
      $("lbBot").textContent = by === "height" ? "60+" : "60%";
      el.innerHTML = by === "density" ? '<span class="sw"><i style="background:#9aa39d"></i>Desirable turf only</span>' : "";
    }
  }

  const state = { view: "veg", selected: null, picked: new Set(), plan: null, focusUnit: null, region: D.regions[0].id };
  const regionOf = (id) => D.regions.find((r) => r.id === id);
  const polyById = {};

  function renderSites() {
    siteLayer.clearLayers();
    const th = thresholds();
    const route = $("thRoute").value, dim = $("thDim").checked;
    D.sites.forEach((s) => {
      s._ev = evaluate(s, th);
      s._rec = recommend(s, s._ev);
      const inRoute = route === "all" || s.route === route;
      let opacity = 0.95, weight = 6;
      if (state.view === "veg") {
        if (!inRoute) opacity = 0.15;
        if (dim && s._ev.status === "good") opacity = 0.18;
      } else {
        const sel = planSel();
        if (!s._rec || !sel.ok || s.region !== sel.region) opacity = 0.15, weight = 4;
        else if (sel.mode === "pick") opacity = state.picked.has(s.id) ? 1 : 0.35;
        else if (!sel.filter(s)) opacity = 0.25;
      }
      if (state.selected === s.id) weight = 10;
      const color = state.view === "plan" && !s._rec ? "#9aa39d" : siteColor(s);
      const pl = L.polyline(s.coords, { color, weight, opacity, lineCap: "butt" });
      // A5: tooltip thumbnail follows the "Color by" mode (built lazily on hover)
      pl.bindTooltip(() => {
        const v = visualFor(s, state.view === "plan" ? "vclass" : $("colorBy").value);
        return '<div class="tip"><img src="' + v.src + '" alt="" onerror="this.onerror=null;this.src=\'' + v.fb + '\'"><div><b>' + esc(s.route + " " + s.dir + " · " + s.label) + "</b><br>" + esc(s.species) +
          "<br>" + esc(STATUS[s._ev.status].label) + (state.view === "plan" && s._rec ? " · " + esc(ACTION[s._rec.action].label) : "") +
          '<br><small>' + esc(v.cap) + " · representative</small></div></div>";
      }, { sticky: true, className: "tip-wrap" });
      pl.on("click", () => onSiteClick(s));
      pl.addTo(siteLayer);
      polyById[s.id] = pl;
    });
    renderSummary();
    renderActivity();
  }

  function renderActivity() {
    activityLayer.clearLayers();
    D.sites.forEach((s) => {
      s.history.filter((e) => CONTROL_TYPES.includes(e.type) && daysSince(e.date) <= 30).forEach((e) => {
        const mid = s.coords[Math.floor(s.coords.length / 2)];
        const c = e.type === "Mowing" || e.type === "Brush cutting" ? css("--a-mow") : css("--a-spray");
        L.marker(mid, { icon: L.divIcon({ className: "", html: '<div class="act-icon" style="background:' + c + '"></div>', iconSize: [14, 14], iconAnchor: [7, 7] }) })
          .bindTooltip(esc(e.type) + " · " + esc(e.date) + "<br>" + esc(s.id)).on("click", () => onSiteClick(s)).addTo(activityLayer);
      });
    });
  }

  // Right-hand site list: status tiles act as tabs; clicking a site opens its card in the same place
  state.listStatus = "control";
  function renderSummary() {
    const route = $("thRoute").value;
    const pool = D.sites.filter((s) => route === "all" || s.route === route);
    const n = { control: 0, monitor: 0, good: 0 };
    pool.forEach((s) => n[s._ev.status]++);
    $("statusSummary").innerHTML = Object.entries(STATUS).map(([k, v]) =>
      '<button type="button" class="stat" data-st="' + k + '" aria-pressed="' + (k === state.listStatus) + '" style="--c:var(' + v.v + ')"><b>' + n[k] + "</b><span>" + v.label + "</span></button>").join("");
    const list = pool.filter((s) => s._ev.status === state.listStatus)
      .sort((a, b) => (b.sight_concern - a.sight_concern) || (b.density_pct - a.density_pct) || a.id.localeCompare(b.id));
    $("listTitle").textContent = STATUS[state.listStatus].label + " · " + list.length + " site" + (list.length === 1 ? "" : "s") + (route === "all" ? "" : " on " + route);
    $("siteList").innerHTML = list.map((s) =>
      '<li data-id="' + s.id + '" tabindex="0">' + shield(s.route) + '<div><div class="sid">' + esc(s.route + " " + s.dir + " · " + s.label) + "</div><div class=\"why\">" +
      esc(s._ev.reasons.join(" · ")) + '</div></div><span class="go" aria-hidden="true">›</span></li>').join("") || '<li class="empty">No sites in this group at these limits.</li>';
  }
  $("statusSummary").addEventListener("click", (e) => { const t = e.target.closest(".stat"); if (!t) return; state.listStatus = t.dataset.st; renderSummary(); $("siteList").scrollTop = 0; });
  $("siteList").addEventListener("click", (e) => { const li = e.target.closest("li[data-id]"); if (li) focusSite(li.dataset.id); });
  $("siteList").addEventListener("keydown", (e) => { if (e.key === "Enter") { const li = e.target.closest("li[data-id]"); if (li) focusSite(li.dataset.id); } });
  function showList() { $("drawer").hidden = true; state.selected = null; $("listCard").hidden = false; renderSites(); }
  $("vizBtn").addEventListener("click", showList);
  $("listClose").addEventListener("click", () => { $("listCard").hidden = true; });
  $("dBack").addEventListener("click", () => { if (state.view === "veg") showList(); else { $("drawer").hidden = true; state.selected = null; renderSites(); } });

  function shield(ref) {
    const [kind, num] = ref.split("-");
    return '<span class="shield ' + (kind === "I" ? "i" : "us") + '">' + num + "</span>";
  }

  /* ------------------------------------------------------------ 4. drawer */
  const byId = Object.fromEntries(D.sites.map((s) => [s.id, s]));
  function focusSite(id) {
    const s = byId[id];
    map.fitBounds(L.latLngBounds(s.coords).pad(0.6), Object.assign({ maxZoom: 15 }, fitPad()));
    openDrawer(s);
  }
  function onSiteClick(s) {
    if (drawing || placingDepot) return; // map click handles drawing / depot placement
    if (state.view === "plan" && planMode() === "pick") {
      // planning works on one connected area at a time: picking in the other area starts a new pick list
      if ([...state.picked].some((id) => byId[id].region !== s.region)) state.picked.clear();
      state.picked.has(s.id) ? state.picked.delete(s.id) : state.picked.add(s.id);
      $("pickCount").textContent = state.picked.size;
      onPlanAreaChange();
      return;
    }
    openDrawer(s);
  }
  function roadwayBlock(s) {
    const r = s.roadway; if (!r) return "";
    return '<div><h3 class="sec-title">Roadway · FHWA HPMS 2024</h3><dl class="attrs">' +
      "<dt>Location</dt><dd>" + esc(s.route) + " " + esc(s.dir) + ", " + esc(s.label) + "</dd>" +
      '<dt>Through lanes</dt><dd><span class="num">' + (r.lanes ?? "–") + "</span></dd>" +
      '<dt>Speed limit</dt><dd><span class="num">' + (r.speed ?? "–") + "</span> mph</dd>" +
      '<dt>Traffic (AADT)</dt><dd><span class="num">' + (r.aadt ? r.aadt.toLocaleString("en-US") : "–") + "</span> vehicles/day</dd>" +
      "<dt>Area</dt><dd>" + esc(r.area) + (r.nhs ? " · National Highway System" : "") + "</dd>" +
      '<dt>HPMS route</dt><dd><span class="num">' + esc(r.hpms_route_id) + "</span> @ " + r.county_mile + "</dd></dl></div>";
  }
  function openDrawer(s) {
    state.selected = s.id;
    renderSites();
    $("listCard").hidden = true;
    $("drawer").hidden = false;
    $("dBack").hidden = state.view !== "veg";
    $("dRoute").innerHTML = shield(s.route) + "<span>" + esc(s.route) + " " + esc(s.dir) + " roadside</span>";
    $("dId").textContent = s.label + " · " + s.id;
    const ev = s._ev, st = STATUS[ev.status], rec = s._rec;
    const age = daysSince(s.last_inspected);
    // A6: an uploaded site photo wins; otherwise show the class illustration, labelled as representative
    // A6: an uploaded site photo wins; otherwise the representative photo/illustration for the class (linked to its source)
    const rc = repImage(classKey(s.vclass)), rs = repImage(stageKey(s.stage));
    const photo = s._photo
      ? '<img src="' + s._photo + '" alt="Uploaded photo of site ' + esc(s.id) + '">'
      : linked(rc, imgTag(rc, "", "Representative " + (rc.photo ? "photo" : "illustration") + " of " + s.vclass)) +
        '<span class="rep-tag">Representative ' + (rc.photo ? "photo" : "image") + " · not of this site</span>";
    const photoCredit = !s._photo && rc.photo
      ? '<p class="credit-line">' + esc(rc.title) + " · " + esc(rc.credit) + ' · <a href="' + rc.page + '" target="_blank" rel="noopener">View source ↗</a></p>' : "";
    const th = thresholds();
    const strip = '<div class="rep-strip">' +
      '<figure>' + linked(rs, imgTag(rs, "", s.stage)) + "<figcaption>" + esc(s.stage) + (rs.photo ? " · photo" : "") + "</figcaption></figure>" +
      '<figure><img src="' + svgURI(heightSVG(s.height_in, th)) + '" alt=""><figcaption>Height</figcaption></figure>' +
      '<figure><img src="' + svgURI(coverSVG(s, th)) + '" alt=""><figcaption>Cover</figcaption></figure></div>';
    // Screening card: one row per check, one result each; the most serious result sets the status
    const RES = { act: "Act", watch: "Watch", ok: "OK", na: "—" };
    const coverBar = (k) => {
      const max = Math.max(th.density * 2, s.density_pct + 5), pct = (v) => (100 * v / max).toFixed(1) + "%";
      return '<span class="scr-bar"><i class="ok" style="width:' + pct(th.monFrac * th.density) + '"></i><i class="watch" style="width:' + pct(th.density - th.monFrac * th.density) +
        '"></i><i class="act"></i><b style="left:' + pct(Math.min(s.density_pct, max)) + '"></b></span>';
    };
    const scrTip = "The most serious result sets the status: Act → Needs control, Watch → Monitor, all OK → No action. A site treated in the last " + th.recent + " days is No action.";
    const checklist = '<div><h3 class="sec-title">Screening result <i class="info" tabindex="0" role="img" aria-label="' + esc(scrTip) + '" data-tip="' + esc(scrTip) + '">i</i></h3><div class="scr">' +
      '<p class="scr-note' + (ev.recent.met ? " on" : "") + '">' + esc(ev.recent.text) + (ev.recent.met ? " → No action (treated within " + th.recent + " days)." : ", so all checks apply.") + "</p>" +
      '<div class="scr-row scr-head"><span>Check</span><span>This site</span><span>Limit</span><span>Result</span></div>' +
      ev.rows.map((k) => '<div class="scr-row' + (ev.recent.met ? " dim" : "") + '"><span>' + esc(k.label) + '</span><span class="cv">' + esc(k.value) + "</span><span>" +
        (k.bar ? coverBar(k) : "") + '<small>' + esc(k.limit) + '</small></span><span class="res ' + k.res + '">' + RES[k.res] + "</span></div>").join("") +
      "</div></div>";
    const herb = s.herbicide ? D.herbicides[s.herbicide] : null;
    const big = s.herbicide
      ? '<div class="big-num"><b>' + s.density_pct + '%</b><span>' + esc(s.species) + " cover</span></div>"
      : '<div class="big-num"><b>' + s.height_in + ' in</b><span>Vegetation height</span></div>';
    $("dBody").innerHTML = big +
      '<div><span class="pill" style="--c:var(' + st.v + ')">' + st.label + "</span>" +
      '<ul class="reasons">' + ev.reasons.map((r) => "<li>" + esc(r) + "</li>").join("") + "</ul>" +
      (rec ? '<p class="hint" style="margin-top:8px"><i class="dot a-' + rec.action + '"></i> Recommended: <b>' + ACTION[rec.action].label + "</b>. " + esc(rec.why) + ".</p>" : "") + "</div>" +
      checklist +
      '<div><div class="photo" id="dPhoto">' + photo + '</div>' + photoCredit + strip + '<label class="btn btn-outline file" style="margin-top:8px;display:inline-block"><input type="file" id="dPhotoIn" accept="image/*">Attach Site Photo</label></div>' +
      '<div><h3 class="sec-title">Vegetation</h3><dl class="attrs">' +
      "<dt>Dominant species</dt><dd>" + esc(s.species) + "</dd>" +
      "<dt>Class</dt><dd>" + esc(s.vclass) + "</dd>" +
      "<dt>Growth stage</dt><dd>" + esc(s.stage) + "</dd>" +
      '<dt>Height</dt><dd><span class="num">' + s.height_in + "</span> in</dd>" +
      '<dt>' + (s.herbicide ? "Weed cover" : "Turf cover") + '</dt><dd><span class="num">' + s.density_pct + "</span> %</dd>" +
      '<dt>Roadside area</dt><dd><span class="num">' + fmt(s.area_ac, 2) + "</span> ac (" + D.meta.row_ft + " ft strip, " + fmt(s.length_mi, 2) + " mi)</dd>" +
      "<dt>Sight distance</dt><dd>" + (s.sight_concern ? "Concern near interchange or curve" : "No concern noted") + "</dd>" +
      "<dt>Suggested herbicide</dt><dd>" + (herb ? esc(herb.name) + " <small>(" + esc(herb.use) + ")</small>" : "None, desirable vegetation") + "</dd>" +
      "<dt>Last inspected</dt><dd>" + esc(s.last_inspected) + " · " + esc(s.inspection_method) + " (" + age + " d ago)</dd>" +
      "</dl></div>" + roadwayBlock(s) +
      '<div><h3 class="sec-title">Inspection and control history</h3><ol class="timeline">' +
      s.history.slice().reverse().map((e) => {
        const c = CONTROL_TYPES.includes(e.type) ? (e.type === "Mowing" || e.type === "Brush cutting" ? "var(--a-mow)" : "var(--a-spray)") : "var(--a-inspect)";
        return '<li style="--c:' + c + '"><time>' + esc(e.date) + "</time><b>" + esc(e.type) + "</b>" + (e.added ? ' <span class="new">added</span>' : "") +
          "<br>" + esc(e.by) + (e.note ? " · " + esc(e.note) : "") + "</li>";
      }).join("") + "</ol></div>" +
      '<form class="record-form" id="recForm"><h3 class="sec-title" style="margin:0">Add a record</h3>' +
      '<div class="grid2"><label class="field"><span>Date</span><input type="date" id="rDate" value="' + D.meta.as_of + '" required></label>' +
      '<label class="field"><span>Activity</span><select id="rType">' +
      CONTROL_TYPES.concat(["Drone inspection", "Ground inspection"]).map((t) => "<option>" + t + "</option>").join("") + "</select></label></div>" +
      '<label class="field"><span>Crew or contractor</span><input type="text" id="rBy" value="IDOT D5 crew"></label>' +
      '<label class="field"><span>Notes</span><input type="text" id="rNote" placeholder="Product, rate, area treated"></label>' +
      '<button class="btn btn-navy" type="submit">Save Record</button></form>';

    $("dPhotoIn").addEventListener("change", (e) => {
      const f = e.target.files[0]; if (!f) return;
      const rd = new FileReader();
      rd.onload = () => { s._photo = rd.result; openDrawer(s); toast("Photo attached to " + s.id); };
      rd.readAsDataURL(f);
    });
    $("recForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const rec = { date: $("rDate").value, type: $("rType").value, by: $("rBy").value || "Unspecified", note: $("rNote").value, added: true };
      s.history.push(rec);
      s.history.sort((a, b) => a.date.localeCompare(b.date));
      if (rec.type.includes("inspection")) { s.last_inspected = rec.date; s.inspection_method = rec.type === "Drone inspection" ? "Drone (RGB)" : "Ground"; }
      openDrawer(s);
      toast(rec.type + " saved for " + s.id);
    });
  }
  $("dClose").addEventListener("click", () => { $("drawer").hidden = true; state.selected = null; renderSites(); });

  /* --------------------------------------------------- 5. planning heuristic */
  const G = D.graph;
  const dijkstraCache = new Map();
  function dijkstra(src) {
    if (dijkstraCache.has(src)) return dijkstraCache.get(src);
    const n = G.nodes.length, dist = new Float64Array(n).fill(Infinity), prev = new Int32Array(n).fill(-1), done = new Uint8Array(n);
    dist[src] = 0;
    const heap = [[0, src]];
    const push = (x) => { heap.push(x); let i = heap.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (heap[p][0] <= heap[i][0]) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; } };
    const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === i) break; [heap[m], heap[i]] = [heap[i], heap[m]]; i = m; } } return top; };
    while (heap.length) {
      const [d, u] = pop(); if (done[u]) continue; done[u] = 1;
      for (const [v, w] of G.adj[u]) { const nd = d + w; if (nd < dist[v]) { dist[v] = nd; prev[v] = u; push([nd, v]); } }
    }
    const res = { dist, prev }; dijkstraCache.set(src, res); return res;
  }
  function pathNodes(a, b) {
    const { prev } = dijkstra(a), out = [];
    for (let v = b; v !== -1; v = prev[v]) { out.push(v); if (v === a) break; }
    return out.reverse();
  }
  const M_PER_MI = 1609.34, TRUCK_MPH = 45;

  function workHours(s, action, p) {
    const herb = s.herbicide ? D.herbicides[s.herbicide] : null;
    if (action === "spray") {
      const treated = s.area_ac * s.density_pct / 100;
      const mix = treated * p.gpa;
      const sorties = Math.max(1, Math.ceil(mix / p.drone.tank_gal));
      const flight = treated / (p.drone.prod_ac_hr * p.eff);
      return { h: flight + sorties * (10 / 60) + 0.25, treated, mix, sorties, product: herb ? treated * herb.rate_gal_ac : 0, herb: s.herbicide };
    }
    if (action === "mow") return { h: s.length_mi * 2 / 4 + 1 / 6, laneMi: s.length_mi * 2 };
    return { h: s.length_mi / 10 + 0.25, flownMi: s.length_mi };
  }

  function readPlanInputs() {
    const drone = D.drones.find((d) => d.id === $("pDrone").value);
    return {
      sel: planSel(), drone, depots: state.depotRows.map((id) => D.depots.find((d) => d.id === id)).filter(Boolean),
      units: { spray: +$("pDrones").value, mow: +$("pMowers").value, inspect: +$("pScouts").value },
      use: { spray: $("pSpray").checked, mow: $("pMow").checked, inspect: $("pInspect").checked },
      date: $("pDate").value, start: $("pStart").value, hours: +$("pHours").value,
      gpa: +$("pGPA").value, wind: +$("pWind").value, windMax: +$("pWindMax").value, eff: +$("pEff").value / 100,
      obj: document.querySelector('input[name="pObj"]:checked').value,
    };
  }

  function buildPlan() {
    const p = readPlanInputs();
    const warn = [];
    const pool = p.sel.ok ? D.sites.filter((s) => s._rec && p.use[s._rec.action] && s.region === p.sel.region && p.sel.filter(s)) : [];
    if (!pool.length) warn.push("No flagged sites match this area and action selection.");
    if (!p.drone.us) warn.push(p.drone.brand + " " + p.drone.model + " is not currently available in the U.S.; results are for comparison only.");
    const windHold = p.wind > p.windMax;
    if (windHold && p.use.spray) warn.push("Forecast wind " + p.wind + " mph exceeds the " + p.windMax + " mph spraying limit. Spray tasks are marked as weather holds.");

    const units = [];
    let colorI = 0;
    ["spray", "inspect", "mow"].forEach((action) => {
      const sites = pool.filter((s) => s._rec.action === action);
      if (!sites.length) return;
      const n = p.units[action];
      if (n === 0) { warn.push(sites.length + " " + ACTION[action].label.toLowerCase() + " site(s) are unassigned: add a crew."); return; }
      // each site goes to its nearest depot; crews are shared out by workload (see docs, Section 6)
      splitByDepot(sites, p.depots, n, action, p).forEach(({ depot, sites: dsites, n: nd }) => {
        // nearest-neighbour tour from the depot; optionally sight-distance sites first
        const groups = p.obj === "safety" ? [dsites.filter((s) => s.sight_concern), dsites.filter((s) => !s.sight_concern)] : [dsites];
        const tour = []; let cur = depot.node;
        groups.forEach((g) => {
          const rest = g.slice();
          while (rest.length) {
            const { dist } = dijkstra(cur);
            let bi = 0; rest.forEach((s, i) => { if (dist[s.mid_node] < dist[rest[bi].mid_node]) bi = i; });
            const s = rest.splice(bi, 1)[0]; tour.push(s); cur = s.mid_node;
          }
        });
        // split the tour into nd chunks of similar workload
        const w = tour.map((s) => workHours(s, action, p).h + 0.2);
        const total = w.reduce((x, y) => x + y, 0), target = total / nd;
        const chunks = [[]]; let acc = 0;
        tour.forEach((s, i) => {
          if (acc >= target && chunks.length < nd) { chunks.push([]); acc = 0; }
          chunks[chunks.length - 1].push(s); acc += w[i];
        });
        chunks.forEach((chunk) => {
          if (!chunk.length) return;
          const k = units.filter((u) => u.action === action).length + 1;
          units.push(scheduleUnit(chunk, action, k, UNIT_COLORS[colorI++ % UNIT_COLORS.length], p, windHold && action === "spray", depot));
        });
      });
    });
    return { p, units, warn };
  }

  // Assign each site to its nearest depot (road distance), then share n crews among depots by workload.
  function splitByDepot(sites, depots, n, action, p) {
    const dists = depots.map((d) => dijkstra(d.node).dist);
    const groups = depots.map(() => []);
    const nearest = (s, among) => among.reduce((bi, i) => (dists[i][s.mid_node] < dists[bi][s.mid_node] ? i : bi), among[0]);
    const all = depots.map((_, i) => i);
    sites.forEach((s) => groups[nearest(s, all)].push(s));
    const load = (i) => groups[i].reduce((a, s) => a + workHours(s, action, p).h, 0);
    let active = all.filter((i) => groups[i].length).sort((x, y) => load(y) - load(x));
    if (n < active.length) { // fewer crews than busy depots: keep the busiest depots, move the rest of the sites to them
      const keep = active.slice(0, n);
      active.slice(n).forEach((i) => { groups[i].forEach((s) => groups[nearest(s, keep)].push(s)); groups[i] = []; });
      active = keep;
    }
    const alloc = {}; active.forEach((i) => (alloc[i] = 1));
    for (let left = n - active.length; left > 0; left--) {
      const bi = active.reduce((b, i) => (load(i) / alloc[i] > load(b) / alloc[b] ? i : b), active[0]);
      alloc[bi]++;
    }
    return active.map((i) => ({ depot: depots[i], sites: groups[i], n: alloc[i] }));
  }

  function scheduleUnit(chunk, action, k, color, p, hold, depot) {
    const label = { spray: "Spray drone crew", mow: "Mower unit", inspect: "Scouting drone" }[action] + " " + k + (p.depots.length > 1 ? " · " + depot.id : "");
    const [sh, sm] = p.start.split(":").map(Number);
    const dayStart = sh + sm / 60;
    let day = 1, used = 0, cur = depot.node, travelM = 0;
    const stops = [], path = [];
    chunk.forEach((s) => {
      const wk = workHours(s, action, p);
      let legM = dijkstra(cur).dist[s.mid_node];
      let legH = legM / M_PER_MI / TRUCK_MPH;
      if (used > 0 && used + legH + wk.h > p.hours) {
        day++; used = 0;
        path.push(...pathNodes(cur, depot.node));
        travelM += dijkstra(cur).dist[depot.node];
        cur = depot.node; legM = dijkstra(cur).dist[s.mid_node]; legH = legM / M_PER_MI / TRUCK_MPH;
      }
      path.push(...pathNodes(cur, s.mid_node));
      travelM += legM; used += legH;
      const t0 = dayStart + used;
      used += wk.h;
      stops.push({ site: s, day, start: t0, end: dayStart + used, wk, hold });
      cur = s.mid_node;
    });
    path.push(...pathNodes(cur, depot.node));
    travelM += dijkstra(cur).dist[depot.node];
    const sum = (f) => stops.reduce((a, x) => a + (x.wk[f] || 0), 0);
    return {
      action, label, color, stops, path, days: day, travelMi: travelM / M_PER_MI,
      workH: stops.reduce((a, x) => a + x.wk.h, 0), mix: sum("mix"), product: sum("product"), sorties: sum("sorties"),
      laneMi: sum("laneMi"), flownMi: sum("flownMi"), hold,
    };
  }

  const clock = (h) => { const hh = Math.floor(h), mm = Math.round((h - hh) * 60); return String(hh + (mm === 60 ? 1 : 0)).padStart(2, "0") + ":" + String(mm % 60).padStart(2, "0"); };
  const dayDate = (iso, day) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + day - 1); return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" }); };

  function renderPlan() {
    const plan = (state.plan = buildPlan());
    state.focusUnit = null;
    $("planOut").hidden = false;
    $("planWarn").hidden = !plan.warn.length;
    $("planWarn").innerHTML = plan.warn.map(esc).join("<br>");
    const U = plan.units;
    const tot = (f) => U.reduce((a, u) => a + u[f], 0);
    const nSites = U.reduce((a, u) => a + u.stops.length, 0);
    const days = U.length ? Math.max(...U.map((u) => u.days)) : 0;
    $("kpis").innerHTML = [
      [nSites, "Sites planned"], [days + (days === 1 ? " day" : " days"), "Time to finish"],
      [fmt(tot("product"), 2) + " gal", "Herbicide product"], [fmt(tot("mix"), 0) + " gal", "Spray mix"],
      [tot("sorties"), "Drone sorties"], [fmt(tot("laneMi"), 1) + " mi", "Lane-miles mowed"],
      [fmt(tot("workH") , 1) + " h", "Crew work time"], [fmt(tot("travelMi"), 0) + " mi", "Road travel"],
    ].map(([v, l]) => '<div class="kpi"><b>' + v + "</b><span>" + l + "</span></div>").join("");
    $("units").innerHTML = U.map((u, i) =>
      '<button type="button" class="unit-card" data-i="' + i + '" aria-pressed="false"><i class="sw" style="background:' + u.color + '"></i><div><b>' + esc(u.label) + "</b><span>" +
      u.stops.length + " sites · " + fmt(u.travelMi, 0) + " mi travel" + (u.action === "spray" ? " · " + u.sorties + " sorties" : "") + (u.hold ? " · weather hold" : "") +
      '</span></div><div class="t">' + u.days + "d · " + fmt(u.workH, 1) + "h</div></button>").join("");

    // herbicide by product
    const byHerb = {};
    U.forEach((u) => u.stops.forEach((x) => { if (x.wk.herb) { const k = x.wk.herb; byHerb[k] = byHerb[k] || { ac: 0, prod: 0 }; byHerb[k].ac += x.wk.treated; byHerb[k].prod += x.wk.product; } }));
    const hk = Object.keys(byHerb);
    $("herbTable").innerHTML = hk.length ? "<table><thead><tr><th>Herbicide</th><th>Treated</th><th>Product</th></tr></thead><tbody>" +
      hk.map((k) => "<tr><td>" + esc(D.herbicides[k].name) + '</td><td class="n">' + fmt(byHerb[k].ac, 2) + ' ac</td><td class="n">' + fmt(byHerb[k].prod, 2) + " gal</td></tr>").join("") +
      '</tbody></table><p class="hint" style="margin-top:6px">Illustrative per-acre rates. Follow the product label in the field.</p>' : "";

    const rows = [];
    U.forEach((u) => u.stops.forEach((x, j) => rows.push({ u, x, j })));
    rows.sort((a, b) => a.x.day - b.x.day || a.x.start - b.x.start);
    $("schedule").innerHTML = "<thead><tr><th>Day</th><th>Time</th><th>Crew</th><th>Site</th><th>Action</th><th>Est.</th></tr></thead><tbody>" +
      rows.map(({ u, x, j }) => '<tr class="' + (x.hold ? "hold" : "") + '"><td>' + dayDate(plan.p.date, x.day) + '</td><td class="n">' + clock(x.start) +
        '</td><td><i class="dot" style="background:' + u.color + '"></i> ' + esc(u.label.replace(/ crew| unit| drone/g, "")) + " #" + (j + 1) +
        '</td><td class="id">' + esc(x.site.id) + "</td><td>" + esc(ACTION[u.action].label) +
        (u.action === "spray" ? "<br><small>" + fmt(x.wk.mix, 1) + " gal mix, " + x.wk.sorties + " sortie" + (x.wk.sorties > 1 ? "s" : "") + "</small>" : "") +
        '</td><td class="n">' + fmt(x.end - x.start, 1) + " h</td></tr>").join("") + "</tbody>";

    drawPlanLayer();
    renderSites();
    drawLegend();
    if (U.length) map.fitBounds(L.featureGroup(planLayer.getLayers()).getBounds().pad(0.05), fitPad());
  }

  function drawPlanLayer() {
    planLayer.clearLayers();
    if (!state.plan || state.view !== "plan") return;
    state.plan.units.forEach((u, i) => {
      const dim = state.focusUnit !== null && state.focusUnit !== i;
      const coords = u.path.map((k) => G.nodes[k]);
      L.polyline(coords, { color: u.color, weight: 4, opacity: dim ? 0.12 : 0.9, dashArray: u.action === "mow" ? null : "8 6", interactive: false }).addTo(planLayer);
      if (dim) return;
      u.stops.forEach((x, j) => {
        const mid = x.site.coords[Math.floor(x.site.coords.length / 2)];
        L.marker(mid, { icon: L.divIcon({ className: "", html: '<div class="stop-icon" style="background:' + u.color + '">' + (j + 1) + "</div>", iconSize: [22, 22], iconAnchor: [11, 11] }) })
          .bindTooltip("<b>" + esc(u.label) + " · stop " + (j + 1) + "</b><br>" + esc(x.site.id) + "<br>" + dayDate(state.plan.p.date, x.day) + ", " + clock(x.start) + "–" + clock(x.end))
          .on("click", () => openDrawer(x.site)).addTo(planLayer);
      });
    });
  }
  $("units").addEventListener("click", (e) => {
    const b = e.target.closest(".unit-card"); if (!b) return;
    const i = +b.dataset.i;
    state.focusUnit = state.focusUnit === i ? null : i;
    document.querySelectorAll(".unit-card").forEach((c) => c.setAttribute("aria-pressed", String(+c.dataset.i === state.focusUnit)));
    drawPlanLayer();
  });

  /* ------------------------------------------------------ 6. CSV + uploads */
  function downloadCSV(name, rows) {
    const text = rows.map((r) => r.map((v) => { const s = String(v ?? ""); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    a.download = name; document.body.appendChild(a); a.click(); a.remove();
    toast("Downloaded " + name);
  }
  $("downloadSites").addEventListener("click", () => {
    downloadCSV("roadside_sites.csv", [["site_id", "route", "direction", "location", "lanes", "speed_mph", "aadt", "area_ac", "species", "class", "stage", "height_in", "cover_pct", "sight_concern", "last_inspected", "status", "reasons"]]
      .concat(D.sites.map((s) => [s.id, s.route, s.dir, s.label, s.roadway.lanes, s.roadway.speed, s.roadway.aadt, s.area_ac, s.species, s.vclass, s.stage, s.height_in, s.density_pct, s.sight_concern, s.last_inspected, STATUS[s._ev.status].label, s._ev.reasons.join("; ")])));
  });
  $("downloadPlan").addEventListener("click", () => {
    const P = state.plan; if (!P) return;
    const rows = [["day", "date", "start", "end", "crew", "stop", "site_id", "action", "spray_mix_gal", "herbicide", "product_gal", "sorties", "weather_hold"]];
    P.units.forEach((u) => u.stops.forEach((x, j) => rows.push([x.day, dayDate(P.p.date, x.day), clock(x.start), clock(x.end), u.label, j + 1, x.site.id, ACTION[u.action].label,
      x.wk.mix ? x.wk.mix.toFixed(2) : "", x.wk.herb ? D.herbicides[x.wk.herb].name : "", x.wk.product ? x.wk.product.toFixed(3) : "", x.wk.sorties || "", x.hold ? "yes" : ""])));
    downloadCSV("vegetation_control_plan.csv", rows);
  });

  $("uploadData").addEventListener("change", (e) => {
    const f = e.target.files[0]; if (!f) return;
    const rd = new FileReader();
    rd.onload = () => {
      try {
        let layer, count = 0;
        const style = { color: "#e0663a", weight: 3, fillOpacity: 0.3 };
        if (/\.csv$/i.test(f.name)) {
          const lines = rd.result.trim().split(/\r?\n/), head = lines[0].split(",").map((h) => h.trim().toLowerCase());
          const la = head.findIndex((h) => ["lat", "latitude", "y"].includes(h)), lo = head.findIndex((h) => ["lon", "lng", "long", "longitude", "x"].includes(h));
          if (la < 0 || lo < 0) throw new Error("The CSV needs latitude and longitude columns (lat, lon).");
          layer = L.featureGroup();
          lines.slice(1).forEach((ln) => {
            const c = ln.split(","); const lat = +c[la], lon = +c[lo]; if (!isFinite(lat) || !isFinite(lon)) return;
            count++;
            L.circleMarker([lat, lon], { radius: 6, color: "#fff", weight: 2, fillColor: "#e0663a", fillOpacity: 0.9 })
              .bindPopup(head.map((h, i) => "<b>" + esc(h) + "</b>: " + esc(c[i] ?? "")).join("<br>")).addTo(layer);
          });
        } else {
          const gj = JSON.parse(rd.result);
          layer = L.geoJSON(gj, {
            style, pointToLayer: (_, ll) => L.circleMarker(ll, { radius: 6, color: "#fff", weight: 2, fillColor: "#e0663a", fillOpacity: 0.9 }),
            onEachFeature: (ft, l) => { count++; if (ft.properties) l.bindPopup(Object.entries(ft.properties).map(([k, v]) => "<b>" + esc(k) + "</b>: " + esc(v)).join("<br>")); },
          });
        }
        if (!count) throw new Error("No features with coordinates were found in " + f.name + ".");
        layer.addTo(uploadLayer);
        map.fitBounds(layer.getBounds().pad(0.2), fitPad());
        $("uploadNote").textContent = "Added " + count + " feature" + (count > 1 ? "s" : "") + " from " + f.name + " (orange on the map).";
      } catch (err) {
        $("uploadNote").textContent = err.message.startsWith("Unexpected") ? "Could not read " + f.name + ". Check that it is valid GeoJSON." : err.message;
      }
      e.target.value = "";
    };
    rd.readAsText(f);
  });

  /* ----------------------------------------------------------- 7. wiring */
  let toastT;
  function toast(msg) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => (t.hidden = true), 2600); }

  D.drones.forEach((d) => $("pDrone").insertAdjacentHTML("beforeend", '<option value="' + d.id + '">' + esc(d.brand + " " + d.model) + (d.us ? "" : " (not sold in U.S.)") + "</option>"));

  function droneSpec() {
    const d = D.drones.find((x) => x.id === $("pDrone").value);
    $("droneSpec").innerHTML = '<dl class="attrs"><dt>Tank</dt><dd><span class="num">' + d.tank_gal + "</span> gal</dd><dt>Rated output</dt><dd><span class=\"num\">" + d.prod_ac_hr +
      "</span> ac/h " + esc(d.rate_note) + "</dd><dt>Battery</dt><dd>" + esc(d.battery) + "</dd><dt>Price</dt><dd>" + esc(d.price) + "</dd></dl>";
  }
  $("pDrone").addEventListener("change", droneSpec); droneSpec();
  $("pEff").addEventListener("input", () => ($("pEffOut").textContent = $("pEff").value + "%"));
  // "Finding routes…" progress card, like INTERMODAL's route search
  $("pRun").addEventListener("click", () => {
    if (!planSel().ok) return;
    LoadKit.Big.show("Finding routes…", "Building crew tours on the road network");
    LoadKit.Big.set(0.35);
    setTimeout(() => { try { renderPlan(); } finally { LoadKit.Big.set(1, "Done"); setTimeout(() => LoadKit.Big.hide(), 250); } }, 60);
  });

  function syncOutputs() {
    $("oDensity").textContent = $("thDensity").value + "%";
    $("oHeight").textContent = $("thHeight").value + " in";
    $("oAge").textContent = $("thAge").value + " days";
    // B1: plain-language rules with the live threshold values
    const th = thresholds();
    $("statusRules").innerHTML =
      "<p>Every site is checked four ways. Each check gives <b>Act</b>, <b>Watch</b> or <b>OK</b>:</p><ul>" +
      "<li><b>Weed cover</b>: watch at <b>" + Math.round(th.monFrac * th.density) + "%</b>, act at <b>" + th.density + "%</b> (weed sites only, not desirable turf)</li>" +
      "<li><b>Height</b>: act at <b>" + th.height + " in</b></li>" +
      (th.sight ? "<li><b>Sight distance</b>: act at <b>" + th.sightH + " in</b> on sight-line sites</li>" : "<li><s>Sight distance</s> (turned off)</li>") +
      "<li><b>Last inspected</b>: watch after <b>" + th.age + " days</b></li></ul>" +
      "<p>The most serious result sets the status: Act → <b>Needs control</b>, Watch → <b>Monitor</b>, all OK → <b>No action</b>. A site mowed or sprayed in the last <b>" + th.recent + " days</b> is No action.</p>" +
      '<p class="hint">Each site gets exactly one status. The Route filter and Dim option change what is shown, not the status.</p>';
  }
  ["colorBy", "thDensity", "thHeight", "thAge", "thRoute", "thSight", "thDim"].forEach((id) => $(id).addEventListener("input", () => { syncOutputs(); drawLegend(); renderSites(); }));
  $("planClose").addEventListener("click", () => { $("planOut").hidden = true; });

  /* ---- GeoJSON export (for ArcGIS / QGIS / DOT GIS systems) ---- */
  function downloadJSON(name, obj) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(obj)], { type: "application/geo+json" }));
    a.download = name; document.body.appendChild(a); a.click(); a.remove();
    toast("Downloaded " + name);
  }
  const lineGeom = (coords) => ({ type: "LineString", coordinates: coords.map(([la, lo]) => [lo, la]) });
  $("downloadSitesGeo").addEventListener("click", () => {
    downloadJSON("roadside_sites.geojson", { type: "FeatureCollection", features: D.sites.map((s) => ({
      type: "Feature", geometry: lineGeom(s.coords),
      properties: { site_id: s.id, route: s.route, direction: s.dir, location: s.label, lanes: s.roadway.lanes, speed_mph: s.roadway.speed, aadt: s.roadway.aadt, area_ac: s.area_ac, species: s.species,
        veg_class: s.vclass, growth_stage: s.stage, height_in: s.height_in, cover_pct: s.density_pct, sight_concern: s.sight_concern,
        last_inspected: s.last_inspected, status: STATUS[s._ev.status].label, recommended_action: s._rec ? ACTION[s._rec.action].label : "" },
    })) });
  });
  $("downloadPlanGeo").addEventListener("click", () => {
    const P = state.plan; if (!P) return;
    const feats = [];
    P.units.forEach((u) => {
      feats.push({ type: "Feature", geometry: lineGeom(u.path.map((k) => G.nodes[k])), properties: { crew: u.label, action: ACTION[u.action].label, days: u.days, travel_mi: +u.travelMi.toFixed(1), work_h: +u.workH.toFixed(2) } });
      u.stops.forEach((x, j) => {
        const m = x.site.coords[Math.floor(x.site.coords.length / 2)];
        feats.push({ type: "Feature", geometry: { type: "Point", coordinates: [m[1], m[0]] },
          properties: { crew: u.label, stop: j + 1, site_id: x.site.id, day: x.day, start: clock(x.start), end: clock(x.end), spray_mix_gal: x.wk.mix ? +x.wk.mix.toFixed(2) : null } });
      });
    });
    downloadJSON("vegetation_control_plan.geojson", { type: "FeatureCollection", features: feats });
  });

  const lyr = { lyrSites: siteLayer, lyrRoads: roadLayer, lyrActivity: activityLayer, lyrDepots: depotLayer };
  $("lyrMP").addEventListener("change", syncMP);
  Object.entries(lyr).forEach(([id, layer]) => $(id).addEventListener("change", (e) => (e.target.checked ? layer.addTo(map) : map.removeLayer(layer))));
  document.querySelectorAll('input[name="basemap"]').forEach((r) => r.addEventListener("change", () => {
    Object.values(tiles).forEach((t) => map.removeLayer(t)); tiles[r.value].addTo(map);
  }));

  const VIEWS = ["home", "veg", "plan", "drones", "team"];
  let fitted = false;
  function setView(v) {
    if (!VIEWS.includes(v)) v = "home";
    if (state.view !== v) { $("drawer").hidden = true; state.selected = null; }
    if (v !== "veg") $("listCard").hidden = true;
    state.view = v;
    renderDepotMarkers();
    document.querySelectorAll(".navbar a").forEach((a) => (a.dataset.view === v ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    document.querySelectorAll("[data-page]").forEach((p) => (p.hidden = p.dataset.page !== v));
    const onMap = v === "veg" || v === "plan";
    $("view-map").hidden = !onMap;
    $("panel-veg").hidden = v !== "veg";
    $("panel-plan").hidden = v !== "plan";
    if (v !== "plan") { $("planOut").hidden = true; if (typeof syncPlanSketch === "function") syncPlanSketch(); }
    else { if (state.plan) $("planOut").hidden = false; if (typeof syncPlanSketch === "function") syncPlanSketch(); }
    if (onMap) {
      map.invalidateSize();
      if (!fitted) { fitAllSites(); fitted = true; }
      drawLegend(); renderSites(); drawPlanLayer();
    }
    document.title = { home: "Roadside Vegetation Portal", veg: "Vegetation Information · Roadside Vegetation", plan: "Operations Planning · Roadside Vegetation", drones: "Drone Technology · Roadside Vegetation", team: "Team · Roadside Vegetation" }[v];
  }
  window.addEventListener("hashchange", () => setView(location.hash.slice(1)));

  /* ----------------------------------------------------- 8. regions (demo areas) */
  function fitAllSites() { map.fitBounds(L.latLngBounds(D.sites.map((s) => s.coords[0])).pad(0.08), fitPad()); }
  function fitRegion() { const r = regionOf(state.region); map.fitBounds(L.latLngBounds(r.bounds).pad(0.06), fitPad()); }
  function setRegion(id) { // the area the plan works on; resets depots and any old plan
    if (state.region === id) return;
    state.region = id; $("drawer").hidden = true; state.selected = null;
    state.plan = null; planLayer.clearLayers(); $("planOut").hidden = true;
    state.depotRows = [D.depots.find((d) => d.region === id).id];
    renderDepotRows();
  }
  // Route filter lists every route that has vegetation data (all demo areas)
  $("thRoute").innerHTML = '<option value="all">All routes</option>' + [...new Set(D.sites.map((x) => x.route))].sort().map((x) => "<option>" + x + "</option>").join("");

  /* ----------------------------------------------------- 9. find a location (state / county / interstate) */
  const STATES = [["01","Alabama"],["02","Alaska"],["04","Arizona"],["05","Arkansas"],["06","California"],["08","Colorado"],["09","Connecticut"],["10","Delaware"],["11","District of Columbia"],["12","Florida"],["13","Georgia"],["15","Hawaii"],["16","Idaho"],["17","Illinois"],["18","Indiana"],["19","Iowa"],["20","Kansas"],["21","Kentucky"],["22","Louisiana"],["23","Maine"],["24","Maryland"],["25","Massachusetts"],["26","Michigan"],["27","Minnesota"],["28","Mississippi"],["29","Missouri"],["30","Montana"],["31","Nebraska"],["32","Nevada"],["33","New Hampshire"],["34","New Jersey"],["35","New Mexico"],["36","New York"],["37","North Carolina"],["38","North Dakota"],["39","Ohio"],["40","Oklahoma"],["41","Oregon"],["42","Pennsylvania"],["44","Rhode Island"],["45","South Carolina"],["46","South Dakota"],["47","Tennessee"],["48","Texas"],["49","Utah"],["50","Vermont"],["51","Virginia"],["53","Washington"],["54","West Virginia"],["55","Wisconsin"],["56","Wyoming"]];
  const POOLED = ["06","08","17","18","20","26","27","28","29","38","42","48"]; // AMT pooled fund member states
  $("locState").insertAdjacentHTML("beforeend",
    '<optgroup label="AMT pooled fund states">' + STATES.filter((x) => POOLED.includes(x[0])).map((x) => '<option value="' + x[0] + '">' + x[1] + "</option>").join("") + "</optgroup>" +
    '<optgroup label="All states">' + STATES.map((x) => '<option value="' + x[0] + '">' + x[1] + "</option>").join("") + "</optgroup>");
  const TIGER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/";
  const outlineLayer = L.layerGroup().addTo(map);
  async function showBoundary(layerId, where, label) {
    const job = LoadKit.Mini.start(label); job.set(0.15, "requesting");
    try {
      const url = TIGER + layerId + "/query?where=" + encodeURIComponent(where) + "&outFields=NAME&returnGeometry=true&outSR=4326&maxAllowableOffset=" + (layerId === 0 ? 0.01 : 0.002) + "&f=geojson";
      const txt = await LoadKit.fetchText(url, 400000, (p) => job.set(0.15 + 0.8 * p, "downloading boundary"));
      const gj = JSON.parse(txt);
      outlineLayer.clearLayers();
      const lay = L.geoJSON(gj, { style: { color: "#fe6f1a", weight: 2.5, fill: false, dashArray: "6 4" }, interactive: false }).addTo(outlineLayer);
      if (lay.getLayers().length) map.fitBounds(lay.getBounds(), fitPad());
      job.done();
    } catch (e) { job.set(1, "could not reach Census TIGERweb"); setTimeout(() => job.done(), 2500); }
  }
  $("locState").addEventListener("change", async () => {
    const st = $("locState").value, cs = $("locCounty");
    cs.disabled = true; cs.innerHTML = '<option value="">Loading counties…</option>';
    if (!st) { cs.innerHTML = '<option value="">Choose a state first</option>'; return; }
    showBoundary(0, "STATE='" + st + "'", "State boundary");
    const job = LoadKit.Mini.start("County list");
    try {
      const txt = await LoadKit.fetchText(TIGER + "1/query?where=" + encodeURIComponent("STATE='" + st + "'") + "&outFields=NAME,GEOID&returnGeometry=false&orderByFields=NAME&f=json", 20000, (p) => job.set(p));
      const j = JSON.parse(txt);
      cs.innerHTML = '<option value="">All counties</option>' + (j.features || []).map((f) => '<option value="' + f.attributes.GEOID + '">' + esc(f.attributes.NAME) + "</option>").join("");
      cs.disabled = false; job.done();
    } catch (e) { cs.innerHTML = '<option value="">Could not load counties</option>'; job.set(1, "Census TIGERweb unavailable"); setTimeout(() => job.done(), 2500); }
  });
  $("locCounty").addEventListener("change", () => {
    const g = $("locCounty").value;
    if (g) showBoundary(1, "GEOID='" + g + "'", "County boundary"); else if ($("locState").value) showBoundary(0, "STATE='" + $("locState").value + "'", "State boundary");
  });

  /* ----------------------------------------------------- 9a. minimize the left panels to one row */
  document.querySelectorAll(".float-panel .collapse").forEach((b) => b.addEventListener("click", () => {
    const panel = b.closest(".float-panel"), min = panel.classList.toggle("min");
    b.setAttribute("aria-expanded", String(!min)); b.setAttribute("aria-label", min ? "Expand panel" : "Minimize panel"); b.title = min ? "Expand panel" : "Minimize panel";
    $("legendBar").classList.toggle("shift", min);
  }));

  /* ----------------------------------------------------- 9b. planning area: location / drawn area / picked sites, and depots */
  const IL_COUNTIES = ["Adams","Alexander","Bond","Boone","Brown","Bureau","Calhoun","Carroll","Cass","Champaign","Christian","Clark","Clay","Clinton","Coles","Cook","Crawford","Cumberland","DeKalb","De Witt","Douglas","DuPage","Edgar","Edwards","Effingham","Fayette","Ford","Franklin","Fulton","Gallatin","Greene","Grundy","Hamilton","Hancock","Hardin","Henderson","Henry","Iroquois","Jackson","Jasper","Jefferson","Jersey","Jo Daviess","Johnson","Kane","Kankakee","Kendall","Knox","Lake","LaSalle","Lawrence","Lee","Livingston","Logan","McDonough","McHenry","McLean","Macon","Macoupin","Madison","Marion","Marshall","Mason","Massac","Menard","Mercer","Monroe","Montgomery","Morgan","Moultrie","Ogle","Peoria","Perry","Piatt","Pike","Pope","Pulaski","Putnam","Randolph","Richland","Rock Island","St. Clair","Saline","Sangamon","Schuyler","Scott","Shelby","Stark","Stephenson","Tazewell","Union","Vermilion","Wabash","Warren","Washington","Wayne","White","Whiteside","Will","Williamson","Winnebago","Woodford"];
  const DATA_COUNTIES = { Champaign: "champaign", Cook: "chicago" }; // counties with vegetation data
  const NA = " — data not available";
  $("psState").innerHTML = STATES.map((x) => '<option value="' + x[0] + '"' + (x[0] === "17" ? " selected" : " disabled") + ">" + x[1] + (x[0] === "17" ? "" : NA) + "</option>").join("");
  $("psCounty").innerHTML = IL_COUNTIES.map((c) => '<option value="' + c + '"' + (DATA_COUNTIES[c] ? "" : " disabled") + (c === "Champaign" ? " selected" : "") + ">" + c + (DATA_COUNTIES[c] ? "" : NA) + "</option>").join("");
  function fillRoutes() {
    const r = regionOf(DATA_COUNTIES[$("psCounty").value]);
    $("psRoute").innerHTML = '<option value="all">All routes</option>' + r.routes.map((x) => '<option value="' + x + '">' + x + "</option>").join("");
  }
  fillRoutes();
  const planMode = () => document.querySelector('input[name="pMode"]:checked').value;

  // ---- drawn polygon
  let drawing = false, drawPts = [], drawPoly = null, placingDepot = false;
  const drawLayer = L.layerGroup();
  // the drawn area and drawing modes belong to the planning page only
  function syncPlanSketch() {
    if (state.view === "plan") drawLayer.addTo(map);
    else { map.removeLayer(drawLayer); if (drawing) finishDraw(); if (placingDepot) stopPlacing(); }
  }
  function inPoly(ll, pts) { // ray casting on lat/lng
    let inside = false;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const [yi, xi] = [pts[i].lat, pts[i].lng], [yj, xj] = [pts[j].lat, pts[j].lng];
      if ((yi > ll[0]) !== (yj > ll[0]) && ll[1] < ((xj - xi) * (ll[0] - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  const midOf = (s) => s.coords[Math.floor(s.coords.length / 2)];
  function redrawSketch() {
    drawLayer.clearLayers();
    if (drawPoly) { L.polygon(drawPoly, { color: "#fe6f1a", weight: 2.5, fillOpacity: 0.08, dashArray: "6 4", interactive: false }).addTo(drawLayer); return; }
    if (drawPts.length) L.polyline(drawPts, { color: "#fe6f1a", weight: 2.5, dashArray: "6 4", interactive: false }).addTo(drawLayer);
    drawPts.forEach((p, i) => L.circleMarker(p, { radius: i ? 4 : 6, color: "#fe6f1a", fillColor: "#fff", fillOpacity: 1, weight: 2, interactive: false }).addTo(drawLayer));
  }
  function stopDrawing() { drawing = false; map.doubleClickZoom.enable(); map.getContainer().classList.remove("drawing"); $("drawStart").textContent = "Draw on map"; }
  function finishDraw() {
    // drop near-duplicate points from the double-click
    const pts = drawPts.filter((p, i) => i === 0 || map.latLngToContainerPoint(p).distanceTo(map.latLngToContainerPoint(drawPts[i - 1])) > 4);
    stopDrawing(); drawPts = [];
    if (pts.length < 3) { drawPoly = null; $("drawNote").textContent = "An area needs at least three corners. Try again."; redrawSketch(); onPlanAreaChange(); return; }
    drawPoly = pts; redrawSketch(); onPlanAreaChange(true);
  }
  $("drawStart").addEventListener("click", () => {
    if (drawing) { finishDraw(); return; }
    drawPoly = null; drawPts = []; redrawSketch(); stopPlacing();
    drawing = true; map.doubleClickZoom.disable(); map.getContainer().classList.add("drawing");
    $("drawStart").textContent = "Finish area";
    $("drawNote").textContent = "Click the map to add corners. Click the first corner or double-click to finish.";
    onPlanAreaChange();
  });
  $("drawClear").addEventListener("click", () => { stopDrawing(); drawPts = []; drawPoly = null; redrawSketch(); onPlanAreaChange(); });

  // ---- what the plan covers right now
  function planSel() {
    const mode = planMode();
    if (mode === "loc") {
      const region = DATA_COUNTIES[$("psCounty").value], route = $("psRoute").value;
      if ($("psState").value !== "17" || !region) return { ok: false, mode, msg: "Vegetation data is available for Champaign and Cook counties only." };
      return { ok: true, mode, region, filter: (s) => route === "all" || s.route === route };
    }
    if (mode === "draw") {
      if (!drawPoly) return { ok: false, mode, msg: drawing ? "Finish the area to continue." : "Draw an area on the map." };
      const inside = D.sites.filter((s) => inPoly(midOf(s), drawPoly));
      const regions = [...new Set(inside.map((s) => s.region))];
      if (!regions.length) return { ok: false, mode, msg: "No sites with vegetation data inside this area. Data is available in Champaign and Cook counties." };
      if (regions.length > 1) return { ok: false, mode, msg: "This area covers both Champaign and Cook counties. Draw inside one county." };
      const ids = new Set(inside.map((s) => s.id));
      return { ok: true, mode, region: regions[0], filter: (s) => ids.has(s.id) };
    }
    const picked = [...state.picked].map((id) => byId[id]);
    if (!picked.length) return { ok: false, mode, msg: "Pick at least one site on the map." };
    return { ok: true, mode, region: picked[0].region, filter: (s) => state.picked.has(s.id) };
  }
  function onPlanAreaChange(fit) {
    const sel = planSel();
    if (state.plan) { state.plan = null; planLayer.clearLayers(); $("planOut").hidden = true; } // selection changed: old plan no longer applies
    if (sel.ok) setRegion(sel.region);
    const flagged = sel.ok ? D.sites.filter((s) => s._rec && s.region === sel.region && sel.filter(s)).length : 0;
    $("pRun").disabled = !sel.ok || !flagged;
    $("pReady").hidden = sel.ok && flagged > 0;
    $("pReady").textContent = !sel.ok ? sel.msg : flagged ? "" : "No flagged sites in this selection.";
    if (sel.mode === "draw" && drawPoly) $("drawNote").textContent = sel.ok ? flagged + " flagged site(s) inside this area." : sel.msg;
    renderSites();
    if (fit && sel.ok && sel.mode !== "pick") {
      const pts = D.sites.filter((s) => s.region === sel.region && sel.filter(s)).flatMap((s) => [s.coords[0], s.coords[s.coords.length - 1]]);
      if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.08), fitPad());
    }
  }
  document.querySelectorAll('input[name="pMode"]').forEach((r) => r.addEventListener("change", () => {
    const m = planMode();
    $("pmLoc").hidden = m !== "loc"; $("pmDraw").hidden = m !== "draw"; $("pmPick").hidden = m !== "pick";
    if (m !== "draw") stopDrawing();
    onPlanAreaChange(m === "loc");
  }));
  $("psCounty").addEventListener("change", () => { fillRoutes(); onPlanAreaChange(true); });
  $("psRoute").addEventListener("change", () => onPlanAreaChange(true));

  // ---- depots: one row per depot; options are the depots of the selected county (plus any placed on the map)
  state.depotRows = [D.depots.find((d) => d.region === state.region).id];
  function renderDepotRows() {
    const opts = D.depots.filter((d) => d.region === state.region);
    $("depotRows").innerHTML = state.depotRows.map((id, i) =>
      '<div class="depot-row"><select data-i="' + i + '" aria-label="Staging area ' + (i + 1) + '">' +
      opts.map((d) => '<option value="' + d.id + '"' + (d.id === id ? " selected" : "") + (d.id !== id && state.depotRows.includes(d.id) ? " disabled" : "") + ">" + esc(d.name) + "</option>").join("") +
      "</select>" + (state.depotRows.length > 1 ? '<button type="button" class="row-x" data-i="' + i + '" aria-label="Remove staging area">×</button>' : "") + "</div>").join("");
    $("depotAdd").disabled = state.depotRows.length >= opts.length;
    renderDepotMarkers();
  }
  $("depotRows").addEventListener("change", (e) => { const sel = e.target.closest("select"); if (!sel) return; state.depotRows[+sel.dataset.i] = sel.value; renderDepotRows(); });
  $("depotRows").addEventListener("click", (e) => { const b = e.target.closest(".row-x"); if (!b) return; state.depotRows.splice(+b.dataset.i, 1); renderDepotRows(); });
  $("depotAdd").addEventListener("click", () => {
    const next = D.depots.find((d) => d.region === state.region && !state.depotRows.includes(d.id));
    if (!next) { toast("All staging areas in this county are added. Use Place on map for a new one."); return; }
    state.depotRows.push(next.id); renderDepotRows();
  });
  function stopPlacing() { placingDepot = false; map.getContainer().classList.remove("drawing"); $("depotPlace").textContent = "Place on map"; }
  $("depotPlace").addEventListener("click", () => {
    if (placingDepot) { stopPlacing(); return; }
    if (drawing) finishDraw();
    placingDepot = true; map.getContainer().classList.add("drawing"); $("depotPlace").textContent = "Cancel";
    toast("Click the map inside the selected county to place a staging area.");
  });
  let customN = 0;
  function placeDepot(ll) {
    const r = regionOf(state.region), b = L.latLngBounds(r.bounds).pad(0.15);
    if (!b.contains(ll)) { toast("Place the staging area inside " + r.name.split(" (")[0] + "."); return; }
    // connect to the nearest road-network node of this area
    let best = -1, bd = Infinity;
    G.nodes.forEach((n, i) => { if (!b.contains(n)) return; const d = map.distance(ll, n); if (d < bd) { bd = d; best = i; } });
    const d = { id: "S" + ++customN, region: state.region, name: "Custom staging area " + customN, latlng: [ll.lat, ll.lng], node: best, custom: true };
    D.depots.push(d);
    state.depotRows.push(d.id); renderDepotRows(); stopPlacing();
    toast(d.name + " added. It joins the road network at the nearest road (" + (bd / M_PER_MI).toFixed(1) + " mi).");
  }
  map.on("click", (e) => {
    if (placingDepot) { placeDepot(e.latlng); return; }
    if (!drawing) return;
    if (drawPts.length >= 3 && map.latLngToContainerPoint(drawPts[0]).distanceTo(e.containerPoint) < 12) { finishDraw(); return; }
    drawPts.push(e.latlng); redrawSketch();
  });
  map.on("dblclick", () => { if (drawing) finishDraw(); });
  renderDepotRows();

  // ---- objective explanation
  const OBJ_NOTE = {
    time: "Orders all selected sites so the whole job finishes in the shortest total time.",
    safety: "Treats sight-distance sites first, then the rest. The whole job may take a little longer.",
  };
  const syncObj = () => ($("objNote").textContent = OBJ_NOTE[document.querySelector('input[name="pObj"]:checked').value]);
  document.querySelectorAll('input[name="pObj"]').forEach((r) => r.addEventListener("change", syncObj));
  syncObj();

  // ---- (i) info tips: one floating box, so tips are not clipped by scrolling panels
  const tipBox = document.createElement("div"); tipBox.className = "info-tip"; tipBox.hidden = true; document.body.appendChild(tipBox);
  function showTip(el) {
    tipBox.textContent = el.dataset.tip; tipBox.hidden = false;
    const r = el.getBoundingClientRect(), w = tipBox.offsetWidth, h = tipBox.offsetHeight;
    let x = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8), y = r.top - h - 8;
    if (y < 8) y = r.bottom + 8;
    tipBox.style.left = x + "px"; tipBox.style.top = y + "px";
  }
  document.addEventListener("mouseover", (e) => { const el = e.target.closest(".info"); if (el) showTip(el); });
  document.addEventListener("mouseout", (e) => { if (e.target.closest(".info")) tipBox.hidden = true; });
  document.addEventListener("focusin", (e) => { const el = e.target.closest(".info"); if (el) showTip(el); });
  document.addEventListener("focusout", (e) => { if (e.target.closest(".info")) tipBox.hidden = true; });
  document.addEventListener("click", (e) => { if (e.target.closest(".info")) e.preventDefault(); }, true);

  /* ----------------------------------------------------- 10. national interstates (lazy) + road detail on demand */
  const canvasR = L.canvas({ padding: 0.3 });
  const usLayer = L.layerGroup();
  let US = null;
  const syncUS = () => { if (US && $("lyrUS").checked && map.getZoom() < 9) usLayer.addTo(map); else map.removeLayer(usLayer); };
  function buildRouteSearch() {
    const opts = [];
    Object.keys(US.index).sort((a, b) => parseInt(a.slice(2)) - parseInt(b.slice(2))).forEach((r) => {
      opts.push(r); Object.keys(US.index[r]).sort().forEach((st) => opts.push(r + " " + st));
    });
    $("routeList").innerHTML = opts.map((o) => '<option value="' + o + '">').join("");
  }
  const hiLayer = L.layerGroup().addTo(map);
  function goRoute() {
    const q = $("locRoute").value.trim().toUpperCase().replace(/^I\s*-?\s*/, "I-");
    const m = q.match(/^(I-\d+[A-Z]?)\s*([A-Z]{2})?$/);
    hiLayer.clearLayers();
    if (!US) { $("locNote").textContent = "The national interstate list is still loading. Try again in a moment."; return; }
    if (!m || !US.index[m[1]]) { $("locNote").textContent = "Route not found. Try a form like I-80 or I-80 IL."; return; }
    const boxes = m[2] ? [US.index[m[1]][m[2]]].filter(Boolean) : Object.values(US.index[m[1]]);
    if (!boxes.length) { $("locNote").textContent = m[1] + " does not run through " + m[2] + "."; return; }
    const b = L.latLngBounds(boxes.flatMap((x) => [[x[0], x[1]], [x[2], x[3]]]));
    const num = m[1].slice(2);
    US.lines.filter((l) => l[0] === num).forEach((l) => L.polyline(l[1], { color: "#fe6f1a", weight: 4, opacity: 0.85, renderer: canvasR, interactive: false }).addTo(hiLayer));
    map.fitBounds(b.pad(0.05), fitPad());
    $("locNote").textContent = "Showing " + m[1] + (m[2] ? " in " + m[2] : "") + ". Zoom in to load road detail from FHWA.";
  }
  $("locGo").addEventListener("click", goRoute);
  $("locRoute").addEventListener("keydown", (e) => { if (e.key === "Enter") goRoute(); });

  const NHS_URL = "https://geo.dot.gov/server/rest/services/Hosted/National_Highway_System_(20210815)/FeatureServer/0/query";
  const nhsLayer = L.layerGroup();
  const nhsCells = new Map(); const CELL = 0.25; let nhsRunning = false;
  const syncNHS = () => { if ($("lyrNHS").checked && map.getZoom() >= 10) nhsLayer.addTo(map); else map.removeLayer(nhsLayer); };
  async function loadNHS() {
    syncNHS();
    if (nhsRunning || !$("lyrNHS").checked || map.getZoom() < 10) return;
    const b = map.getBounds(); const cells = [];
    for (let y = Math.floor(b.getSouth() / CELL); y <= Math.floor(b.getNorth() / CELL); y++)
      for (let x = Math.floor(b.getWest() / CELL); x <= Math.floor(b.getEast() / CELL); x++) cells.push(x + ":" + y);
    const todo = cells.filter((c) => !nhsCells.has(c)).slice(0, 24);
    if (!todo.length) return;
    nhsRunning = true;
    const job = LoadKit.Mini.start("Road detail from FHWA"); let done = 0, feats = 0;
    for (const c of todo) {
      const [x, y] = c.split(":").map(Number); nhsCells.set(c, "loading");
      try {
        for (let off = 0; ; off += 2000) {
          const url = NHS_URL + "?where=1%3D1&geometry=" + [x * CELL, y * CELL, (x + 1) * CELL, (y + 1) * CELL].join(",") +
            "&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=sign1,lname,fclass,through_la,aadt" +
            "&outSR=4326&geometryPrecision=5&maxAllowableOffset=0.0001&resultOffset=" + off + "&resultRecordCount=2000&f=geojson";
          const gj = JSON.parse(await LoadKit.fetchText(url, 150000, (p) => job.set((done + p * 0.95) / todo.length)));
          L.geoJSON(gj, {
            style: (f) => ({ color: "#4b5563", weight: f.properties.fclass <= 1 ? 2.6 : f.properties.fclass <= 3 ? 2 : 1.3, opacity: 0.55, renderer: canvasR }),
            onEachFeature: (f, l) => { const q = f.properties; l.bindTooltip("<b>" + esc((q.sign1 || "").trim() || q.lname || "NHS route") + "</b>" + (q.lname && q.sign1 ? " · " + esc(q.lname) : "") + "<br>" + (q.through_la ? q.through_la + " lanes · " : "") + (q.aadt ? "AADT " + Number(q.aadt).toLocaleString("en-US") : "") + "<br><small>FHWA NHS 2021</small>", { sticky: true }); },
          }).addTo(nhsLayer);
          feats += gj.features ? gj.features.length : 0;
          if (!gj.exceededTransferLimit && (!gj.features || gj.features.length < 2000)) break;
        }
        nhsCells.set(c, "ok");
      } catch (e) { nhsCells.delete(c); job.set(done / todo.length, "FHWA server not reachable"); }
      done++; job.set(done / todo.length, done + "/" + todo.length + " areas · " + feats.toLocaleString("en-US") + " segments");
    }
    job.done(); nhsRunning = false;
    loadNHS(); // pick up cells that came into view while loading
  }
  let nhsTimer;
  map.on("moveend", () => { syncUS(); clearTimeout(nhsTimer); nhsTimer = setTimeout(loadNHS, 450); });
  $("lyrUS").addEventListener("change", syncUS);
  $("lyrNHS").addEventListener("change", loadNHS);

  async function loadNational() {
    const job = LoadKit.Mini.start("U.S. Interstates");
    try {
      await LoadKit.loadScript("data/us_interstates.js", 1361375, (p) => job.set(p * 0.9, "downloading"));
      US = window.US_INTERSTATES;
      US.lines.forEach((l) => L.polyline(l[1], { color: "#2b3f5d", weight: 1.6, opacity: 0.55, renderer: canvasR, interactive: false }).addTo(usLayer));
      buildRouteSearch(); syncUS(); job.done();
    } catch (e) { job.set(1, "could not load"); setTimeout(() => job.done(), 2500); }
  }

  /* ----------------------------------------------------- 11. photo credits (Home page) */
  $("credits").innerHTML = Object.entries(PHOTOS).map(([k, ph]) =>
    '<li><a href="' + ph[4] + '" target="_blank" rel="noopener">' + esc(ph[1]) + "</a> — " + esc(ph[2]) + ", " +
    (LIC_URL[ph[3]] ? '<a href="' + LIC_URL[ph[3]] + '" target="_blank" rel="noopener">' + esc(ph[3]) + "</a>" : esc(ph[3])) +
    ' <span class="muted">(' + esc(k.replace("/", ": ")) + ")</span></li>").join("") +
    '<li class="muted">Height and cover schematics are drawn by the portal.</li>';

  syncOutputs();
  setView((location.hash || "#home").slice(1));
  onPlanAreaChange();
  if (window.LoadKit) { LoadKit.Big.hide(); loadNational(); }
})();
