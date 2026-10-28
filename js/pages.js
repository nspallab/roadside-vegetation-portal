/* Simple pages, loaded first so they appear at once even on a slow phone connection,
   before Leaflet and the ~1 MB map data arrive:
   - switches Home / Drone Technology / Team until app.js takes over (window.Pages.ready = true)
   - builds the Drone Technology table. window.DRONES is also used by app.js for planning
     (it overrides the copy in data/data.js). swath_m is a planning assumption for drawing spray passes, not a spec-sheet value. */
(function () {
  "use strict";
  const VIEWS = ["home", "veg", "plan", "drones", "team"];
  window.Pages = { ready: false, MAP_VIEWS: ["veg", "plan"] };
  function show() {
    if (window.Pages.ready) return;
    let v = location.hash.slice(1); if (!VIEWS.includes(v)) v = "home";
    document.querySelectorAll(".navbar a").forEach((a) => (a.dataset.view === v ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    document.querySelectorAll("[data-page]").forEach((p) => (p.hidden = p.dataset.page !== v));
  }
  window.addEventListener("hashchange", show);
  show();
  window.DRONES = [
    {
      "id": "ares",
      "model": "ARES HYL-150",
      "brand": "Hylio",
      "tank_gal": 13.0,
      "swath_m": 7.6,
      "prod_ac_hr": 70,
      "rate_note": "@ 2 GPA",
      "battery": "18S 30Ah LiPo, 14 kg",
      "price": "$29,000 base / $46,000 configured",
      "us": true,
      "liquid": "110 lb (50 kg) · 13 gal (50 L)",
      "solid": "110 lb (50 kg) · 20 gal (76 L)",
      "productivity": "Liquid up to 70 ac/h @ 2 GPA; solid up to 120 ac/h @ 20 lb/ac",
      "empty_weight": "80 lb (36 kg)",
      "avoidance": "4 lateral + 1 upward 62 GHz radars, 1 downward 24 GHz radar",
      "compliance": "NDAA FY2019 Sec. 889 & FY2020 Sec. 848; FCC Part 15"
    },
    {
      "id": "t40",
      "model": "Agras T40",
      "brand": "DJI",
      "tank_gal": 10.6,
      "swath_m": 11,
      "prod_ac_hr": 52.6,
      "rate_note": "21.3 ha/h @ 15 L/ha",
      "battery": "30 Ah, 52.22 V, ~12 kg",
      "price": "Not available in the U.S.",
      "us": false,
      "liquid": "40 kg · 40 L",
      "solid": "50 kg · 70 L",
      "productivity": "Liquid up to 21.3 ha/h @ 15 L/ha; solid 1.5 t/h @ 149 kg/ha",
      "empty_weight": "38 kg without battery, 50 kg with",
      "avoidance": "Omnidirectional radar, 1.5–50 m horizontal",
      "compliance": "Currently unavailable in the U.S."
    },
    {
      "id": "pegasus",
      "model": "PEGASUS HYL-30",
      "brand": "Hylio",
      "tank_gal": 2.5,
      "swath_m": 4.6,
      "prod_ac_hr": 13,
      "rate_note": "@ 2 gal/ac",
      "battery": "12S 16Ah LiPo, 4.5 kg",
      "price": "$15,000 base / $27,000 configured",
      "us": true,
      "liquid": "20–21 lb (9.5 kg) · 2.5 gal (9.5 L)",
      "solid": "20–21 lb (9.5 kg) · 4 gal (15.1 L)",
      "productivity": "Liquid up to 13 ac/h @ 2 gal/ac; solid up to 22 ac/h @ 20 lb/ac",
      "empty_weight": "13 lb without battery and payload equipment",
      "avoidance": "Wide-angle radar sphere; 3-axis gimbal + 1080p RGB camera",
      "compliance": "NDAA FY2019 Sec. 889 & FY2020 Sec. 848; FCC Part 15"
    }
  ];
  // product images (img/drones) and manufacturer pages
  const PHOTO = {
    ares: { src: "img/drones/ares.webp", w: 792, h: 314, link: "https://www.hyl.io/ares" },
    t40: { src: "img/drones/t40.webp", w: 765, h: 486, link: "https://www.dji.com/t40" },
    pegasus: { src: "img/drones/pegasus.webp", w: 792, h: 438, link: "https://www.hyl.io/pegasus" },
  };
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const D = window.DRONES;
  const rows = [["Brand", (d) => esc(d.brand)], ["Liquid payload", (d) => esc(d.liquid)], ["Solid payload", (d) => esc(d.solid)],
    ["Productivity", (d) => esc(d.productivity)], ["Battery", (d) => esc(d.battery)], ["Empty weight", (d) => esc(d.empty_weight)],
    ["Obstacle avoidance", (d) => esc(d.avoidance)],
    ["Regulatory status", (d) => '<span class="badge ' + (d.us ? "ok" : "no") + '">' + (d.us ? "U.S. eligible" : "Not available in U.S.") + "</span><br>" + esc(d.compliance)],
    ["Price", (d) => esc(d.price)],
    ["Spray swath <small>(planning assumption)</small>", (d) => esc(d.swath_m + " m (" + Math.round(d.swath_m / 0.3048) + " ft)")]];
  const photoCell = (d) => {
    const ph = PHOTO[d.id];
    if (!ph) return "<td></td>";
    return '<td><a class="dr-photo" href="' + ph.link + '" target="_blank" rel="noopener" title="' + esc(d.brand + " " + d.model + " — manufacturer page") + '">' +
      '<picture><source srcset="' + ph.src + '" type="image/webp"><img src="' + ph.src.replace(".webp", ".jpg") + '" width="' + ph.w + '" height="' + ph.h + '" alt="' + esc(d.brand + " " + d.model) + '"></picture></a>' +
      '<a class="dr-link" href="' + ph.link + '" target="_blank" rel="noopener">' + esc(ph.link.replace("https://www.", "")) + " ↗</a></td>";
  };
  const t = document.getElementById("marketTable");
  if (t) t.innerHTML = "<thead><tr><th></th>" + D.map((d) => "<th>" + esc(d.model) + "<small>" + esc(d.brand) + "</small></th>").join("") + "</tr></thead><tbody>" +
    "<tr><th>Photo</th>" + D.map(photoCell).join("") + "</tr>" +
    rows.map(([k, f]) => "<tr><th>" + k + "</th>" + D.map((d) => "<td>" + f(d) + "</td>").join("") + "</tr>").join("") + "</tbody>";
})();
