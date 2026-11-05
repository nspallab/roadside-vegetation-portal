# Vegetation images

Every site of the same vegetation class or growth stage shows the same representative image.

## Where the images are

| What | Where | Used in |
|---|---|---|
| Vegetation class photos (project photos) | `photos/class/<class>.jpg` | Site card ground photo, map legend, "Color by: Vegetation class" tooltips |
| Growth stage photos | Wikimedia Commons, linked from `js/app.js` (the `PHOTOS` list, keys `stage/...`) | Site card growth-stage picture, "Color by: Growth stage" |
| Fallback illustrations | `class/*.svg`, `stage/*.svg` | Shown only if a photo cannot load |

Class file names: `noxious-broadleaf`, `invasive-broadleaf`, `noxious-grass`, `invasive-grass`, `woody-brush`, `turf`.
Stage names: `rosette`, `fall-regrowth`, `vegetative`, `leaf-out`, `bolting`, `boot`, `heading`, `full-leaf`,
`flowering`, `fruiting`, `seed-set`, `dormant`.

## Changing an image

- **Class photo:** replace the file in `photos/class/` and keep its name (JPG, about 1000 px wide). To change the
  caption or credit, edit that class's line in `PHOTOS` in `js/app.js`.
- **Growth stage photo:** save the photo as `photos/stage/<stage>.jpg`, then in `PHOTOS` in `js/app.js` change that
  stage's URL to `img/vegetation/photos/stage/<stage>.jpg` and its credit, licence and source page (use `null` if
  there is no source page).

Height and cover schematics are not files: `js/app.js` draws them for each site (`heightSVG`, `coverSVG`).
Regenerate the illustrations with: `python tools/gen_illustrations.py img/vegetation`
