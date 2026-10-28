/* 3D drone viewer on the Drone Technology page.
   three.js (lib/three) loads only when the page is opened. The models in img/drones/3d are simplified drones built in
   Blender to published dimensions by tools/gen_drones_blender.py; each prop_N node spins about its hub (userData.spin = ±1). */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  // model facts not in the market table: rotor layout and prop size
  const EXTRA = {
    ares: { rotors: "4 rotors", prop: "56 in props" },
    t40: { rotors: "8 rotors (4 coaxial pairs)", prop: "54 in props" },
    pegasus: { rotors: "4 rotors", prop: "30 in props" },
  };
  const drone = (id) => (window.DRONES || []).find((d) => d.id === id);
  // hover labels, by node name without its _N suffix
  const PART = (id) => {
    const d = drone(id) || {};
    return {
      tank: "Spray tank · " + (d.liquid || ""), battery: "Battery · " + (d.battery || ""), prop: "Propeller · " + EXTRA[id].prop.replace(" props", ""),
      motor: "Brushless motor", nozzle: id === "t40" ? "Centrifugal atomizing sprinkler" : "Spray nozzle", hoses: "Spray lines from pump to nozzles",
      radar: "Obstacle-avoidance and altitude radar", gear: "Landing gear", arm: "Carbon-fibre arm", body: "Frame, flight controller and pump",
      camera: "1080p RGB camera", gimbal: "3-axis gimbal", antenna: "Radio antenna",
    };
  };
  const SPRAY_PARTS = ["tank", "nozzle", "hoses"];
  const partOf = (name) => name.replace(/_(\d+|up|down|front|rear|left|right)$/, "");

  let started = false;
  function maybeStart() {
    if (location.hash.slice(1) !== "drones" || started || !$("v3Canvas")) return;
    started = true;
    ["lib/three/three.min.js", "lib/three/GLTFLoader.js", "lib/three/OrbitControls.js"]
      .reduce((p, src) => p.then(() => new Promise((res, rej) => { const s = document.createElement("script"); s.src = src; s.onload = res; s.onerror = () => rej(new Error(src)); document.head.appendChild(s); })), Promise.resolve())
      .then(init)
      .catch(() => { $("v3Load").textContent = "The 3D viewer could not load. The specification table below has the same information."; });
  }
  window.addEventListener("hashchange", maybeStart);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", maybeStart); else maybeStart();

  function init() {
    const T = window.THREE, canvas = $("v3Canvas"), stage = canvas.parentElement;
    if (!T || !window.WebGLRenderingContext) { $("v3Load").textContent = "3D needs WebGL, which this browser does not provide."; return; }
    const renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.outputEncoding = T.sRGBEncoding;
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFSoftShadowMap;
    const scene = new T.Scene();
    scene.add(new T.HemisphereLight(0xffffff, 0x9aa3ad, 0.85));
    const sun = new T.DirectionalLight(0xffffff, 0.9);
    sun.position.set(3, 6, 4); sun.castShadow = true; sun.shadow.mapSize.set(1024, 1024);
    Object.assign(sun.shadow.camera, { left: -3, right: 3, top: 3, bottom: -3, near: 0.5, far: 20 });
    scene.add(sun);
    const ground = new T.Mesh(new T.CircleGeometry(4, 48), new T.ShadowMaterial({ opacity: 0.16 }));
    ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; scene.add(ground);
    const grid = new T.GridHelper(6, 12, 0xc9ced6, 0xe1e4e8); grid.position.y = 0.001; scene.add(grid); // 0.5 m cells
    const camera = new T.PerspectiveCamera(32, 1, 0.05, 60);
    const controls = new T.OrbitControls(camera, canvas);
    Object.assign(controls, { enableDamping: true, enablePan: false, enableZoom: false, minPolarAngle: 0.15, maxPolarAngle: Math.PI / 2 - 0.02, autoRotateSpeed: 1.1 });

    const loader = new T.GLTFLoader(), cache = {};
    let cur = null, curId = null, props = [];
    function frame(obj) {
      const box = new T.Box3().setFromObject(obj), size = box.getSize(new T.Vector3()), c = box.getCenter(new T.Vector3());
      const r = Math.max(size.x, size.z, size.y * 1.6) * 0.42, d = r / Math.sin(T.MathUtils.degToRad(camera.fov / 2)) * (camera.aspect < 1 ? 1.35 : 1);
      controls.target.set(0, c.y * 0.7, 0);
      camera.position.set(d * 0.62, c.y + d * 0.42, d * 0.66);
      controls.update();
    }
    function show(id) {
      curId = id;
      document.querySelectorAll("#v3Tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.id === id)));
      renderInfo(id);
      const go = (root) => {
        if (curId !== id) return;
        if (cur) scene.remove(cur);
        cur = root; scene.add(root);
        props = []; root.traverse((o) => { if (/^prop_\d+$/.test(o.name)) props.push(o); });
        applyHighlight(); frame(root);
        $("v3Load").hidden = true;
      };
      if (cache[id]) { go(cache[id]); return; }
      $("v3Load").hidden = false; $("v3Load").textContent = "Loading 3D model…";
      loader.load("img/drones/3d/" + id + ".glb", (g) => {
        g.scene.traverse((o) => {
          if (!o.isMesh) return;
          o.castShadow = true; o.material = o.material.clone();
          let p = o; while (p && !PART(id)[partOf(p.name)]) p = p.parent; // nearest named part
          o.userData.part = p ? partOf(p.name) : "";
          o.userData.orig = { opacity: o.material.opacity, transparent: o.material.transparent, emissive: o.material.emissive ? o.material.emissive.getHex() : 0 };
        });
        cache[id] = g.scene; go(g.scene);
      }, undefined, () => { $("v3Load").textContent = "Could not load the " + id + " model."; });
    }
    function applyHighlight() {
      if (!cur) return;
      const on = $("v3Spray").checked;
      cur.traverse((o) => {
        if (!o.isMesh) return;
        const m = o.material, sp = SPRAY_PARTS.includes(o.userData.part), O = o.userData.orig;
        m.transparent = on && !sp ? true : O.transparent; m.opacity = on && !sp ? 0.16 : O.opacity; m.depthWrite = !(on && !sp); o.castShadow = !(on && !sp);
        if (m.emissive) m.emissive.setHex(on && sp ? 0x7a2e00 : O.emissive);
        m.needsUpdate = true;
      });
    }
    function renderInfo(id) {
      const d = drone(id); if (!d) return;
      $("v3Info").innerHTML = '<p class="v3-brand">' + esc(d.brand) + '</p><h3 class="v3-name">' + esc(d.model) + "</h3>" +
        '<dl class="v3-facts"><div><dt>Spray tank</dt><dd>' + esc(d.tank_gal) + " gal</dd></div><div><dt>Rated output</dt><dd>" + esc(d.prod_ac_hr) + " ac/h</dd></div>" +
        "<div><dt>Rotors</dt><dd>" + esc(EXTRA[id].rotors) + "</dd></div><div><dt>Props</dt><dd>" + esc(EXTRA[id].prop.replace(" props", "")) + "</dd></div></dl>" +
        '<span class="badge ' + (d.us ? "ok" : "no") + '">' + (d.us ? "U.S. eligible" : "Not available in U.S.") + "</span>";
    }

    $("v3Tabs").innerHTML = ["ares", "t40", "pegasus"].map((id) => { const d = drone(id); return '<button type="button" role="tab" data-id="' + id + '" aria-selected="false">' + esc(d ? d.model : id) + "</button>"; }).join("");
    $("v3Tabs").addEventListener("click", (e) => { const b = e.target.closest("button[data-id]"); if (b) show(b.dataset.id); });
    $("v3Spray").addEventListener("change", applyHighlight);

    // hover a part to see what it is
    const ray = new T.Raycaster(), ptr = new T.Vector2();
    canvas.addEventListener("pointermove", (e) => {
      if (!cur || e.buttons) { $("v3Tip").hidden = true; return; }
      const r = canvas.getBoundingClientRect();
      ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ptr, camera);
      const hit = ray.intersectObject(cur, true).find((h) => h.object.userData.part && h.object.material.opacity > 0.5);
      const label = hit && PART(curId)[hit.object.userData.part];
      $("v3Tip").hidden = !label;
      if (label) { $("v3Tip").textContent = label; $("v3Tip").style.left = (e.clientX - r.left + 12) + "px"; $("v3Tip").style.top = (e.clientY - r.top + 12) + "px"; }
    });
    canvas.addEventListener("pointerleave", () => ($("v3Tip").hidden = true));

    const resize = () => {
      const w = stage.clientWidth, h = stage.clientHeight; if (!w || !h) return;
      renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
      if (cur) frame(cur);
    };
    new ResizeObserver(resize).observe(stage);
    resize();

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { $("v3Spin").checked = false; $("v3Auto").checked = false; }
    let last = performance.now();
    renderer.setAnimationLoop((now) => {
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      if ($("view-drones").hidden) return; // page not shown: skip drawing
      if ($("v3Spin").checked) props.forEach((p) => (p.rotation.y += (p.userData.spin || 1) * dt * 22));
      controls.autoRotate = $("v3Auto").checked;
      controls.update();
      renderer.render(scene, camera);
    });
    show("ares");
  }
})();
