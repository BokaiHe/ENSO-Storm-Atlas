# Academic analysis

[Read the executed English notebook](enso_storm_atlas_research.ipynb)

A complete English research narrative: questions and background, data definitions, methods, computed results, robustness, discussion, and conclusions. Statistics are recomputed from a fixed processed snapshot; no fitted website results are read.

## Reproduce

From the repository root (verified with Python 3.13):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
pip install -r requirements-notebook.txt
python scripts/run_research_notebook.py
python scripts/check_research_notebook.py
```

The runner starts a fresh kernel and saves the notebook only after successful execution. It never reuses old cell outputs. After dependencies are installed, analysis needs no network or large raw-data download. Classification permutations and 1,000 paired season bootstraps dominate runtime.

`requirements-notebook-lock.txt` records the main tested dependency versions; `results/environment.json` records the executed environment. You may also run all cells in JupyterLab or VS Code from the repository root or `notebooks/`.

## Contents

| Path | Contents |
|---|---|
| `enso_storm_atlas_research.ipynb` | Executed English narrative, code, figures, tables |
| `atlas_analysis.py` | Statistical and plotting implementation |
| `data/` | Fixed 979-track snapshot, coastline, sources and checksums |
| `figures/` | Seven figure sets: 300 dpi PNG and PDF/SVG |
| `results/` | Estimates, intervals, null distributions, bootstrap samples, environment |

`../scripts/build_research_notebook.py` generates the narrative and cells, clearing saved outputs. Run it only when regenerating the source structure, followed by the execution script.

## Design and interpretation

- Primary comparison: 1966–2025, 14 La Niña and 15 El Niño seasons (391 storms). Neutral seasons provide context.
- Years are the resampling units; the exact symmetric centroid decomposition adds type mix and within-type displacement.
- Holm correction is within activity, type-rate, and decomposition families; BH adjustment is within moments and classification feature sets. Intervals are marginal.
- Primary type labels remain fixed to preserve the atlas definition. New trajectories use haversine segment distances; geodesic K=3–7 refits test geometric and grouping sensitivity.
- Circular shifts retain ENSO's cyclic temporal ordering. Their stationarity assumption differs from independent-year permutations; both are reported.
- Standardization is fitted within training folds. Copies of the same bootstrapped season cannot enter different folds.
- AUC grey bars are shuffled-label 5–95% ranges, not observed-AUC confidence intervals. The paired gain interval uses 1,000 season bootstraps.
- Completed-track discrimination is retrospective; it is not an early-warning or future-period forecast.

The notebook adds uncertainty and sensitivity analyses beyond the website. Its geodesic refits, empirical intervals, and corrected p values need not match the website's earlier settings. It does not rewrite website statistics.
