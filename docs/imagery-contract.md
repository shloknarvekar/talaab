# Imagery contract: pond outlines and satellite thumbnails

Goal: on the map, show each pond's real **outline**, and in the pond panel a strip of real
**true-colour satellite thumbnails** (the pond on 16 Jan, 26 Mar, 5 May…) so anyone can *see* it
shrink. Everything here is static files served with the website, so no backend or API is involved.

**Nikhil writes** (pipeline) · **Ranit reads** (web)

## Files

```
web/public/imagery/{region}/
  index.json                 # what exists (read this first)
  outlines.geojson           # one polygon per pond
  {pondId}/{YYYY-MM-DD}.jpg  # one thumbnail per pond per pass
```

`{region}` is `latur-2024` or `latur-2026`.

### `index.json`

```jsonc
{
  "region": "latur-2024",
  "credit": "Contains modified Copernicus Sentinel data 2024, via AWS Open Data",
  "ponds": {
    "P001": { "dates": ["2024-01-16", "2024-01-21"], "bbox": [76.53, 18.37, 76.54, 18.38] }  // bbox of the thumbnail, lon/lat
  }
}
```

### `outlines.geojson`

A GeoJSON `FeatureCollection` in **WGS84 (lon, lat)**. One `Polygon` (or `MultiPolygon`) per
pond: the water component on the reference date (not the dilated footprint), simplified to about
one 10 m pixel so the file stays small.

```jsonc
{ "type": "Feature", "properties": { "id": "P001", "refAreaHa": 33.1 }, "geometry": { "type": "Polygon", "coordinates": [[[76.53, 18.37], "..."]] } }
```

### Thumbnails

- **True colour** from the Sentinel-2 `visual` asset (already RGB, 10 m).
- **Square crop** around the pond's outline with about 50% padding, so the shoreline context is visible.
- **256×256 JPEG**, quality ~80 (aim for 15–30 KB each).
- **One per pass, valid or not**: the web greys out invalid or suspect passes using `measurements.json`.

## Rules

- **Pond ids must match the final `measurements.json`.** `apply_quality_rules` excludes ponds and
  renumbers the rest (P001 = largest). Generate imagery **after** it, matching ponds by their
  lat/lon, and produce nothing for excluded ponds.
- **Size budget:** at most about 10 MB per region (12 ponds × 24 passes × 25 KB ≈ 7 MB).
- Never commit raw GeoTIFFs (`*.tif` is git-ignored); only these JPEGs and JSON.
- Credit Copernicus on every view that shows the imagery (`index.json.credit`).

## Web (Ranit)

- Map: draw `outlines.geojson`, filled with the pond's status colour, under the existing markers. Clicking an outline selects the pond.
- Pond panel: a horizontal strip of thumbnails for the passes up to the current as-of date (never after it, to keep the replay honest), with the date under each; dim invalid passes. Clicking one enlarges it.
- If `index.json` is missing for a region, hide these features silently (the live region may not have imagery yet).
