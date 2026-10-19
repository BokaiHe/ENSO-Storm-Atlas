"""Download the raw inputs into data/raw.

- IBTrACS v04r01 North Atlantic best tracks (NOAA NCEI, ~58 MB)
- Oceanic Nino Index (NOAA CPC)
- Natural Earth 1:50m land and country outlines (world-atlas)

Usage: python scripts/download_data.py [--force]
"""
import sys
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
FILES = {
    "ibtracs_na.csv": "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.NA.list.v04r01.csv",
    "oni.txt": "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt",
    "land50.json": "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/land-50m.json",
    "countries50.json": "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-50m.json",
}

if __name__ == "__main__":
    force = "--force" in sys.argv
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        dest = RAW / name
        if dest.exists() and not force:
            print(f"skip  {name} (exists; use --force to refresh)")
            continue
        print(f"fetch {name} ...", flush=True)
        urllib.request.urlretrieve(url, dest)
        print(f"      {dest.stat().st_size / 1e6:.1f} MB")
