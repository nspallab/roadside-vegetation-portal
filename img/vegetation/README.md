# Vegetation images

Every site of the same vegetation class shows the same representative photo. Growth stages have no photos:
the site card lists the stage as text, and the map can be coloured by stage.

## Where the images are

| What | Where | Used in |
|---|---|---|
| Vegetation class photos (project photos) | `photos/class/<class>.jpg` | Site card ground photo, map legend, "Color by: Vegetation class" tooltips |
| Fallback illustrations | `class/*.svg` | Shown only if a class photo cannot load |
| Growth-stage illustrations | `stage/*.svg` | Not used by the site at present; kept for later |

Class file names: `noxious-broadleaf`, `invasive-broadleaf`, `noxious-grass`, `invasive-grass`, `woody-brush`, `turf`.
Stage names: `rosette`, `fall-regrowth`, `vegetative`, `leaf-out`, `bolting`, `boot`, `heading`, `full-leaf`,
`flowering`, `fruiting`, `seed-set`, `dormant`.

## Changing an image

- **Class photo:** replace the file in `photos/class/` and keep its name (JPG, about 1000 px wide). To change the
  caption or credit, edit that class's line in `PHOTOS` in `js/app.js`.

Height and cover schematics are not files: `js/app.js` draws them for each site (`heightSVG`, `coverSVG`).
Regenerate the illustrations with: `python tools/gen_illustrations.py img/vegetation`
