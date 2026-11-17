# industrial-atlas-data

Versioned, hash-verified data releases for Industrial Atlas. Hamilton (Ontario) first.

Each release is a self-contained directory that never changes after it is published. A new
source version or a new build is a new release, not an edit.

```
releases/<release_unit>/<release_id>/
  manifest.json            small; read first: release id, counts, contract revisions, hash of files.json
  files.json               path, size and SHA-256 of every other file in the release
  shards/<KK>.json        core record per parcel, 1,024 shards by the last two characters of the key
  detail/<KK>.json        full address lists and source feature ids, loaded on demand
  provenance/sources.json  where each source came from
  label-seed.json          seed wording for the label register
  tiles/                   parcel tiles (later)
```

## Verifying a release

1. Read `manifest.json`. Hash `files.json` with SHA-256 and compare with `files_sha256`.
2. For any file you use, compare its size and SHA-256 with its entry in `files.json`.
3. A record hash is the SHA-256 of the record's canonical JSON (RFC 8785 subset).

## What is in the data

Facts relayed from public sources with the source named on every value. Owner names, mailing
addresses and legal descriptions are never read or written. Display wording is not stored in
the data.

## Status

Public preview release `ca-on-hamilton/2026-11-16-d070` contains the schema 2
Hamilton dossier and the D-070 key-only parcel tiles. Leak, allowlist, size and
full-release reproducibility checks passed before publication. This early preview is
for inspecting what works; it is not a final launch declaration. The release directory
is immutable; corrections require a new release id.

## Hamilton map layers

`map-releases/ca-on-hamilton/2026-11-16-layer-set-001/` contains 11 screened
thematic overlays and the OpenStreetMap/Protomaps vector basemap. The overlays
are grouped into planning, protected-area, and parks PMTiles archives; the
basemap remains its own archive. `manifest.json` describes every layer, its
source, feature count, zoom range, field allowlist, color, and archive. The
release `files.json` records sizes and SHA-256 hashes.

Raw source snapshots remain outside this repository. To recreate the immutable
release from the approved local snapshots:

```sh
python3 scripts/build_hamilton_map_layers.py \
  --input-root /path/to/na/local-data \
  --basemap /path/to/na/local-data/basemap/hamilton/hamilton-20261116.pmtiles \
  --output /path/to/new-empty-release \
  --tippecanoe /path/to/tippecanoe
```

The builder checks expected feature counts, filters properties to the documented
allowlists, hashes inputs and outputs, and records its commands and source
provenance. Tippecanoe 2.53.0 is required. Never rebuild into an existing
release; create a new release id when source data or processing changes.

### Layer set 002 (2026-11-17)

`map-releases/ca-on-hamilton/2026-11-17-layer-set-002/` contains everything in
layer set 001 plus two new groups:

- **freight**: truck routes, average daily traffic on counted street segments
  (all vehicles, latest count year per segment), railways, railway crossings, and
  bridges and culverts with their height and weight limits;
- **utilities**: watermains and sewer mains (from zoom 14), sewer lift stations and
  water pressure districts, shown by owner decision D-077.

Source snapshots for the new layers were pulled on 2026-11-17. The manifest notes state
what these layers do not mean: nearness is not access or rail service; counts are not
truck volumes; a main near a parcel is not a connection or capacity; coded fields are the
source's values, not yet defined by the City. Railway owner and spur names are excluded.
Rebuild with `--release-id 2026-11-17-layer-set-002`; set 001 still rebuilds byte for byte.

