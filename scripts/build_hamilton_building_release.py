#!/usr/bin/env python3
"""Create immutable Hamilton map-layer set 003 from screened local inputs.

Raw source data and ranked GeoJSON remain local. The release contains public
tiles, parcel fact shards, a concise manifest, and provenance hashes only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: pathlib.Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-release", required=True, type=pathlib.Path)
    parser.add_argument("--ranked-ndjson", required=True, type=pathlib.Path)
    parser.add_argument("--facts-index", required=True, type=pathlib.Path)
    parser.add_argument("--facts-dir", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--tippecanoe", default="tippecanoe")
    args = parser.parse_args()

    base = args.base_release.resolve()
    ranked = args.ranked_ndjson.resolve()
    facts_index = args.facts_index.resolve()
    facts_dir = args.facts_dir.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit("output must be empty; map releases are immutable")
    if not ranked.is_file() or not facts_index.is_file() or not facts_dir.is_dir():
        raise SystemExit("ranked building stream and parcel facts are required")

    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("release", {}).get("id") != "2026-11-17-layer-set-002":
        raise SystemExit("expected the pinned layer-set-002 release as the base")
    shutil.copytree(base, output, dirs_exist_ok=True)
    fact_index = json.loads(facts_index.read_text(encoding="utf-8"))
    if fact_index.get("schema") != 1 or fact_index.get("parcel_count") != 166745:
        raise SystemExit("parcel-facts index failed schema or coverage checks")
    (output / "parcel-building-facts-index.json").write_bytes(facts_index.read_bytes())
    shutil.copytree(facts_dir, output / "parcel-building-facts")

    executable = pathlib.Path(args.tippecanoe).expanduser()
    version_result = subprocess.run([str(executable), "--version"], text=True, capture_output=True, check=True)
    version = (version_result.stdout + version_result.stderr).strip()
    if version != "tippecanoe v2.53.0":
        raise SystemExit(f"expected tippecanoe v2.53.0, got {version}")

    with tempfile.TemporaryDirectory(prefix="hamilton-buildings-") as temp_name:
        temp = pathlib.Path(temp_name)
        pmtiles = temp / "built-form.pmtiles"
        subprocess.run([
            str(executable), "--force", "--read-parallel", "--no-progress-indicator",
            f"--temporary-directory={temp}", "-o", str(pmtiles),
            "-n", "Hamilton building footprints", "-Z", "13", "-z", "15",
            "--simplification=1", "--no-feature-limit", "--no-tile-size-limit",
            "-L", f"building-footprints:{ranked}",
        ], check=True)
        tile_target = output / "tiles" / "built-form.pmtiles"
        tile_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pmtiles, tile_target)

    building_layer = {
        "id": "building-footprints",
        "label": "Building footprints (size-ranked per parcel)",
        "source": "City of Hamilton; parcel ranks derived by HeavyMap",
        "source_url": "https://services.arcgis.com/rYz782eMbySr2srL/arcgis/rest/services/Buildings/FeatureServer/8",
        "source_date": "2026-10-17",
        "clearance": "Public dataset; explicitly cleared by project owner for this release.",
        "tile_layer": "building-footprints",
        "feature_count": 214287,
        "min_zoom": 13,
        "max_zoom": 15,
        "file": "tiles/built-form.pmtiles",
        "color": "#a45834",
        "default_visible": False,
        "properties": ["BUILD_ID", "PARCEL_ID", "BUILD_NO", "AREA_M2", "OVL_M2", "N_PARCELS", "EDGE_M"],
        "group": "built-form",
        "geometry": "polygon",
    }
    manifest["release"]["id"] = "2026-11-17-layer-set-003"
    manifest["generated_at"] = "2026-11-17"
    manifest["layers"].append(building_layer)
    manifest["notes"].extend([
        "Building polygons are City of Hamilton footprints pulled 2026-10-17; they show plan-view outline, not floor area, height, use, or building condition.",
        "BUILD_NO ranks the whole footprint plan-view area within its primary parcel; stable BUILD_ID is the individual cross-release identity. AREA_M2 remains numeric for future size filters.",
        "Primary parcel is the greatest positive intersection. N_PARCELS and OVL_M2 disclose multi-parcel footprints; edge distance is the minimum distance from footprint area to the parcel boundary line in metres. A boundary that touches, crosses, or lies within a footprint reports zero.",
        "Summed footprint area is not parcel coverage: overlapping footprint outlines can double-count. No coverage percentage is asserted.",
    ])
    write_json(output / "manifest.json", manifest)
    write_json(output / "provenance" / "buildings.json", {
        "schema": 1,
        "ranked_ndjson": {"sha256": sha256(ranked), "feature_count": 214287},
        "parcel_facts_index": {"sha256": sha256(facts_index), "parcel_count": 166745},
        "tile_generator": version,
        "tile_layer": building_layer,
        "fields": building_layer["properties"],
        "source_names_and_row_ids_included": False,
    })
    files = []
    for path in sorted(p for p in output.rglob("*") if p.is_file() and p.name != "files.json"):
        files.append({"path": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    write_json(output / "files.json", {"schema": 1, "files": files})
    print(f"Built {len(manifest['layers'])} layers, {len(files)} files, {sum(row['bytes'] for row in files)} bytes")
    print(f"Building tile: {tile_target.stat().st_size} bytes")


if __name__ == "__main__":
    main()
