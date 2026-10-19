"""Statistics behind the page: permutation tests by season, cluster shares, track moments and
El Nino vs La Nina classification AUC. Reads build/data.json (run build_data.py first).

Usage: python scripts/analyze.py
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import skew, kurtosis, chi2_contingency, spearmanr
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score, silhouette_score

D = json.load(open(Path(__file__).resolve().parents[1] / "build" / "data.json", encoding="utf-8"))
Y = pd.DataFrame(D["years"]).set_index("y")
S = pd.DataFrame(D["storms"]); S["p"] = S.y.map(Y.p)
S["glon"] = S.g.str[0]; S["glat"] = S.g.str[1]
S = S[S.y >= 1966].reset_index(drop=True)
yy = Y[Y.index >= 1966]
rng = np.random.default_rng(42)

# ---------- 1. year-level permutation tests (fast, numpy) ----------
def year_table(s):
    g = s.groupby("y")
    t = pd.DataFrame({"n": g.size(), "ace": g.ace.sum(), "us": g.us.sum(), "rc": g.rc.sum(),
                      "gl": g.glon.sum(), "gt": g.glat.sum(),
                      "k0": g.k.apply(lambda k: (k == 0).sum()), "k3": g.k.apply(lambda k: (k == 3).sum())})
    return t.reindex(yy.index, fill_value=0)

def perm(t, cols, mode, N=4000):
    A = (yy.p == "nino").values; B = (yy.p == "nina").values
    idx = np.where(A | B)[0]; nA = A.sum()
    X = t[cols].to_numpy(float)
    def f(sel):
        if mode == "mean": return X[sel, 0].mean()
        return X[sel, 0].sum() / X[sel, 1].sum()
    obs = f(np.where(B)[0]) - f(np.where(A)[0]); h = 0
    for _ in range(N):
        pr = rng.permutation(idx)
        h += abs(f(pr[nA:]) - f(pr[:nA])) >= abs(obs) - 1e-12
    return round(obs, 3), round((h + 1) / (N + 1), 4)

print("=== 1. La Nina - El Nino, 1966-2025 ===")
for c in [0, 1, 3]:
    t = year_table(S[S.c >= c])
    r = {m: perm(t, [m], "mean") for m in ["n", "ace", "us"]}
    r.update({m: perm(t, [m, "n"], "ratio") for m in ["rc", "gl", "gt", "k0", "k3"]})
    print("cat>=", c, r)

s = S
print("\nper-storm means by phase:\n", s.groupby("p").agg(maxw=("w", "mean"), dur=("dur", "mean"), ace=("ace", "mean"), glat=("glat", "mean"), glon=("glon", "mean"), us=("us", "mean"), rc=("rc", "mean")).round(2))
ny = yy.p.value_counts()
print("\ncluster storms per year:\n", pd.crosstab(s.p, s.k).div(ny, axis=0).round(2))
print("\ncluster share:\n", pd.crosstab(s.p, s.k, normalize="index").round(3))
print("chi2 (all phases):", chi2_contingency(pd.crosstab(s.p, s.k))[:2])
print("\nUS landfalls per year by cluster:\n", pd.crosstab(s.p, s.k, values=s.us.astype(int), aggfunc="sum").div(ny, axis=0).round(2))
print("\nmonth share:\n", pd.crosstab(s.p, s.m, normalize="index").round(2))
t = year_table(S)
for m in ["n", "ace", "us"]:
    r = spearmanr(yy.oni, t[m]); print("spearman ONI vs", m, round(r.statistic, 3), round(r.pvalue, 5))

# ---------- 2. higher-order moments ----------
def decode(tk):
    a = np.array(tk, float).reshape(-1, 3); return a[:, 0] / 10, a[:, 1] / 10

feats = []
tracks = []
for tk in pd.DataFrame(D["storms"]).set_index("id").loc[S.id, "tk"]:
    lon, lat = decode(tk); tracks.append((lon, lat))
    if len(lon) < 4:
        feats.append([np.nan] * 9); continue
    cov = np.cov(lon, lat)
    feats.append([lon.mean(), lat.mean(), cov[0, 0], cov[1, 1], cov[0, 1],
                  skew(lon), skew(lat), kurtosis(lon), kurtosis(lat)])
M = pd.DataFrame(feats, columns=["Ex", "Ey", "Vx", "Vy", "Cxy", "Sx", "Sy", "Kx", "Ky"])
ok = M.notna().all(1).to_numpy()
print("\n=== 2. moments: storms with >=4 points:", ok.sum(), "of", len(M))

# per-moment differences (year-blocked permutation of storm-level mean)
Ms = M[ok].copy(); Ms["y"] = S.y[ok].values; Ms["p"] = S.p[ok].values
for col in M.columns:
    g = Ms.groupby("y")[col].agg(["sum", "count"]).reindex(yy.index, fill_value=0)
    print(col, {p: round(Ms[Ms.p == p][col].mean(), 2) for p in ["nino", "neutral", "nina"]},
          perm(g.rename(columns={"sum": col, "count": "cnt"}), [col, "cnt"], "ratio"))

# K-Means on moments (as in original project), single model, then chi2 vs phase
X9 = StandardScaler().fit_transform(Ms[M.columns])
for k in [4, 6]:
    lab = KMeans(k, n_init=20, random_state=0).fit_predict(X9)
    tab = pd.crosstab(Ms.p, lab)
    print(f"moments KMeans k={k}: silhouette {silhouette_score(X9, lab):.3f}, chi2 vs phase", np.round(chi2_contingency(tab)[:2], 4))
    print(tab.div(tab.sum(1), axis=0).round(2))

# ---------- 3. can track shape tell El Nino from La Nina storms? ----------
# Seasons are the unit of independence: every split keeps whole years together, and every null
# shuffles labels between whole years. Because the label is constant within a year, leaving years
# out shifts the class balance between training and test folds; an unweighted model then learns an
# intercept pointing the wrong way and a no-information feature scores ~0.35 instead of 0.5. Balanced
# class weights remove that bias. Only ~29 seasons (1966-2025) carry the El Nino / La Nina label, so the
# repeated splits below are not independent experiments; they only average out fold-assignment noise.
sub = ok & S.p.isin(["nino", "nina"]).to_numpy()
yb = (S.p[sub] == "nina").astype(int).to_numpy(); groups = S.y[sub].to_numpy(); uy = np.unique(groups)
N = 16
def resample(lon, lat):
    x = lon * np.cos(np.radians(lat)); s_ = np.r_[0, np.cumsum(np.hypot(np.diff(x), np.diff(lat)))]
    q = np.linspace(0, s_[-1], N); return np.r_[np.interp(q, s_, lon), np.interp(q, s_, lat)]
R16 = np.array([resample(*tracks[i]) for i in np.where(sub)[0]])
# order matches the chart on the page
sets = {
    "higher": M.loc[sub, ["Sx", "Sy", "Kx", "Ky"]].to_numpy(),
    "genesis": S.loc[sub, ["glon", "glat"]].to_numpy(),
    "m12": M.loc[sub, ["Ex", "Ey", "Vx", "Vy", "Cxy"]].to_numpy(),
    "m1": M.loc[sub, ["Ex", "Ey"]].to_numpy(),
    "track": R16,
    "all9": M.loc[sub].to_numpy(),
}
logit = lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
SPLITS, PERMS, BOOT, BOOT_SPLITS = 10, 100, 200, 5

def cv_auc(X, y, g, seed):
    """10-fold CV with whole seasons (group ids g) assigned to folds at random; scaler fitted inside each fold."""
    ug = np.unique(g); r = np.random.default_rng(seed); fold_of = dict(zip(ug, r.permutation(len(ug)) % 10))
    folds = np.array([fold_of[v] for v in g]); pr = np.zeros(len(y))
    for f in range(10):
        tr, te = folds != f, folds == f
        pr[te] = logit().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    return roc_auc_score(y, pr)
mean_auc = lambda X, y, g, n=SPLITS: np.mean([cv_auc(X, y, g, s) for s in range(n)])

def shuffled_years(seed):
    r = np.random.default_rng(seed); lab = dict(zip(uy, r.permutation([int(Y.p[u] == "nina") for u in uy])))
    return np.array([lab[v] for v in groups])

print(f"\n=== 3. El Nino vs La Nina storms ({len(uy)} seasons, {len(yb)} storms): mean AUC over the same "
      f"{SPLITS} season-grouped splits; null = season labels shuffled between years ({PERMS}x, same splits) ===")
results = {"seasons": int(len(uy)), "storms": int(len(yb)), "splits": SPLITS, "perms": PERMS, "sets": {}}
for name, X in sets.items():
    obs = mean_auc(X, yb, groups)
    null = np.array([mean_auc(X, shuffled_years(500 + k), groups) for k in range(PERMS)])
    p = (np.sum(null >= obs) + 1) / (PERMS + 1)
    results["sets"][name] = {"auc": round(obs, 3), "null_mean": round(null.mean(), 3),
                             "null_lo": round(np.percentile(null, 5), 3), "null_hi": round(np.percentile(null, 95), 3), "p": round(p, 3)}
    print(f"{name:8s} AUC {obs:.3f} | null mean {null.mean():.3f}, 5-95% [{np.percentile(null, 5):.3f}, {np.percentile(null, 95):.3f}], p = {p:.3f}")

# ---------- 4. does adding skewness/kurtosis to the 1st+2nd moments help? ----------
# Season-level bootstrap: resample El Nino years and La Nina years with replacement (whole seasons, all
# their storms together; copies of a year share a group id so they never straddle a fold), refit both
# models on identical splits and record the AUC gain. The percentile interval reflects season-to-season
# sampling variability; it is an estimate, not an exact test.
print(f"\n=== 4. Gain from adding skewness/kurtosis to 1st+2nd moments (season bootstrap, {BOOT}x) ===")
X12 = sets["m12"]; X9 = np.c_[X12, sets["higher"]]
a12, a9 = mean_auc(X12, yb, groups), mean_auc(X9, yb, groups)
idx_by_year = {u: np.where(groups == u)[0] for u in uy}
nino_y = [u for u in uy if Y.p[u] == "nino"]; nina_y = [u for u in uy if Y.p[u] == "nina"]
gains = []
for b in range(BOOT):
    r = np.random.default_rng(9000 + b)
    pick = list(r.choice(nino_y, len(nino_y))) + list(r.choice(nina_y, len(nina_y)))
    ids = np.concatenate([idx_by_year[u] for u in pick]); gb = groups[ids]
    gains.append(mean_auc(X9[ids], yb[ids], gb, BOOT_SPLITS) - mean_auc(X12[ids], yb[ids], gb, BOOT_SPLITS))
gains = np.array(gains); lo, hi = np.percentile(gains, [2.5, 97.5])
results["gain"] = {"auc12": round(a12, 3), "auc9": round(a9, 3), "delta": round(a9 - a12, 3),
                   "ci_lo": round(lo, 3), "ci_hi": round(hi, 3), "boot": BOOT, "share_positive": round(float(np.mean(gains > 0)), 3)}
print(f"AUC 1st+2nd {a12:.3f} -> all 9 {a9:.3f}: gain {a9 - a12:+.3f}; season-bootstrap 95% interval [{lo:+.3f}, {hi:+.3f}], "
      f"share of resamples with a gain {np.mean(gains > 0):.2f}")

out = Path(__file__).resolve().parents[1] / "build" / "ml_results.json"
out.write_text(json.dumps(results, indent=1), encoding="utf-8"); print("wrote", out)
