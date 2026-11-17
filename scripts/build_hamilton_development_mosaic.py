#!/usr/bin/env python3
"""Derive a privacy-minimised citywide permit mosaic from pinned releases.

Each issued permit contributes once to the hex cell containing the mean of its
linked parcel representative points. The output contains only cell geometry and
monthly counts; permit and parcel identifiers never leave the local inputs.
"""

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


FOCUS_SECTORS = {
    "industrial",
    "warehouse_logistics",
    "commercial",
    "commercial_retail",
    "commercial_office_professional",
    "commercial_hospitality_food",
    "residential_multi_unit",
}
HEX_RADIUS_M = 650
SQRT3 = math.sqrt(3)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utm17_to_lonlat(easting, northing):
    """Convert EPSG:26917 to WGS84 using the inverse UTM series."""
    a = 6378137.0
    f = 1 / 298.257222101
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    k0 = 0.9996
    x = (easting - 500000.0) / k0
    y = northing / k0
    m = y
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    j1 = 3 * e1 / 2 - 27 * e1**3 / 32
    j2 = 21 * e1**2 / 16 - 55 * e1**4 / 32
    j3 = 151 * e1**3 / 96
    j4 = 1097 * e1**4 / 512
    fp = mu + j1 * math.sin(2 * mu) + j2 * math.sin(4 * mu) + j3 * math.sin(6 * mu) + j4 * math.sin(8 * mu)
    sin_fp = math.sin(fp)
    cos_fp = math.cos(fp)
    tan_fp = math.tan(fp)
    c1 = ep2 * cos_fp**2
    t1 = tan_fp**2
    n1 = a / math.sqrt(1 - e2 * sin_fp**2)
    r1 = a * (1 - e2) / (1 - e2 * sin_fp**2) ** 1.5
    d = x / n1
    lat = fp - (n1 * tan_fp / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )
    lon = math.radians(-81) + (
        d - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
    ) / cos_fp
    return math.degrees(lon), math.degrees(lat)


def round_hex(x, y):
    # Pointy-top axial coordinates followed by cube-coordinate rounding.
    size = HEX_RADIUS_M
    q = (SQRT3 / 3 * x - y / 3) / size
    r = (2 / 3 * y) / size
    cx, cz, cy = q, r, -q - r
    rx, ry, rz = round(cx), round(cy), round(cz)
    dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return rx, rz


def hex_ring(q, r):
    size = HEX_RADIUS_M
    cx = size * SQRT3 * (q + r / 2)
    cy = size * 1.5 * r
    ring = []
    for index in range(7):
        angle = math.radians(60 * index - 30)
        ring.append(utm17_to_lonlat(cx + size * math.cos(angle), cy + size * math.sin(angle)))
    return ring


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--parcels", type=Path, required=True, help="Hamilton registry parcels.csv, EPSG:26917")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.records.read_text())
    months = source["report_months"] if "report_months" in source else None
    if months is None:
        manifest_path = args.records.with_name("development_release_manifest.json")
        if manifest_path.exists():
            months = json.loads(manifest_path.read_text())["report_months"]
        else:
            months = sorted({record["report_month"] for record in source["records"] if record.get("report_month")})
    month_index = {month: index for index, month in enumerate(months)}

    parcel_points = {}
    with args.parcels.open(newline="") as parcels_file:
        for row in csv.DictReader(parcels_file):
            if row.get("status") != "active":
                continue
            try:
                parcel_points[row["ia_id"]] = (float(row["rep_x"]), float(row["rep_y"]))
            except (KeyError, ValueError):
                continue

    # Each record is counted once at the mean location of its linked parcels.
    cells = defaultdict(lambda: {"all": [0] * len(months), "focus": [0] * len(months)})
    attached_records = 0
    locationless_records = 0
    focus_records_total = 0
    focus_records_attached = 0
    for record in source["records"]:
        month = record.get("report_month")
        index = month_index.get(month)
        if index is None:
            continue
        points = [parcel_points[key] for key in record.get("parcel_ids", []) if key in parcel_points]
        is_focus = bool(FOCUS_SECTORS.intersection(record.get("derived_sector_tags", [])))
        if is_focus:
            focus_records_total += 1
        if not points:
            locationless_records += 1
            continue
        x = sum(point[0] for point in points) / len(points)
        y = sum(point[1] for point in points) / len(points)
        cell = cells[round_hex(x, y)]
        cell["all"][index] += 1
        if is_focus:
            cell["focus"][index] += 1
            focus_records_attached += 1
        attached_records += 1

    features = []
    for (q, r), counts in sorted(cells.items()):
        props = {f"a{i:02}": value for i, value in enumerate(counts["all"])}
        props.update({f"f{i:02}": value for i, value in enumerate(counts["focus"])})
        props["n"] = sum(counts["all"])
        props["f"] = sum(counts["focus"])
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [hex_ring(q, r)]},
        })

    output = {
        "type": "FeatureCollection",
        "name": "hamilton_development_activity_mosaic",
        "metadata": {
            "schema_version": "hamilton-development-mosaic/0.1.0",
            "jurisdiction": "ca/on/hamilton",
            "source_activity": "permit issuance in monthly digest report month; no current open/closed status inferred",
            "spatial_unit": "1.3 km pointy hexagonal aggregation cell",
            "location_method": "mean EPSG:26917 representative point of linked parcels, then hexagonal binning",
            "count_unit": "distinct permit records, one contribution per record",
            "focus_sectors": sorted(FOCUS_SECTORS),
            "report_months": months,
            "linked_records_counted": attached_records,
            "records_without_usable_parcel_location": locationless_records,
            "focus_records_counted": focus_records_attached,
            "focus_records_without_usable_parcel_location": focus_records_total - focus_records_attached,
            "parcel_or_permit_identifiers_in_output": False,
            "owner_and_builder_contact_addresses_in_output": False,
        },
        "features": features,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, separators=(",", ":")) + "\n")
    old_manifest_path = args.records.with_name("development_release_manifest.json")
    old_manifest = json.loads(old_manifest_path.read_text())
    if old_manifest.get("schema_version") != "hamilton-development-release-manifest/0.2.0":
        raise ValueError("Expected the immutable Hamilton field-screen v0.2 manifest beside --records")
    source_files = list(old_manifest["outputs"])
    output_files = source_files + [args.output.name]
    for name in source_files:
        if not (args.output.parent / name).is_file():
            raise FileNotFoundError(f"Copy the unchanged v0.2 release file into the output directory first: {name}")
    registry_manifest_path = args.parcels.with_name("MANIFEST.json")
    registry_manifest = json.loads(registry_manifest_path.read_text())
    manifest = {
        **{key: value for key, value in old_manifest.items() if key not in {"schema_version", "outputs"}},
        "schema_version": "hamilton-development-release-manifest/0.3.0",
        "outputs": {name: sha256(args.output.parent / name) for name in output_files},
        "activity_mosaic": {
            "schema_version": output["metadata"]["schema_version"],
            "file": args.output.name,
            "cell_count": len(features),
            "linked_records_counted": attached_records,
            "records_without_usable_parcel_location": locationless_records,
            "focus_records_counted": focus_records_attached,
            "focus_records_without_usable_parcel_location": focus_records_total - focus_records_attached,
            "focus_sectors": sorted(FOCUS_SECTORS),
            "spatial_unit": output["metadata"]["spatial_unit"],
            "location_method": output["metadata"]["location_method"],
            "count_unit": output["metadata"]["count_unit"],
            "parcel_or_permit_identifiers_in_output": False,
            "owner_and_builder_contact_addresses_in_output": False,
        },
        "provenance": {
            "viewer_release": "ca-on-hamilton/2026-11-17-field-screen-v0.2",
            "viewer_input_sha256": old_manifest["outputs"][args.records.name],
            "registry_run_id": registry_manifest["run_id"],
            "registry_parcels_sha256": sha256(args.parcels),
            "builder": "scripts/build_hamilton_development_mosaic.py",
            "builder_version": "0.1.0",
        },
    }
    (args.output.parent / "development_release_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"cells={len(features)} linked_records_counted={attached_records} without_location={locationless_records} months={len(months)}")


if __name__ == "__main__":
    main()
