"""Simplified 3D models of the three spray drones on the Drone Technology page, for the three.js viewer.
Hylio ARES HYL-150, DJI Agras T40 and Hylio PEGASUS HYL-30. These are illustrations: proportions follow
published specs (prop size, motor spacing, tank volume) but details are simplified.

Usage (Blender 4.x, from the repository root):
  blender -b --factory-startup --python tools/gen_drones_blender.py -- img/drones/3d
Writes ares.glb, t40.glb and pegasus.glb.

Conventions: metres, glTF +Y up, the nose faces +Z (Blender -Y), bottom of the landing gear at y = 0.
Every rotor is its own node prop_N with its origin on the motor hub, so it can be spun about its local +Y.
Node extras carry spin (+1 = counter-clockwise seen from above, -1 = clockwise).
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix, Euler

# name: (sRGB colour, roughness, metallic)
PALETTE = {
    "white": ("#eceeee", 0.42, 0.0),
    "light_grey": ("#c3c6c9", 0.45, 0.0),
    "grey": ("#868b91", 0.45, 0.0),
    "dark_grey": ("#3b3e43", 0.5, 0.0),
    "black": ("#1c1d20", 0.45, 0.0),
    "carbon": ("#151618", 0.3, 0.0),
    "prop": ("#111214", 0.35, 0.0),
    "prop_tip": ("#f2b705", 0.4, 0.0),
    "metal": ("#a3a8ae", 0.3, 0.9),
    "tank": ("#f3f2ea", 0.3, 0.0),
    "hose": ("#a9bccb", 0.25, 0.0),
    "nozzle": ("#f07c1a", 0.45, 0.0),
    "radar": ("#2b2e33", 0.25, 0.0),
    "rubber": ("#0d0d0e", 0.85, 0.0),
    "lens": ("#06080b", 0.08, 0.3),
    "led": ("#2fd27a", 0.3, 0.0),
}


def srgb_to_linear(hexcol):
    c = [int(hexcol[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def material(name):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    hexcol, rough, metal = PALETTE[name]
    rgb = srgb_to_linear(hexcol)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    m.diffuse_color = (*rgb, 1)
    return m


def xform(loc=(0, 0, 0), rot=None, scale=None):
    m = Matrix.Translation(Vector(loc))
    if rot is not None:
        m = m @ Euler(rot).to_matrix().to_4x4()
    if scale is not None:
        m = m @ Matrix.Diagonal((*scale, 1))
    return m


def chaikin(pts, n=3):
    """Round off the corners of a polyline (keeps both end points)."""
    pts = [Vector(p) for p in pts]
    for _ in range(n):
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out += [a.lerp(b, 0.25), a.lerp(b, 0.75)]
        pts = out + [pts[-1]]
    return pts


class Part:
    """Collects primitives (each with its own material) into one named mesh object."""

    def __init__(self, name):
        self.name, self.bm, self.mats = name, bmesh.new(), []

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

    def box(self, mat, size, loc=(0, 0, 0), rot=None, bevel=0.01, seg=2, top=(1, 1), bottom=(1, 1)):
        vs = bmesh.ops.create_cube(self.bm, size=1.0)["verts"]
        for v in vs:
            k = top if v.co.z > 0 else bottom
            v.co = Vector((v.co.x * size[0] * k[0], v.co.y * size[1] * k[1], v.co.z * size[2]))
        bmesh.ops.transform(self.bm, matrix=xform(loc, rot), verts=vs)
        self._finish(vs, mat, bevel, seg)

    def cyl(self, mat, r, depth, loc=(0, 0, 0), rot=None, seg=24, r2=None, bevel=0.0):
        vs = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r,
                                   radius2=r if r2 is None else r2, depth=depth, matrix=xform(loc, rot))["verts"]
        self._finish(vs, mat, bevel)

    def rod(self, mat, a, b, r, seg=16, r2=None, bevel=0.0):
        a, b = Vector(a), Vector(b)
        m = Matrix.Translation((a + b) / 2) @ (b - a).to_track_quat('Z', 'Y').to_matrix().to_4x4()
        vs = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r,
                                   radius2=r if r2 is None else r2, depth=(b - a).length, matrix=m)["verts"]
        self._finish(vs, mat, bevel)

    def sphere(self, mat, r, loc, scale=(1, 1, 1), seg=24, rings=12):
        vs = bmesh.ops.create_uvsphere(self.bm, u_segments=seg, v_segments=rings, radius=r,
                                       matrix=xform(loc, None, scale))["verts"]
        self._finish(vs, mat)

    def tube(self, mat, pts, r, seg=10):
        """Sweep a circle along a path (hoses, bent legs)."""
        pts, bm, n = [Vector(p) for p in pts], self.bm, len(pts)
        tang = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
        up = Vector((0, 0, 1)) if abs(tang[0].z) < 0.9 else Vector((1, 0, 0))
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

    def blade(self, R, r0, cmax, pitch, spin, ang, tip_mat=None, ns=16, npf=14):
        """One tapered, twisted rotor blade along +X (rotated by ang), thin cambered airfoil section."""
        bm, si = self.bm, self.slot("prop")
        ti = self.slot(tip_mat) if tip_mat else si
        rot = Matrix.Rotation(ang, 3, 'Z')
        rings, ts = [], []
        for i in range(ns + 1):
            t = 1 - (1 - i / ns) ** 1.35          # sections bunch up towards the tip
            r = r0 + (R - r0) * t
            k = 0.5 + 0.5 * math.sin(math.pi / 2 * t / 0.25) if t < 0.25 else 1 - 0.55 * (t - 0.25) / 0.75
            if t > 0.9:                            # rounded tip
                k *= 0.15 + 0.85 * math.sqrt(max(0.0, 1 - ((t - 0.9) / 0.1) ** 2))
            c = cmax * k
            th = c * (0.14 - 0.08 * t)
            tw = min(math.radians(28), math.atan(pitch / (2 * math.pi * r)))
            sweep = -0.12 * cmax * t * t
            ring = []
            for j in range(npf):
                a = 2 * math.pi * j / npf
                u = 0.5 * math.cos(a)              # +0.5 leading edge, -0.5 trailing edge
                z = 0.5 * th * math.sin(a) * (0.35 + 0.65 * (u + 0.5)) + 0.04 * c * (1 - 4 * u * u)
                y = u * c + sweep
                y, z = y * math.cos(tw) - z * math.sin(tw), y * math.sin(tw) + z * math.cos(tw)
                ring.append(bm.verts.new(rot @ Vector((r, spin * y, z))))
            rings.append(ring)
            ts.append(t)
        for i in range(ns):
            for j in range(npf):
                f = bm.faces.new((rings[i][j], rings[i][(j + 1) % npf], rings[i + 1][(j + 1) % npf], rings[i + 1][j]))
                f.material_index, f.smooth = (ti if ts[i] >= 0.86 else si), True
        for ring, mi in ((rings[0], si), (rings[-1], ti)):   # close root and tip with a fan
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
        me.set_sharp_from_angle(angle=math.radians(40))
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.location, ob.parent = loc, parent
        wn = ob.modifiers.new("WeightedNormal", 'WEIGHTED_NORMAL')   # keeps bevelled boxes crisp
        wn.keep_sharp = True
        return ob


def P(d, r, z):
    """Point at distance r along the horizontal direction d, height z."""
    return Vector((d.x * r, d.y * r, z))


def motor_can(p, base, r, h, up=1):
    """Outrunner motor standing on base (or hanging below it when up=-1); returns the hub height."""
    x, y, z = base
    p.cyl("dark_grey", r, h * 0.45, (x, y, z + up * h * 0.225), seg=28, bevel=r * 0.06)
    p.cyl("metal", r * 0.97, h * 0.40, (x, y, z + up * h * 0.65), seg=28, bevel=r * 0.05)
    p.cyl("black", r * 0.6, h * 0.15, (x, y, z + up * h * 0.925), seg=24, bevel=r * 0.04)
    return z + up * h


def make_prop(root, name, loc, R, cmax, pitch, hub_r, spin, phi, tip_mat=None, down=False):
    """2-blade rotor with its origin at the hub; spin +1 = CCW from above."""
    p = Part(name)
    hh = hub_r * 0.8
    p.cyl("black", hub_r, hh, (0, 0, 0), seg=24, bevel=hub_r * 0.12)
    p.sphere("metal", hub_r * 0.7, (0, 0, (-1 if down else 1) * hh * 0.5), scale=(1, 1, 0.6), seg=20, rings=8)
    for k in (0, 1):
        a = phi + k * math.pi
        p.box("black", (hub_r * 1.4, hub_r * 1.1, hh * 0.85), (math.cos(a) * hub_r * 1.3, math.sin(a) * hub_r * 1.3, 0),
              rot=(0, 0, a), bevel=hub_r * 0.15)                     # blade grip / folding hinge
        p.blade(R, hub_r * 1.5, cmax, pitch, spin, a, tip_mat)
    ob = p.build(root, loc)
    ob["spin"] = spin
    return ob


def splayed_gear(g, tops, feet, r, bar_z, foot_r):
    """Four straight legs from tops to feet with left-right cross bars at bar_z and rubber feet."""
    for t, f in zip(tops, feet):
        g.rod("carbon", t, f, r, seg=16)
        g.box("dark_grey", (r * 3.4, r * 3.4, r * 3), t, bevel=r * 0.5)
        g.sphere("rubber", foot_r, f, scale=(1, 1, 0.7), seg=16, rings=8)
    pts = []
    for t, f in zip(tops, feet):
        k = (t.z - bar_z) / (t.z - f.z)
        pts.append(t.lerp(f, k))
    for a, b in ((pts[0], pts[1]), (pts[2], pts[3])):     # tops/feet ordered FR, FL, RL, RR
        g.rod("carbon", a, b, r * 0.8, seg=12)


# FR, FL, RL, RR (Blender -Y is the nose); props alternate CCW / CW like a standard quad X
CORNERS = [Vector((1, -1, 0)).normalized(), Vector((-1, -1, 0)).normalized(),
           Vector((-1, 1, 0)).normalized(), Vector((1, 1, 0)).normalized()]
SPIN = [1, -1, 1, -1]


def build_ares(root):
    R, ZA = 1.05, 0.86                       # motor radius (2.1 m motor diagonal), arm height
    body = Part("body")
    body.box("white", (0.46, 0.50, 0.30), (0, 0, 0.81), bevel=0.035, seg=3)
    body.cyl("dark_grey", 0.045, 0.012, (0, -0.25, 0.85), rot=(math.pi / 2, 0, 0), seg=6, bevel=0.002)  # badge
    body.cyl("white", 0.028, 0.016, (0, -0.255, 0.85), rot=(math.pi / 2, 0, 0), seg=6)
    for sx in (-1, 1):
        body.box("dark_grey", (0.012, 0.22, 0.09), (sx * 0.23, 0, 0.83), bevel=0.004)          # side vents
    body.box("led", (0.06, 0.008, 0.012), (0, -0.252, 0.93), bevel=0.003)
    body.build(root)

    tank = Part("tank")                      # 50 L
    tank.box("tank", (0.44, 0.46, 0.36), (0, 0, 0.48), bevel=0.04, seg=3, bottom=(0.7, 0.7))
    tank.box("dark_grey", (0.16, 0.12, 0.06), (0, -0.04, 0.275), bevel=0.012)            # pump
    for sx in (-1, 1):
        tank.cyl("nozzle", 0.012, 0.03, (sx * 0.06, -0.04, 0.255), seg=12)              # brass-ish fittings
    tank.build(root)

    bat = Part("battery")                    # 14 kg LiPo pack
    bat.box("dark_grey", (0.32, 0.24, 0.15), (0, 0.05, 1.035), bevel=0.018, seg=3)
    bat.box("black", (0.26, 0.18, 0.006), (0, 0.05, 1.111), bevel=0.002)
    bat.tube("black", chaikin([(-0.09, 0.05, 1.105), (-0.08, 0.05, 1.16), (0.08, 0.05, 1.16), (0.09, 0.05, 1.105)], 3), 0.011)
    bat.box("led", (0.05, 0.006, 0.01), (0.1, -0.072, 1.07), bevel=0.002)
    bat.build(root)

    for nm, size, loc in (("radar_front", (0.11, 0.03, 0.06), (0, -0.262, 0.715)),
                          ("radar_rear", (0.11, 0.03, 0.06), (0, 0.262, 0.715)),
                          ("radar_left", (0.03, 0.11, 0.06), (-0.242, 0, 0.715)),
                          ("radar_right", (0.03, 0.11, 0.06), (0.242, 0, 0.715)),
                          ("radar_down", (0.09, 0.07, 0.03), (0, 0.115, 0.29))):
        rp = Part(nm)
        rp.box("radar", size, loc, bevel=0.01, seg=2)
        rp.build(root)
    rp = Part("radar_up")
    rp.cyl("radar", 0.045, 0.02, (0, -0.18, 0.97), seg=24, bevel=0.004)
    rp.sphere("radar", 0.042, (0, -0.18, 0.98), scale=(1, 1, 0.6))
    rp.build(root)

    hoses = Part("hoses")
    for i, d in enumerate(CORNERS):
        ang = math.atan2(d.y, d.x)
        tip = P(d, R, ZA)
        arm = Part(f"arm_{i + 1}")
        arm.rod("carbon", P(d, 0.18, ZA), tip, 0.024, seg=20)
        arm.rod("dark_grey", P(d, 0.24, ZA), P(d, 0.30, ZA), 0.032, seg=20, bevel=0.005)    # root clamp
        arm.rod("dark_grey", P(d, 0.40, ZA), P(d, 0.48, ZA), 0.034, seg=20, bevel=0.006)    # folding joint
        arm.build(root)

        mot = Part(f"motor_{i + 1}")
        mot.box("black", (0.14, 0.14, 0.07), tip, rot=(0, 0, ang), bevel=0.02)              # motor mount
        mot.cyl("black", 0.062, 0.08, tip - Vector((0, 0, 0.075)), seg=28, bevel=0.012)     # ESC pod
        hub = motor_can(mot, tip + Vector((0, 0, 0.035)), 0.068, 0.085)
        mot.build(root)
        make_prop(root, f"prop_{i + 1}", (tip.x, tip.y, hub + 0.016), R=0.71, cmax=0.105, pitch=0.5,
                  hub_r=0.042, spin=SPIN[i], phi=ang + math.radians(60 + 35 * i))

        nz = Part(f"nozzle_{i + 1}")
        top = ZA - 0.115
        nz.rod("black", (tip.x, tip.y, top), (tip.x, tip.y, top - 0.14), 0.012)
        nz.cyl("nozzle", 0.02, 0.045, (tip.x, tip.y, top - 0.16), seg=16, bevel=0.004)
        nz.cyl("black", 0.012, 0.025, (tip.x, tip.y, top - 0.195), r2=0.005, seg=16)
        nz.build(root)

        hoses.tube("hose", chaikin([P(d, 0.05, 0.27), P(d, 0.20, 0.28), P(d, 0.31, 0.45), P(d, 0.34, 0.70),
                                    P(d, 0.38, 0.825), P(d, 0.92, 0.825), P(d, 0.975, 0.80), P(d, 0.98, 0.70),
                                    P(d, 1.0, 0.66), P(d, 1.035, 0.65)], 3), 0.007, seg=8)
    hoses.build(root)

    g = Part("gear")
    sgn = [(1, -1), (-1, -1), (-1, 1), (1, 1)]
    splayed_gear(g, [Vector((sx * 0.22, sy * 0.14, 0.70)) for sx, sy in sgn],
                 [Vector((sx * 0.50, sy * 0.30, 0.03)) for sx, sy in sgn], 0.018, 0.10, 0.028)
    g.build(root)


def build_t40(root):
    MX, MY, ZA = 0.715, 0.865, 0.56          # 1.37 m props -> about 2.8 x 3.1 m unfolded
    body = Part("body")
    body.box("dark_grey", (0.40, 0.64, 0.13), (0, 0.02, 0.555), bevel=0.03, seg=3)
    body.box("grey", (0.30, 0.18, 0.03), (0, -0.04, 0.625), bevel=0.01)
    for sx in (-1, 1):
        body.box("black", (0.012, 0.36, 0.05), (sx * 0.2, 0.05, 0.555), bevel=0.004)       # side grilles
    body.build(root)

    tank = Part("tank")                      # 40 L, front/centre, lid on top
    tank.box("tank", (0.34, 0.36, 0.40), (0, -0.12, 0.46), bevel=0.04, seg=3, bottom=(0.8, 0.8))
    tank.cyl("light_grey", 0.075, 0.03, (0, -0.17, 0.672), seg=16, bevel=0.008)
    tank.cyl("dark_grey", 0.05, 0.012, (0, -0.17, 0.69), seg=24, bevel=0.003)
    tank.box("dark_grey", (0.14, 0.10, 0.05), (0, -0.10, 0.24), bevel=0.012)              # pump
    tank.build(root)

    bat = Part("battery")                    # battery slot, top rear
    bat.box("dark_grey", (0.27, 0.23, 0.15), (0, 0.19, 0.685), bevel=0.02, seg=3)
    bat.box("light_grey", (0.24, 0.20, 0.02), (0, 0.19, 0.76), bevel=0.008)
    bat.tube("black", chaikin([(-0.07, 0.19, 0.765), (-0.06, 0.19, 0.80), (0.06, 0.19, 0.80), (0.07, 0.19, 0.765)], 3), 0.01)
    bat.build(root)

    for nm, y, z, s in (("radar_front", -0.285, 0.36, -1), ("radar_rear", 0.345, 0.53, 1)):
        rp = Part(nm)
        rp.cyl("dark_grey", 0.07, 0.03, (0, y, z), rot=(math.pi / 2, 0, 0), seg=28, bevel=0.006)
        rp.sphere("radar", 0.066, (0, y + s * 0.012, z), scale=(1, 0.6, 1), seg=28, rings=14)
        rp.build(root)

    tips = [Vector((MX, -MY, ZA)), Vector((-MX, -MY, ZA)), Vector((-MX, MY, ZA)), Vector((MX, MY, ZA))]
    roots = [Vector((math.copysign(0.17, t.x), math.copysign(0.27, t.y), ZA)) for t in tips]
    hoses = Part("hoses")
    for i, (rt, tip) in enumerate(zip(roots, tips)):
        d = (tip - rt).normalized()
        ang = math.atan2(d.y, d.x)
        arm = Part(f"arm_{i + 1}")
        arm.rod("carbon", rt, tip, 0.026, seg=20)
        arm.box("black", (0.08, 0.07, 0.07), rt, rot=(0, 0, ang), bevel=0.012)                 # root hinge
        arm.rod("grey", rt.lerp(tip, 0.18), rt.lerp(tip, 0.26), 0.036, seg=20, bevel=0.006)   # folding joint
        arm.box("black", (0.12, 0.11, 0.10), tip, rot=(0, 0, ang), bevel=0.02, seg=3)        # coaxial motor mount
        arm.build(root)

        up = Part(f"motor_{i + 1}")
        hub = motor_can(up, tip + Vector((0, 0, 0.05)), 0.065, 0.075)
        up.build(root)
        lo = Part(f"motor_{i + 5}")
        hub_lo = motor_can(lo, tip - Vector((0, 0, 0.05)), 0.065, 0.075, up=-1)
        lo.build(root)
        phi = ang + math.radians(75 + 40 * i)
        make_prop(root, f"prop_{i + 1}", (tip.x, tip.y, hub + 0.015), R=0.685, cmax=0.10, pitch=0.5,
                  hub_r=0.04, spin=SPIN[i], phi=phi, tip_mat="prop_tip")
        make_prop(root, f"prop_{i + 5}", (tip.x, tip.y, hub_lo - 0.015), R=0.685, cmax=0.10, pitch=0.5,
                  hub_r=0.04, spin=-SPIN[i], phi=phi + math.radians(90), tip_mat="prop_tip", down=True)

        if tip.y > 0:                        # centrifugal sprinklers under the rear arms
            k = 1 if tip.x < 0 else 2
            nz = Part(f"nozzle_{k}")
            z0 = hub_lo - 0.04
            nz.rod("black", (tip.x, tip.y, z0), (tip.x, tip.y, z0 - 0.06), 0.008, seg=12)
            nz.cyl("dark_grey", 0.032, 0.05, (tip.x, tip.y, z0 - 0.085), seg=24, bevel=0.006)
            nz.cyl("nozzle", 0.058, 0.012, (tip.x, tip.y, z0 - 0.118), seg=32, bevel=0.003)   # atomizing disc
            nz.cyl("black", 0.022, 0.02, (tip.x, tip.y, z0 - 0.134), r2=0.008, seg=20)
            nz.build(root)
            hoses.tube("hose", chaikin([(0, -0.04, 0.24), (tip.x * 0.12, 0.08, 0.27), (tip.x * 0.22, 0.24, 0.42),
                                        rt.lerp(tip, 0.1) - Vector((0, 0, 0.04)), rt.lerp(tip, 0.88) - Vector((0, 0, 0.035))], 3),
                       0.008, seg=8)
    hoses.build(root)

    g = Part("gear")
    sgn = [(1, -1), (-1, -1), (-1, 1), (1, 1)]
    splayed_gear(g, [Vector((sx * 0.16, sy * 0.20, 0.49)) for sx, sy in sgn],
                 [Vector((sx * 0.25, sy * 0.30, 0.025)) for sx, sy in sgn], 0.018, 0.07, 0.026)
    g.build(root)


def build_pegasus(root):
    R, ZA = 0.60, 0.42                        # 1.2 m motor diagonal, 30 in props
    body = Part("body")
    body.box("white", (0.30, 0.32, 0.11), (0, 0, 0.425), bevel=0.022, seg=3)
    body.box("dark_grey", (0.16, 0.008, 0.04), (0, -0.161, 0.43), bevel=0.003)           # name plate
    body.build(root)

    tank = Part("tank")                      # 9.5 L
    tank.box("tank", (0.26, 0.28, 0.20), (0, 0, 0.27), bevel=0.025, seg=3, bottom=(0.72, 0.72))
    tank.box("dark_grey", (0.075, 0.008, 0.075), (0.04, -0.128, 0.30), rot=(-0.2, 0, 0), bevel=0.004)  # status panel
    tank.build(root)

    rp = Part("radar_down")
    rp.cyl("dark_grey", 0.03, 0.012, (0, 0, 0.166), seg=20)
    rp.sphere("radar", 0.024, (0, 0, 0.158), scale=(1, 1, 0.8), seg=20, rings=10)
    rp.build(root)

    bat = Part("battery")
    bat.box("dark_grey", (0.20, 0.13, 0.055), (0, 0.0, 0.507), bevel=0.012, seg=3)
    bat.tube("black", chaikin([(-0.05, 0.0, 0.53), (-0.045, 0.0, 0.555), (0.045, 0.0, 0.555), (0.05, 0.0, 0.53)], 3), 0.006)
    bat.build(root)

    for k, sx in ((1, -1), (2, 1)):
        an = Part(f"antenna_{k}")
        an.cyl("black", 0.013, 0.035, (sx * 0.12, 0.11, 0.497), seg=16, bevel=0.003)
        an.rod("black", (sx * 0.12, 0.11, 0.51), (sx * 0.12, 0.11, 0.80), 0.0045, seg=10)
        an.cyl("black", 0.007, 0.02, (sx * 0.12, 0.11, 0.80), seg=12)
        an.build(root)

    hoses = Part("hoses")
    for i, d in enumerate(CORNERS):
        ang = math.atan2(d.y, d.x)
        tip = P(d, R, ZA)
        arm = Part(f"arm_{i + 1}")
        arm.rod("grey", P(d, 0.13, ZA), tip, 0.02, seg=20)
        arm.rod("black", P(d, 0.19, ZA), P(d, 0.23, ZA), 0.026, seg=20, bevel=0.004)
        arm.build(root)

        mot = Part(f"motor_{i + 1}")
        mot.box("black", (0.075, 0.075, 0.055), tip, rot=(0, 0, ang), bevel=0.012)
        mot.cyl("black", 0.03, 0.035, tip - Vector((0, 0, 0.045)), seg=24, bevel=0.006)
        hub = motor_can(mot, tip + Vector((0, 0, 0.0275)), 0.042, 0.05)
        mot.build(root)
        make_prop(root, f"prop_{i + 1}", (tip.x, tip.y, hub + 0.01), R=0.38, cmax=0.06, pitch=0.25,
                  hub_r=0.024, spin=SPIN[i], phi=ang + math.radians(60 + 35 * i))

        nz = Part(f"nozzle_{i + 1}")
        top = ZA - 0.0625
        nz.rod("black", (tip.x, tip.y, top), (tip.x, tip.y, top - 0.07), 0.006, seg=12)
        nz.cyl("nozzle", 0.013, 0.03, (tip.x, tip.y, top - 0.08), seg=16, bevel=0.003)
        nz.cyl("black", 0.008, 0.016, (tip.x, tip.y, top - 0.103), r2=0.003, seg=12)
        nz.build(root)
        hoses.tube("hose", chaikin([P(d, 0.03, 0.172), P(d, 0.14, 0.20), P(d, 0.19, 0.33), P(d, 0.25, 0.395),
                                    P(d, 0.53, 0.395), P(d, 0.555, 0.37), P(d, 0.56, 0.33), P(d, 0.6, 0.31)], 3),
                   0.0045, seg=8)
    hoses.build(root)

    gim = Part("gimbal")                     # 3-axis gimbal under the nose
    gim.box("black", (0.05, 0.06, 0.012), (0, -0.175, 0.364), bevel=0.003)
    gim.cyl("dark_grey", 0.02, 0.02, (0, -0.2, 0.348), seg=20, bevel=0.003)                       # yaw
    gim.tube("black", chaikin([(0, -0.2, 0.336), (0.045, -0.2, 0.336), (0.045, -0.2, 0.30)], 2), 0.005, seg=8)
    gim.cyl("dark_grey", 0.016, 0.016, (0.045, -0.188, 0.318), rot=(math.pi / 2, 0, 0), seg=20, bevel=0.002)  # roll
    gim.cyl("dark_grey", 0.016, 0.016, (0.045, -0.2, 0.285), rot=(0, math.pi / 2, 0), seg=20, bevel=0.002)   # pitch
    gim.build(root)
    cam = Part("camera")
    cam.box("black", (0.06, 0.05, 0.045), (0, -0.2, 0.285), bevel=0.008, seg=2)
    cam.cyl("dark_grey", 0.017, 0.02, (0, -0.232, 0.285), rot=(math.pi / 2, 0, 0), seg=24, bevel=0.003)
    cam.cyl("lens", 0.011, 0.004, (0, -0.243, 0.285), rot=(math.pi / 2, 0, 0), seg=24)
    cam.build(root)

    g = Part("gear")                         # hoop legs on two skids
    for sx in (-1, 1):
        for sy in (-1, 1):
            g.tube("black", chaikin([(sx * 0.13, sy * 0.11, 0.38), (sx * 0.21, sy * 0.12, 0.34), (sx * 0.26, sy * 0.13, 0.20),
                                     (sx * 0.25, sy * 0.13, 0.05), (sx * 0.25, sy * 0.13, 0.018)], 3), 0.009, seg=10)
        g.tube("black", chaikin([(sx * 0.25, -0.25, 0.045), (sx * 0.25, -0.20, 0.012), (sx * 0.25, 0.20, 0.012),
                                 (sx * 0.25, 0.25, 0.045)], 3), 0.011, seg=12)
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
        root = bpy.data.objects.new(key, None)
        bpy.context.scene.collection.objects.link(root)
        fn(root)
        ground_and_export(root, os.path.join(out, key + ".glb"))
        print(key, len(root.children), "parts ->", os.path.join(out, key + ".glb"))
