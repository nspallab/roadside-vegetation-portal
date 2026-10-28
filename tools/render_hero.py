"""Render the Home page hero image: the ARES HYL-150 model (img/drones/3d/ares.glb) on a transparent background.

Usage (Blender 4.x, from the repository root):
  blender -b --factory-startup --python tools/render_hero.py -- img/drones/3d/ares.glb img/hero-drone.png
Then convert to WebP (img/hero-drone.webp) for the site; see README.
"""
import bpy, math, sys
from mathutils import Vector

SRC, OUT = sys.argv[sys.argv.index("--") + 1:][:2]

for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob)
bpy.ops.import_scene.gltf(filepath=SRC)
sc = bpy.context.scene
meshes = [o for o in sc.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo, hi = Vector(map(min, *pts)), Vector(map(max, *pts))
centre, size = (lo + hi) / 2, (hi - lo).length

# props a little turned so the blades read as an X, not a line
for o in sc.objects:
    if o.name.startswith("prop_"):
        o.rotation_mode = "XYZ"
        o.rotation_euler.z += math.radians(28)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
cam.data.lens = 50
d = size * 1.55
cam.location = centre + Vector((d * 0.72, -d * 0.62, d * 0.42))
cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.camera = cam

def light(name, kind, loc, energy, size_=1.0):
    L = bpy.data.objects.new(name, bpy.data.lights.new(name, kind))
    L.data.energy = energy
    if kind == "AREA":
        L.data.size = size_
    L.location = centre + Vector(loc)
    L.rotation_euler = (centre - L.location).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(L)

light("key", "AREA", (3, -2.5, 4), 900, 3)
light("fill", "AREA", (-3.5, -1.5, 2), 300, 4)
light("rim", "AREA", (0, 4, 3), 450, 3)
sc.world = sc.world or bpy.data.worlds.new("w")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.94, 0.97, 1)
sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.6

sc.render.engine = "BLENDER_EEVEE_NEXT"
sc.render.film_transparent = True
sc.render.resolution_x, sc.render.resolution_y = 1600, 1100
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "AgX"
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("wrote", OUT)
