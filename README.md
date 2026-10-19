# ENSO Storm Atlas

An interactive, bilingual (English / 中文) website on how El Niño and La Niña reshape North Atlantic hurricanes, 1950–2025. It is a redesign and correction of [sarika-debruyn/hurricane-prediction-ml](https://github.com/sarika-debruyn/hurricane-prediction-ml).

Open `docs/index.html` in a browser. It is a single self-contained file with the data embedded. It needs an internet connection only for the d3 library and web fonts.

## Interface

- English / 中文 and dark / light themes, with preferences saved in the browser.
- Translucent section backgrounds, aligned chart panels, and emphasis on key results and uncertainty.
- Responsive desktop and mobile layouts, touch controls, season replay, and reduced-motion support.

The final browser review covered 320–1440 px viewports, both languages and themes, desktop interactions, and simulated mobile touch. It checked filters, chart labels, panel alignment, replay controls, state persistence, and browser errors. Mobile coverage uses Chromium device emulation; it is not a physical-device compatibility certification.

## Publish on GitHub Pages

The checked-in `docs/index.html` is ready to serve. In the repository's **Settings → Pages**, choose **Deploy from a branch**, select **main** and **/docs**, then save. GitHub Pages availability depends on the repository visibility and account plan.

For local preview, open `docs/index.html`, or run `python -m http.server 8000 --directory docs` from the project root and visit `http://localhost:8000`.

## What the page shows

| Section | Content |
|---|---|
| ONI dial | Each hurricane season is a dot placed by its Aug–Oct ONI. Drag to select seasons and the map animates every storm from them. |
| Head to head | Storms, ACE, US landfalls and Gulf-type storms per year, La Niña vs El Niño, with permutation-test p-values. |
| Hot zones | Track-density maps for the two phases, with a draggable comparison slider and a difference view. |
| Season replay | Fast-forward any season from 1950 to 2025, with storms coloured by Saffir–Simpson category and a running ACE total. |
| Four track types | A single K-Means model on resampled tracks, and how often each type occurs in each ENSO phase. |
| Shape fingerprint | The nine track moments from the original project (centroid, variance, covariance, skewness, kurtosis), plus a test of whether one track can reveal its season type. |

Main results for 1966–2025: La Niña seasons average 16.1 named storms against 11.0 in El Niño seasons (p ≈ 0.005), with 1.6× the ACE and 1.9× the US landfalls. Nearly all of the drop is in the Gulf & Caribbean track type (5.9 vs 2.3 per year).

## Project layout

```
scripts/
  download_data.py   fetch IBTrACS, ONI and coastline files into data/raw/
  build_data.py      clean tracks, assign ENSO phase, compute ACE/landfall/recurvature, cluster tracks -> build/data.json
  analyze.py         statistics quoted on the page (permutation tests, moments, classification AUC)
                     -> build/analysis.txt and build/ml_results.json (needed by build_site.py)
  decompose.py       split the El Niño centroid shift into type mix vs within-type parts, K = 3..7
                     -> build/decomp.json (needed by build_site.py)
  build_site.py      embed data into site/template.html -> docs/index.html
site/template.html   page source: HTML, CSS, JS and both languages
docs/index.html      the built website (GitHub Pages can serve this folder)
data/raw/            downloaded inputs (git-ignored)
build/               intermediate data.json, analysis.txt, and artifact.html (the same page
                     without the <html> wrapper, used to publish the claude.ai version); git-ignored
```

## Rebuild from scratch

```bash
pip install -r requirements.txt
python scripts/download_data.py
python scripts/build_data.py
python scripts/analyze.py     # ~10 minutes; writes build/ml_results.json
python scripts/decompose.py   # ~2 minutes; writes build/decomp.json
python scripts/build_site.py
```

`analyze.py` prints the statistics behind the page and writes the classification results that the page embeds, so run it before `build_site.py`. To refresh the data later, for example once the 2026 season ends, run `download_data.py --force`, raise `Y1` in `build_data.py`, and rebuild.

## Data and methods

- **Tracks:** IBTrACS v04r01 North Atlantic. Uses `main` tracks at 00/06/12/18 UTC fixes and `USA_WIND` (1-minute sustained wind, kt). A storm is included if it has at least one tropical or subtropical fix of 34 kt or more, which gives 979 storms for 1950–2025.
- **ENSO phase:** NOAA CPC ONI for each year's ASO season. El Niño is ONI ≥ +0.5 and La Niña is ONI ≤ −0.5. This one definition is used throughout.
- **Significance:** permutation tests that shuffle whole seasons (4,000 shuffles, fixed seed), so storms from the same year are never treated as independent.
- **Track types:** each track is resampled to 16 points along its length and clustered with one K-Means model. K = 4 has the best silhouette score for K = 3–7.
- **Single-track classification:** El Niño and La Niña storms (1966–2025: 29 seasons, 391 storms) are classified with logistic regression using balanced class weights. Without the weights, leaving whole years out shifts the class mix and pushes a no-information model to AUC ≈ 0.35. Each score is the mean over the same 10 random season-grouped 10-fold splits. It is compared with that feature set's own null, built by shuffling season labels between years 100 times on the same splits. All nine moments score AUC 0.625 against a null 5–95% range of 0.41–0.57. Every feature set sits above its null (p ≤ 0.04). This signal is weak, but it is real.
- **Type mix vs within type:** the El Niño − La Niña difference in mean track centroid is split into two parts, one from a change in which track types occur and one from tracks of the same type running elsewhere. The split uses two components with averaged weights, and p-values come from 1,000 shuffles of season labels between years. For 1966–2025 the 6.7° eastward shift is almost all type mix (5.8°, p = 0.002) at every K from 3 to 7. The 2.2° northward shift is mostly within type (1.6°, p = 0.005). That holds for K = 4–7 and after detrending, but not at K = 3 (p = 0.14).
- **Do skewness and kurtosis add anything?** Adding them to the 1st and 2nd moments raises AUC from 0.603 to 0.625 (+0.022). A season-level bootstrap resamples El Niño and La Niña years with replacement, keeping each year's storms together and in the same fold. Its 95% interval for the gain is −0.045 to +0.083, so the gain is not established. Repeated splits reuse the same 29 seasons, so they are not independent evidence. Results are in `build/ml_results.json`, which `build_site.py` embeds in the page.
- **Limitations:** La Niña / El Niño sample sizes depend on the selected period: 18 / 20 seasons for 1950–2025, 14 / 15 for 1966–2025, and 10 / 12 for 1980–2025. The page displays the counts for the current period. Pre-1966 records miss some short-lived storms. The AMO and long-term warming are not controlled for. The results are correlations.

## Fixes relative to the original notebook

- The Saffir–Simpson categorisation counted tropical depressions as Category 1 and treated missing winds as Category 5.
- The ENSO 5-month rule sorted months alphabetically, and three different ENSO definitions were mixed.
- Clustering dropped track points instead of storms, which truncated the tracks.
- Each phase had its own K-Means model, so cluster labels could not be compared across phases.
- No significance testing was done.
