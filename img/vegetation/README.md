# Representative vegetation images

These are schematic illustrations (original drawings, no license restrictions) used as placeholders.
Every site of the same class or growth stage shows the same image.

class/  noxious-broadleaf, invasive-broadleaf, noxious-grass, invasive-grass, woody-brush, turf
stage/  rosette, fall-regrowth, vegetative, leaf-out, bolting, boot, heading, full-leaf,
        flowering, fruiting, seed-set, dormant

To use a real photo: save it with the SAME file name (keep the .svg name, or use .jpg and change
the extension in js/app.js: functions classImg() and stageImg()). Use photos the team took, or
images with a license that allows reuse (e.g., USDA PLANTS, public-domain), and credit them.

Height and cover schematics are not files: js/app.js draws them for each site (heightSVG, coverSVG).
Regenerate the illustrations with: python tools/gen_illustrations.py img/vegetation
