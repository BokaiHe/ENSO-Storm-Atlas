# Fixed analysis snapshot

`atlas_snapshot.json` is byte-identical to the atlas data bundle at the source commit recorded in `manifest.json`. It contains the 1950–2025 seasonal ONI assignments, 979 selected storms, packed track points, shared track-type labels, and descriptive cluster metadata. This compact, processed snapshot makes the notebook executable without a new download.

- Packed track triples: longitude × 10, latitude × 10, wind speed in kt + 1000 for the tropical/subtropical fixes satisfying the ACE threshold.
- Coordinates are rounded to 0.1°; per-storm ACE is rounded to two decimals.
- The full-track segment starts at the first qualifying tropical/subtropical fix of at least 34 kt and continues to the record endpoint.
- `atlantic_land.geojson` is the decoded Natural Earth / world-atlas land layer used for geographic context.
- `manifest.json` records SHA-256 checksums, source URLs, the snapshot date, and the matching source commit. Raw input checksums record which downloads produced this snapshot; those large raw files are not committed.

To rebuild raw inputs, run `scripts/download_data.py` and `scripts/build_data.py` from the repository root. Upstream revisions can change the results; preserve a new manifest when updating this fixed snapshot. All inferential results are recomputed by the research notebook from these inputs.
