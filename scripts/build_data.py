"""Build the data bundle for the ENSO x Atlantic hurricane track page.

Inputs (data/raw): ibtracs_na.csv (IBTrACS v04r01 NA), oni.txt (CPC ONI), countries50.json (world-atlas).
Output: build/data.json

Usage: python scripts/build_data.py [K]   (K = number of track clusters; default picks the best silhouette in 3-7)
"""
import json, sys
from pathlib import Path as FsPath
import numpy as np, pandas as pd
from matplotlib.path import Path
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

ROOT = FsPath(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "build" / "data.json"
OUT.parent.mkdir(exist_ok=True)
Y0, Y1 = 1950, 2025

# ---------- ONI ----------
oni = pd.read_csv(f"{RAW}/oni.txt", sep=r"\s+")
oni.columns = ["seas", "yr", "total", "anom"]
oni_series = [[int(r.yr), r.seas, float(r.anom)] for r in oni.itertuples()]
aso = oni[oni.seas == "ASO"].set_index("yr")["anom"]

def phase_of(v):
    return "nino" if v >= 0.5 else ("nina" if v <= -0.5 else "neutral")

years = []
for y in range(Y0, Y1 + 1):
    v = float(aso.loc[y])
    years.append({"y": y, "oni": round(v, 2), "p": phase_of(v)})
phase_by_year = {d["y"]: d["p"] for d in years}

# ---------- US polygon for landfall ----------
topo = json.load(open(f"{RAW}/countries50.json", encoding="utf-8"))
sc, tr = topo["transform"]["scale"], topo["transform"]["translate"]
arcs = []
for a in topo["arcs"]:
    x = y = 0; pts = []
    for dx, dy in a:
        x += dx; y += dy
        pts.append((x * sc[0] + tr[0], y * sc[1] + tr[1]))
    arcs.append(pts)

def ring(idx):
    pts = []
    for i in idx:
        seg = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(seg if not pts else seg[1:])
    return pts

def country_paths(name):
    for g in topo["objects"]["countries"]["geometries"]:
        if g.get("properties", {}).get("name") == name:
            polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
            return [Path(ring(p[0])) for p in polys]
    raise KeyError(name)

us_paths = [p for p in country_paths("United States of America")
            if p.vertices[:, 1].max() < 50 and p.vertices[:, 0].min() > -130]  # CONUS-ish (drop Alaska/Hawaii)

def in_us(lon, lat):
    pts = np.c_[lon, lat]
    m = np.zeros(len(pts), bool)
    for p in us_paths:
        m |= p.contains_points(pts, radius=0.05)
    return m

# ---------- IBTrACS ----------
cols = ["SID", "SEASON", "NAME", "ISO_TIME", "NATURE", "LAT", "LON", "USA_WIND", "TRACK_TYPE", "LANDFALL"]
d = pd.read_csv(f"{RAW}/ibtracs_na.csv", skiprows=[1], usecols=cols, low_memory=False)
d = d[d.TRACK_TYPE.isin(["main", "PROVISIONAL"]) & d.SEASON.between(Y0, Y1)].copy()
d["t"] = pd.to_datetime(d.ISO_TIME)
d = d[d.t.dt.hour.isin([0, 6, 12, 18]) & (d.t.dt.minute == 0)]
for c in ["LAT", "LON", "USA_WIND", "LANDFALL"]:
    d[c] = pd.to_numeric(d[c], errors="coerce")
d = d.dropna(subset=["LAT", "LON"]).sort_values(["SID", "t"])
d.loc[d.LON > 180, "LON"] -= 360

def category(w):
    if w >= 137: return 5
    if w >= 113: return 4
    if w >= 96: return 3
    if w >= 83: return 2
    if w >= 64: return 1
    return 0

storms = []
for sid, g in d.groupby("SID", sort=False):
    trop = g.NATURE.isin(["TS", "SS"]) & (g.USA_WIND >= 34)
    if not trop.any():
        continue
    w = g.USA_WIND.fillna(-1).to_numpy()
    first = np.argmax(trop.to_numpy())
    gen = g.iloc[first]
    lon, lat = g.LON.to_numpy(), g.LAT.to_numpy()
    tw = g.USA_WIND.where(trop)
    maxw = int(tw.max())
    ace = float((tw.dropna() ** 2).sum() / 1e4)
    lf = (g.LANDFALL.to_numpy() == 0) & (w >= 34)
    lf_us = bool(in_us(lon[lf], lat[lf]).any()) if lf.any() else False
    # recurvature: after the westernmost point the storm heads at least 5 degrees back east
    seg_lon = lon[first:]
    iw = int(np.argmin(seg_lon))
    recurve = bool(iw < len(seg_lon) - 1 and seg_lon[iw + 1:].max() - seg_lon[iw] >= 5)
    days = (g.t.iloc[-1] - gen.t).total_seconds() / 86400
    name = str(gen.NAME).title() if isinstance(gen.NAME, str) and gen.NAME != "NOT_NAMED" else ""
    storms.append({
        "id": sid, "n": name, "y": int(gen.SEASON), "m": int(gen.t.month),
        "w": maxw, "c": category(maxw), "ace": round(ace, 2),
        "g": [round(float(gen.LON), 1), round(float(gen.LAT), 1)],
        "t0": round((gen.t - pd.Timestamp(int(gen.SEASON), 1, 1)).total_seconds() / 3600),
        "lf": bool(lf.any()), "us": lf_us, "rc": recurve, "dur": round(days, 1),
        "_lon": lon[first:], "_lat": lat[first:],
        # full track from genesis, packed: lon*10, lat*10, wind (kt) + 1000 if the fix is tropical/subtropical
        # (the page needs the flag so its running ACE matches the per-storm ACE above)
        "tk": [v for i in range(first, len(g)) for v in
               (int(round(lon[i] * 10)), int(round(lat[i] * 10)), int(round(max(w[i], 0))) + (1000 if trop.iat[i] else 0))],
    })
print("storms", len(storms), file=sys.stderr)

# ---------- one global track clustering ----------
N = 16
def resample(lon, lat):
    x = lon * np.cos(np.radians(lat)); y = lat
    s = np.r_[0, np.cumsum(np.hypot(np.diff(x), np.diff(y)))]
    if s[-1] == 0:
        return np.r_[np.full(N, lon[0]), np.full(N, lat[0])]
    q = np.linspace(0, s[-1], N)
    return np.r_[np.interp(q, s, lon), np.interp(q, s, lat)]

X = np.array([resample(s["_lon"], s["_lat"]) for s in storms])
Xs = X.copy()
Xs[:, :N] *= np.cos(np.radians(25))  # put degrees of longitude on roughly the same footing as latitude
scores = {}
for k in range(3, 8):
    km = KMeans(k, n_init=20, random_state=0).fit(Xs)
    scores[k] = silhouette_score(Xs, km.labels_)
print("silhouette", {k: round(v, 3) for k, v in scores.items()}, file=sys.stderr)
K = int(sys.argv[1]) if len(sys.argv) > 1 else max(scores, key=scores.get)
km = KMeans(K, n_init=50, random_state=0).fit(Xs)
# order clusters by mean genesis longitude, west -> east
cent = np.array([X[km.labels_ == c].mean(0) for c in range(K)])
order = np.argsort(cent[:, 0])
remap = {int(c): i for i, c in enumerate(order)}
clusters = []
for i, c in enumerate(order):
    mem = km.labels_ == c
    clusters.append({
        "k": i, "size": int(mem.sum()),
        "mean": [[round(float(cent[c, j]), 2), round(float(cent[c, N + j]), 2)] for j in range(N)],
        "us": round(float(np.mean([storms[t]["us"] for t in np.where(mem)[0]])), 3),
        "rc": round(float(np.mean([storms[t]["rc"] for t in np.where(mem)[0]])), 3),
    })
for s, lab in zip(storms, km.labels_):
    s["k"] = remap[int(lab)]
    del s["_lon"], s["_lat"]

json.dump({"years": years, "oni": oni_series, "storms": storms, "clusters": clusters,
           "silhouette": {str(k): round(v, 3) for k, v in scores.items()}, "K": K,
           "source": {"ibtracs": "IBTrACS v04r01 North Atlantic, NOAA NCEI (file last record "
                      + str(pd.to_datetime(pd.read_csv(f"{RAW}/ibtracs_na.csv", skiprows=[1], usecols=["ISO_TIME"]).ISO_TIME).max().date()) + ")",
                      "oni": "NOAA CPC Oceanic Niño Index (ERSSTv5)"}},
          open(OUT, "w", encoding="utf-8"), separators=(",", ":"))
