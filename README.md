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
| **Home** | Project overview, research flow (Tasks 1–7), project facts. |
| **Vegetation Information** | Roadside sites in both demo areas (Champaign–Urbana and Chicago), shown together. Click a site for details, photos, and its inspection and control history. You can add records, attach photos, upload GeoJSON or CSV data, export the site layer (GeoJSON/CSV), and screen the network with adjustable triggers. |
| **Operations Planning** | Choose the sites by location (state → county → route, or all routes), by drawing an area on the map, or by picking sites. Add staging areas from the county list or place your own on the map. Other inputs: drone model, number of crews, work hours, wind and spray volume. Outputs: a recommended action for each site (drone spraying, mowing or inspection), routes on the map, schedule, duration and herbicide use. Exports schedule (CSV) and routes (GeoJSON). |
| **Drone Technology** | Market survey table (Task 1.2) and key FAA rules. |
| **Team** | Research team, IDOT contacts, pooled fund chairs. |

## Files

```
index.html          page layout
css/style.css       design
js/app.js           map, screening rules, planning heuristic
js/pages.js         loads first: switches the simple pages, builds the drone table (drone specs live here)
js/loader.js        progress ring; loads Leaflet and the data files, then js/app.js
data/data.js        sites (Champaign + Chicago), routing network, mileposts (generated)
data/hpms.js        HPMS 2024 highway network layer (generated)
data/us_interstates.js  national interstate overview + route search index (generated)
img/vegetation/     illustrations (photos are linked from Wikimedia Commons)
img/drones/         product images for the Drone Technology page
lib/leaflet/        Leaflet 1.9.4 map library (local copy)
tools/gen_data.py   regenerates data/data.js
```

## Data

- **Real:**
  - Road network, lanes, speed limits and traffic (AADT): FHWA HPMS 2024, Champaign and Cook counties (`08_GIS_Data/Highways_HPMS_2024_Illinois`).
  - Interstate mileposts: IDOT IL Milepost layer (`08_GIS_Data/Mileposts_IDOT`). Sites on I-74 and I-57 are cut at real mileposts (e.g. I-74 EB, MP 181–182). US-45 has no milepost signs, so its sites use IDOT county log miles.
  - Drone specifications: the project's market survey.
- **Example data:** vegetation, inspection and control history, and herbicide rates. Replace these when IDOT or field data arrives.
- Demo regions:
  - Champaign–Urbana: I-74 (MP 169–197), I-57 (MP 218–257), US-45 north and south. 192 sites.
  - Chicago area (Cook County): I-55 (MP 276–294), I-57 (MP 338–358), I-80 (MP 149–163). 100 sites.
- Anywhere else in the U.S.: choose a state/county or search an interstate; road detail loads from FHWA when you zoom in.
- To regenerate the data (from the project root):

```bash
python 05_Website_Prototype/tools/gen_data.py 08_GIS_Data 05_Website_Prototype/data
```

## Photos

Representative photos come from Wikimedia Commons (CC BY, CC BY-SA, CC0 or public domain). Every vegetation class and growth stage has a photo. Credits are listed on the Home page and in each site card, with links to the source pages. The illustrations in `img/vegetation/` are only a fallback if a photo cannot load.

## Next steps (back end)

The planning function `buildPlan()` in `js/app.js` is a placeholder heuristic. Later, it will be replaced by a call to a Python (FastAPI) back end that runs the optimization model. The inputs are already collected in `readPlanInputs()`.
