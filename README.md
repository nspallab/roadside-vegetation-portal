# Roadside Vegetation Portal (prototype)

A front-end prototype for the AMT Phase 2 pooled fund project TPF-5(559): drone-based herbicide spraying for roadside vegetation control.

## How to open it

**Simplest way:** double-click `index.html`. It opens in your browser, with no server needed.

**As a local web server** (closer to how it will be hosted later):

```bash
cd 05_Website_Prototype
python -m http.server 8000
```

Then open http://localhost:8000 in a browser.

You need an internet connection for the map background (Esri tiles, no API key), web fonts, the representative photos (Wikimedia Commons), and on-demand road detail (FHWA) and county lookups (Census TIGERweb). Everything else works offline.

A circular progress ring shows loading progress at startup and for background jobs.

## Logo

The header uses a placeholder mark. To use the official University of Illinois Block I, put the image file at `img/logo.png` (the same file INTERMODAL uses, or one from the university brand site). It will replace the placeholder automatically.

## What it shows

| Page | Purpose |
|---|---|
| **Home** | Hero with the main actions, a live snapshot of the demo network (sites, miles, acres, sites needing control), links to the three tools, the demo areas and a short project summary. Reading pages share a footer with data sources. |
| **Vegetation Information** | Roadside sites in both demo areas (Champaign–Urbana and Chicago), shown together. Zoom in to see each site's roadside vegetation area (the 30 ft right-of-way strip) and, closer still, the weed patches inside it. Click a segment or area for vegetation type, height, cover, growth stage, a priority score, a ground photo and a drone view (satellite imagery of the site with its strip and patches), and the inspection and control history. Add records (optionally with a new height, cover or stage), attach photos, upload field updates as CSV or GeoJSON (rows with a `site_id` update that site and add records; the template button gives an example), export the site layer, and screen the network with adjustable triggers. The site list ranks flagged sites by priority. |
| **Operations Planning** | Choose the sites by location (state → county → route, or all routes), by drawing an area on the map, or by picking sites. The Recommended actions card lists each flagged site with its action (drone spot spraying, mowing or further inspection) and reason; the planner can change or drop any of them. Crews start from IDOT maintenance yards (or a place you put on the map). Other inputs: drone model, number of crews, work hours, wind and spray volume. Outputs: routes on the map, schedule, duration and herbicide use, plus a timeline (Gantt chart and Play slider) that moves each crew along its route. Zoomed in, the map shows the drone's spray passes over the weed patches and the mower's passes along the strip. Exports schedule (CSV) and routes (GeoJSON). |
| **Drone Technology** | Interactive 3D models of the three spray drones (drag to turn, spinning rotors, spray-system highlight, part names on hover), the market survey table (Task 1.2) and key FAA rules. |
| **Team** | Faculty and researchers at the University of Illinois, IDOT contacts and pooled fund chairs, and a map of the 12 pooled fund member states with Indiana DOT as lead agency. Headshots are in `img/team/<first-last>.jpg` (square, 400 px): faculty from the CEE directory, Prof. Ouyang's students from his group page, and Shayan Bafandkar and Tina Radvand from the team. A profile without a photo shows initials. |

## Files

```
index.html          page layout
css/style.css       design
js/app.js           map, screening rules, planning heuristic
js/pages.js         loads first: switches the simple pages, builds the drone table (drone specs live here)
js/loader.js        progress ring; loads Leaflet and the data files, then js/app.js
js/drones3d.js      3D drone viewer; loads three.js only when the Drone Technology page opens
js/team.js          member-state map on the Team page; loads data/us_states.js only when the page opens
data/data.js        sites (Champaign + Chicago), routing network, mileposts (generated)
data/hpms.js        HPMS 2024 highway network layer (generated)
data/us_interstates.js  national interstate overview + route search index (generated)
data/us_states.js   lower-48 state outlines for the Team map (generated)
img/vegetation/     illustrations (photos are linked from Wikimedia Commons)
img/drones/         product images for the Drone Technology page
img/drones/3d/      3D drone models (.glb), built by tools/gen_drones_blender.py
img/hero-drone.webp Home page hero image (ARES model render, tools/render_hero.py)
lib/leaflet/        Leaflet 1.9.4 map library (local copy)
lib/three/          three.js r147 with GLTFLoader and OrbitControls (local copy, MIT)
tools/gen_data.py   regenerates data/data.js, data/hpms.js, data/us_interstates.js
tools/gen_drones_blender.py  regenerates img/drones/3d/*.glb in Blender
tools/render_hero.py         renders the Home hero image from the ARES model in Blender
tools/gen_us_states.py       regenerates data/us_states.js
gis_source_data/    source GIS files (FHWA HPMS 2024, FHWA NHS 2021, IDOT mileposts, IDOT maintenance yards, Census state boundaries)
```

## Data

- **Real:**
  - Road network, lanes, speed limits and traffic (AADT): FHWA HPMS 2024, Champaign and Cook counties (`gis_source_data/Highways_HPMS_2024_Illinois`).
  - Interstate mileposts: IDOT IL Milepost layer (`gis_source_data/Mileposts_IDOT`). Sites on I-74 and I-57 are cut at real mileposts (e.g. I-74 EB, MP 181–182). US-45 has no milepost signs, so its sites use IDOT county log miles.
  - Crew staging areas: IDOT maintenance yards from the IDOT district facilities layer (`gis_source_data/IDOT_Facilities`), e.g. 543 Champaign (201 Eisner Road) and E34 Interstate 57 (Markham).
  - Drone view imagery: Esri World Imagery, standing in for the project's drone orthomosaics.
  - State outlines on the Team page: Census TIGERweb (generalized), `gis_source_data/Census_States`.
  - Drone specifications: the project's market survey.
- **Example data:** vegetation, inspection and control history, and herbicide rates. Replace these when IDOT or field data arrives.
- **Illustrative:** weed patch outlines (their total area matches each site's weed cover), drone spray swaths (a planning assumption shown in the drone table), coverage paths and the priority score weights.
- Demo regions:
  - Champaign–Urbana: I-74 (MP 169–197), I-57 (MP 218–257), US-45 north and south. 192 sites.
  - Chicago area (Cook County): I-55 (MP 276–294), I-57 (MP 338–358), I-80 (MP 149–163). 100 sites.
- Anywhere else in the U.S.: choose a state/county or search an interstate; road detail loads from FHWA when you zoom in.
- To regenerate the data (from the repository root; the output is identical to the files in `data/`):

```bash
python tools/gen_data.py gis_source_data data
```

To regenerate the 3D drone models (Blender 4.x):

```bash
blender -b --factory-startup --python tools/gen_drones_blender.py -- img/drones/3d
```

## Design

The navy header band and orange navigation bar use the University of Illinois colours and stay as they are. Reading pages (Home, Drone Technology, Team) are full width: each section is a band across the window with its content in a centred column up to 1440 px. Elsewhere, orange text and filled buttons use UIUC Altgeld orange (`--orange-ink`, #C84113, 4.97:1 on white) so they meet WCAG AA contrast; Illini Orange stays for accents. Fonts are Montserrat (headings) and Source Sans 3 (body). Interactive targets are at least 24 px, focus rings are visible, a skip link appears on keyboard focus, and motion respects reduced-motion settings.

## Photos

Representative photos come from Wikimedia Commons (CC BY, CC BY-SA, CC0 or public domain). Every vegetation class and growth stage has a photo. Credits are listed on the Home page and in each site card, with links to the source pages. The illustrations in `img/vegetation/` are only a fallback if a photo cannot load.

## Next steps (back end)

The planning function `buildPlan()` in `js/app.js` is a placeholder heuristic. Later, it will be replaced by a call to a Python (FastAPI) back end that runs the optimization model. The inputs are already collected in `readPlanInputs()`.
