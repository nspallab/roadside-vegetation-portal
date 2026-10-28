"""Detailed 3D models of the three spray drones on the Drone Technology page, for the three.js viewer.
Hylio ARES HYL-150, DJI Agras T40 and Hylio PEGASUS HYL-30. These are illustrations: proportions follow
published specs (prop size, motor spacing, tank volume); parts are modelled after product photos, not CAD.

Usage (Blender 4.x, from the repository root):
  blender -b --factory-startup --python tools/gen_drones_blender.py -- img/drones/3d
Writes ares.glb, t40.glb and pegasus.glb.

Conventions: metres, glTF +Y up, the nose faces +Z (Blender -Y), bottom of the landing gear at y = 0.
Every rotor is its own node prop_N with its origin on the motor hub, so it can be spun about its local +Y;
node extras carry spin (+1 = counter-clockwise seen from above, -1 = clockwise). On the T40, props 1-4 are
the upper rotors and 5-8 the lower ones on the same arms. The other nodes are named by part so the viewer
can label them: body, frame, tank, battery, arm_N, joint_N, motor_N, nozzle_N, hoses, pump, flowmeter,
radar_*, gnss_N, light_N, fpv, gear, and on the PEGASUS camera, gimbal and antenna_N.
"""
import bpy, bmesh, math, os, sys
from contextlib import contextmanager
from mathutils import Vector, Matrix, Euler

Z = Vector((0, 0, 1))
ROT_Y90 = Matrix.Rotation(math.pi / 2, 4, 'Y')       # turns a lathe axis (local Z) onto local X

# name: (sRGB colour, roughness, metallic[, extras]); extras: coat = clearcoat weight, emit = emission strength
PALETTE = {
    "shell": ("#eef0ef", 0.3, 0.0, {"coat": 0.35, "coat_rough": 0.15}),
    "body_dark": ("#3a3d42", 0.42, 0.0, {"coat": 0.25, "coat_rough": 0.2}),
    "tank": ("#f1f0e8", 0.4, 0.0),
    "light_grey": ("#c4c7ca", 0.45, 0.0),
    "dark_grey": ("#3b3e43", 0.55, 0.0),
    "black": ("#1c1d20", 0.5, 0.0),
    "seam": ("#24262a", 0.75, 0.0),
    "socket": ("#0a0a0b", 0.85, 0.0),
    "carbon": ("#16171a", 0.35, 0.0, {"coat": 1.0, "coat_rough": 0.06}),
    "carbon_plate": ("#1b1c1f", 0.45, 0.0, {"coat": 0.5, "coat_rough": 0.15}),
    "arm_grey": ("#8a8f96", 0.35, 0.0, {"coat": 0.8, "coat_rough": 0.08}),
    "prop": ("#121315", 0.38, 0.0, {"coat": 0.5, "coat_rough": 0.12}),
    "prop_tip": ("#e8eaec", 0.4, 0.0),
    "alu": ("#bcc1c7", 0.3, 0.75),
    "alu_dark": ("#5a5f66", 0.35, 0.75),
    "alu_black": ("#2a2c30", 0.38, 0.7),
    "alu_accent": ("#d4561f", 0.35, 0.7),
    "steel": ("#9ca2a8", 0.28, 0.85),
    "copper": ("#b8733a", 0.35, 0.8),
    "mesh": ("#5b6067", 0.5, 0.6),
    "hose": ("#a9bccb", 0.22, 0.0, {"coat": 0.6, "coat_rough": 0.05}),
    "nozzle": ("#f07c1a", 0.45, 0.0),
    "valve": ("#62676e", 0.45, 0.0),
    "window": ("#8fa6b5", 0.12, 0.0, {"coat": 1.0, "coat_rough": 0.03}),
    "radar": ("#2b2e33", 0.35, 0.0),
    "radome": ("#5c626a", 0.6, 0.0),
    "gnss": ("#efefec", 0.4, 0.0),
    "lens": ("#05070a", 0.05, 0.0, {"coat": 1.0, "coat_rough": 0.02}),
    "rubber": ("#121213", 0.9, 0.0),
    "sleeve": ("#2a2c30", 0.75, 0.0),
    "plug": ("#d9a91c", 0.45, 0.0),
    "led_green": ("#2fe07a", 0.3, 0.0, {"emit": 1.0}),
    "led_red": ("#ff3b30", 0.3, 0.0, {"emit": 1.0}),
    "led_white": ("#f2f4ff", 0.3, 0.0, {"emit": 1.0}),
}
# per model: anodised accent colour (lock rings, motor bands) and prop tip colour
ACCENT = {"ares": ("#d4561f", "#e8eaec"), "t40": ("#80868e", "#f2b705"), "pegasus": ("#2f6fd0", "#e8eaec")}


def srgb_to_linear(hexcol):
    c = [int(hexcol[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def material(name):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    hexcol, rough, metal, *extra = PALETTE[name]
    extra = extra[0] if extra else {}
    rgb = srgb_to_linear(hexcol)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if "coat" in extra:
        bsdf.inputs["Coat Weight"].default_value = extra["coat"]
        bsdf.inputs["Coat Roughness"].default_value = extra.get("coat_rough", 0.05)
    if "emit" in extra:
        bsdf.inputs["Emission Color"].default_value = (*rgb, 1)
        bsdf.inputs["Emission Strength"].default_value = extra["emit"]
    m.diffuse_color = (*rgb, 1)
    m.use_backface_culling = True          # every part is a closed solid: export single-sided
    return m


# ------------------------------------------------------------------ frames and outlines
def xform(loc=(0, 0, 0), rot=None, scale=None):
    m = Matrix.Translation(Vector(loc))
    if rot is not None:
        m = m @ (rot.to_4x4() if isinstance(rot, Matrix) else Euler(rot).to_matrix().to_4x4())
    if scale is not None:
        m = m @ Matrix.Diagonal((*scale, 1))
    return m


def _frame(origin, x, y, z):
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(origin)
    return m


def along(origin, xdir):
    """Frame with X along a direction (an arm, a pipe) and Z as close to up as possible."""
    x = Vector(xdir).normalized()
    y = Z.cross(x).normalized()
    return _frame(origin, x, y, x.cross(y))


def facing(origin, n):
    """Frame on a surface: Z along the outward normal n, Y up the surface (+Y on a horizontal face)."""
    z = Vector(n).normalized()
    up = Z if abs(z.z) < 0.95 else Vector((0, 1, 0))
    y = (up - z * up.dot(z)).normalized()
    return _frame(origin, y.cross(z), y, z)


def align(origin, zdir):
    """Frame with Z along zdir (rods, legs, parts on a slant)."""
    m = Vector(zdir).to_track_quat('Z', 'Y').to_matrix().to_4x4()
    m.translation = Vector(origin)
    return m


def T(x, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def P(d, r, z):
    """Point at distance r along the horizontal direction d, height z."""
    return Vector((d.x * r, d.y * r, z))


def rounded_rect(w, d, r, n=5):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, d / 2 - r, 0), (r - w / 2, d / 2 - r, 90), (r - w / 2, r - d / 2, 180), (w / 2 - r, r - d / 2, 270)):
        pts += [(cx + r * math.cos(math.radians(a0 + 90 * k / n)), cy + r * math.sin(math.radians(a0 + 90 * k / n))) for k in range(n + 1)]
    return pts


def stadium(L, W, n=6):
    """Slot outline: straight length L between two round ends of diameter W, centred on the origin along X."""
    r = W / 2
    right = [(L / 2 + r * math.cos(math.radians(-90 + 180 * k / n)), r * math.sin(math.radians(-90 + 180 * k / n))) for k in range(n + 1)]
    left = [(-L / 2 + r * math.cos(math.radians(90 + 180 * k / n)), r * math.sin(math.radians(90 + 180 * k / n))) for k in range(n + 1)]
    return right + left


def chaikin(pts, n=3):
    """Round off the corners of a polyline (keeps both end points)."""
    pts = [Vector(p) for p in pts]
    for _ in range(n):
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out += [a.lerp(b, 0.25), a.lerp(b, 0.75)]
        pts = out + [pts[-1]]
    return pts


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def knurl(amp):
    return lambda j: 1 + amp * (j % 2)


# ------------------------------------------------------------------ mesh builder
class Part:
    """Collects primitives (each with its own material) into one named mesh object.
    `with part.at(matrix):` places everything built inside it in that local frame."""

    def __init__(self, name):
        self.name, self.bm, self.mats, self.M = name, bmesh.new(), [], Matrix.Identity(4)

    @contextmanager
    def at(self, m):
        old = self.M
        self.M = old @ m
        try:
            yield self
        finally:
            self.M = old

    def slot(self, mat):
        m = material(mat)
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def _finish(self, verts, mat, bevel=0.0, seg=2):
        si = self.slot(mat)
        for f in {f for v in verts for f in v.link_faces}:
            f.material_index, f.smooth = si, True
        if bevel > 0:   # round the hard edges only
            edges = [e for e in {e for v in verts for e in v.link_edges} if e.calc_face_angle(0) > 0.6]
            res = bmesh.ops.bevel(self.bm, geom=edges, offset=bevel, offset_type='OFFSET', segments=seg,
                                  profile=0.5, affect='EDGES', clamp_overlap=True, material=si)
            for f in res["faces"]:
                f.smooth = True

    def _place(self, verts, m):
        bmesh.ops.transform(self.bm, matrix=self.M @ m, verts=verts)

    def box(self, mat, size, loc=(0, 0, 0), rot=None, bevel=0.01, seg=2, top=(1, 1), bottom=(1, 1)):
        vs = bmesh.ops.create_cube(self.bm, size=1.0)["verts"]
        for v in vs:
            k = top if v.co.z > 0 else bottom
            v.co = Vector((v.co.x * size[0] * k[0], v.co.y * size[1] * k[1], v.co.z * size[2]))
        self._place(vs, xform(loc, rot))
        self._finish(vs, mat, bevel, seg)

    def cyl(self, mat, r, depth, loc=(0, 0, 0), rot=None, seg=24, r2=None, bevel=0.0):
        vs = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r,
                                   radius2=r if r2 is None else r2, depth=depth)["verts"]
        self._place(vs, xform(loc, rot))
        self._finish(vs, mat, bevel)

    def rod(self, mat, a, b, r, seg=16, r2=None, bevel=0.0):
        a, b = Vector(a), Vector(b)
        vs = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r,
                                   radius2=r if r2 is None else r2, depth=(b - a).length)["verts"]
        self._place(vs, align((a + b) / 2, b - a))
        self._finish(vs, mat, bevel)

    def sphere(self, mat, r, loc, scale=(1, 1, 1), seg=24, rings=12):
        vs = bmesh.ops.create_uvsphere(self.bm, u_segments=seg, v_segments=rings, radius=r)["verts"]
        self._place(vs, xform(loc, None, scale))
        self._finish(vs, mat)

    def lathe(self, mat, prof, m=None, seg=24, closed=False, mod=None):
        """Revolve an (r, z[, flag]) profile, listed bottom to top, around local Z; r = 0 points close on the axis.
        closed=True joins the last point back to the first (rings); mod(j) scales the radius of flagged points."""
        bm, M = self.bm, self.M @ (m if m is not None else Matrix.Identity(4))
        rings = []
        for pt in prof:
            r, z = pt[0], pt[1]
            if r <= 1e-9:
                rings.append([bm.verts.new(M @ Vector((0, 0, z)))])
                continue
            k = mod if (mod and len(pt) > 2 and pt[2]) else (lambda j: 1.0)
            rings.append([bm.verts.new(M @ Vector((r * k(j) * math.cos(2 * math.pi * j / seg),
                                                   r * k(j) * math.sin(2 * math.pi * j / seg), z))) for j in range(seg)])
        for A, B in list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else []):
            if len(A) == 1 and len(B) == 1:
                continue
            for j in range(seg):
                j1 = (j + 1) % seg
                if len(A) == 1:
                    bm.faces.new((A[0], B[j1], B[j]))
                elif len(B) == 1:
                    bm.faces.new((A[j], A[j1], B[0]))
                else:
                    bm.faces.new((A[j], A[j1], B[j1], B[j]))
        if not closed:
            if len(rings[0]) > 1:
                bm.faces.new(list(reversed(rings[0])))
            if len(rings[-1]) > 1:
                bm.faces.new(rings[-1])
        self._finish([v for ring in rings for v in ring], mat)

    def prism(self, mat, outline, z0, z1, m=None, bevel=0.0, seg=1):
        """Extrude a counter-clockwise outline (x, y) between heights z0 and z1."""
        bm, M = self.bm, self.M @ (m if m is not None else Matrix.Identity(4))
        lo = [bm.verts.new(M @ Vector((x, y, z0))) for x, y in outline]
        hi = [bm.verts.new(M @ Vector((x, y, z1))) for x, y in outline]
        n = len(outline)
        bm.faces.new(list(reversed(lo)))
        bm.faces.new(hi)
        for i in range(n):
            bm.faces.new((lo[i], lo[(i + 1) % n], hi[(i + 1) % n], hi[i]))
        self._finish(lo + hi, mat, bevel, seg)

    def tube(self, mat, pts, r, seg=10):
        """Sweep a circle along a path (hoses, bent legs, handles)."""
        pts, bm = [self.M @ Vector(p) for p in pts], self.bm
        n = len(pts)
        tang = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
        up = Z if abs(tang[0].z) < 0.9 else Vector((1, 0, 0))
        nrm, rings = tang[0].cross(up).normalized(), []
        for i in range(n):
            nrm = (nrm - tang[i] * nrm.dot(tang[i])).normalized()   # parallel transport
            bi = tang[i].cross(nrm)
            rings.append([bm.verts.new(pts[i] + r * (math.cos(a) * nrm + math.sin(a) * bi))
                          for a in (2 * math.pi * j / seg for j in range(seg))])
        for i in range(n - 1):
            for j in range(seg):
                bm.faces.new((rings[i][j], rings[i][(j + 1) % seg], rings[i + 1][(j + 1) % seg], rings[i + 1][j]))
        bm.faces.new(list(reversed(rings[0])))
        bm.faces.new(rings[-1])
        self._finish([v for ring in rings for v in ring], mat)

    def blade(self, R, r0, cmax, pitch, spin, ang, tip_mat, root_c, root_t, tip_from=0.88, ns=24, npf=14):
        """Folding rotor blade along +X (turned by ang) from its hinge at r0: a flat root shank that blends
        into a tapered, twisted, cambered airfoil with a rounded, coloured tip."""
        bm, si, ti = self.bm, self.slot("prop"), self.slot(tip_mat)
        rot = self.M @ Matrix.Rotation(ang, 4, 'Z')
        rings, ts = [], []
        for i in range(ns + 1):
            t = 0.5 - 0.5 * math.cos(math.pi * i / ns)          # sections bunch up at the root and the tip
            r = r0 + (R - r0) * t
            ramp = smoothstep(t / 0.16)
            k = 0.62 + 0.38 * math.sin(math.pi / 2 * t / 0.3) if t < 0.3 else 1 - 0.55 * (t - 0.3) / 0.7
            if t > 0.9:
                k *= 0.15 + 0.85 * math.sqrt(max(0.0, 1 - ((t - 0.9) / 0.1) ** 2))
            c = root_c + (cmax * k - root_c) * ramp
            th = root_t + (c * (0.13 - 0.07 * t) - root_t) * ramp
            tw = min(math.radians(28), math.atan(pitch / (2 * math.pi * r))) * ramp
            sweep = -0.12 * cmax * t * t
            ring = []
            for j in range(npf):
                a = 2 * math.pi * j / npf
                u = 0.5 * math.cos(a)                              # +0.5 leading edge, -0.5 trailing edge
                f = 1 + (0.35 + 0.65 * (u + 0.5) - 1) * ramp       # thinner trailing edge once out of the shank
                z = 0.5 * th * math.sin(a) * f + 0.04 * c * (1 - 4 * u * u) * ramp
                y = u * c + sweep
                y, z = y * math.cos(tw) - z * math.sin(tw), y * math.sin(tw) + z * math.cos(tw)
                ring.append(bm.verts.new(rot @ Vector((r, spin * y, z))))
            rings.append(ring)
            ts.append(t)
        for i in range(ns):
            for j in range(npf):
                f = bm.faces.new((rings[i][j], rings[i][(j + 1) % npf], rings[i + 1][(j + 1) % npf], rings[i + 1][j]))
                f.material_index, f.smooth = (ti if ts[i] >= tip_from else si), True
        for ring, mi in ((rings[0], si), (rings[-1], ti)):          # close root and tip with a fan
            ctr = bm.verts.new(sum((v.co for v in ring), Vector()) / npf)
            for j in range(npf):
                f = bm.faces.new((ring[j], ring[(j + 1) % npf], ctr))
                f.material_index, f.smooth = mi, True

    def build(self, parent, loc=(0, 0, 0)):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces[:])
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(m)
        me.set_sharp_from_angle(angle=math.radians(50))
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.location, ob.parent = loc, parent
        wn = ob.modifiers.new("WeightedNormal", 'WEIGHTED_NORMAL')   # keeps bevelled boxes crisp
        wn.keep_sharp = True
        return ob


# ------------------------------------------------------------------ small hardware
def screw(p, loc, n=Z, r=0.004, mat="steel"):
    """Socket-head cap screw standing on a surface with outward normal n."""
    h = r * 0.9
    with p.at(facing(loc, n)):
        p.lathe(mat, [(0, -0.0005), (r, -0.0005), (r, h * 0.7), (r * 0.8, h), (0, h)], seg=8)
        p.cyl("socket", r * 0.42, 0.001, (0, 0, h), seg=6)


def hex_bolt(p, loc, n=Z, r=0.006, mat="steel"):
    with p.at(facing(loc, n)):
        p.cyl(mat, r, r * 0.65, (0, 0, r * 0.32), seg=6, bevel=r * 0.08)
        p.cyl(mat, r * 0.5, r * 0.35, (0, 0, r * 0.8), seg=10)


def vent(p, loc, n, w, h, slats=5):
    """Inset louvre vent: dark recess with angled slats."""
    with p.at(facing(loc, n)):
        p.box("seam", (w, h, 0.003), (0, 0, 0), bevel=0.001, seg=1)
        for k in range(slats):
            p.box("black", (w - 0.006, h / slats * 0.7, 0.0018), (0, -h / 2 + h * (k + 0.5) / slats, 0.0008),
                  rot=(math.radians(-35), 0, 0), bevel=0)


def seam(p, a, b, n, w=0.0022):
    """Thin dark panel line from a to b on a surface with outward normal n."""
    a, b = Vector(a), Vector(b)
    x = (b - a).normalized()
    y = Vector(n).normalized().cross(x)
    with p.at(_frame((a + b) / 2, x, y, x.cross(y))):
        p.box("seam", ((b - a).length, w, 0.0016), (0, 0, 0), bevel=0)


def led_strip(p, loc, n, w, count, mat="led_green"):
    with p.at(facing(loc, n)):
        p.box("black", (w, 0.012, 0.004), (0, 0, 0), bevel=0.0015, seg=1)
        for k in range(count):
            p.box(mat, (w / count * 0.62, 0.005, 0.002), (-w / 2 + w * (k + 0.5) / count, 0, 0.0018), bevel=0)


def tube_clamp(p, m, L, w, h, mat="alu_dark"):
    """Split clamp block around a tube (m: X along the tube), halves bolted through the sides."""
    with p.at(m):
        for s in (-1, 1):
            p.box(mat, (L, w / 2 - 0.0008, h), (0, s * (w / 4 + 0.0004), 0), bevel=min(L, w, h) * 0.12, seg=2)
        p.box("seam", (L * 0.97, 0.002, h * 0.97), (0, 0, 0), bevel=0)
        for s in (-1, 1):
            for x in (-L * 0.3, L * 0.3):
                screw(p, (x, s * w / 2, 0), (0, s, 0), r=min(L, h) * 0.075)


# ------------------------------------------------------------------ propulsion
def motor_unit(p, base, r, h, up=1, windows=12):
    """Outrunner: stator base, bell with cooling windows over copper windings, top cap with bolts.
    Stands on base (up=1) or hangs below it (up=-1). Returns the height of the shaft boss."""
    with p.at(T(*base) @ Matrix.Diagonal((1, 1, up, 1))):
        p.lathe("alu_black", [(0, 0), (r * 0.9, 0), (r * 0.96, 0.025 * h), (r * 0.96, 0.17 * h), (0, 0.17 * h)], seg=32)
        p.lathe("copper", [(0, 0.16 * h), (r * 0.88, 0.16 * h), (r * 0.88, 0.8 * h), (0, 0.8 * h)], seg=24)
        p.lathe("alu_accent", [(0, 0.19 * h), (r, 0.19 * h), (r, 0.24 * h), (0, 0.24 * h)], seg=32)
        p.lathe("alu_black", [(0, 0.24 * h), (r, 0.24 * h), (r, 0.42 * h), (0, 0.42 * h)], seg=32)
        for k in range(windows):                               # bell posts between the cooling windows
            a = 2 * math.pi * (k + 0.5) / windows
            p.box("alu_black", (r * 0.13, 2 * math.pi * r / windows * 0.45, 0.32 * h),
                  (math.cos(a) * r * 0.935, math.sin(a) * r * 0.935, 0.57 * h), rot=(0, 0, a), bevel=0)
        p.lathe("alu_black", [(0, 0.72 * h), (r, 0.72 * h), (r, 0.9 * h), (0, 0.9 * h)], seg=32)
        p.lathe("alu", [(0, 0.9 * h), (r * 0.99, 0.9 * h), (r * 0.99, 0.95 * h), (r * 0.93, h), (r * 0.36, h),
                        (r * 0.36, 1.06 * h), (r * 0.3, 1.1 * h), (0, 1.1 * h)], seg=32)
        for k in range(6):
            a = 2 * math.pi * k / 6
            screw(p, (math.cos(a) * r * 0.62, math.sin(a) * r * 0.62, h), Z, r=r * 0.065)
            b = a + math.pi / 6                                # cooling slots in the cap
            p.box("socket", (r * 0.3, r * 0.08, 0.003), (math.cos(b) * r * 0.66, math.sin(b) * r * 0.66, h), rot=(0, 0, b), bevel=0)
    return base[2] + up * 1.1 * h


def esc_pod(p, top, r, h, fins=16):
    """Finned ESC housing hanging under a motor mount."""
    x, y, z = top
    p.lathe("alu_black", [(0, z - h), (r * 0.6, z - h), (r * 0.9, z - h + 0.14 * h), (r * 0.9, z), (0, z)], m=T(x, y), seg=28)
    for k in range(fins):
        a = 2 * math.pi * k / fins
        p.box("alu_black", (r * 0.22, r * 0.05, h * 0.7), (x + math.cos(a) * r * 0.98, y + math.sin(a) * r * 0.98, z - h * 0.42),
              rot=(0, 0, a), bevel=0)


def prop_seat(hub_r):
    """Height of the prop origin above the motor's shaft boss (adapter + lower plate + half the blade gap)."""
    return 0.54 * hub_r


def make_prop(root, name, loc, R, cmax, pitch, hub_r, spin, phi, tip_from=0.88, down=False):
    """Folding 2-blade rotor with its origin on the hub; spin +1 = CCW from above. Two clamp plates hold the
    blade roots on hinge bolts; the adapter, spinner and bolt heads flip for the hanging lower rotors."""
    p = Part(name)
    g, tp, W, rp = 0.28 * hub_r, 0.1 * hub_r, 0.9 * hub_r, 1.75 * hub_r
    for z0 in (-g / 2 - tp, g / 2):
        p.prism("alu_dark", stadium(2 * rp, W), z0, z0 + tp, m=Matrix.Rotation(phi, 4, 'Z'), bevel=tp * 0.3)
    p.lathe("alu", [(0, -g / 2), (0.5 * hub_r, -g / 2), (0.5 * hub_r, g / 2), (0, g / 2)], seg=20)
    for k in (0, 1):
        a = phi + k * math.pi
        p.cyl("prop", W * 0.46, g * 0.98, (math.cos(a) * rp, math.sin(a) * rp, 0), seg=16)      # blade root lug
        p.blade(R, rp, cmax, pitch, spin, a, "prop_tip", root_c=W * 0.85, root_t=g * 0.8, tip_from=tip_from)
    z0 = g / 2 + tp
    with p.at(Matrix.Diagonal((1, 1, -1 if down else 1, 1))):
        za = -z0 - 0.3 * hub_r
        p.lathe("alu", [(0, za), (0.62 * hub_r, za), (0.62 * hub_r, -z0), (0, -z0)], seg=20)     # motor adapter
        p.lathe("alu", [(0, z0), (0.52 * hub_r, z0), (0.52 * hub_r, z0 + 0.1 * hub_r), (0.45 * hub_r, z0 + 0.25 * hub_r),
                        (0.3 * hub_r, z0 + 0.38 * hub_r), (0.12 * hub_r, z0 + 0.45 * hub_r), (0, z0 + 0.47 * hub_r)], seg=20)  # spinner
        for k in (0, 1):
            a = phi + k * math.pi
            c, s = Vector((math.cos(a), math.sin(a), 0)) * rp, Vector((math.cos(a), math.sin(a), 0)) * 0.95 * hub_r
            hex_bolt(p, (c.x, c.y, z0), Z, r=0.17 * hub_r)                       # hinge bolt and nut
            p.cyl("steel", 0.15 * hub_r, 0.12 * hub_r, (c.x, c.y, -z0 - 0.06 * hub_r), seg=6)
            screw(p, (s.x, s.y, z0), Z, r=0.1 * hub_r)
    ob = p.build(root, loc)
    ob["spin"] = spin
    return ob


def arm_part(root, name, m, x0, x1, tr, joint_x, clamp, ties=(), mat="carbon"):
    """Arm tube along local X (frame m) with its root clamp, a cable sleeve along its side and cable ties."""
    p = Part(name)
    rs = tr * 0.24
    sy = tr + rs + 0.0008
    with p.at(m):
        p.cyl(mat, tr, x1 - x0, ((x0 + x1) / 2, 0, 0), rot=(0, math.pi / 2, 0), seg=24)
        bump = tr * 1.35 * 1.16 * 1.03 + rs + 0.002                # clears the joint's lock ring
        xs = (x0 + 0.02, joint_x - 3.2 * tr, joint_x - 2.4 * tr, joint_x + 2.6 * tr, joint_x + 3.4 * tr, x1 - 0.01)
        ys = (sy, sy, bump, bump, sy, sy)
        p.tube("sleeve", chaikin([(x, y, 0) for x, y in zip(xs, ys)], 2), rs, seg=8)
        a, b, cy = (tr + sy + rs) / 2 + 0.0012, tr + 0.0012, (sy + rs - tr) / 2
        for x in ties:                                             # elliptical tie round tube and sleeve
            with p.at(T(x, cy) @ ROT_Y90 @ Matrix.Diagonal((b, a, 1, 1))):
                k = 0.0018 / b
                p.lathe("black", [(1.0, -0.002), (1.0 + k, -0.002), (1.0 + k, 0.002), (1.0, 0.002)], seg=20, closed=True)
    cx, L, w, h = clamp
    tube_clamp(p, m @ T(cx), L, w, h)
    p.build(root)


def fold_joint(root, name, m, tr):
    """Folding arm joint: clamp sleeves either side of the fold, a hinge on the side and a knurled lock ring.
    m: X along the arm, origin at the fold."""
    p = Part(name)
    R1 = tr * 1.35
    with p.at(m @ ROT_Y90):
        for z0, z1 in ((-2.4 * tr, -0.06 * tr), (0.06 * tr, 2.4 * tr)):
            p.lathe("alu_dark", [(0, z0), (R1 * 0.9, z0), (R1, z0 + 0.12 * tr), (R1, z1 - 0.12 * tr), (R1 * 0.9, z1), (0, z1)], seg=28)
        p.lathe("alu_accent", [(R1 * 0.98, 1.0 * tr), (R1 * 1.16, 1.0 * tr, 1), (R1 * 1.16, 2.3 * tr, 1), (R1 * 0.98, 2.3 * tr)],
                seg=48, closed=True, mod=knurl(0.03))
    with p.at(m):
        y = -(R1 + 0.32 * tr)                                     # hinge on the side away from the cable sleeve
        for x0 in (-0.5 * tr, 0.5 * tr):
            p.box("alu_dark", (0.8 * tr, 0.6 * tr, 1.5 * tr), (x0, -R1 * 0.85, 0), bevel=0.1 * tr)
        for z0, z1 in ((-1.1, -0.4), (-0.36, 0.36), (0.4, 1.1)):
            p.cyl("alu_dark", 0.4 * tr, (z1 - z0) * tr, (0, y, (z0 + z1) / 2 * tr), seg=14, bevel=0.05 * tr)
        for s in (-1, 1):
            p.cyl("steel", 0.22 * tr, 0.12 * tr, (0, y, s * 1.16 * tr), seg=6)
            screw(p, (-1.5 * tr, 0, s * R1), (0, 0, s), r=0.17 * tr)
    p.build(root)


def nav_light(root, name, pos, d, colour, s=1.0):
    p = Part(name)
    with p.at(along(pos, d) @ Matrix.Diagonal((s, s, s, 1))):
        p.box("black", (0.026, 0.03, 0.022), (0, 0, 0), bevel=0.006)
        p.sphere("led_" + colour, 0.0105, (0.011, 0, 0), scale=(0.75, 1, 1), seg=16, rings=8)
    p.build(root)


# ------------------------------------------------------------------ spray system
def fan_nozzle(root, name, top, inlet_dir, s=1.0):
    """Flat-fan nozzle hanging from top: drop stem, diaphragm check valve with a side inlet barb, coloured
    bayonet cap and slotted tip. Returns the end of the inlet barb."""
    p = Part(name)
    d = Vector(inlet_dir)
    M = T(*top) @ Matrix.Diagonal((s, s, s, 1)) @ Matrix.Rotation(math.atan2(d.y, d.x), 4, 'Z')
    with p.at(M):
        p.cyl("black", 0.008, 0.072, (0, 0, -0.036), seg=12)
        p.lathe("valve", [(0, -0.08), (0.019, -0.08), (0.019, -0.073), (0.016, -0.069), (0, -0.069)], seg=24)   # valve cap
        p.lathe("black", [(0, -0.112), (0.014, -0.112), (0.016, -0.109), (0.016, -0.08), (0, -0.08)], seg=24)   # valve body
        p.rod("black", (0.012, 0, -0.095), (0.026, 0, -0.095), 0.0055, seg=12)
        p.rod("black", (0.026, 0, -0.095), (0.034, 0, -0.095), 0.0048, r2=0.0036, seg=12)                    # hose barb
        p.lathe("nozzle", [(0, -0.128), (0.012, -0.128), (0.016, -0.124), (0.017, -0.116), (0.017, -0.112), (0, -0.112)], seg=24)
        for sy in (-1, 1):
            p.box("nozzle", (0.01, 0.008, 0.012), (0, sy * 0.019, -0.119), bevel=0.0015, seg=1)                # bayonet wings
        p.lathe("valve", [(0, -0.136), (0.006, -0.135), (0.0075, -0.131), (0.0075, -0.128), (0, -0.128)], seg=16)
        p.box("socket", (0.013, 0.0014, 0.003), (0, 0, -0.1355), bevel=0)                                      # fan slot
    p.build(root)
    return M @ Vector((0.034, 0, -0.095))


def sprinkler(root, name, top):
    """Centrifugal atomizer: small finned motor spinning a toothed disc, fed by a drip tube."""
    p = Part(name)
    with p.at(T(*top)):
        p.cyl("steel", 0.007, 0.03, (0, 0, -0.015), seg=12)
        p.lathe("dark_grey", [(0, -0.085), (0.026, -0.085), (0.031, -0.08), (0.033, -0.07), (0.033, -0.04), (0.028, -0.03), (0, -0.03)], seg=32)
        for k in range(12):
            a = 2 * math.pi * k / 12
            p.box("dark_grey", (0.008, 0.003, 0.04), (math.cos(a) * 0.035, math.sin(a) * 0.035, -0.058), rot=(0, 0, a), bevel=0)
        p.cyl("black", 0.012, 0.012, (0, 0, -0.091), seg=16)
        p.lathe("nozzle", [(0, -0.104), (0.05, -0.102), (0.06, -0.098), (0.06, -0.094), (0.022, -0.093), (0, -0.093)], seg=40)
        for k in range(24):                                      # atomizing teeth
            a = 2 * math.pi * k / 24
            p.box("nozzle", (0.012, 0.0018, 0.003), (math.cos(a) * 0.051, math.sin(a) * 0.051, -0.0925), rot=(0, 0, a), bevel=0)
        p.lathe("black", [(0, -0.115), (0.006, -0.112), (0.01, -0.104), (0, -0.104)], seg=16)
        p.tube("steel", chaikin([(0.03, 0, -0.035), (0.045, 0, -0.045), (0.042, 0, -0.08), (0.036, 0, -0.088)], 2), 0.0035, seg=8)
    p.build(root)


def pump_unit(root, c, axis, s=1.0, out=(0, 0, 1), mount=0.0):
    """Centrifugal pump: finned motor along axis with the volute at its front end and a radial outlet.
    Returns the inlet and outlet stub ends in world space."""
    p = Part("pump")
    M = along(c, axis) @ Matrix.Diagonal((s, s, s, 1))
    with p.at(M @ ROT_Y90):
        p.lathe("dark_grey", [(0, 0), (0.029, 0), (0.031, 0.004), (0.031, 0.07), (0.028, 0.075), (0, 0.075)], seg=32)
        p.lathe("black", [(0, 0.075), (0.024, 0.075), (0.024, 0.083), (0.016, 0.087), (0, 0.087)], seg=24)
        p.lathe("valve", [(0, -0.032), (0.028, -0.032), (0.036, -0.026), (0.036, -0.004), (0.032, 0), (0, 0)], seg=32)
        p.lathe("valve", [(0, -0.05), (0.0095, -0.05), (0.0095, -0.032), (0, -0.032)], seg=16)
    o = Vector(out).normalized()
    with p.at(M):
        for k in range(10):
            a = 2 * math.pi * k / 10
            p.box("dark_grey", (0.058, 0.0035, 0.007), (0.038, math.cos(a) * 0.033, math.sin(a) * 0.033), rot=(a - math.pi / 2, 0, 0), bevel=0)
        o0, o1 = Vector((-0.016, 0, 0)) + o * 0.03, Vector((-0.016, 0, 0)) + o * 0.058
        p.rod("valve", o0, o1, 0.0085, seg=16)
        p.box("alu_dark", (0.066, 0.006, 0.012), (0.035, 0, 0.034), bevel=0.002)          # strap
        if mount > 0:
            p.box("alu_dark", (0.03, 0.004, mount / s), (0.035, 0, 0.031 + mount / s / 2), bevel=0.001)
    p.build(root)
    return M @ Vector((-0.05, 0, 0)), M @ o1


def flowmeter(root, a, b, r=0.014):
    """Inline flowmeter between a and b with its electronics head and display on top."""
    p = Part("flowmeter")
    a, b = Vector(a), Vector(b)
    L = (b - a).length
    with p.at(align(a, b - a)):
        p.lathe("alu", [(0, 0), (r * 0.8, 0), (r, 0.004), (r, L - 0.004), (r * 0.8, L), (0, L)], seg=24)
        for z in (0.005, L - 0.005):
            p.cyl("steel", r * 1.22, 0.009, (0, 0, z), seg=6, bevel=0.0008)
        p.box("black", (0.026, 0.02, min(0.03, L * 0.6)), (0, r + 0.009, L / 2), bevel=0.004)
        p.box("window", (0.016, 0.002, min(0.018, L * 0.4)), (0, r + 0.0195, L / 2), bevel=0.0006)
    p.build(root)


def outlet_strainer(p, top, s=1.0):
    """Tank outlet fitting with a basket strainer under it; returns the strainer outlet (its bottom)."""
    with p.at(T(*top) @ Matrix.Diagonal((s, s, s, 1))):
        p.cyl("black", 0.022, 0.012, (0, 0, -0.006), seg=6, bevel=0.0015)
        p.cyl("alu", 0.011, 0.012, (0, 0, -0.018), seg=16)
        p.lathe("alu", [(0, -0.036), (0.025, -0.036), (0.025, -0.026), (0.02, -0.022), (0, -0.022)], seg=32)
        p.lathe("mesh", [(0, -0.07), (0.021, -0.07, 1), (0.021, -0.036, 1), (0, -0.036)], seg=48, mod=knurl(0.06))
        p.lathe("alu", [(0, -0.082), (0.012, -0.082), (0.024, -0.078), (0.024, -0.07), (0, -0.07)], seg=32)
    return Vector(top) - Z * 0.082 * s


def tank_point(c, size, bottom, side, u, v):
    """Point on a side face of a tapered tank box (u: offset along the face, v: height above its bottom)
    and the outward normal of that face."""
    w, d, h = size
    k = v / h
    if side[0] == "x":
        s = 1 if side[1] == "+" else -1
        half = w / 2 * (bottom[0] + (1 - bottom[0]) * k)
        return Vector((c[0] + s * half, c[1] + u, c[2] - h / 2 + v)), Vector((s * h, 0, -w / 2 * (1 - bottom[0]))).normalized()
    s = 1 if side[1] == "+" else -1
    half = d / 2 * (bottom[1] + (1 - bottom[1]) * k)
    return Vector((c[0] + u, c[1] + s * half, c[2] - h / 2 + v)), Vector((0, s * h, -d / 2 * (1 - bottom[1]))).normalized()


def level_window(p, pt, n, L):
    """Level sight strip with graduation ticks."""
    with p.at(facing(pt, n)):
        p.box("window", (0.022, L, 0.003), (0, 0, 0.0006), bevel=0.001, seg=1)
        for k in range(11):
            big = k % 5 == 0
            p.box("seam", (0.016 if big else 0.009, 0.0016, 0.0012),
                  (-0.012 - (0.008 if big else 0.0045), -L / 2 + 0.008 + (L - 0.016) * k / 10, 0.0004), bevel=0)


def fill_cap(p, base, axis, r):
    """Fill neck with a knurled screw cap and a breather vent."""
    with p.at(align(base, axis)):
        p.lathe("tank", [(0, -0.012), (r * 0.82, -0.012), (r * 0.82, 0.016), (0, 0.016)], seg=32)
        p.lathe("light_grey", [(0, 0.014), (r * 0.98, 0.014), (r, 0.017, 1), (r, 0.036, 1), (r * 0.95, 0.04), (0, 0.04)],
                seg=48, mod=knurl(0.035))
        p.lathe("dark_grey", [(0, 0.039), (0.0075, 0.039), (0.0075, 0.047), (0.0055, 0.05), (0, 0.05)], m=T(r * 0.45), seg=12)


def latch(p, pt, n):
    """Over-centre quick-release latch: base on the tank, lever, and hook up to the frame."""
    with p.at(facing(pt, n)):
        p.box("alu_dark", (0.028, 0.026, 0.006), (0, 0, 0.002), bevel=0.0015, seg=1)
        p.box("alu", (0.02, 0.034, 0.006), (0, 0.014, 0.007), rot=(math.radians(-10), 0, 0), bevel=0.0015, seg=1)
        p.box("alu_dark", (0.014, 0.026, 0.004), (0, 0.04, 0.004), bevel=0.001, seg=1)
        for sx in (-1, 1):
            p.cyl("steel", 0.002, 0.003, (sx * 0.009, -0.007, 0.0055), seg=8)


def hose_run(p, pts, r, n=2):
    p.tube("hose", chaikin(pts, n), r, seg=8)


def hose_clip(p, hose_pt, d, tube_z, r_hose):
    """Strap from a hose (running along d) up to the arm tube above it."""
    h = Vector(hose_pt)
    with p.at(along(h, d)):
        p.box("black", (0.004, 0.008, tube_z - h.z), (0, 0, (tube_z - h.z) / 2), bevel=0)
    with p.at(align(h, d)):
        p.lathe("black", [(r_hose, -0.0035), (r_hose + 0.0015, -0.0035), (r_hose + 0.0015, 0.0035), (r_hose, 0.0035)], seg=12, closed=True)


# ------------------------------------------------------------------ sensors, battery, frame, gear
def radar_module(root, name, loc, n, w, h, d=0.024):
    """Flat radar module: housing on a screwed flange, lighter radome face with its patch array."""
    p = Part(name)
    with p.at(facing(loc, n)):
        p.box("radar", (w + 0.018, h + 0.008, 0.003), (0, 0, 0.0015), bevel=0.001, seg=1)
        p.box("radar", (w, h, d), (0, 0, d / 2 - 0.006), bevel=0.006, seg=2)
        p.box("radome", (w - 0.014, h - 0.014, 0.004), (0, 0, d - 0.006 + 0.0008), bevel=0.0015, seg=1)
        nx, ny = max(2, int((w - 0.03) / 0.022)), max(1, int((h - 0.03) / 0.022))
        for i in range(nx):
            for j in range(ny):
                p.box("radar", (0.011, 0.011, 0.001), (-(nx - 1) * 0.011 + i * 0.022, -(ny - 1) * 0.011 + j * 0.022, d - 0.006 + 0.0029), bevel=0)
        for sx in (-1, 1):
            for sy in (-1, 1):
                screw(p, (sx * (w / 2 + 0.0055), sy * (h / 2 - 0.004), 0.003), Z, r=0.0022)
    p.build(root)


def radar_dome(root, name, loc, n, r=0.066, bracket=None):
    """Phased-array radar under a domed radome on a screwed bezel (bracket: optional (size, centre) box)."""
    p = Part(name)
    if bracket:
        p.box("alu_dark", bracket[0], bracket[1], bevel=0.002)
    with p.at(facing(loc, n)):
        p.lathe("dark_grey", [(0, 0), (r * 1.12, 0), (r * 1.12, 0.012), (r * 1.06, 0.02), (0, 0.02)], seg=32)
        p.lathe("radar", [(0, 0.015), (r, 0.015), (r * 0.97, 0.03), (r * 0.85, 0.05), (r * 0.6, 0.066), (r * 0.3, 0.074), (0, 0.076)], seg=32)
        for k in range(6):
            a = 2 * math.pi * (k + 0.5) / 6
            screw(p, (math.cos(a) * r * 1.07, math.sin(a) * r * 1.07, 0.012), Z, r=0.0028)
    p.build(root)


def gnss(root, name, base, h, r=0.032):
    """GNSS/RTK antenna puck on a short folding mast."""
    p = Part(name)
    x, y, z = base
    p.lathe("alu_dark", [(0, z), (0.014, z), (0.014, z + 0.012), (0.009, z + 0.02), (0, z + 0.02)], m=T(x, y), seg=20)
    p.cyl("alu_dark", 0.004, 0.024, (x, y, z + 0.008), rot=(math.pi / 2, 0, 0), seg=10)     # fold pin
    p.cyl("carbon", 0.0065, h - 0.02, (x, y, z + 0.02 + (h - 0.02) / 2), seg=12)
    top = z + h
    p.lathe("dark_grey", [(0, top - 0.008), (r * 0.9, top - 0.008), (r * 0.9, top), (0, top)], m=T(x, y), seg=32)
    p.lathe("gnss", [(0, top), (r, top), (r, top + 0.012), (r * 0.9, top + 0.02), (r * 0.55, top + 0.026), (0, top + 0.028)], m=T(x, y), seg=32)
    p.build(root)


def fpv(root, loc, n, mount=0.0):
    """Forward FPV camera: housing, lens barrel and glass, tilted slightly down."""
    p = Part("fpv")
    with p.at(facing(loc, n)):
        if mount > 0:
            p.box("alu_dark", (0.03, mount, 0.006), (0, 0.019 + mount / 2, 0.006), bevel=0.001)
        with p.at(Matrix.Rotation(math.radians(12), 4, 'X')):
            p.box("black", (0.05, 0.038, 0.034), (0, 0, 0.012), bevel=0.007, seg=2)
            p.lathe("dark_grey", [(0, 0.028), (0.0145, 0.028), (0.0145, 0.04), (0.012, 0.044), (0, 0.044)], seg=28)
            p.cyl("lens", 0.009, 0.003, (0, 0, 0.0445), seg=24)
            for sx in (-1, 1):
                screw(p, (sx * 0.025, 0, 0.012), (sx, 0, 0), r=0.003)
    p.build(root)


def battery_pack(root, c, size, led_n, plug_n, lead_end, cap="light_grey"):
    """Smart battery: ribbed shell with a top panel, carry handle, charge-LED row and power button, and a
    high-current plug whose lead runs into the body."""
    p = Part("battery")
    w, d, h = size
    c, led_n, plug_n = Vector(c), Vector(led_n), Vector(plug_n)
    top = c.z + h / 2
    p.box("dark_grey", size, c, bevel=min(size) * 0.09, seg=3)
    p.box(cap, (w - 0.03, d - 0.03, 0.006), (c.x, c.y, top), bevel=0.0025)
    for sx in (-1, 1):
        for k in range(5):
            p.box("dark_grey", (0.007, d * 0.72, 0.006), (c.x + sx * (w / 2 + 0.0015), c.y, c.z - h * 0.3 + k * h * 0.14), bevel=0.0015, seg=1)
    hx, k = w * 0.3, min(1.0, max(0.6, w / 0.3))         # handle scaled to the pack
    for sx in (-1, 1):
        p.box("black", (0.02 * k, 0.028 * k, 0.03 * k), (c.x + sx * hx, c.y, top + 0.018 * k), bevel=0.006 * k)
    p.tube("black", chaikin([(c.x - hx, c.y, top + 0.026 * k), (c.x - hx + 0.012 * k, c.y, top + 0.046 * k), (c.x + hx - 0.012 * k, c.y, top + 0.046 * k),
                             (c.x + hx, c.y, top + 0.026 * k)], 2), 0.0085 * k, seg=12)
    p.rod("rubber", (c.x - hx * 0.6, c.y, top + 0.046 * k), (c.x + hx * 0.6, c.y, top + 0.046 * k), 0.0115 * k, seg=16)
    with p.at(facing(c + Vector((led_n.x * w / 2, led_n.y * d / 2, 0)), led_n)):
        for k in range(4):
            p.box("led_green", (0.008, 0.005, 0.003), (w * 0.12 + k * 0.014, h * 0.28, 0.0006), bevel=0)
        p.cyl("black", 0.006, 0.004, (w * 0.12 + 4 * 0.014 + 0.006, h * 0.28, 0.001), seg=16)
    pp = c + Vector((plug_n.x * (w / 2 + 0.012), plug_n.y * (d / 2 + 0.012), -h * 0.15)) + Z.cross(plug_n).normalized() * w * 0.18
    with p.at(facing(pp, plug_n)):
        p.box("plug", (0.06, 0.032, 0.024), (0, 0, 0), bevel=0.004)
        p.box("black", (0.05, 0.022, 0.004), (0, 0, 0.012), bevel=0.001)
    e = pp + plug_n * 0.012
    p.tube("black", chaikin([e, e + plug_n * 0.02 - Z * 0.01, Vector(lead_end) + plug_n * 0.014 + Z * 0.03, Vector(lead_end)], 2), 0.008, seg=10)
    p.build(root)


def frame_plates(p, outline, zb, zt, t, lobes, standoffs):
    """Carbon top and bottom plates (zb/zt are their inner faces) with arm-mount lobes, hex standoffs and screws."""
    for z0, z1 in ((zb - t, zb), (zt, zt + t)):
        p.prism("carbon_plate", outline, z0, z1, bevel=t * 0.25)
        for m, L, W in lobes:   # a hair thinner than the plate so the faces don't fight
            p.prism("carbon_plate", stadium(L, W), z0 + 0.0003, z1 - 0.0003, m=m, bevel=t * 0.25)
    for x, y in standoffs:
        p.lathe("alu", [(0, zb), (0.0055, zb), (0.0055, zt), (0, zt)], m=T(x, y), seg=6)
        screw(p, (x, y, zt + t), Z, r=0.0042)
        screw(p, (x, y, zb - t), -Z, r=0.0042)


def leg_gear(root, tops, feet, r, bar_z):
    """Four legs with rubber dampers under their brackets, T-clamped cross bars front and rear, rubber feet."""
    g = Part("gear")
    bars = []
    for top, foot in zip(tops, feet):
        d = (foot - top).normalized()
        g.box("alu_dark", (0.05, 0.046, 0.03), top + Vector((0, 0, 0.012)), bevel=0.006)
        with g.at(align(top, d)):
            g.lathe("rubber", [(0, 0), (r * 1.3, 0), (r * 1.5, 0.008), (r * 1.3, 0.016), (r * 1.5, 0.024), (r * 1.3, 0.032), (r * 1.4, 0.04), (0, 0.04)], seg=20)
            g.lathe("alu", [(0, 0.04), (r * 1.3, 0.04), (r * 1.3, 0.072), (r * 1.12, 0.078), (0, 0.078)], seg=20)
        g.rod("carbon", top + d * 0.076, foot - d * 0.03, r, seg=16)
        with g.at(align(foot, d)):
            g.lathe("rubber", [(0, -0.05), (r * 1.25, -0.05), (r * 1.4, -0.042), (r * 1.4, 0.0), (r * 1.15, 0.012), (r * 0.6, 0.017), (0, 0.018)], seg=20)
        bars.append(top.lerp(foot, (top.z - bar_z) / (top.z - foot.z)))
    for i, j in ((0, 1), (2, 3)):                      # tops/feet ordered FR, FL, RL, RR
        g.rod("carbon", bars[i], bars[j], r * 0.8, seg=14)
        for k in (i, j):
            with g.at(align(bars[k], feet[k] - tops[k])):
                g.lathe("alu", [(0, -0.022), (r * 1.45, -0.022), (r * 1.45, 0.022), (0, 0.022)], seg=20)
                g.cyl("steel", 0.003, 0.004, (r * 1.45, 0, 0.012), rot=(0, math.pi / 2, 0), seg=8)
    g.build(root)


# FR, FL, RL, RR (Blender -Y is the nose); props alternate CCW / CW like a standard quad X
CORNERS = [Vector((1, -1, 0)).normalized(), Vector((-1, -1, 0)).normalized(),
           Vector((-1, 1, 0)).normalized(), Vector((1, 1, 0)).normalized()]
SPIN = [1, -1, 1, -1]
LIGHTS = ["green", "red", "white", "white"]            # starboard green, port red, white aft


# ------------------------------------------------------------------ models
def build_ares(root):
    R, ZA, TR = 1.05, 0.86, 0.024                       # motor radius (2.1 m motor diagonal), arm height, tube
    ZB, ZT = ZA - TR - 0.002, ZA + TR + 0.002           # inner faces of the frame plates
    HZ = 0.812                                          # hose height under the arms
    body = Part("body")
    body.box("shell", (0.46, 0.50, 0.166), (0, 0, 0.743), bevel=0.03, seg=3)        # lower shell
    body.box("shell", (0.46, 0.50, 0.10), (0, 0, 0.944), bevel=0.03, seg=3)         # top cover
    body.box("seam", (0.44, 0.48, ZT - ZB), (0, 0, ZA), bevel=0.008)                # avionics bay between the plates
    for sx in (-1, 1):
        for sy in (-1, 1):
            vent(body, (sx * 0.23, sy * 0.13, 0.745), (sx, 0, 0), 0.06, 0.07)
            screw(body, (sx * 0.19, sy * 0.25, 0.70), (0, sy, 0))
        vent(body, (sx * 0.183, 0, 0.994), Z, 0.022, 0.16, slats=8)
        for y in (-0.09, 0.09):                                                     # carry handles
            body.box("black", (0.026, 0.024, 0.026), (sx * 0.238, y, 0.944), bevel=0.006)
        body.tube("black", chaikin([(sx * 0.245, -0.09, 0.944), (sx * 0.264, -0.084, 0.944), (sx * 0.266, -0.05, 0.944),
                                    (sx * 0.266, 0.05, 0.944), (sx * 0.264, 0.084, 0.944), (sx * 0.245, 0.09, 0.944)], 2), 0.008, seg=12)
        body.box("black", (0.02, 0.26, 0.011), (sx * 0.12, 0, 0.9995), bevel=0.003)  # battery rails
    vent(body, (0, 0.25, 0.944), (0, 1, 0), 0.20, 0.034, slats=4)
    for x, y in ((-0.195, -0.215), (0.195, -0.215), (-0.10, 0.215), (0.10, 0.215)):
        screw(body, (x, y, 0.994), Z)
    led_strip(body, (0, -0.25, 0.787), (0, -1, 0), 0.15, 6)
    for sy in (-1, 1):
        for x in (-0.105, 0.105):
            seam(body, (x, sy * 0.25, 0.69), (x, sy * 0.25, 0.778), (0, sy, 0))
    body.build(root)

    fr = Part("frame")
    frame_plates(fr, rounded_rect(0.50, 0.54, 0.05), ZB, ZT, 0.005, [(along(P(d, 0.33, 0), d), 0.12, 0.105) for d in CORNERS],
                 [(sx * 0.238, sy * 0.09) for sx in (-1, 1) for sy in (-1, 1)] + [(sx * 0.09, sy * 0.258) for sx in (-1, 1) for sy in (-1, 1)])
    for d in CORNERS:                                   # screws through the plates into the arm root clamps
        for rr in (0.37, 0.40):
            for s in (-1, 1):
                q = P(d, rr, 0) + Vector((-d.y, d.x, 0)) * 0.024 * s
                screw(fr, (q.x, q.y, ZT + 0.005), Z, r=0.0038)
                screw(fr, (q.x, q.y, ZB - 0.005), -Z, r=0.0038)
    fr.build(root)

    TC, TS, TB = Vector((0, 0, 0.48)), (0.44, 0.46, 0.36), (0.7, 0.7)               # 50 L
    tank = Part("tank")
    tank.box("tank", TS, TC, bevel=0.04, seg=3, bottom=TB)
    level_window(tank, *tank_point(TC, TS, TB, "y-", 0.12, 0.20), 0.24)
    pt, n = tank_point(TC, TS, TB, "y-", -0.10, 0.27)
    fill_cap(tank, pt - n * 0.004, (n + Z * 0.7).normalized(), 0.034)
    for side in ("x+", "x-"):
        for u in (-0.12, 0.12):
            latch(tank, *tank_point(TC, TS, TB, side, u, 0.31))
    sb = outlet_strainer(tank, (-0.06, 0.0, 0.30))
    tank.build(root)

    battery_pack(root, (0, 0, 1.08), (0.32, 0.24, 0.15), (0, -1, 0), (0, 1, 0), (-0.058, 0.205, 0.994))
    for nm, loc, n in (("radar_front", (0, -0.25, 0.735), (0, -1, 0)), ("radar_rear", (0, 0.25, 0.735), (0, 1, 0)),
                       ("radar_left", (-0.23, 0, 0.735), (-1, 0, 0)), ("radar_right", (0.23, 0, 0.735), (1, 0, 0))):
        radar_module(root, nm, loc, n, 0.12, 0.075)
    radar_module(root, "radar_down", (0, 0.10, 0.30), (0, 0, -1), 0.10, 0.07)
    rp = Part("radar_up")
    rp.lathe("radar", [(0, 0.994), (0.042, 0.994), (0.042, 1.004), (0.038, 1.008), (0, 1.008)], m=T(0, -0.19), seg=32)
    rp.lathe("radome", [(0, 1.006), (0.036, 1.006), (0.034, 1.016), (0.026, 1.026), (0.014, 1.031), (0, 1.032)], m=T(0, -0.19), seg=32)
    rp.build(root)
    fpv(root, (0, -0.25, 0.944), (0, -1, 0))
    for k, sx in ((1, -1), (2, 1)):
        gnss(root, f"gnss_{k}", (sx * 0.17, 0.19, 0.994), 0.17)

    pin, pout = pump_unit(root, (0.03, 0.0, 0.205), (1, 0, 0), out=(0, -1, 0), mount=0.06)
    fa, fb = pout + Vector((0, -0.002, 0)), pout + Vector((0, -0.052, 0))
    flowmeter(root, fa, fb)
    hoses = Part("hoses")
    hose_run(hoses, [sb, sb - Z * 0.012, pin - Vector((0.02, 0, 0)), pin], 0.0085)
    mf = fb + Vector((0, -0.016, 0))
    hoses.box("valve", (0.05, 0.03, 0.028), mf, bevel=0.004)                       # 4-way manifold
    for i, d in enumerate(CORNERS):
        n, ang, tip = i + 1, math.atan2(d.y, d.x), P(d, R, ZA)
        m = along(P(d, 0, ZA), d)
        arm_part(root, f"arm_{n}", m, 0.18, R, TR, 0.53, (0.385, 0.06, 0.066, ZT - ZB), ties=(0.68, 0.88))
        fold_joint(root, f"joint_{n}", m @ T(0.53), TR)
        mot = Part(f"motor_{n}")
        tube_clamp(mot, along(tip, d), 0.11, 0.07, 0.06)
        mot.lathe("alu_dark", [(0, ZA + 0.03), (0.074, ZA + 0.03), (0.074, ZA + 0.034), (0, ZA + 0.034)], m=T(tip.x, tip.y), seg=36)
        esc_pod(mot, (tip.x, tip.y, ZA - 0.03), 0.055, 0.08)
        top = motor_unit(mot, (tip.x, tip.y, ZA + 0.034), 0.068, 0.085)
        mot.build(root)
        make_prop(root, f"prop_{n}", (tip.x, tip.y, top + prop_seat(0.042)), R=0.71, cmax=0.105, pitch=0.5,
                  hub_r=0.042, spin=SPIN[i], phi=ang + math.radians(60 + 35 * i), tip_from=0.92)
        nav_light(root, f"light_{n}", P(d, R + 0.067, ZA), d, LIGHTS[i])
        inlet = fan_nozzle(root, f"nozzle_{n}", (tip.x, tip.y, ZA - 0.11), -d)

        sx, sy = math.copysign(1, d.x), math.copysign(1, d.y)
        start = Vector((mf.x + sx * 0.025, mf.y + sy * 0.008, mf.z))
        hoses.rod("valve", start, start + Vector((sx * 0.012, 0, 0)), 0.0055, r2=0.004, seg=12)
        way = Vector((sx * 0.12, -0.06, 0.25)) if sy > 0 else Vector((sx * 0.11, -0.14, 0.25))
        hose_run(hoses, [start + Vector((sx * 0.01, 0, 0)), start + Vector((sx * 0.03, 0, 0.004)), way, P(d, 0.20, 0.285), P(d, 0.25, 0.30),
                         P(d, 0.285, 0.48), P(d, 0.33, 0.65), P(d, 0.355, 0.72), P(d, 0.365, 0.79), P(d, 0.40, HZ), P(d, R - 0.12, HZ),
                         P(d, R - 0.09, HZ - 0.012), P(d, R - 0.085, 0.70), P(d, R - 0.06, 0.662), inlet], 0.007)
        for rr in (0.78, 0.95):
            hose_clip(hoses, P(d, rr, HZ), d, ZA - TR, 0.007)
    hoses.build(root)

    sg = [(1, -1), (-1, -1), (-1, 1), (1, 1)]
    leg_gear(root, [Vector((sx * 0.245, sy * 0.19, 0.70)) for sx, sy in sg],
             [Vector((sx * 0.50, sy * 0.32, 0.035)) for sx, sy in sg], 0.018, 0.10)


def build_t40(root):
    MX, MY, ZA, TR = 0.715, 0.865, 0.56, 0.026          # 1.37 m props -> about 2.8 x 3.1 m unfolded
    ZB, ZT = ZA - TR - 0.002, ZA + TR + 0.002
    CY, HZ = 0.02, 0.502                                # body centre (the tank sits forward), hose height
    tips = [Vector((MX, -MY, ZA)), Vector((-MX, -MY, ZA)), Vector((-MX, MY, ZA)), Vector((MX, MY, ZA))]
    roots = [Vector((math.copysign(0.17, t.x), math.copysign(0.27, t.y), ZA)) for t in tips]

    body = Part("body")
    body.box("body_dark", (0.40, 0.64, 0.05), (0, CY, 0.50), bevel=0.012, seg=3)     # lower shell
    body.box("body_dark", (0.40, 0.64, 0.045), (0, CY, 0.6175), bevel=0.012, seg=3)  # upper shell
    body.box("seam", (0.38, 0.62, ZT - ZB), (0, CY, ZA), bevel=0.006)
    for sx in (-1, 1):
        for y in (-0.10, 0.17):
            vent(body, (sx * 0.20, y, 0.50), (sx, 0, 0), 0.12, 0.018, slats=3)
        for y in (-0.22, 0.26):
            screw(body, (sx * 0.20, y, 0.50), (sx, 0, 0), r=0.0038)
        vent(body, (sx * 0.168, 0.17, 0.64), Z, 0.03, 0.18, slats=9)
        body.box("black", (0.012, 0.23, 0.04), (sx * 0.142, 0.19, 0.66), bevel=0.003)   # battery slot guides
        seam(body, (sx * 0.20, -0.27, 0.6175), (sx * 0.20, 0.31, 0.6175), (sx, 0, 0))
    led_strip(body, (0, 0.34, 0.6175), (0, 1, 0), 0.12, 6)
    body.build(root)

    fr = Part("frame")
    lobes = [(along(rt + (tp - rt).normalized() * 0.07 - Z * ZA, tp - rt), 0.08, 0.10) for rt, tp in zip(roots, tips)]
    frame_plates(fr, [(x, y + CY) for x, y in rounded_rect(0.42, 0.66, 0.05)], ZB, ZT, 0.004, lobes,
                 [(sx * 0.198, CY + sy * 0.12) for sx in (-1, 1) for sy in (-1, 1)] + [(sx * 0.08, CY + sy * 0.318) for sx in (-1, 1) for sy in (-1, 1)])
    for rt, tp in zip(roots, tips):
        d = (tp - rt).normalized()
        for x in (0.08, 0.11):
            for s in (-1, 1):
                q = rt + d * x + Vector((-d.y, d.x, 0)) * 0.026 * s
                screw(fr, (q.x, q.y, ZT + 0.004), Z, r=0.0038)
                screw(fr, (q.x, q.y, ZB - 0.004), -Z, r=0.0038)
    fr.build(root)

    TC, TS, TB = Vector((0, -0.12, 0.475)), (0.34, 0.36, 0.42), (0.8, 0.8)            # 40 L, front/centre
    tank = Part("tank")
    tank.box("tank", TS, TC, bevel=0.04, seg=3, bottom=TB)
    fill_cap(tank, (0, -0.17, 0.682), Z, 0.07)
    level_window(tank, *tank_point(TC, TS, TB, "x-", 0.0, 0.115), 0.16)
    for side in ("x+", "x-"):
        for u in (-0.08, 0.06):
            latch(tank, *tank_point(TC, TS, TB, side, u, 0.17))
    sb = outlet_strainer(tank, (0, -0.12, 0.265))
    tank.build(root)

    battery_pack(root, (0, 0.19, 0.723), (0.27, 0.23, 0.15), (0, 1, 0), (0, 1, 0), (-0.05, 0.341, 0.615))
    radar_dome(root, "radar_front", (0, -0.27, 0.34), (0, -1, 0))
    radar_dome(root, "radar_rear", (0, 0.33, 0.40), (0, 1, 0), bracket=((0.06, 0.03, 0.012), (0, 0.33, 0.478)))
    fpv(root, (0, -0.292, 0.452), (0, -1, 0), mount=0.006)
    for k, sx in ((1, -1), (2, 1)):
        gnss(root, f"gnss_{k}", (sx * 0.165, 0.30, 0.64), 0.13)

    pin, pout = pump_unit(root, (0, 0.135, 0.36), (0, 1, 0), out=(0, 0, 1), mount=0.084)
    flowmeter(root, pout + Z * 0.002, pout + Z * 0.037)
    hoses = Part("hoses")
    hose_run(hoses, [sb, sb - Z * 0.012, (0, -0.04, 0.172), (0, 0.04, 0.22), (0, 0.062, 0.33), (0, 0.072, 0.36), pin], 0.009)
    tj = pout + Z * 0.048
    hoses.box("valve", (0.03, 0.03, 0.02), tj, bevel=0.003)                          # T splitter to the two sprinklers
    for i, (rt, tip) in enumerate(zip(roots, tips)):
        n = i + 1
        d, L = (tip - rt).normalized(), (tip - rt).length
        ang = math.atan2(d.y, d.x)
        m = along(rt, d)
        arm_part(root, f"arm_{n}", m, 0.0, L, TR, 0.20, (0.095, 0.06, 0.07, ZT - ZB), ties=(0.42, 0.62))
        fold_joint(root, f"joint_{n}", m @ T(0.20), TR)
        up = Part(f"motor_{n}")                                                      # coaxial mount + upper motor
        with up.at(along(tip, d)):
            up.box("black", (0.11, 0.10, 0.10), (0, 0, 0), bevel=0.016, seg=3)
            with up.at(ROT_Y90):
                up.lathe("alu_dark", [(0, -0.075), (TR * 1.4, -0.075), (TR * 1.4, -0.055), (0, -0.055)], seg=24)
            for sx in (-1, 1):
                for sy in (-1, 1):
                    screw(up, (sx * 0.036, sy * 0.034, 0.05), Z, r=0.0042)
                screw(up, (sx * 0.03, 0.05, 0.0), (0, 1, 0), r=0.004)
                screw(up, (sx * 0.03, -0.05, 0.0), (0, -1, 0), r=0.004)
        up.lathe("alu_dark", [(0, ZA + 0.05), (0.07, ZA + 0.05), (0.07, ZA + 0.054), (0, ZA + 0.054)], m=T(tip.x, tip.y), seg=36)
        top = motor_unit(up, (tip.x, tip.y, ZA + 0.054), 0.065, 0.075)
        up.build(root)
        lo = Part(f"motor_{n + 4}")
        lo.lathe("alu_dark", [(0, ZA - 0.054), (0.07, ZA - 0.054), (0.07, ZA - 0.05), (0, ZA - 0.05)], m=T(tip.x, tip.y), seg=36)
        bot = motor_unit(lo, (tip.x, tip.y, ZA - 0.054), 0.065, 0.075, up=-1)
        lo.build(root)
        phi = ang + math.radians(75 + 40 * i)
        make_prop(root, f"prop_{n}", (tip.x, tip.y, top + prop_seat(0.04)), R=0.685, cmax=0.10, pitch=0.5,
                  hub_r=0.04, spin=SPIN[i], phi=phi)
        make_prop(root, f"prop_{n + 4}", (tip.x, tip.y, bot - prop_seat(0.04)), R=0.685, cmax=0.10, pitch=0.5,
                  hub_r=0.04, spin=-SPIN[i], phi=phi + math.radians(90), down=True)
        nav_light(root, f"light_{n}", tip + d * 0.067, d, LIGHTS[i])
        if tip.y > 0:                                # centrifugal sprinklers under the rear rotors
            sprinkler(root, f"nozzle_{1 if tip.x < 0 else 2}", (tip.x, tip.y, bot - prop_seat(0.04) - 0.0284))
            sx = math.copysign(1, tip.x)
            hoses.rod("valve", tj + Vector((sx * 0.015, 0, 0)), tj + Vector((sx * 0.028, 0, 0)), 0.006, r2=0.0045, seg=12)
            hose_run(hoses, [tj + Vector((sx * 0.026, 0, 0)), (sx * 0.10, 0.15, 0.462), (sx * 0.21, 0.27, 0.465),
                             (sx * 0.232, 0.33, HZ + 0.005), rt + d * 0.16 + Vector((0, 0, HZ - ZA)), rt + d * (L - 0.075) + Vector((0, 0, HZ - ZA)),
                             tip - d * 0.06 + Vector((0, 0, 0.512 - ZA)), tip - d * 0.045 + Vector((0, 0, 0.53 - ZA))], 0.008)
            for x in (0.40, 0.60):
                hose_clip(hoses, rt + d * x + Vector((0, 0, HZ - ZA)), d, ZA - TR, 0.008)
    hoses.build(root)

    sg = [(1, -1), (-1, -1), (-1, 1), (1, 1)]
    leg_gear(root, [Vector((sx * 0.185, sy * 0.17, 0.475)) for sx, sy in sg],
             [Vector((sx * 0.27, sy * 0.30, 0.035)) for sx, sy in sg], 0.017, 0.075)


def build_pegasus(root):
    R, ZA, TR = 0.60, 0.42, 0.02                        # 1.2 m motor diagonal, 30 in props
    ZB, ZT = ZA - TR - 0.002, ZA + TR + 0.002
    HZ = 0.379
    body = Part("body")
    body.box("shell", (0.30, 0.32, 0.032), (0, 0, 0.376), bevel=0.01, seg=2)        # lower shell
    body.box("shell", (0.30, 0.32, 0.055), (0, 0, 0.4755), bevel=0.016, seg=3)      # upper shell
    body.box("seam", (0.27, 0.29, ZT - ZB), (0, 0, ZA), bevel=0.005)
    for sx in (-1, 1):
        vent(body, (sx * 0.118, -0.03, 0.503), Z, 0.02, 0.13, slats=7)
        for y in (-0.06, 0.06):                                                     # carry handles
            body.box("black", (0.018, 0.016, 0.018), (sx * 0.155, y, 0.4755), bevel=0.004)
        body.tube("black", chaikin([(sx * 0.16, -0.06, 0.4755), (sx * 0.172, -0.056, 0.4755), (sx * 0.174, -0.03, 0.4755),
                                    (sx * 0.174, 0.03, 0.4755), (sx * 0.172, 0.056, 0.4755), (sx * 0.16, 0.06, 0.4755)], 2), 0.0055, seg=10)
        body.box("black", (0.014, 0.15, 0.006), (sx * 0.07, 0, 0.506), bevel=0.002)  # battery rails
        seam(body, (sx * 0.065, -0.16, 0.466), (sx * 0.065, -0.16, 0.486), (0, -1, 0))
    led_strip(body, (0, -0.16, 0.4755), (0, -1, 0), 0.10, 5)
    for x, y in ((-0.125, -0.13), (0.125, -0.13), (-0.06, 0.135), (0.06, 0.135)):
        screw(body, (x, y, 0.503), Z, r=0.0035)
    body.build(root)

    fr = Part("frame")
    frame_plates(fr, rounded_rect(0.33, 0.35, 0.035), ZB, ZT, 0.003, [(along(P(d, 0.215, 0), d), 0.09, 0.07) for d in CORNERS],
                 [(sx * 0.155, sy * 0.07) for sx in (-1, 1) for sy in (-1, 1)] + [(sx * 0.07, sy * 0.165) for sx in (-1, 1) for sy in (-1, 1)])
    for d in CORNERS:
        for rr in (0.245, 0.265):
            for s in (-1, 1):
                q = P(d, rr, 0) + Vector((-d.y, d.x, 0)) * 0.017 * s
                screw(fr, (q.x, q.y, ZT + 0.003), Z, r=0.003)
                screw(fr, (q.x, q.y, ZB - 0.003), -Z, r=0.003)
    fr.build(root)

    TC, TS, TB = Vector((0, 0, 0.2625)), (0.26, 0.28, 0.195), (0.72, 0.72)         # 9.5 L
    tank = Part("tank")
    tank.box("tank", TS, TC, bevel=0.025, seg=3, bottom=TB)
    pt, n = tank_point(TC, TS, TB, "y-", 0.065, 0.11)
    with tank.at(facing(pt, n)):                                                    # status panel
        tank.box("black", (0.05, 0.05, 0.004), (0, 0, 0.0005), bevel=0.003, seg=1)
        for i in range(3):
            for j in range(2):
                tank.box("led_green" if j else "window", (0.01, 0.01, 0.0015), (-0.014 + i * 0.014, -0.008 + j * 0.016, 0.0028), bevel=0)
    level_window(tank, *tank_point(TC, TS, TB, "y-", -0.055, 0.10), 0.12)
    pt, n = tank_point(TC, TS, TB, "x+", -0.05, 0.15)
    fill_cap(tank, pt - n * 0.003, (n + Z * 0.8).normalized(), 0.024)
    for side in ("x+", "x-"):
        for u in ((0.07,) if side == "x+" else (-0.07, 0.07)):
            latch(tank, *tank_point(TC, TS, TB, side, u, 0.162))
    sb = outlet_strainer(tank, (-0.06, 0.06, 0.165), s=0.7)
    tank.build(root)

    battery_pack(root, (0, 0, 0.5365), (0.20, 0.13, 0.055), (0, -1, 0), (0, 1, 0), (-0.03, 0.12, 0.503))
    radar_module(root, "radar_down", (0, -0.05, 0.165), (0, 0, -1), 0.06, 0.04, d=0.018)
    for k, sx in ((1, -1), (2, 1)):
        an = Part(f"antenna_{k}")
        x, y = sx * 0.12, 0.115
        an.lathe("black", [(0, 0.503), (0.013, 0.503), (0.013, 0.522), (0.009, 0.528), (0, 0.528)], m=T(x, y), seg=16)
        an.cyl("alu_dark", 0.004, 0.03, (x, y, 0.515), rot=(0, math.pi / 2, 0), seg=10)
        an.lathe("black", [(0, 0.526), (0.0075, 0.526), (0.0065, 0.62), (0.0045, 0.63), (0.0045, 0.785), (0.006, 0.79), (0.006, 0.80), (0, 0.803)], m=T(x, y), seg=12)
        an.build(root)

    pin, pout = pump_unit(root, (-0.01, 0.02, 0.138), (1, 0, 0), s=0.7, out=(0, 1, 0))
    fb = pout + Vector((0, 0.04, 0))
    flowmeter(root, pout + Vector((0, 0.002, 0)), fb, r=0.01)
    hoses = Part("hoses")
    hose_run(hoses, [sb, sb - Z * 0.01, (sb.x, sb.y - 0.02, sb.z - 0.02), (pin.x - 0.012, pin.y, pin.z - 0.012), pin], 0.006)
    mf = fb + Vector((0, 0.014, 0))
    hoses.box("valve", (0.034, 0.022, 0.02), mf, bevel=0.003)
    for i, d in enumerate(CORNERS):
        n, ang, tip = i + 1, math.atan2(d.y, d.x), P(d, R, ZA)
        m = along(P(d, 0, ZA), d)
        arm_part(root, f"arm_{n}", m, 0.13, R, TR, 0.335, (0.255, 0.04, 0.046, ZT - ZB), ties=(0.43, 0.50), mat="arm_grey")
        fold_joint(root, f"joint_{n}", m @ T(0.335), TR)
        mot = Part(f"motor_{n}")
        tube_clamp(mot, along(tip, d), 0.075, 0.054, 0.045)
        mot.lathe("alu_dark", [(0, ZA + 0.0225), (0.047, ZA + 0.0225), (0.047, ZA + 0.0255), (0, ZA + 0.0255)], m=T(tip.x, tip.y), seg=32)
        esc_pod(mot, (tip.x, tip.y, ZA - 0.0225), 0.03, 0.035, fins=12)
        top = motor_unit(mot, (tip.x, tip.y, ZA + 0.0255), 0.042, 0.05, windows=10)
        mot.build(root)
        make_prop(root, f"prop_{n}", (tip.x, tip.y, top + prop_seat(0.024)), R=0.38, cmax=0.06, pitch=0.25,
                  hub_r=0.024, spin=SPIN[i], phi=ang + math.radians(60 + 35 * i), tip_from=0.92)
        nav_light(root, f"light_{n}", P(d, R + 0.046, ZA), d, LIGHTS[i], s=0.7)
        inlet = fan_nozzle(root, f"nozzle_{n}", (tip.x, tip.y, ZA - 0.0575), -d, s=0.75)
        sx, sy = math.copysign(1, d.x), math.copysign(1, d.y)
        start = Vector((mf.x + sx * 0.017, mf.y + sy * 0.006, mf.z))
        hoses.rod("valve", start, start + Vector((sx * 0.01, 0, 0)), 0.004, r2=0.003, seg=10)
        way = [(sx * 0.075, 0.12, 0.155)] if sy > 0 else [(sx * 0.085, 0.09, 0.15), (sx * 0.10, -0.02, 0.155)]
        hose_run(hoses, [start + Vector((sx * 0.008, 0, 0)), start + Vector((sx * 0.03, 0, 0.01))] + way + [
                         (sx * 0.105, sy * 0.105, 0.175), P(d, 0.17, 0.25), P(d, 0.205, 0.35), P(d, 0.235, 0.375), P(d, 0.28, HZ),
                         P(d, R - 0.075, HZ), P(d, R - 0.058, HZ - 0.012), P(d, R - 0.052, 0.33), P(d, R - 0.04, 0.297), inlet], 0.0045)
        for rr in (0.46, 0.53):
            hose_clip(hoses, P(d, rr, HZ), d, ZA - TR, 0.0045)
    hoses.build(root)

    gim = Part("gimbal")                     # 3-axis gimbal on a damped plate under the nose
    gim.box("alu_dark", (0.06, 0.07, 0.005), (0, -0.175, 0.3575), bevel=0.0015, seg=1)
    for sx in (-1, 1):
        for sy in (-1, 1):
            gim.sphere("rubber", 0.006, (sx * 0.021, -0.175 + sy * 0.026, 0.35), seg=12, rings=6)
    gim.box("alu_dark", (0.052, 0.062, 0.004), (0, -0.175, 0.3425), bevel=0.0012, seg=1)
    gim.lathe("dark_grey", [(0, 0.318), (0.018, 0.318), (0.02, 0.322), (0.02, 0.336), (0.018, 0.3405), (0, 0.3405)], m=T(0, -0.19), seg=28)   # yaw
    gim.tube("alu_black", chaikin([(0, -0.19, 0.314), (0.042, -0.19, 0.314), (0.046, -0.19, 0.306), (0.046, -0.19, 0.29)], 2), 0.0045, seg=10)
    gim.lathe("dark_grey", [(0, -0.008), (0.015, -0.008), (0.016, -0.005), (0.016, 0.006), (0.014, 0.008), (0, 0.008)], m=T(0.046, -0.178, 0.30) @ Matrix.Rotation(math.pi / 2, 4, 'X'), seg=24)   # roll
    gim.lathe("dark_grey", [(0, -0.008), (0.015, -0.008), (0.016, -0.005), (0.016, 0.006), (0.014, 0.008), (0, 0.008)], m=T(0.04, -0.2, 0.275) @ ROT_Y90, seg=24)   # pitch
    gim.build(root)
    cam = Part("camera")
    cam.box("black", (0.06, 0.05, 0.045), (0, -0.2, 0.275), bevel=0.008, seg=2)
    for k in range(4):
        cam.box("black", (0.05, 0.003, 0.006), (0, -0.174, 0.262 + k * 0.009), bevel=0)        # heat-sink fins
    cam.lathe("dark_grey", [(0, 0), (0.018, 0), (0.018, 0.016), (0.0155, 0.02), (0, 0.02)], m=T(0, -0.224, 0.275) @ Matrix.Rotation(math.pi / 2, 4, 'X'), seg=28)
    cam.cyl("lens", 0.0115, 0.003, (0, -0.2445, 0.275), rot=(math.pi / 2, 0, 0), seg=24)
    cam.build(root)

    g = Part("gear")                         # hoop legs on two skids
    for sx in (-1, 1):
        for sy in (-1, 1):
            g.box("alu_dark", (0.03, 0.03, 0.012), (sx * 0.14, sy * 0.11, 0.358), bevel=0.003)
            with g.at(align((sx * 0.14, sy * 0.11, 0.352), (sx * 0.06, sy * 0.01, -0.03))):
                g.lathe("rubber", [(0, 0), (0.013, 0), (0.014, 0.006), (0.012, 0.012), (0, 0.012)], seg=16)
            g.tube("black", chaikin([(sx * 0.15, sy * 0.112, 0.345), (sx * 0.21, sy * 0.12, 0.33), (sx * 0.26, sy * 0.13, 0.20),
                                     (sx * 0.25, sy * 0.13, 0.05), (sx * 0.25, sy * 0.13, 0.018)], 3), 0.009, seg=12)
            with g.at(T(sx * 0.25, sy * 0.13, 0.018) @ Matrix.Rotation(math.pi / 2, 4, 'X')):
                g.lathe("alu_dark", [(0, -0.016), (0.0145, -0.016), (0.0145, 0.016), (0, 0.016)], seg=16)   # T-joint on the skid
        g.tube("black", chaikin([(sx * 0.25, -0.25, 0.045), (sx * 0.25, -0.20, 0.012), (sx * 0.25, 0.20, 0.012),
                                 (sx * 0.25, 0.25, 0.045)], 3), 0.011, seg=14)
        for sy in (-1, 1):
            g.sphere("rubber", 0.0125, (sx * 0.25, sy * 0.25, 0.045), seg=14, rings=8)
    g.build(root)


def reset():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for x in list(coll):
            coll.remove(x)


def ground_and_export(root, path):
    """Shift the model so the landing gear touches z = 0, then write a .glb."""
    bpy.context.view_layer.update()
    zmin = min((ob.matrix_world @ v.co).z for ob in root.children for v in ob.data.vertices)
    for ob in root.children:
        ob.location.z -= zmin
    bpy.ops.export_scene.gltf(filepath=path, export_format='GLB', use_selection=False, export_yup=True,
                              export_apply=True, export_extras=True, export_texcoords=False, export_normals=True,
                              export_cameras=False, export_lights=False, export_animations=False)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = os.path.abspath(argv[0] if argv else "img/drones/3d")
    os.makedirs(out, exist_ok=True)
    for key, fn in (("ares", build_ares), ("t40", build_t40), ("pegasus", build_pegasus)):
        reset()
        PALETTE["alu_accent"] = (ACCENT[key][0], 0.35, 0.7)
        PALETTE["prop_tip"] = (ACCENT[key][1], 0.4, 0.0)
        root = bpy.data.objects.new(key, None)
        bpy.context.scene.collection.objects.link(root)
        fn(root)
        ground_and_export(root, os.path.join(out, key + ".glb"))
        print(key, len(root.children), "parts ->", os.path.join(out, key + ".glb"))
