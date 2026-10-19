"""Split the El Nino - La Nina shift of track centroids into a type-mix part and a within-type part.

For each El Nino / La Nina difference in mean centroid longitude (Ex) and latitude (Ey):
    total = sum_k (p_k^nino - p_k^nina) * (m_k^nino + m_k^nina) / 2      <- type mix (which tracks occur)
          + sum_k (p_k^nino + p_k^nina) / 2 * (m_k^nino - m_k^nina)      <- within type (how each type runs)
where p_k is the share of storms in track type k and m_k the type's mean centroid (two-fold split with
average weights). p-values shuffle El Nino / La Nina labels between whole seasons.

Robustness: the track types are re-clustered with K = 3..7 (same features as build_data.py), and the
K = 4 split is repeated after removing a linear year trend in centroid latitude.

Writes build/decomp.json (embedded in the page by build_site.py).
Usage: python scripts/decompose.py
"""
import json
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.cluster import KMeans

ROOT = Path(__file__).resolve().parents[1]
Y0, PERMS = 1966, 1000
D = json.loads((ROOT / "build" / "data.json").read_text(encoding="utf-8"))
Y = pd.DataFrame(D["years"]).set_index("y")
ALL = pd.DataFrame(D["storms"])

N = 16
def resample(lon, lat):
    x = lon * np.cos(np.radians(lat)); s = np.r_[0, np.cumsum(np.hypot(np.diff(x), np.diff(lat)))]
    if s[-1] == 0:
        return np.r_[np.full(N, lon[0]), np.full(N, lat[0])]
    q = np.linspace(0, s[-1], N)
    return np.r_[np.interp(q, s, lon), np.interp(q, s, lat)]

feat, ex, ey = [], [], []
for tk in ALL.tk:
    a = np.array(tk, float).reshape(-1, 3); lon, lat = a[:, 0] / 10, a[:, 1] / 10
    feat.append(resample(lon, lat)); ex.append(lon.mean()); ey.append(lat.mean())
X = np.array(feat); X[:, :N] *= np.cos(np.radians(25))  # same scaling as build_data.py; fitted on all 1950-2025 storms
ALL["Ex"], ALL["Ey"], ALL["p"] = ex, ey, ALL.y.map(Y.p)


def split(df, v, K):
    nino, nina = df[df.p == "nino"], df[df.p == "nina"]
    tot = nino[v].mean() - nina[v].mean(); mix = within = 0.0
    for k in range(K):
        pn, pl = np.mean(nino.k == k), np.mean(nina.k == k)
        mn, ml = nino[nino.k == k][v].mean(), nina[nina.k == k][v].mean()
        if np.isnan(mn) or np.isnan(ml):
            continue
        mix += (pn - pl) * (mn + ml) / 2
        within += (pn + pl) / 2 * (mn - ml)
    return tot, mix, within


def run(labels, K, detrend=False):
    S = ALL.assign(k=labels)[ALL.y >= Y0].copy()
    if detrend:
        S["Ey"] = S.Ey - np.polyval(np.polyfit(S.y, S.Ey, 1), S.y) + S.Ey.mean()
    S = S[S.p.isin(["nino", "nina"])]
    yrs = sorted(S.y.unique()); labs = [Y.p[y] for y in yrs]; rng = np.random.default_rng(1)
    res = {"K": K, "detrended": detrend}
    for v, name in (("Ex", "lon"), ("Ey", "lat")):
        obs = split(S, v, K); null = []
        for _ in range(PERMS):
            pm = dict(zip(yrs, rng.permutation(labs)))
            null.append(split(S.assign(p=S.y.map(pm)), v, K))
        null = np.array(null)
        ps = [(np.sum(np.abs(null[:, j]) >= abs(obs[j])) + 1) / (PERMS + 1) for j in range(3)]
        res[name] = {"total": round(obs[0], 2), "mix": round(obs[1], 2), "within": round(obs[2], 2),
                     "p_total": round(ps[0], 3), "p_mix": round(ps[1], 3), "p_within": round(ps[2], 3)}
    return res


out = {"y0": Y0, "perms": PERMS, "main": run(ALL.k.to_numpy(), 4), "robust": []}
print("main (page clusters, K=4):", out["main"])
for K in range(3, 8):
    lab = KMeans(K, n_init=20, random_state=0).fit_predict(X)
    out["robust"].append(run(lab, K)); print(out["robust"][-1])
out["detrended"] = run(ALL.k.to_numpy(), 4, detrend=True); print("detrended:", out["detrended"])
yrs = [y for y in Y.index if y >= Y0]
out["mean_year"] = {p: round(float(np.mean([y for y in yrs if Y.p[y] == p])), 1) for p in ("nino", "nina")}
S = ALL[ALL.y >= Y0]; out["lat_trend_per_decade"] = round(float(np.polyfit(S.y, S.Ey, 1)[0] * 10), 2)
(ROOT / "build" / "decomp.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
print("wrote build/decomp.json")
