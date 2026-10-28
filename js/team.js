/* Team page: map of the pooled fund member states.
   data/us_states.js (built by tools/gen_us_states.py from Census TIGERweb) loads only when the page opens.
   Pointing at a state, or at its chip, highlights both and shows the agency's role. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const LEAD = "IN";
  const MEMBERS = ["IN", "CA", "CO", "IL", "KS", "MI", "MN", "MS", "MO", "ND", "PA", "TX"]; // lead first, then alphabetical by name
  const ROLE = { IN: "Lead agency · Indiana DOT", IL: "Member · Illinois DOT supports this project; the research team is at the University of Illinois" };

  let started = false;
  function maybeStart() {
    if (location.hash.slice(1) !== "team" || started || !$("usMap")) return;
    started = true;
    const s = document.createElement("script");
    s.src = "data/us_states.js";
    s.onload = build;
    s.onerror = () => { $("usMap").querySelector(".map-load").textContent = "The map could not load. Member states: " + MEMBERS.join(", ") + "."; };
    document.head.appendChild(s);
  }
  window.addEventListener("hashchange", maybeStart);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", maybeStart); else maybeStart();

  function build() {
    const U = window.US_STATES, box = $("usMap");
    const byAbbr = Object.fromEntries(U.states.map((s) => [s.abbr, s]));
    const cls = (a) => "st" + (a === LEAD ? " lead" : MEMBERS.includes(a) ? " member" : "");
    const [ux, uy] = U.uiuc;
    box.innerHTML = '<svg viewBox="0 0 ' + U.w + " " + U.h + '" aria-hidden="true">' +
      U.states.map((s) => '<path d="' + s.d + '" class="' + cls(s.abbr) + '" data-abbr="' + s.abbr + '"/>').join("") +
      '<circle cx="' + ux + '" cy="' + uy + '" r="14" class="uiuc-pulse"/><circle cx="' + ux + '" cy="' + uy + '" r="6.5" class="uiuc-dot"/>' +
      "</svg>" + '<div class="map-tip" hidden></div>';
    $("stateChips").innerHTML = MEMBERS.map((a) =>
      '<button type="button" class="chip' + (a === LEAD ? " lead" : "") + '" data-abbr="' + a + '" aria-pressed="false">' + esc(byAbbr[a].name) + (a === LEAD ? " <small>lead</small>" : "") + "</button>").join("");

    const svg = box.querySelector("svg"), tip = box.querySelector(".map-tip");
    function show(abbr, at) {
      svg.querySelectorAll(".hl").forEach((p) => p.classList.remove("hl"));
      document.querySelectorAll("#stateChips .chip").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.abbr === abbr)));
      if (!abbr) { tip.hidden = true; return; }
      const path = svg.querySelector('path[data-abbr="' + abbr + '"]');
      path.classList.add("hl");
      svg.appendChild(path); // draw on top so the outline is not hidden by neighbours
      svg.appendChild(svg.querySelector(".uiuc-pulse")); svg.appendChild(svg.querySelector(".uiuc-dot"));
      const member = MEMBERS.includes(abbr);
      tip.innerHTML = "<b>" + esc(byAbbr[abbr].name) + "</b>" + (member ? "<span>" + esc(ROLE[abbr] || "Member state DOT") + "</span>" : "<span>Not a pooled fund member</span>");
      tip.hidden = false;
      // place the tip at the pointer, or above the state when chosen from a chip
      const r = box.getBoundingClientRect();
      let x, y;
      if (at) { x = at.clientX - r.left; y = at.clientY - r.top; }
      else { const b = path.getBBox(), k = svg.getBoundingClientRect().width / U.w; x = (b.x + b.width / 2) * k; y = b.y * k; }
      tip.style.left = Math.max(8, Math.min(r.width - tip.offsetWidth - 8, x - tip.offsetWidth / 2)) + "px";
      tip.style.top = Math.max(4, y - tip.offsetHeight - 10) + "px";
    }
    svg.addEventListener("pointermove", (e) => { const p = e.target.closest("path"); if (p) show(p.dataset.abbr, e); });
    svg.addEventListener("pointerleave", () => show(null));
    const chipEv = (e) => { const c = e.target.closest(".chip"); if (c) show(c.dataset.abbr); };
    $("stateChips").addEventListener("pointerover", chipEv);
    $("stateChips").addEventListener("focusin", chipEv);
    $("stateChips").addEventListener("click", chipEv);
    $("stateChips").addEventListener("pointerleave", () => show(null));
    $("stateChips").addEventListener("focusout", (e) => { if (!$("stateChips").contains(e.relatedTarget)) show(null); });
  }
})();
