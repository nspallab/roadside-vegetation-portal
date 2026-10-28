"""Original schematic illustrations for the Roadside Vegetation Portal.
Writes img/vegetation/class/*.svg and img/vegetation/stage/*.svg (240x160 viewBox).
Replace any file with a real photo of the same name (or .jpg + update app.js IMG map) later."""
import math, random, os, sys

OUT = sys.argv[1]
W, H, BASE = 240, 160, 140   # plant base (ground line) at y=140

def frame(body, title):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 12 {W} {H-12}" role="img" aria-label="{title}">
<title>{title}</title>
<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e8f1f8"/><stop offset="1" stop-color="#f6f8f4"/></linearGradient></defs>
<rect width="{W}" height="{H}" fill="url(#sky)"/>
<path d="M0 {BASE-6} Q60 {BASE-10} 120 {BASE-7} T240 {BASE-6} V{H} H0Z" fill="#a9c98a"/>
<rect y="{H-12}" width="{W}" height="12" fill="#5f656c"/>
<rect y="{H-12}" width="{W}" height="2" fill="#f4f4f0"/>
{body}
</svg>'''

R = random.Random(7)
def blade(x, base, h, lean, color, w=1.6):
    tx = x + lean; cx = x + lean * 0.3
    return f'<path d="M{x:.1f} {base} Q{cx:.1f} {base-h*0.6:.1f} {tx:.1f} {base-h:.1f}" stroke="{color}" stroke-width="{w}" fill="none" stroke-linecap="round"/>'

def grass_clump(x, h, n=14, spread=14, color="#4f8a3a", w=1.8, base=BASE):
    s = ""
    for i in range(n):
        xi = x + R.uniform(-spread / 3, spread / 3)
        s += blade(xi, base, h * R.uniform(.7, 1.05), R.uniform(-spread, spread), R.choice([color, "#5f9c45", "#3f7a30"]), w)
    return s

def turf_band(h=14, x0=0, x1=W, dens=3):
    s = ""
    x = x0
    while x < x1:
        s += blade(x, BASE + 2, h * R.uniform(.7, 1.1), R.uniform(-3, 3), R.choice(["#5f9c45", "#4f8a3a", "#6aa84f"]), 1.4)
        x += R.uniform(1.2, dens)
    return s

def leaf(x, y, L, ang, wd, color, stroke="#2f5d25"):
    a = math.radians(ang)
    tx, ty = x + L * math.cos(a), y - L * math.sin(a)
    nx, ny = -math.sin(a) * wd, -math.cos(a) * wd
    mx, my = (x + tx) / 2, (y + ty) / 2
    return (f'<path d="M{x:.1f} {y:.1f} Q{mx+nx:.1f} {my+ny:.1f} {tx:.1f} {ty:.1f} Q{mx-nx:.1f} {my-ny:.1f} {x:.1f} {y:.1f}Z" '
            f'fill="{color}" stroke="{stroke}" stroke-width=".6"/>')

def spiny_leaf(x, y, L, ang, color="#4e8b3d"):
    a = math.radians(ang); pts = []
    for i in range(9):
        t = i / 8; r = 7 * math.sin(math.pi * t) * (1.25 if i % 2 else .55)
        px, py = x + L * t * math.cos(a), y - L * t * math.sin(a)
        pts.append((px - math.sin(a) * r, py - math.cos(a) * r))
    for i in range(8, -1, -1):
        t = i / 8; r = 7 * math.sin(math.pi * t) * (1.25 if i % 2 else .55)
        px, py = x + L * t * math.cos(a), y - L * t * math.sin(a)
        pts.append((px + math.sin(a) * r, py + math.cos(a) * r))
    return '<polygon points="' + " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in pts) + f'" fill="{color}" stroke="#2f5d25" stroke-width=".6"/>'

def stem(x, y0, y1, color="#4a7c34", w=2.2, bend=0):
    return f'<path d="M{x} {y0} Q{x+bend} {(y0+y1)/2} {x+bend*0.4} {y1}" stroke="{color}" stroke-width="{w}" fill="none" stroke-linecap="round"/>'

def thistle_head(x, y, s=1, color="#a24bb5"):
    return (f'<ellipse cx="{x}" cy="{y+4*s}" rx="{6*s}" ry="{6*s}" fill="#6f9a4a" stroke="#3f6a2a" stroke-width=".8"/>'
            + "".join(f'<line x1="{x}" y1="{y+2*s}" x2="{x+9*s*math.cos(math.radians(a)):.1f}" y2="{y+2*s-9*s*math.sin(math.radians(a)):.1f}" stroke="{color}" stroke-width="{1.6*s}" stroke-linecap="round"/>' for a in range(30, 151, 15)))

def umbel(x, y, r=16, color="#e8c62f", n=9):
    s = ""
    for i in range(n):
        a = math.radians(200 + i * (140 / (n - 1)))
        px, py = x + r * math.cos(a), y + r * math.sin(a) * .55
        s += f'<line x1="{x}" y1="{y+6}" x2="{px:.1f}" y2="{py:.1f}" stroke="#5f8f3f" stroke-width=".9"/>'
        for j in range(5):
            s += f'<circle cx="{px+R.uniform(-3,3):.1f}" cy="{py+R.uniform(-2.5,1):.1f}" r="1.6" fill="{color}"/>'
    return s

def shrub(x, scale=1.0, leaves="#3f7f3a", berries=False, bare=False, leaf_scale=1.0, dry=False):
    s = ""
    stems = [(-18, -60), (-6, -78), (8, -74), (20, -56), (0, -50)]
    tips = []
    for dx, dy in stems:
        tx, ty = x + dx * scale, BASE + dy * scale
        s += f'<path d="M{x} {BASE} Q{x+dx*0.3*scale:.1f} {BASE+dy*0.5*scale:.1f} {tx:.1f} {ty:.1f}" stroke="{"#8a7a6a" if dry else "#6b4a2a"}" stroke-width="{2.6*scale:.1f}" fill="none" stroke-linecap="round"/>'
        for k in range(3):
            bx, by = x + dx * scale * (0.5 + 0.2 * k), BASE + dy * scale * (0.5 + 0.2 * k)
            ex, ey = bx + R.uniform(-14, 14) * scale, by - R.uniform(6, 14) * scale
            s += f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="{"#8a7a6a" if dry else "#6b4a2a"}" stroke-width="{1.2*scale:.1f}" stroke-linecap="round"/>'
            tips.append((ex, ey))
        tips.append((tx, ty))
    if not bare:
        for (tx, ty) in tips:
            for k in range(4 if leaf_scale >= 1 else 3):
                s += leaf(tx, ty, R.uniform(8, 12) * leaf_scale * scale, R.uniform(0, 360), 3.6 * leaf_scale * scale, R.choice([leaves, "#4f8f45", "#367035"]))
    if berries:
        for (tx, ty) in tips[::2]:
            for k in range(3):
                s += f'<circle cx="{tx+R.uniform(-5,5):.1f}" cy="{ty+R.uniform(-2,6):.1f}" r="2.2" fill="#c62f2f" stroke="#7a1414" stroke-width=".4"/>'
    return s

def rosette(x, y=BASE - 2, r=26, colors=("#4e8b3d", "#5f9c45"), spiny=True, n=10):
    s = ""
    for i in range(n):
        a = i * 360 / n + R.uniform(-8, 8)
        L = r * R.uniform(.8, 1.05)
        a2 = math.radians(a)
        ex, ey = x + L * math.cos(a2), y + L * math.sin(a2) * .28
        ang = math.degrees(math.atan2(-(ey - y), ex - x))
        s += spiny_leaf(x, y, math.hypot(ex - x, ey - y), ang, R.choice(colors)) if spiny else leaf(x, y, math.hypot(ex - x, ey - y), ang, 5, R.choice(colors))
    return s

def panicle_open(x, y, color="#9c4a3a", n=10, L=20):
    """Open, pyramid-shaped panicle: branches leave the main axis and droop outward."""
    s = stem(x, y + 34, y, "#6b8a4a", 1.4)
    for i in range(n):
        yy = y + 3 + i * 3; side = -1 if i % 2 else 1; Li = L * (0.35 + 0.65 * i / n)
        ex, ey = x + side * Li, yy + Li * 0.55
        s += f'<path d="M{x} {yy:.1f} Q{x+side*Li*0.5:.1f} {yy-2:.1f} {ex:.1f} {ey:.1f}" stroke="#7a5a3a" stroke-width=".8" fill="none"/>'
        for k in range(3):
            t = 0.45 + 0.25 * k
            s += f'<ellipse cx="{x+side*Li*t:.1f}" cy="{yy+(ey-yy)*t*t:.1f}" rx="1.1" ry="2" fill="{color}"/>'
    return s

def spike(x, y, h=16, color="#c9a46a", w=3.2):
    return f'<ellipse cx="{x}" cy="{y}" rx="{w}" ry="{h/2}" fill="{color}" stroke="#8a6a3a" stroke-width=".6"/>'

def label_svg(name, body):
    return frame(body, name)

CLASSES, STAGES = {}, {}

# ---------------- classes ----------------
b = turf_band(10)
for x in (70, 165):
    b += stem(x, BASE, BASE - 88, bend=R.uniform(-6, 6))
    for k, yy in enumerate(range(BASE - 20, BASE - 80, -16)):
        b += spiny_leaf(x, yy, 26, 25 if k % 2 else 155)
    b += thistle_head(x - 2, BASE - 98) + thistle_head(x + 12, BASE - 86, .8)
b += rosette(118, r=30)
CLASSES["noxious-broadleaf"] = ("Noxious broadleaf (e.g., Canada thistle)", b)

b = turf_band(10)
for x, h in ((80, 100), (160, 88)):
    b += stem(x, BASE, BASE - h, "#5b8e3e", 2.6)
    for yy in range(BASE - 18, BASE - h + 20, -20):
        b += leaf(x, yy, 22, R.choice([20, 160]), 7, "#6aa84f")
        b += leaf(x, yy - 8, 18, R.choice([35, 145]), 6, "#5f9c45")
    b += umbel(x, BASE - h - 6, 20)
    b += stem(x, BASE - h + 30, BASE - h - 6 + 20, "#5b8e3e", 1.4, bend=18) + umbel(x + 20, BASE - h + 14, 11)
CLASSES["invasive-broadleaf"] = ("Invasive broadleaf (e.g., wild parsnip, poison hemlock)", b)

b = turf_band(10)
for x in (60, 120, 180):
    b += grass_clump(x, 92, n=9, spread=22, color="#4c8a3c", w=3.2)
    b += panicle_open(x + R.uniform(-4, 4), BASE - 118, "#a2493a")
CLASSES["noxious-grass"] = ("Noxious grass (e.g., Johnsongrass)", b)

b = turf_band(10)
for x in range(30, 230, 18):
    b += grass_clump(x, 84 + R.uniform(-8, 8), n=6, spread=8, color="#5a8f45", w=1.7)
    b += stem(x, BASE - 70, BASE - 98, "#6b8f4a", 1.2) + spike(x, BASE - 100, 16, "#c7b1d6")
CLASSES["invasive-grass"] = ("Invasive grass (e.g., reed canary grass)", b)

b = turf_band(10) + shrub(80, 1.15, berries=True) + shrub(170, .95, berries=True)
CLASSES["woody-brush"] = ("Woody brush (e.g., bush honeysuckle, autumn olive)", b)

b = turf_band(34, dens=1.2) + turf_band(26, dens=1.6) + turf_band(18, dens=2.0)
for x in range(14, 240, 38):
    b += f'<circle cx="{x}" cy="{BASE-30}" r="2.6" fill="#f7f7f2"/><circle cx="{x}" cy="{BASE-30}" r="1.1" fill="#e8c62f"/>'
CLASSES["turf"] = ("Turf grass, desirable (e.g., tall fescue, smooth brome)", b)

# ---------------- stages ----------------
STAGES["rosette"] = ("Rosette", turf_band(8) + rosette(120, r=52, n=14))
STAGES["fall-regrowth"] = ("Fall regrowth", turf_band(8, dens=2.6) + stem(150, BASE, BASE - 80, "#9a7b55", 2) + thistle_head(150, BASE - 88, .9, "#b9a48a")
                          + rosette(100, r=46, colors=("#7f9a3d", "#b07a2f", "#5f8a3d")))
STAGES["vegetative"] = ("Vegetative", turf_band(8) + grass_clump(80, 86, 20, 26) + grass_clump(165, 78, 18, 24))
b = turf_band(8) + shrub(120, 1.2, leaves="#9fd17a", leaf_scale=.45)
STAGES["leaf-out"] = ("Leaf-out", b)
b = turf_band(8) + rosette(120, r=26) + stem(120, BASE - 4, BASE - 92)
for yy in (BASE - 40, BASE - 64):
    b += spiny_leaf(120, yy, 18, R.choice([30, 150]))
b += "".join(f'<ellipse cx="{120+dx}" cy="{BASE-96+abs(dx)/2}" rx="3.6" ry="4.6" fill="#7aa64f" stroke="#3f6a2a" stroke-width=".6"/>' for dx in (-6, 0, 6))
STAGES["bolting"] = ("Bolting", b)
b = turf_band(8)
for x in (90, 150):
    b += grass_clump(x, 70, 10, 16)
    for dx in (-5, 0, 5):
        b += stem(x + dx, BASE, BASE - 84, "#5d8a3d", 1.6) + f'<ellipse cx="{x+dx}" cy="{BASE-80}" rx="3.2" ry="9" fill="#6aa84f" stroke="#3f6a2a" stroke-width=".6"/>'
STAGES["boot"] = ("Boot", b)
b = turf_band(8)
for x in (90, 150):
    b += grass_clump(x, 70, 10, 16)
    for dx in (-5, 0, 5):
        b += stem(x + dx, BASE, BASE - 90, "#5d8a3d", 1.6) + spike(x + dx, BASE - 96, 14, "#b9c97a", 2.6)
STAGES["heading"] = ("Heading", b)
STAGES["full-leaf"] = ("Full leaf", turf_band(8) + shrub(120, 1.3))
b = turf_band(8)
for x in (85, 155):
    b += stem(x, BASE, BASE - 86) + spiny_leaf(x, BASE - 40, 22, 30) + spiny_leaf(x, BASE - 58, 20, 150)
    b += thistle_head(x, BASE - 96) + thistle_head(x + 14, BASE - 82, .8)
b += umbel(120, BASE - 70, 16) + stem(120, BASE, BASE - 64, "#5b8e3e", 2)
STAGES["flowering"] = ("Flowering", b)
STAGES["fruiting"] = ("Fruiting", turf_band(8) + shrub(120, 1.3, berries=True))
b = turf_band(8, dens=2.4)
for x in (85, 155):
    b += stem(x, BASE, BASE - 86, "#8f7a4a") + spiny_leaf(x, BASE - 50, 18, 30, "#9a8a4a")
    b += thistle_head(x, BASE - 96, 1, "#efe9dc")
    for k in range(7):
        sx, sy = x + R.uniform(10, 70), BASE - 100 - R.uniform(-10, 30)
        b += f'<g stroke="#bdb6a6" stroke-width=".7"><line x1="{sx:.1f}" y1="{sy:.1f}" x2="{sx:.1f}" y2="{sy+6:.1f}"/>' + "".join(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{sx+4*math.cos(math.radians(a)):.1f}" y2="{sy-4*math.sin(math.radians(a)):.1f}"/>' for a in (30, 90, 150)) + "</g>"
STAGES["seed-set"] = ("Seed set", b)
b = '<path d="M0 {0} Q60 {1} 120 {2} T240 {0} V160 H0Z" fill="#cbbf95"/>'.format(BASE - 6, BASE - 10, BASE - 7)
b += "".join(blade(x, BASE + 2, R.uniform(8, 16), R.uniform(-4, 4), R.choice(["#b9a67a", "#a8956a"]), 1.4) for x in range(0, 240, 2))
b += shrub(90, 1.0, bare=True, dry=True) + stem(170, BASE, BASE - 82, "#9a8a6a", 2) + thistle_head(170, BASE - 90, .9, "#cfc6b0")
STAGES["dormant"] = ("Dormant", b)

for sub, d in (("class", CLASSES), ("stage", STAGES)):
    os.makedirs(f"{OUT}/{sub}", exist_ok=True)
    for slug, (title, body) in d.items():
        open(f"{OUT}/{sub}/{slug}.svg", "w").write(label_svg(title, body))
print(len(CLASSES), "class +", len(STAGES), "stage illustrations written to", OUT)
