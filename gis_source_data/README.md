# Source GIS data: highways and mileposts

These files are the inputs to `tools/gen_data.py`, which builds the website's `data/` files. The website itself does not load them.

Downloaded 2026-10-26 from official public ArcGIS services. All files are GeoJSON in WGS84 (EPSG:4326) and open in QGIS, ArcGIS Pro, or Leaflet.

## Highways_HPMS_2024_Illinois/
Source: FHWA Highway Performance Monitoring System, Illinois, data year 2024 (submitted 2025).
Service: https://geo.dot.gov/server/rest/services/Hosted/HPMS_FULL_IL_2024/FeatureServer/0

| File | Filter | Features |
|---|---|---|
| HPMS_2024_IL_Champaign_County_FS1-4.geojson | county_id = 19 (Champaign), f_system 1–4 | 2,723 |
| HPMS_2024_IL_Interstates_Freeways.geojson | statewide, f_system 1–2 | 33,473 |

f_system: 1 Interstate, 2 Other freeway/expressway, 3 Other principal arterial, 4 Minor arterial.
routesigning: 2 Interstate, 3 U.S. route, 4 State route.
Kept fields: route_id, begin_point, end_point, routenumber, routename, nhs, county_id, urban_id, ownership,
facility_type, access_control, through_lanes, lane_width, median_type/width, shoulder_type/width (r, l),
speed_limit, aadt, data_year.

## Highways_NHS_2021/
Source: FHWA / BTS NTAD National Highway System, version 2021-08-15.
Service: https://geo.dot.gov/server/rest/services/Hosted/National_Highway_System_(20210815)/FeatureServer/0

| File | Filter | Features |
|---|---|---|
| NHS_2021_Illinois.geojson | stfips = 17, full detail | 9,571 |
| NHS_2021_US_Interstates_simplified.geojson | all Interstates, 52 states/territories; geometry simplified to ~50 m for web maps | 73,453 |

signt1: I Interstate, U U.S. route, S State route, C County. The full national NHS (490,741 segments) was not downloaded because of its size.

## Mileposts_IDOT/
Source: IDOT "IL Milepost" layer, created from 2021–2022 LiDAR sign-face inventory (MUTCD D10 mile markers).
Service: https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services/IL_MilePost/FeatureServer/0
IL_Milepost: 6,222 points. SIGN_LEGEN is the milepost number shown on the sign; ROUTE_NUMB is the IDOT route key
(e.g. 010_10074_000000 = I-74 in Champaign County).
IDOT disclaimer: compiled from numerous sources, may not be complete or accurate, not for site-specific use.

## IDOT_Facilities/
Source: IDOT district facilities ("District Location Maps"), downloaded 2026-10-27.
Service: https://services2.arcgis.com/aIrBD8yn1TDTEXoz/arcgis/rest/services/IDOT_District_Facilities_View/FeatureServer/0
IDOT_Maintenance_Yards_Illinois.geojson: 199 points, FAC_TYPE_1 in TEAM SECTION, TEAM SECTION SUB HEADQUARTERS, STORAGE.
Kept fields: Fac_Name, Fac_Type, FAC_TYPE_1, District, County, Address, City_Zip, FAC_STATUS. The service also lists staff names and
phone numbers; those fields were not downloaded. gen_data.py uses yards 543 and 544 (Champaign) and E34, E26, 031, 032, E33, E25 (Cook)
as crew staging areas.
