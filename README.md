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
