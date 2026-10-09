"""Replay and live dataset generation orchestration script.

Executes the pipeline to discover Sentinel-2 L2A scenes, detect ponds on the reference date,
measure water surface area over time, apply cloud/shadow and spike cleanup, fetch Open-Meteo weather,
and produce contract-compliant measurements.json files for latur-2024 and latur-2026.

Data credits: Sentinel-2 L2A (Copernicus, via AWS Open Data / Element 84 Earth Search), Open-Meteo (CC BY 4.0).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List

from pipeline.cleanup import apply_quality_rules
from pipeline.evaporation import fetch_climatology_2019_2023, fetch_daily_weather
from pipeline.export import build_measurements_doc, export_measurements_json
from pipeline.imagery import export_region_imagery
from pipeline.ponds import DetectedPond, PondMeasurement, detect_ponds, measure_pond_pass
from pipeline.stac import STACScene, search_scenes
from pipeline.water import read_scene_bands

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_pipeline_for_region(
    region_id: str,
    region_name: str,
    bbox: List[float],
    start_date: str,
    end_date: str,
    reference_date: str | None,
    output_path: Path,
    include_weather: bool = True,
    max_cloud_cover: float = 20.0,
) -> Path:
    """Run full pipeline for a region and write measurements.json."""
    print(f"\n==================================================")
    print(f"Running pipeline for region: {region_id} ({region_name})")
    print(f"BBox: {bbox} | Dates: {start_date} to {end_date}")
    print(f"==================================================")

    # 1. Discover STAC scenes
    print("Step 1: Discovering STAC Sentinel-2 L2A scenes...")
    scenes = search_scenes(bbox=bbox, start_date=start_date, end_date=end_date, max_cloud_cover=max_cloud_cover)
    if not scenes:
        raise RuntimeError(f"No STAC scenes found for region {region_id} between {start_date} and {end_date}")

    print(f"Found {len(scenes)} scenes:")
    for s in scenes:
        print(f"  - {s.date} ({s.id}, cloud: {s.cloud_cover:.1f}%)")

    # Determine reference scene
    ref_scene = None
    if reference_date:
        for s in scenes:
            if s.date == reference_date:
                ref_scene = s
                break
    if ref_scene is None:
        ref_scene = scenes[0]
        reference_date = ref_scene.date

    print(f"\nStep 2: Detecting ponds on reference date {ref_scene.date} ({ref_scene.id})...")
    ref_bands = read_scene_bands(ref_scene.green_url, ref_scene.nir_url, ref_scene.scl_url, bbox)
    detected_ponds = detect_ponds(
        water_mask=ref_bands["water_mask"],
        scl_invalid_mask=ref_bands["scl_invalid_mask"],
        transform_affine=ref_bands["transform"],
        crs=ref_bands["crs"],
        pixel_area_ha=ref_bands["pixel_area_ha"],
    )
    print(f"Detected {len(detected_ponds)} ponds on reference date:")
    for p in detected_ponds[:5]:
        print(f"  - {p.id}: {p.ref_area_ha:.2f} ha at ({p.lat:.4f}, {p.lon:.4f}) {p.place}")
    if len(detected_ponds) > 5:
        print(f"  ... and {len(detected_ponds) - 5} more ponds")

    # 3. Measure ponds for each pass
    print(f"\nStep 3: Measuring pond water area across all {len(scenes)} scenes...")
    pond_histories: Dict[str, List[dict]] = {p.id: [] for p in detected_ponds}

    for idx, scene in enumerate(scenes, start=1):
        print(f"  Processing pass {idx}/{len(scenes)}: {scene.date}...", end=" ")
        try:
            bands = read_scene_bands(scene.green_url, scene.nir_url, scene.scl_url, bbox)
            valid_meas_count = 0
            for p in detected_ponds:
                meas = measure_pond_pass(p, bands["water_mask"], bands["scl_invalid_mask"], scene.date, bands["pixel_area_ha"])
                pond_histories[p.id].append(meas.to_dict())
                if meas.valid:
                    valid_meas_count += 1
            print(f"OK ({valid_meas_count}/{len(detected_ponds)} valid measurements)")
        except Exception as e:
            print(f"FAILED ({e})")
            # Fill with invalid zero measurements if a scene download fails
            for p in detected_ponds:
                pond_histories[p.id].append({"date": scene.date, "areaHa": 0.0, "valid": False})

    # 4. Fetch weather if required
    et0_data: List[dict] = []
    et0_clim: Dict[str, float] = {}
    precip_by_date: Dict[str, float] = {}

    if include_weather:
        print("\nStep 4: Fetching Open-Meteo weather and climatology...")
        first_scene_dt = date.fromisoformat(scenes[0].date)
        last_scene_dt = date.fromisoformat(scenes[-1].date)
        # Weather needs to start at least 45 days prior to first scene
        weather_start = (first_scene_dt - timedelta(days=45)).isoformat()
        weather_end = last_scene_dt.isoformat()

        print(f"  Fetching daily ET0 & precipitation from {weather_start} to {weather_end}...")
        et0_data = fetch_daily_weather(weather_start, weather_end)
        for w in et0_data:
            precip_by_date[w["date"]] = w["precip"]

        print("  Fetching 2019-2023 ET0 climatology (heat expectation)...")
        et0_clim = fetch_climatology_2019_2023()
        print(f"  Fetched {len(et0_data)} daily weather records, {len(et0_clim)} climatology entries.")
    else:
        print("\nStep 4: Weather fetching skipped (backend handles weather for live mode).")

    # 5. Quality Assurance & Cleanup (see pipeline/cleanup.py: suspect passes up or down,
    #    spikes and dips, ponds that were never really there or whose signal is not water level)
    print("\nStep 5: Applying quality rules...")
    raw_scenes = [{"date": s.date, "id": s.id, "status": "ok"} for s in scenes]
    raw_ponds = [
        dict(
            p.to_dict(),
            history=pond_histories[p.id],
            footprint_mask=p.footprint_mask,
            water_component_mask=p.water_component_mask,
        )
        for p in detected_ponds
    ]
    scene_records, cleaned_ponds, excluded_ponds, quality = apply_quality_rules(
        raw_scenes, raw_ponds, precip_by_date, reference_date)
    print(f"  Suspect passes: {quality['suspectScenes'] or 'none'}; "
          f"spikes/dips removed: {quality['spikesAndDipsRemoved']}; "
          f"ponds kept {quality['pondsKept']}, excluded {quality['pondsExcluded']}")
    for e in excluded_ponds:
        print(f"  - excluded {e['id']} ({e['refAreaHa']} ha): {e['reason']}")

    # 5b. Export imagery (outlines.geojson, index.json, thumbnail JPEGs)
    print("\nStep 5b: Exporting region imagery assets...")
    export_region_imagery(
        region_id=region_id,
        scenes=scenes,
        ponds=cleaned_ponds,
        ref_bands=ref_bands,
        bbox=bbox,
    )

    # 6. Export measurements JSON
    print(f"\nStep 6: Exporting measurements JSON to {output_path}...")
    doc = build_measurements_doc(
        region_id=region_id,
        region_name=region_name,
        bbox=bbox,
        reference_date=reference_date,
        scenes=scene_records,
        ponds=cleaned_ponds,
        et0=et0_data,
        et0_climatology=et0_clim,
    )

    doc["excludedPonds"] = excluded_ponds
    doc["quality"] = quality
    out_file = export_measurements_json(doc, output_path)
    print(f"Successfully exported {out_file}!")
    return out_file


def main():
    parser = argparse.ArgumentParser(description="Talaab Satellite Pipeline Replay & Live Exporter")
    parser.add_argument(
        "--region",
        choices=["latur-2024", "latur-2026", "all"],
        default="all",
        help="Region to process (default: all)",
    )
    args = parser.parse_args()

    bbox_latur = [76.47, 18.33, 76.62, 18.48]

    if args.region in ("latur-2024", "all"):
        run_pipeline_for_region(
            region_id="latur-2024",
            region_name="Latur (2024 replay)",
            bbox=bbox_latur,
            start_date="2024-01-01",
            end_date="2024-06-30",
            reference_date="2024-01-16",
            output_path=REPO_ROOT / "data" / "latur-2024" / "measurements.json",
            include_weather=True,
        )

    if args.region in ("latur-2026", "all"):
        run_pipeline_for_region(
            region_id="latur-2026",
            region_name="Latur (2026 live)",
            bbox=bbox_latur,
            start_date="2026-09-01",
            end_date="2026-10-31",
            reference_date="2026-09-27",  # 0% cloud: detect ponds on a clear pass, never a cloudy one
            output_path=REPO_ROOT / "data" / "latur-2026" / "measurements.json",
            include_weather=False,  # Weather is optional for live mode
            # Right after the monsoon few passes are below 20% tile cloud. Accept up to 45%: the
            # per-pond SCL check (>20% of a pond's footprint cloudy -> invalid) still drops cloudy readings.
            max_cloud_cover=45.0,
        )


if __name__ == "__main__":
    main()
