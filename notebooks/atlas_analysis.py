"""Reproducible season-blocked analysis for the accompanying research notebook.

No precomputed statistical results are read. Inputs are the fixed atlas snapshot.
All confidence intervals resample complete seasons, with phase-specific resampling.
"""
from pathlib import Path
import hashlib
import json
import platform
import importlib.metadata
import numpy as np
import pandas as pd
from scipy.stats import skew, kurtosis, gaussian_kde
from sklearn.cluster import KMeans
from sklearn.metrics import roc_auc_score, silhouette_score, adjusted_rand_score
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from threadpoolctl import threadpool_limits
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.lines import Line2D

BASE = Path(__file__).resolve().parent
OUT = BASE / 'results'
FIG = BASE / 'figures'
for folder in (OUT, FIG):
    folder.mkdir(exist_ok=True)
PHASES = ['nina', 'neutral', 'nino']
COLORS = {'nina': '#1768AE', 'neutral': '#87919C', 'nino': '#C44727'}
LABELS = {'nina': 'La Niña', 'neutral': 'Neutral', 'nino': 'El Niño'}
TYPES = ['Gulf & Caribbean', 'East Coast recurver', 'Mid-Atlantic recurver', 'Cape Verde type']
MOMENTS = ['Ex', 'Ey', 'Vx', 'Vy', 'Cxy', 'Sx', 'Sy', 'Kx', 'Ky']
MOM_LABELS = ['Centroid longitude (°)', 'Centroid latitude (°)', 'Longitude variance (°²)',
              'Latitude variance (°²)', 'Covariance (°²)', 'Longitude skewness',
              'Latitude skewness', 'Longitude excess kurtosis', 'Latitude excess kurtosis']
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.titlesize': 11,
                     'axes.labelsize': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.linewidth': .8, 'legend.frameon': False, 'svg.fonttype': 'none',
                     'pdf.fonttype': 42, 'figure.dpi': 110, 'savefig.dpi': 300})


def save(fig, name):
    for suffix in ('png', 'pdf', 'svg'):
        fig.savefig(FIG / f'{name}.{suffix}', dpi=300, bbox_inches='tight', facecolor='white')
    plt.show()
    plt.close(fig)


def write_table(table, name):
    table.to_csv(OUT / f'{name}.csv', index=False, encoding='utf-8')
    return table


def ptext(p):
    return f'p = {p:.3f}' if p >= .001 else 'p < 0.001'


def adjust(pvalues, method='holm'):
    p = np.asarray(pvalues, float)
    order = np.argsort(p)
    m = len(p)
    if method == 'holm':
        q = np.maximum.accumulate(p[order] * (m - np.arange(m)))
    else:
        q = np.minimum.accumulate((p[order] * m / np.arange(1, m + 1))[::-1])[::-1]
    result = np.empty(m)
    result[order] = np.clip(q, 0, 1)
    return result


def load_data():
    manifest = json.loads((BASE / 'data/manifest.json').read_text(encoding='utf-8'))
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((BASE / 'data' / name).read_bytes()).hexdigest() == digest, name
    d = json.loads((BASE / 'data/atlas_snapshot.json').read_text(encoding='utf-8'))
    years = pd.DataFrame(d['years']).set_index('y')
    storms = pd.DataFrame(d['storms'])
    storms['phase'] = storms.y.map(years.p)
    tracks, features, moments = [], [], []
    for tk in storms.tk:
        a = np.asarray(tk, dtype=float).reshape(-1, 3)
        lon, lat = a[:, 0] / 10, a[:, 1] / 10
        assert np.isfinite(a).all()
        tracks.append(np.c_[lon, lat])
        x = lon * np.cos(np.radians(lat))
        distance = np.r_[0., np.cumsum(np.hypot(np.diff(x), np.diff(lat)))]
        if distance[-1] == 0:
            features.append(np.r_[np.full(16, lon[0]), np.full(16, lat[0])])
        else:
            q = np.linspace(0, distance[-1], 16)
            features.append(np.r_[np.interp(q, distance, lon), np.interp(q, distance, lat)])
        if len(lon) < 4:
            moments.append([lon.mean(), lat.mean()] + [np.nan] * 7)
        else:
            cov = np.cov(lon, lat)
            moments.append([lon.mean(), lat.mean(), cov[0, 0], cov[1, 1], cov[0, 1],
                            skew(lon), skew(lat), kurtosis(lon), kurtosis(lat)])
    storms[MOMENTS] = np.asarray(moments)
    assert storms.id.is_unique and len(storms) == 979
    assert years.index.min() == 1950 and years.index.max() == 2025
    assert ((years.oni >= .5) == (years.p == 'nino')).all()
    assert ((years.oni <= -.5) == (years.p == 'nina')).all()
    # Packed tropical flag reproduces the archived ACE to the per-storm rounding precision.
    ace_reconstructed = []
    for tk in storms.tk:
        w = np.asarray(tk).reshape(-1, 3)[:, 2]
        ace_reconstructed.append(np.sum((w[w >= 1000] - 1000) ** 2) / 1e4)
    assert np.max(np.abs(storms.ace - ace_reconstructed)) <= .00501
    season = storms.groupby('y').agg(storms=('id', 'size'), ace=('ace', 'sum'), us=('us', 'sum'))
    season = season.reindex(years.index, fill_value=0).join(years)
    for k in range(4):
        season[f'k{k}'] = storms[storms.k == k].groupby('y').size().reindex(years.index, fill_value=0)
    cohorts = []
    for start in (1950, 1966, 1980):
        for phase in PHASES:
            ss = storms[(storms.y >= start) & (storms.phase == phase)]
            cohorts.append({'start': start, 'phase': phase, 'seasons': int(((years.index >= start) & (years.p == phase)).sum()),
                            'storms': len(ss), 'finite_nine_moments': int(np.isfinite(ss[MOMENTS]).all(axis=1).sum())})
    write_table(pd.DataFrame(cohorts), 'cohorts')
    versions = {name: importlib.metadata.version(name) for name in
                ['numpy', 'pandas', 'scipy', 'scikit-learn', 'matplotlib', 'nbformat', 'nbclient', 'ipykernel']}
    versions['python'] = platform.python_version()
    (OUT / 'environment.json').write_text(json.dumps(versions, indent=2), encoding='utf-8')
    return d, years, storms, tracks, np.array(features), season, pd.DataFrame(cohorts)


def mean_contrast(a, b, permutations=9999, bootstrap=5000, seed=42):
    """Mean(a)-mean(b), independent whole-season rows; stratified percentile CI."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    rng = np.random.default_rng(seed)
    obs = a.mean(axis=0) - b.mean(axis=0)
    joint = np.concatenate([a, b])
    null = np.array([joint[q[:len(a)]].mean(axis=0) - joint[q[len(a):]].mean(axis=0)
                     for q in (rng.permutation(len(joint)) for _ in range(permutations))])
    boots = (a[rng.integers(len(a), size=(bootstrap, len(a)))].mean(axis=1)
             - b[rng.integers(len(b), size=(bootstrap, len(b)))].mean(axis=1))
    p = (1 + np.sum(np.abs(null) >= np.abs(obs) - 1e-12, axis=0)) / (permutations + 1)
    return obs, np.percentile(boots, [2.5, 97.5], axis=0), p


def seasonal_results(season):
    s = season.loc[1966:2025]
    names = ['storms', 'ace', 'us']
    a, b = s[s.p == 'nina'][names], s[s.p == 'nino'][names]
    delta, ci, ps = mean_contrast(a, b)
    table = pd.DataFrame({'outcome': names, 'nina_mean': a.mean().values, 'nino_mean': b.mean().values,
                          'delta_nina_minus_nino': delta, 'ci_low': ci[0], 'ci_high': ci[1],
                          'p_permutation': ps, 'p_holm': adjust(ps)})
    return write_table(table, 'seasonal_contrasts')


def coastline(ax):
    land = json.loads((BASE / 'data/atlantic_land.geojson').read_text())
    ax.add_collection(PolyCollection([poly[0] for poly in land['coordinates']],
                                    facecolors='#E9EDF0', edgecolors='#9BA7B3', linewidths=.4, zorder=0))
    ax.set(xlim=(-105, 0), ylim=(5, 60), xlabel='Longitude (°)', ylabel='Latitude (°N)')
    ax.set_aspect(1 / np.cos(np.radians(30)))
    ax.set_xticks([-100, -75, -50, -25, 0])
    ax.set_xticklabels(['100W', '75W', '50W', '25W', '0'])


def fig_context(season):
    fig, axs = plt.subplots(2, 1, figsize=(11, 5.8), sharex=True, layout='constrained')
    colors = [COLORS[p] for p in season.p]
    axs[0].bar(season.index, season.oni, color=colors, width=.85)
    axs[0].axhline(.5, color='#555', ls='--', lw=.8)
    axs[0].axhline(-.5, color='#555', ls='--', lw=.8)
    axs[0].set(ylabel='ASO ONI (°C)', title='a  ENSO exposure is assigned once per season')
    axs[1].bar(season.index, season.storms, color=colors, width=.85)
    axs[1].set(ylabel='Named storms / season', xlabel='Year', title='b  Annual activity and the primary analysis window')
    for ax in axs:
        ax.axvspan(1949.5, 1965.5, facecolor='#E5E5E5', alpha=.45)
        ax.axvline(1965.5, color='#444', lw=1)
        ax.set_xlim(1949, 2026)
    axs[0].set_ylim(-1.6, 2.7)
    axs[1].set_ylim(0, 34)
    axs[1].text(1951, 31, '1950–1965 context', fontsize=9)
    axs[1].text(1967, 31, '1966–2025 primary analysis', fontsize=9)
    axs[0].legend(handles=[Line2D([], [], lw=7, color=COLORS[p], label=LABELS[p]) for p in PHASES],
                  ncol=3, loc='upper right')
    save(fig, 'fig01_seasons')


def fig_activity(season, results):
    fig, axs = plt.subplots(1, 3, figsize=(11.5, 4.4), layout='constrained')
    rng = np.random.default_rng(101)
    for j, (key, label) in enumerate(zip(['storms', 'ace', 'us'], ['Named storms / season', 'ACE (10⁴ kt²) / season', 'US-landfall storms / season'])):
        ax = axs[j]
        for i, phase in enumerate(PHASES):
            vals = season.loc[1966:].query('p == @phase')[key].to_numpy(float)
            ax.scatter(i + rng.uniform(-.12, .12, len(vals)), vals, c=COLORS[phase], s=24, alpha=.65, linewidths=0)
            boot = vals[rng.integers(len(vals), size=(5000, len(vals)))].mean(axis=1)
            lo, hi = np.percentile(boot, [2.5, 97.5])
            ax.errorbar(i+.23, vals.mean(), yerr=[[vals.mean()-lo], [hi-vals.mean()]], fmt='D',
                        color=COLORS[phase], capsize=4, markersize=6)
        row = results.iloc[j]
        ax.set_xticks(range(3), [f'{LABELS[p]}\nn = {int((season.loc[1966:].p == p).sum())}' for p in PHASES])
        ax.set(ylabel=label, ylim=(0, ax.get_ylim()[1]*1.12), title=f'{chr(97+j)}  {label.split(" /")[0]}')
        ax.text(.02, .97, f'Δ(LN − EN) = {row.delta_nina_minus_nino:.1f}\nHolm {ptext(row.p_holm)}',
                transform=ax.transAxes, va='top', fontsize=9)
    save(fig, 'fig02_activity')


def cluster_results(storms, features, season):
    # Longitude weighting matches the atlas; full-track positions, not moments, define types.
    x = features.copy(); x[:, :16] *= np.cos(np.radians(25))
    fits, rows = {}, []
    with threadpool_limits(limits=1):
        for k in range(3, 8):
            fit = KMeans(k, n_init=20, random_state=0).fit(x)
            fits[k] = fit.labels_
            rows.append({'K': k, 'silhouette': silhouette_score(x, fit.labels_)})
    types = ['k0', 'k1', 'k2', 'k3']
    s = season.loc[1966:]
    a, b = s[s.p == 'nina'][types], s[s.p == 'nino'][types]
    delta, ci, ps = mean_contrast(a, b, seed=43)
    tab = pd.DataFrame({'type': TYPES, 'nina_mean': a.mean().values, 'nino_mean': b.mean().values,
                        'delta_nina_minus_nino': delta, 'ci_low': ci[0], 'ci_high': ci[1],
                        'p_permutation': ps, 'p_holm': adjust(ps)})
    write_table(pd.DataFrame(rows), 'cluster_selection')
    write_table(tab, 'type_rates')
    # Re-fitting rounded positions can change a few assignments; snapshot labels are the atlas definition.
    agreement = adjusted_rand_score(storms.k, fits[4])
    return fits, tab, pd.DataFrame(rows), agreement


def fig_types(storms, tracks, features, season, table):
    fig, axs = plt.subplots(2, 4, figsize=(13.3, 6.8), layout='constrained', gridspec_kw={'height_ratios': [1.15, 1]})
    rng = np.random.default_rng(52)
    for k in range(4):
        ax = axs[0, k]; coastline(ax)
        ids = np.flatnonzero((storms.k == k) & (storms.y >= 1966))
        ax.add_collection(LineCollection([tracks[i] for i in ids], colors='#435B6B', alpha=.09, linewidths=.5))
        mean = features[ids].mean(axis=0)
        ax.plot(mean[:16], mean[16:], color='#182C3B', lw=2.2)
        ax.scatter(mean[0], mean[16], color='#182C3B', s=25, zorder=5)
        ax.set_title(f'{chr(97+k)}  {TYPES[k]}', fontsize=10)
        if k: ax.set_ylabel('')
        ax = axs[1, k]
        for i, phase in enumerate(PHASES):
            vals = season.loc[1966:].query('p == @phase')[f'k{k}'].to_numpy(float)
            boots = vals[rng.integers(len(vals), size=(5000, len(vals)))].mean(axis=1)
            lo, hi = np.percentile(boots, [2.5, 97.5])
            ax.bar(i, vals.mean(), color=COLORS[phase], edgecolor='white', width=.65)
            ax.errorbar(i, vals.mean(), yerr=[[vals.mean()-lo], [hi-vals.mean()]], color='#222', capsize=3, fmt='none')
        ax.set_xticks(range(3), ['LN', 'Neutral', 'EN'])
        ax.set_ylim(0, 9)
        ax.set_title(f'{chr(101+k)}  Holm {ptext(table.iloc[k].p_holm)}', fontsize=10)
        if k == 0: ax.set_ylabel('Mean storms / season (95% CI)')
    save(fig, 'fig03_track_types')


def year_blocks(storms, labels, k, start=1966, detrend=False):
    s = storms.assign(cluster=np.asarray(labels)).query('y >= @start').copy()
    if detrend:
        s['Ey'] = s.Ey - np.polyval(np.polyfit(s.y, s.Ey, 1), s.y) + s.Ey.mean()
    s = s[s.phase.isin(['nino', 'nina'])]
    years = np.sort(s.y.unique())
    counts = np.zeros((len(years), k))
    sums = np.zeros((len(years), k, 2))
    for i, y in enumerate(years):
        for typ in range(k):
            part = s[(s.y == y) & (s.cluster == typ)]
            counts[i, typ] = len(part)
            sums[i, typ] = part[['Ex', 'Ey']].sum().to_numpy()
    positive = np.array([s.loc[s.y == y, 'phase'].iloc[0] == 'nino' for y in years])
    return years, counts, sums, positive


def component(ca, sa, cb, sb):
    if (ca == 0).any() or (cb == 0).any():
        return None
    pa, pb = ca / ca.sum(), cb / cb.sum()
    ma, mb = sa / ca[:, None], sb / cb[:, None]
    total = sa.sum(axis=0) / ca.sum() - sb.sum(axis=0) / cb.sum()
    mix = ((pa-pb)[:, None] * (ma+mb) / 2).sum(axis=0)
    within = ((pa+pb)[:, None] / 2 * (ma-mb)).sum(axis=0)
    assert np.allclose(total, mix+within, atol=1e-10)
    return np.array([total, mix, within]).T


def decompose(storms, labels, k=4, start=1966, detrend=False, permutations=3999, bootstrap=2000, seed=17):
    years, counts, sums, positive = year_blocks(storms, labels, k, start, detrend)
    ia, ib = np.flatnonzero(positive), np.flatnonzero(~positive)
    def evaluate(a, b):
        return component(counts[a].sum(axis=0), sums[a].sum(axis=0), counts[b].sum(axis=0), sums[b].sum(axis=0))
    obs = evaluate(ia, ib)
    assert obs is not None
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(permutations):
        q = rng.permutation(len(years)); value = evaluate(q[:len(ia)], q[len(ia):])
        # Empty type means make this particular decomposition undefined, not zero.
        if value is None: raise ValueError('Empty type in permutation: coarsen K or specify another estimand.')
        null.append(value)
    null = np.array(null)
    p = (1+(np.abs(null) >= np.abs(obs)-1e-12).sum(axis=0))/(permutations+1)
    boot, invalid = [], 0
    for _ in range(bootstrap):
        value = evaluate(rng.choice(ia, len(ia), replace=True), rng.choice(ib, len(ib), replace=True))
        if value is None: invalid += 1
        else: boot.append(value)
    assert invalid == 0, f'{invalid} bootstrap replicates had an empty type'
    ci = np.percentile(boot, [2.5, 97.5], axis=0) if bootstrap else np.full((2, 2, 3), np.nan)
    rows = []
    for axis, name in enumerate(['longitude', 'latitude']):
        for j, label in enumerate(['total', 'type_mix', 'within_type']):
            rows.append({'axis': name, 'component': label, 'estimate': obs[axis,j], 'ci_low': ci[0,axis,j],
                         'ci_high': ci[1,axis,j], 'p_permutation': p[axis,j], 'K': k, 'start': start, 'detrended': detrend})
    table = pd.DataFrame(rows)
    table['p_holm'] = adjust(table.p_permutation)
    return table


def fig_decomposition(storms, table):
    fig = plt.figure(figsize=(11.5, 6), layout='constrained')
    gs = fig.add_gridspec(2, 2, width_ratios=[1.15, 1])
    ax = fig.add_subplot(gs[:, 0]); coastline(ax)
    for phase in ['nina', 'nino']:
        s = storms[(storms.y >= 1966) & (storms.phase == phase)]
        ax.scatter(s.Ex, s.Ey, s=10, c=COLORS[phase], alpha=.3, linewidths=0)
        ax.scatter(s.Ex.mean(), s.Ey.mean(), s=95, c=COLORS[phase], edgecolors='white', linewidths=1.3,
                   label=LABELS[phase], zorder=5)
    ax.legend(loc='lower left')
    ax.set_title('a  Storm centroids, 1966–2025')
    for i, name in enumerate(['longitude', 'latitude']):
        ax = fig.add_subplot(gs[i, 1]); t = table[table.axis == name]
        for j, (_, row) in enumerate(t.iterrows()):
            ax.errorbar(row.estimate, j, xerr=[[row.estimate-row.ci_low],[row.ci_high-row.estimate]],
                        fmt='o', color=['#252C35','#1768AE','#C44727'][j], capsize=4)
        ax.set_yticks(range(3), ['Total', 'Type mix', 'Within type'])
        ax.invert_yaxis(); ax.axvline(0, ls='--', color='#A0A0A0', lw=.8)
        ax.set(xlabel='El Niño − La Niña (°, 95% CI)', title=f'{chr(98+i)}  {name.capitalize()} shift')
    save(fig, 'fig04_centroid_decomposition')


def robustness(storms, fits, season):
    rows = []
    for k in range(3, 8):
        t = decompose(storms, fits[k], k, permutations=999, bootstrap=0)
        t['model'] = f'K = {k}'
        rows.append(t)
    t = decompose(storms, storms.k, detrend=True, permutations=999, bootstrap=0)
    t['model'] = 'K = 4, detrended'; rows.append(t)
    result = write_table(pd.concat(rows, ignore_index=True), 'decomposition_robustness')
    sensitivity = []
    for start in [1950, 1966, 1980]:
        for cat in [0, 1, 3]:
            subset = storms[(storms.y >= start) & (storms.c >= cat)]
            s = subset.groupby('y').size().reindex(season.loc[start:].index, fill_value=0)
            phases = season.loc[start:].p
            delta, ci, p = mean_contrast(s[phases == 'nina'], s[phases == 'nino'], permutations=3999, bootstrap=2000, seed=88)
            sensitivity.append({'start':start,'min_category':cat,'delta_storms_per_year':float(delta),'ci_low':ci[0], 'ci_high':ci[1], 'p':float(p)})
    write_table(pd.DataFrame(sensitivity), 'period_intensity_sensitivity')
    loo = []
    for year in storms.query('y >= 1966 and phase != "neutral"').y.unique():
        t = decompose(storms[storms.y != year], storms.loc[storms.y != year, 'k'], permutations=19, bootstrap=0)
        for axis in ['longitude', 'latitude']:
            row = t[(t.axis == axis) & (t.component == 'total')].iloc[0]
            loo.append({'omitted_year':int(year),'axis':axis,'estimate':row.estimate})
    write_table(pd.DataFrame(loo), 'leave_one_season_out')
    return result, pd.DataFrame(sensitivity), pd.DataFrame(loo)


def fig_robustness(table, sensitivity):
    fig, axs = plt.subplots(1, 3, figsize=(12.5, 5), layout='constrained')
    for ax, axis, comp, title in zip(axs[:2], ['longitude','latitude'], ['type_mix','within_type'],
                                    ['a  East shift: type mix', 'b  North shift: within type']):
        t = table[(table.axis == axis) & (table.component == comp)]
        for i, (_, r) in enumerate(t.iterrows()):
            ax.scatter(r.estimate, i, s=55, color='#1768AE' if axis=='longitude' else '#C44727',
                       facecolors='none' if r.p_permutation>=.05 else None)
            ax.annotate(ptext(r.p_permutation), (r.estimate, i), xytext=(8, 0), textcoords='offset points', va='center', fontsize=8)
        ax.set_yticks(range(len(t)), t.model); ax.invert_yaxis()
        ax.set(xlabel='El Niño − La Niña (°)', title=title)
        ax.set_xlim(0, 9 if axis=='longitude' else 3.5)
    ax=axs[2]
    for j, cat in enumerate([0,1,3]):
        t=sensitivity[sensitivity.min_category==cat]
        ax.errorbar(t.start+j*1.2, t.delta_storms_per_year,
                    yerr=[t.delta_storms_per_year-t.ci_low,t.ci_high-t.delta_storms_per_year],
                    fmt=['o','s','^'][j], capsize=3, label=['All named','Hurricanes','Major'][j])
    ax.axhline(0,color='#999',ls='--',lw=.8)
    ax.set(xticks=[1950,1966,1980],xlabel='First season (end: 2025)',ylabel='La Niña − El Niño storms / season',title='c  Period and intensity sensitivity')
    ax.legend(fontsize=8,loc='upper left')
    save(fig,'fig05_robustness')


def moment_results(storms, permutations=9999):
    s=storms[(storms.y>=1966)&storms.phase.isin(['nino','nina'])].dropna(subset=MOMENTS)
    years=np.sort(s.y.unique()); counts=np.array([(s.y==y).sum() for y in years])
    sums=np.array([s.loc[s.y==y,MOMENTS].sum().values for y in years])
    pos=np.array([s.loc[s.y==y,'phase'].iloc[0]=='nino' for y in years]);a,b=np.flatnonzero(pos),np.flatnonzero(~pos)
    def contrast(a,b):return sums[a].sum(0)/counts[a].sum()-sums[b].sum(0)/counts[b].sum()
    obs=contrast(a,b);rng=np.random.default_rng(66)
    null=np.array([contrast(q[:len(a)],q[len(a):]) for q in (rng.permutation(len(years)) for _ in range(permutations))])
    ps=(1+(abs(null)>=abs(obs)-1e-12).sum(0))/(permutations+1)
    table=pd.DataFrame({'moment':MOMENTS,'delta_nino_minus_nina':obs,'p_permutation':ps,'q_bh':adjust(ps,'bh')})
    return write_table(table,'moment_contrasts')


def fig_moments(storms, table):
    fig,axs=plt.subplots(3,3,figsize=(11.5,9),layout='constrained')
    s=storms[(storms.y>=1966)&storms.phase.isin(['nino','nina'])].dropna(subset=MOMENTS)
    for j,(ax,col,label) in enumerate(zip(axs.flat,MOMENTS,MOM_LABELS)):
        lo,hi=s[col].min(),s[col].max()
        left = max(0, lo-.06*(hi-lo)) if col in ['Vx','Vy'] else lo-.06*(hi-lo)
        grid=np.linspace(left,hi+.06*(hi-lo),400)
        for phase in ['nina','nino']:
            vals=s[s.phase==phase][col]; density=gaussian_kde(vals)(grid)
            ax.plot(grid,density,color=COLORS[phase],lw=1.6,label=LABELS[phase])
            ax.fill_between(grid,0,density,color=COLORS[phase],alpha=.08)
        ax.set(xlabel=label,ylabel='Density',title=f'{chr(97+j)}  BH q = {table.iloc[j].q_bh:.3f}')
    axs[0,0].legend(fontsize=8)
    save(fig,'fig06_moment_distributions')


def cv_auc(x, y, groups, seed, balanced=True):
    unique=np.unique(groups);rng=np.random.default_rng(seed)
    foldmap=dict(zip(unique,rng.permutation(len(unique)) % 10))
    fold=np.array([foldmap[g] for g in groups]);pred=np.zeros(len(y))
    for f in np.unique(fold):
        tr,te=fold!=f,fold==f
        assert not set(groups[tr]) & set(groups[te])
        if len(np.unique(y[tr]))!=2:raise ValueError('Training fold contains one class')
        model=make_pipeline(StandardScaler(),LogisticRegression(max_iter=2000,class_weight='balanced' if balanced else None))
        model.fit(x[tr],y[tr]);pred[te]=model.predict_proba(x[te])[:,1]
    return roc_auc_score(y,pred)


def classification(storms,features,splits=10,permutations=199,bootstrap=200):
    s=storms[(storms.y>=1966)&storms.phase.isin(['nina','nino'])].dropna(subset=MOMENTS)
    groups=s.y.to_numpy();y=(s.phase=='nina').to_numpy(int);years=np.unique(groups)
    sets={'Centroid':s[['Ex','Ey']].to_numpy(),'First + second':s[MOMENTS[:5]].to_numpy(),
          'Skewness + kurtosis':s[MOMENTS[5:]].to_numpy(),'All nine moments':s[MOMENTS].to_numpy(),
          'Genesis':np.stack(s.g),'Resampled track':features[s.index]}
    def score(x,yy=y,gg=groups):return np.mean([cv_auc(x,yy,gg,seed) for seed in range(splits)])
    # Null refits the entire scaling/classifier pipeline on identical folds.
    season_labels=np.array([y[np.flatnonzero(groups==u)[0]] for u in years])
    null_labels=[]
    for k in range(permutations):
        labels=dict(zip(years,np.random.default_rng(500+k).permutation(season_labels)))
        null_labels.append(np.array([labels[u] for u in groups]))
    rows=[];nulls={}
    with threadpool_limits(limits=1):
        for name,x in sets.items():
            repeated=np.array([cv_auc(x,y,groups,seed) for seed in range(splits)])
            null=np.array([score(x,yy) for yy in null_labels]);obs=repeated.mean();nulls[name]=null
            lo,hi=np.percentile(null,[5,95]);p=(1+(null>=obs).sum())/(permutations+1)
            rows.append({'features':name,'auc':obs,'split_min':repeated.min(),'split_max':repeated.max(),
                         'null_mean':null.mean(),'null_05':lo,'null_95':hi,'p_permutation':p})
            print(f'{name}: AUC {obs:.3f}; permutation p {p:.3f}',flush=True)
        a=sets['First + second'];b=sets['All nine moments'];gains=[]
        ids={u:np.flatnonzero(groups==u) for u in years};en=years[season_labels==0];ln=years[season_labels==1]
        for rep in range(bootstrap):
            rng=np.random.default_rng(9000+rep)
            sampled=np.r_[rng.choice(en,len(en),replace=True),rng.choice(ln,len(ln),replace=True)]
            idx=np.concatenate([ids[u] for u in sampled])
            # Repeated copies retain the original year group: no copy enters train and test.
            gains.append(score(b[idx],y[idx],groups[idx])-score(a[idx],y[idx],groups[idx]))
            if (rep+1)%50==0:print(f'Paired season bootstrap: {rep+1}/{bootstrap}',flush=True)
    table=pd.DataFrame(rows);table['q_bh']=adjust(table.p_permutation,'bh')
    write_table(table,'classification');write_table(pd.DataFrame({'replicate':range(bootstrap),'auc_gain':gains}),'auc_gain_bootstrap')
    write_table(pd.DataFrame(nulls),'auc_permutation_nulls')
    delta=float(table.loc[table.features=='All nine moments','auc'].iloc[0]-table.loc[table.features=='First + second','auc'].iloc[0])
    lo,hi=np.percentile(gains,[2.5,97.5]);gain={'delta':delta,'ci_low':float(lo),'ci_high':float(hi),'bootstrap':bootstrap,
                                            'permutations':permutations,'splits':splits,'seasons':len(years),'storms':len(s)}
    (OUT/'classification_config.json').write_text(json.dumps(gain,indent=2),encoding='utf-8')
    return table,np.array(gains),gain


def fig_classification(table,gains,gain):
    fig,axs=plt.subplots(1,2,figsize=(11.5,4.8),layout='constrained',gridspec_kw={'width_ratios':[1.2,1]})
    ax=axs[0]
    for j,(_,r) in enumerate(table.iterrows()):
        ax.plot([r.null_05,r.null_95],[j,j],lw=9,color='#D4D9DE',solid_capstyle='butt')
        ax.scatter(r.auc,j,c='#1768AE',s=50,zorder=5)
        ax.text(.82,j,f'{r.auc:.3f}  q={r.q_bh:.4f}',va='center',fontsize=8)
    ax.axvline(.5,color='#999',ls='--',lw=.8);ax.set_ylim(len(table)+.4,-.5)
    ax.set(yticks=range(len(table)),yticklabels=table.features,xlim=(.3,1),xlabel='Season-grouped cross-validated AUC',title='a  Weak discrimination of single tracks')
    ax.legend(handles=[Line2D([],[],color='#D4D9DE',lw=7,label='Shuffled-label 5–95% range'),Line2D([],[],marker='o',color='#1768AE',ls='',label='Observed mean AUC')],loc='lower right',fontsize=8)
    ax=axs[1];ax.hist(gains,bins=22,color='#90AFC8',edgecolor='white',linewidth=.6)
    ax.set_ylim(0,np.histogram(gains,bins=22)[0].max()*1.35)
    ax.axvline(0,color='#555',ls='--',lw=1);ax.axvline(gain['delta'],color='#C44727',lw=2,label=f'Observed gain {gain["delta"]:+.3f}')
    ax.axvspan(gain['ci_low'],gain['ci_high'],color='#1768AE',alpha=.07)
    ax.set(xlabel='AUC(all nine) − AUC(first + second)',ylabel='Bootstrap replicates',title='b  Increment from higher-order moments')
    ax.legend(fontsize=9);ax.text(.03,.88,f'95% season-bootstrap interval\n[{gain["ci_low"]:+.3f}, {gain["ci_high"]:+.3f}]',transform=ax.transAxes,fontsize=9)
    save(fig,'fig07_predictive_information')
