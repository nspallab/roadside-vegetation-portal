"""Generate demo data for the Roadside Vegetation Portal (multi-region).

REAL inputs (from gis_source_data/ in the repository; 08_GIS_Data in the project Box folder):
  - FHWA HPMS 2024 Illinois: Champaign County (f_system 1-4) and statewide interstates/freeways (f_system 1-2)
  - IDOT IL Milepost (2021-22 LiDAR sign inventory)
  - IDOT district facilities: maintenance yards (team section headquarters), used as crew staging areas
  - FHWA/BTS NHS 2021 US interstates (for the national overview layer and route index)
SYNTHETIC: vegetation, inspection and control records (example data for the prototype).

Usage:
  python tools/gen_data.py gis_source_data data      (from the repository root)
Writes data.js (window.VEG_DATA), hpms.js (window.HPMS_BG), us_interstates.js (window.US_INTERSTATES).
"""
import json, math, random, datetime as dt, sys, statistics, collections, os, re

random.seed(74)
GIS, OUT = sys.argv[1], sys.argv[2]
hp_champ = json.load(open(f"{GIS}/Highways_HPMS_2024_Illinois/HPMS_2024_IL_Champaign_County_FS1-4.geojson"))["features"]
hp_state = json.load(open(f"{GIS}/Highways_HPMS_2024_Illinois/HPMS_2024_IL_Interstates_Freeways.geojson"))["features"]
mp = json.load(open(f"{GIS}/Mileposts_IDOT/IDOT_Mileposts_Illinois.geojson"))["features"]
# IDOT maintenance yards, by facility number (the part of Fac_Name before " - ", e.g. "543" or "E34")
yards = {f["properties"]["Fac_Name"].split(" - ")[0].strip(): f for f in json.load(open(f"{GIS}/IDOT_Facilities/IDOT_Maintenance_Yards_Illinois.geojson"))["features"]}
us_i = json.load(open(f"{GIS}/Highways_NHS_2021/NHS_2021_US_Interstates_simplified.geojson"))["features"]

# ------------------------------------------------------------------ regions
REGIONS = [
    {"id": "champaign", "code": "CU", "name": "Champaign–Urbana (Champaign County)", "county": 19, "origin": (40.13, -88.25),
     "hpms": hp_champ,
     "corridors": [
         ("I-74", "I-74", "Interstate 74", ["010  10074 000000"], "010_10074_000000"),
         ("I-57", "I-57", "Interstate 57", ["010  10057 000000"], "010_10057_000000"),
         ("US-45N", "US-45", "US Route 45 north (Urbana to Rantoul)", ["010  20800 000000"], None),
         ("US-45S", "US-45", "US Route 45 south (Champaign to Tolono)", ["010  20804 000000"], None)],
     "depots": ["543", "544"]},
    {"id": "chicago", "code": "CHI", "name": "Chicago area (Cook County)", "county": 31, "origin": (41.70, -87.75),
     "hpms": [f for f in hp_state if f["properties"]["county_id"] == 31],
     "corridors": [
         ("I-55", "I-55", "Interstate 55 (Stevenson Expressway)", ["016  10055 000000"], "016_10055_000000"),
         ("I-57", "I-57", "Interstate 57 (south Cook County)", ["016  10057 000000"], "016_10057_000000"),
         ("I-80", "I-80", "Interstate 80 (south Cook County)", ["016  10080 000000"], "016_10080_000000")],
     "depots": ["E34", "E26", "031", "032", "E33", "E25"]},
]

class Proj:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111320 * math.cos(math.radians(lat0)); self.ky = 110950
    def xy(self, lonlat): return ((lonlat[0] - self.lon0) * self.kx, (lonlat[1] - self.lat0) * self.ky)
    def ll(self, x, y): return [round(y / self.ky + self.lat0, 5), round(x / self.kx + self.lon0, 5)]

def chain(hp, P, route_ids):
    pts = []
    for rid in route_ids:
        segs = sorted([f for f in hp if f["properties"]["route_id"] == rid], key=lambda f: f["properties"]["begin_point"])
        for f in segs:
            p = f["properties"]; xy = [P.xy(q) for q in f["geometry"]["coordinates"]]
            if pts and math.dist(pts[-1][:2], xy[-1]) < math.dist(pts[-1][:2], xy[0]): xy.reverse()
            L = sum(math.dist(a, b) for a, b in zip(xy, xy[1:])) or 1; acc = 0
            for i, q in enumerate(xy):
                if i: acc += math.dist(xy[i - 1], q)
                m = p["begin_point"] + (p["end_point"] - p["begin_point"]) * acc / L
                if pts and math.dist(pts[-1][:2], q) < 1: continue
                pts.append((q[0], q[1], m, p))
    return pts

def sign_value(txt):
    """'181' -> 181.0 ; enhanced reference marker '149; 81' -> 149.81"""
    m = re.fullmatch(r"\s*(\d+)\s*(?:;\s*(\d{1,2}))?\s*", str(txt))
    if not m: return None
    return int(m.group(1)) + (int(m.group(2)) / 100 if m.group(2) else 0)
def mp_offset(key):
    vals = [sign_value(f["properties"]["SIGN_LEGEN"]) - f["properties"]["START_ODOM"] for f in mp
            if f["properties"]["ROUTE_NUMB"] == key and sign_value(f["properties"]["SIGN_LEGEN"]) is not None]
    return round(statistics.median(vals), 2) if vals else None

def resample(pts, step=100.0):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        d = math.dist(a[:2], b[:2]); n = max(1, int(d // step))
        for k in range(1, n + 1):
            t = k / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, b[3] if t > .5 else a[3]))
    return out

def offset(P, line, off):
    res = []
    for i in range(len(line)):
        a = line[max(0, i - 1)]; b = line[min(len(line) - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dy) or 1
        res.append(P.ll(line[i][0] + dy / L * off, line[i][1] - dx / L * off))
    return res

# ------------------------------------------------------------------ synthetic vegetation
SPECIES = [
    ("Canada thistle", "Noxious broadleaf", "aminopyralid", 14), ("Musk thistle", "Noxious broadleaf", "aminopyralid", 6),
    ("Poison hemlock", "Invasive broadleaf", "triclopyr_24d", 9), ("Wild parsnip", "Invasive broadleaf", "aminopyralid", 8),
    ("Cut-leaved teasel", "Invasive broadleaf", "triclopyr_24d", 7), ("Johnsongrass", "Noxious grass", "glyphosate", 8),
    ("Reed canary grass", "Invasive grass", "imazapic", 5), ("Bush honeysuckle", "Woody brush", "triclopyr_24d", 6),
    ("Autumn olive", "Woody brush", "triclopyr_24d", 4), ("Tall fescue / smooth brome", "Turf grass (desirable)", None, 30),
]
STAGES = {
    "Noxious broadleaf": ["Rosette", "Bolting", "Flowering", "Seed set", "Fall regrowth"],
    "Invasive broadleaf": ["Rosette", "Bolting", "Flowering", "Seed set"],
    "Noxious grass": ["Vegetative", "Boot", "Flowering", "Seed set"],
    "Invasive grass": ["Vegetative", "Flowering", "Seed set"],
    "Woody brush": ["Leaf-out", "Full leaf", "Fruiting", "Dormant"],
    "Turf grass (desirable)": ["Vegetative", "Heading", "Seed set"],
}
HERBS = {
    "aminopyralid": {"name": "Aminopyralid", "use": "Thistles, wild parsnip (selective broadleaf)", "rate_gal_ac": 0.055},
    "triclopyr_24d": {"name": "Triclopyr + 2,4-D", "use": "Broadleaf weeds and woody brush", "rate_gal_ac": 0.5},
    "glyphosate": {"name": "Glyphosate", "use": "Johnsongrass spot treatment (non-selective)", "rate_gal_ac": 0.5},
    "imazapic": {"name": "Imazapic", "use": "Invasive grasses", "rate_gal_ac": 0.0625},
}
TODAY = dt.date(2026, 10, 20)
def rdate(lo, hi): return (TODAY - dt.timedelta(days=random.randint(lo, hi))).isoformat()
def history(herb, crew):
    ev = [{"date": rdate(120, 160), "type": "Ground inspection", "by": crew + " crew", "note": "Routine windshield survey"}]
    if random.random() < .7: ev.append({"date": rdate(60, 110), "type": "Mowing", "by": crew + " mower", "note": "Safety strip, 15 ft"})
    if herb and random.random() < .45:
        ev.append({"date": rdate(40, 90), "type": random.choice(["Ground spray (boom truck)", "Drone spot spray"]), "by": "Contractor", "note": HERBS[herb]["name"] + " applied"})
    if random.random() < .6: ev.append({"date": rdate(5, 40), "type": "Drone inspection", "by": "UIUC research team", "note": "RGB imagery, 120 ft AGL"})
    return sorted(ev, key=lambda e: e["date"])

ROW_FT = 30
CREW = {"champaign": "IDOT D5", "chicago": "IDOT D1"}

roads_out, sites, mileposts, meta_routes, depots = [], [], [], [], []
CONNECTORS = []
nodes, adj = [], []          # one graph, regions are separate components
region_out = []

for R in REGIONS:
    P = Proj(*R["origin"])
    centerlines = {}
    for key, ref, name, rids, mpkey in R["corridors"]:
        line = resample(chain(R["hpms"], P, rids))
        centerlines[key] = line
        roads_out.append({"region": R["id"], "key": key, "ref": ref, "name": name, "coords": [P.ll(p[0], p[1]) for p in line]})
        off = mp_offset(mpkey) if mpkey else None
        val = [p[2] + (off or 0) for p in line]
        dy = line[-1][1] - line[0][1]; dx = line[-1][0] - line[0][0]
        dirs = (("EB", "WB") if dx > 0 else ("WB", "EB")) if abs(dx) > abs(dy) else (("NB", "SB") if dy > 0 else ("SB", "NB"))
        lo, hi = math.ceil(min(val)), math.floor(max(val))
        meta_routes.append({"region": R["id"], "key": key, "ref": ref, "mp_offset": off, "from": round(min(val), 2), "to": round(max(val), 2)})
        for m0 in range(int(lo), int(hi)):
            idx = [i for i, v in enumerate(val) if m0 - 0.001 <= v <= m0 + 1.001]
            if len(idx) < 3: continue
            part = [line[i] for i in idx]; mid = part[len(part) // 2]; hpp = mid[3]
            length_mi = abs(val[idx[-1]] - val[idx[0]])
            for dirn, o in ((dirs[0], 40), (dirs[1], -40)):
                nm, cls, herb, _ = random.choices(SPECIES, weights=[s[3] for s in SPECIES])[0]
                dens = int(4 + random.betavariate(1.6, 3.2) * 70) if herb else random.randint(75, 100)
                hgt = {"Woody brush": random.randint(30, 96), "Turf grass (desirable)": max(5, int(random.gauss(12, 4.5)))}.get(cls, max(6, int(random.gauss(15, 7))))
                label = ("MP " if off is not None else "County mile ") + f"{m0}–{m0 + 1}"
                sid = f"{R['code']}-{key.replace('-', '')}-{dirn}-{'MP' if off is not None else 'CM'}{m0:03d}"
                sites.append({
                    "id": sid, "region": R["id"], "route": ref, "corridor": key, "dir": dirn, "label": label, "mp_from": m0, "mp_to": m0 + 1,
                    "length_mi": round(length_mi, 2), "area_ac": round(length_mi * 5280 * ROW_FT / 43560, 2),
                    "species": nm, "vclass": cls, "herbicide": herb, "height_in": hgt, "density_pct": dens,
                    "stage": random.choice(STAGES[cls]), "sight_concern": random.random() < .10,
                    "last_inspected": rdate(3, 75), "inspection_method": random.choice(["Drone (RGB)", "Drone (multispectral)", "Ground"]),
                    "history": history(herb, CREW[R["id"]]),
                    "roadway": {"lanes": hpp.get("through_lanes"), "speed": hpp.get("speed_limit"), "aadt": hpp.get("aadt"),
                                "area": "Rural" if hpp.get("urban_id") == 99999 else "Urban", "nhs": bool(hpp.get("nhs")),
                                "hpms_route_id": hpp.get("route_id").strip(), "county_mile": round(mid[2], 2)},
                    "coords": offset(P, part, o), "_mid": mid[:2], "_P": P,
                })
    # graph for this region
    base = {}
    for key, line in centerlines.items():
        base[key] = len(nodes)
        for i, p in enumerate(line):
            nodes.append(P.ll(p[0], p[1])); adj.append([])
            if i:
                a, b = len(nodes) - 2, len(nodes) - 1; d = round(math.dist(line[i - 1][:2], p[:2]))
                adj[a].append([b, d]); adj[b].append([a, d])
    keys = list(centerlines); links = {}
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            A, B = centerlines[keys[i]], centerlines[keys[j]]
            best = min(((math.dist(p[:2], q[:2]), a, b) for a, p in enumerate(A) for b, q in enumerate(B)))
            links[keys[i] + "/" + keys[j]] = round(best[0])
            if best[0] < 800:
                u, v = base[keys[i]] + best[1], base[keys[j]] + best[2]; d = round(best[0])
                adj[u].append([v, d]); adj[v].append([u, d])
    # connect any remaining components with an approximate local-road connector (straight distance x 1.4)
    comp = {}
    def find(x):
        while comp.get(x, x) != x: x = comp[x]
        return x
    def union(a, b): comp[find(a)] = find(b)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if links[keys[i] + "/" + keys[j]] < 800: union(keys[i], keys[j])
    pairs = sorted(((links[keys[i] + "/" + keys[j]], keys[i], keys[j]) for i in range(len(keys)) for j in range(i + 1, len(keys))))
    for d0, ka, kb in pairs:
        if find(ka) == find(kb): continue
        A, B = centerlines[ka], centerlines[kb]
        best = min(((math.dist(p[:2], q[:2]), a, b) for a, p in enumerate(A) for b, q in enumerate(B)))
        u, v = base[ka] + best[1], base[kb] + best[2]; d = round(best[0] * 1.4)
        adj[u].append([v, d]); adj[v].append([u, d]); union(ka, kb)
        CONNECTORS.append({"region": R["id"], "between": [ka, kb], "straight_m": round(best[0]), "weight_m": d, "a": nodes[u], "b": nodes[v]})
    print(R["id"], "junction gaps (m):", links)
    rng = range(base[keys[0]], len(nodes))
    def nearest(xy):
        return min(rng, key=lambda k: math.dist(P.xy([nodes[k][1], nodes[k][0]]), xy))
    for s in sites:
        if s["region"] == R["id"] and "_mid" in s:
            s["mid_node"] = nearest(s.pop("_mid")); s.pop("_P")
    for did in R["depots"]:
        q, (lon, lat) = yards[did]["properties"], yards[did]["geometry"]["coordinates"][:2]
        ll = [round(lat, 5), round(lon, 5)]
        nm = "IDOT " + q["Fac_Name"].split(" - ", 1)[-1].strip().title() + " yard (" + did + ")"
        xy = P.xy([ll[1], ll[0]]); k = nearest(xy)
        nodes.append([round(ll[0], 5), round(ll[1], 5)]); adj.append([]); n = len(nodes) - 1
        d = round(math.dist(xy, P.xy([nodes[k][1], nodes[k][0]])))
        adj[n].append([k, d]); adj[k].append([n, d])
        depots.append({"id": did, "region": R["id"], "name": nm, "latlng": ll, "node": n, "address": (q["Address"] or "").strip().title(), "district": q["District"]})
    # mileposts for this county
    pref = "%03d_" % (10 if R["id"] == "champaign" else 16)
    seen = set()
    for f in mp:
        q = f["properties"]
        if not q["ROUTE_NUMB"].startswith(pref) or not f["geometry"]: continue
        if not str(q["SIGN_LEGEN"]).strip().isdigit(): continue   # map shows whole-mile signs only
        key2 = (q["ROUTE_NUMB"], q["SIGN_LEGEN"], q["DIRECTION"])
        if key2 in seen: continue
        seen.add(key2)
        lon, lat = f["geometry"]["coordinates"][:2]
        mileposts.append({"ll": [round(lat, 5), round(lon, 5)], "route": "I-%d" % int(re.match(r"\d{3}_1(\d{4})", q["ROUTE_NUMB"]).group(1)), "mp": q["SIGN_LEGEN"], "region": R["id"]})
    allc = [c for r in roads_out if r["region"] == R["id"] for c in r["coords"]]
    region_out.append({"id": R["id"], "name": R["name"], "bounds": [[min(c[0] for c in allc), min(c[1] for c in allc)], [max(c[0] for c in allc), max(c[1] for c in allc)]],
                       "routes": sorted({r["ref"] for r in roads_out if r["region"] == R["id"]})})

DRONES = [
    {"id": "ares", "model": "ARES HYL-150", "brand": "Hylio", "tank_gal": 13.0, "prod_ac_hr": 70, "rate_note": "@ 2 GPA",
     "battery": "18S 30Ah LiPo, 14 kg", "price": "$29,000 base / $46,000 configured", "us": True,
     "liquid": "110 lb (50 kg) · 13 gal (50 L)", "solid": "110 lb (50 kg) · 20 gal (76 L)",
     "productivity": "Liquid up to 70 ac/h @ 2 GPA; solid up to 120 ac/h @ 20 lb/ac",
     "empty_weight": "80 lb (36 kg)", "avoidance": "4 lateral + 1 upward 62 GHz radars, 1 downward 24 GHz radar",
     "compliance": "NDAA FY2019 Sec. 889 & FY2020 Sec. 848; FCC Part 15"},
    {"id": "t40", "model": "Agras T40", "brand": "DJI", "tank_gal": 10.6, "prod_ac_hr": 52.6, "rate_note": "21.3 ha/h @ 15 L/ha",
     "battery": "30 Ah, 52.22 V, ~12 kg", "price": "Not available in the U.S.", "us": False,
     "liquid": "40 kg · 40 L", "solid": "50 kg · 70 L",
     "productivity": "Liquid up to 21.3 ha/h @ 15 L/ha; solid 1.5 t/h @ 149 kg/ha",
     "empty_weight": "38 kg without battery, 50 kg with", "avoidance": "Omnidirectional radar, 1.5–50 m horizontal",
     "compliance": "Currently unavailable in the U.S."},
    {"id": "pegasus", "model": "PEGASUS HYL-30", "brand": "Hylio", "tank_gal": 2.5, "prod_ac_hr": 13, "rate_note": "@ 2 gal/ac",
     "battery": "12S 16Ah LiPo, 4.5 kg", "price": "$15,000 base / $27,000 configured", "us": True,
     "liquid": "20–21 lb (9.5 kg) · 2.5 gal (9.5 L)", "solid": "20–21 lb (9.5 kg) · 4 gal (15.1 L)",
     "productivity": "Liquid up to 13 ac/h @ 2 gal/ac; solid up to 22 ac/h @ 20 lb/ac",
     "empty_weight": "13 lb without battery and payload equipment", "avoidance": "Wide-angle radar sphere; 3-axis gimbal + 1080p RGB camera",
     "compliance": "NDAA FY2019 Sec. 889 & FY2020 Sec. 848; FCC Part 15"},
]

out = {
    "meta": {"as_of": TODAY.isoformat(), "row_ft": ROW_FT, "routes": meta_routes,
             "note": "Road geometry, lanes, speed limits and AADT from FHWA HPMS 2024; mileposts from IDOT. Vegetation, inspection and control records are synthetic examples."},
    "regions": region_out, "roads": roads_out, "sites": sites, "mileposts": mileposts,
    "graph": {"nodes": nodes, "adj": adj, "connectors": CONNECTORS}, "depots": depots, "drones": DRONES, "herbicides": HERBS,
}
open(f"{OUT}/data.js", "w").write("/* Generated by tools/gen_data.py. Roads: FHWA HPMS 2024. Vegetation: synthetic. */\nwindow.VEG_DATA = " + json.dumps(out, separators=(",", ":")) + ";\n")

# ------------------------------------------------------------------ HPMS background (per region)
def dp_simplify(coords, P, eps):
    xy = [P.xy(q) for q in coords]
    keep = [0, len(xy) - 1]; stack = [(0, len(xy) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2: continue
        x0, y0 = xy[a]; x1, y1 = xy[b]; L = math.hypot(x1 - x0, y1 - y0) or 1e-9
        k, dmax = a, 0
        for i in range(a + 1, b):
            d = abs((x1 - x0) * (y0 - xy[i][1]) - (x0 - xy[i][0]) * (y1 - y0)) / L
            if d > dmax: k, dmax = i, d
        if dmax > eps: keep.append(k); stack += [(a, k), (k, b)]
    return [[round(coords[i][1], 5), round(coords[i][0], 5)] for i in sorted(set(keep))]
bg = collections.defaultdict(list)
for R in REGIONS:
    P = Proj(*R["origin"])
    for f in R["hpms"]:
        p = f["properties"]
        name = (("I-" if p["routesigning"] == 2 else "US-" if p["routesigning"] == 3 else "IL-" if p["routesigning"] == 4 else "") + str(p["routenumber"])) if p["routenumber"] else (p["routename"] or "")
        bg[p["f_system"]].append([dp_simplify(f["geometry"]["coordinates"], P, 8.0), name, p["through_lanes"], p["speed_limit"], p["aadt"]])
open(f"{OUT}/hpms.js", "w").write("/* FHWA HPMS 2024 Illinois: Champaign County f_system 1-4, Cook County f_system 1-2. [coords, name, lanes, speed, aadt] by f_system */\nwindow.HPMS_BG = " + json.dumps(bg, separators=(",", ":")) + ";\n")

# ------------------------------------------------------------------ national interstates overview + route index
STATES = {1:"AL",2:"AK",4:"AZ",5:"AR",6:"CA",8:"CO",9:"CT",10:"DE",11:"DC",12:"FL",13:"GA",15:"HI",16:"ID",17:"IL",18:"IN",19:"IA",20:"KS",21:"KY",22:"LA",23:"ME",24:"MD",25:"MA",26:"MI",27:"MN",28:"MS",29:"MO",30:"MT",31:"NE",32:"NV",33:"NH",34:"NJ",35:"NM",36:"NY",37:"NC",38:"ND",39:"OH",40:"OK",41:"OR",42:"PA",44:"RI",45:"SC",46:"SD",47:"TN",48:"TX",49:"UT",50:"VT",51:"VA",53:"WA",54:"WV",55:"WI",56:"WY",72:"PR"}
PUS = Proj(39.0, -96.0)
lines, index = [], collections.defaultdict(lambda: collections.defaultdict(lambda: [999, 999, -999, -999]))
for f in us_i:
    p = f["properties"]; g = f["geometry"]
    if not g: continue
    num = (p.get("signn1") or "").strip()
    if not num: continue
    parts = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
    st = STATES.get(int(p["stfips"]), str(p["stfips"]))
    for c in parts:
        if len(c) < 2: continue
        s = dp_simplify(c, PUS, 1500.0)
        s = [[round(a, 2), round(b, 2)] for a, b in s]
        lines.append([num, s])
        bb = index["I-" + num][st]
        for la, lo in s:
            bb[0] = min(bb[0], la); bb[1] = min(bb[1], lo); bb[2] = max(bb[2], la); bb[3] = max(bb[3], lo)
# merge pieces per route by dropping degenerate segments
lines = [l for l in lines if len(l[1]) >= 2 and l[1][0] != l[1][-1]]
idx_out = {r: {s: v for s, v in d.items()} for r, d in index.items()}
open(f"{OUT}/us_interstates.js", "w").write("/* FHWA/BTS NTAD National Highway System 2021, Interstates, simplified ~1.5 km for the national overview. [route number, [[lat,lng],...]] + route-state bounding boxes */\nwindow.US_INTERSTATES = " +
    json.dumps({"lines": lines, "index": idx_out}, separators=(",", ":")) + ";\n")

for fn in ("data.js", "hpms.js", "us_interstates.js"):
    print(fn, os.path.getsize(f"{OUT}/{fn}") // 1024, "KB")
print(len(sites), "sites:", collections.Counter(s["region"] + ":" + s["corridor"] for s in sites))
print("mileposts by region:", collections.Counter(m["region"] for m in mileposts), "routes meta:", meta_routes)
