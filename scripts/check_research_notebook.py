"""Independent integrity checks for the executed notebook and exported scientific results."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
import nbformat
from PIL import Image
from scipy.stats import false_discovery_control

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'notebooks'
nb = nbformat.read(BASE / 'enso_storm_atlas_research.ipynb', as_version=4)
nbformat.validate(nb)
code = [c for c in nb.cells if c.cell_type == 'code']
assert [c.execution_count for c in code] == list(range(1, len(code)+1))
assert not any(o.output_type == 'error' for c in code for o in c.outputs)
assert sum('image/png' in o.get('data', {}) for c in code for o in c.outputs) == 7
manifest = json.loads((BASE / 'data/manifest.json').read_text())
for name, checksum in manifest['files'].items():
    assert hashlib.sha256((BASE / 'data' / name).read_bytes()).hexdigest() == checksum
s = pd.DataFrame(json.loads((BASE / 'data/atlas_snapshot.json').read_text())['storms'])
assert s.id.is_unique and len(s) == 979
results = BASE / 'results'
activity = pd.read_csv(results / 'seasonal_contrasts.csv')
types = pd.read_csv(results / 'type_rates.csv')
assert np.isclose(types.delta_nina_minus_nino.sum(), activity.iloc[0].delta_nina_minus_nino)
dec = pd.read_csv(results / 'centroid_decomposition.csv')
for _, t in dec.groupby('axis'):
    v = t.set_index('component').estimate
    assert np.isclose(v.total, v.type_mix+v.within_type)
for name in ['moment_contrasts', 'classification']:
    table = pd.read_csv(results / f'{name}.csv')
    assert np.allclose(table.q_bh, false_discovery_control(table.p_permutation.to_numpy()))
config = json.loads((results / 'classification_config.json').read_text())
gains = pd.read_csv(results / 'auc_gain_bootstrap.csv').auc_gain
assert len(gains) == config['bootstrap']
assert np.allclose(np.percentile(gains, [2.5, 97.5]), [config['ci_low'], config['ci_high']])
clf = pd.read_csv(results / 'classification.csv').set_index('features')
nulls = pd.read_csv(results / 'auc_permutation_nulls.csv')
assert len(nulls) == config['permutations']
for name, row in clf.iterrows():
    assert np.allclose(np.percentile(nulls[name], [5, 95]), [row.null_05, row.null_95])
    assert np.isclose((1 + (nulls[name] >= row.auc).sum()) / (len(nulls)+1), row.p_permutation)
assert np.isclose(clf.loc['All nine moments', 'auc'] - clf.loc['First + second', 'auc'], config['delta'])
for suffix in ['png','pdf','svg']:
    files = sorted((BASE / 'figures').glob(f'fig*.{suffix}'))
    assert len(files) == 7
    for f in files:
        assert f.stat().st_size > 1000
        if suffix == 'png':
            with Image.open(f) as im:
                im.verify()
            with Image.open(f) as im:
                assert min(im.info['dpi']) >= 299
                assert im.width > 2500 and im.height > 1000
assert '原项目' not in ''.join(c.source for c in nb.cells)
print(f'PASS: {len(code)} executed code cells, 7 inline figures, 21 exported figures, input hashes and statistical consistency.')
