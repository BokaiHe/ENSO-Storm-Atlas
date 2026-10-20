"""Independent integrity checks for the executed notebook and exported scientific results."""
from pathlib import Path
import hashlib
import json
import re
import sys
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
assert nb.metadata.enso_atlas.language == 'en'
assert not re.search(r'[\u4e00-\u9fff]', ''.join(c.source for c in nb.cells))
for cell in code:
    for output in cell.outputs:
        content = output.get('text', '') + ''.join(v for k,v in output.get('data',{}).items() if k in ['text/plain','text/html','text/markdown'])
        assert not re.search(r'[\u4e00-\u9fff]', content)

# Independently verify Holm adjustment via intersection hypotheses.
def holm_reference(p):
    p=np.asarray(p)
    return np.array([min(1., max((len(p)-np.count_nonzero(p < t))*t for t in p if t <= x)) for x in p])
for filename in ['seasonal_contrasts','type_rates','centroid_decomposition']:
    table=pd.read_csv(results / f'{filename}.csv')
    assert np.allclose(table.p_holm,holm_reference(table.p_permutation))
robust=pd.read_csv(results / 'decomposition_robustness.csv')
for _, table in robust.groupby('model'):
    assert np.allclose(table.p_holm,holm_reference(table.p_permutation))
    assert table[['ci_low','ci_high']].notna().all().all()

shares=pd.read_csv(results / 'type_shares.csv')
assert np.allclose(shares.groupby('phase').share.sum(),1)
assert np.allclose(shares.share,shares.storms/shares.total_storms)
boot=pd.read_csv(results / 'auc_gain_bootstrap.csv')
assert len(boot)==1000 and np.allclose(boot.auc_gain,boot.auc_all_nine-boot.auc_first_second)
assert np.allclose(np.percentile(boot.auc_all_nine,[2.5,97.5]),[config['all_nine_ci_low'],config['all_nine_ci_high']])

# Circular shifts include the observed alignment exactly once; no Monte Carlo +1.
cyclic=pd.read_csv(results / 'circular_shift_nulls.csv').set_index('shift')
temporal=pd.read_csv(results / 'temporal_sensitivity.csv').set_index('outcome')
assert list(cyclic.index)==list(range(60))
for name, row in temporal.iterrows():
    assert np.isclose(row.estimate,cyclic.loc[0,name])
    assert np.isclose(row.p_circular,(cyclic[name].abs() >= abs(row.estimate)-1e-12).mean())
for names in [list(temporal.index[:3]),list(temporal.index[3:])]:
    part=temporal.loc[names]
    assert np.allclose(part.p_holm_within_family,holm_reference(part.p_circular))
assert np.allclose(temporal.estimate.iloc[:3],activity.delta_nina_minus_nino)
assert np.allclose(temporal.estimate.iloc[3:],dec.estimate)

# Compare the geodesic interpolation to an independent library reference.
sys.path.insert(0,str(BASE))
import atlas_analysis as aa
from sklearn.metrics.pairwise import haversine_distances
lon=np.array([-85.,-75.,-60.,-55.]);lat=np.array([12.,25.,38.,40.])
angles=haversine_distances(np.radians(np.c_[lat,lon]))
distance=np.r_[0.,np.cumsum(np.diag(angles,1))]
q=np.linspace(0,distance[-1],16)
expected=np.r_[np.interp(q,distance,lon),np.interp(q,distance,lat)]
assert np.allclose(aa.resample_track(lon,lat),expected)
shifted=aa.resample_track(lon+60,lat);shifted[:16]-=60
assert np.allclose(shifted,expected), 'Distances must not depend on longitude origin'
assert np.allclose(aa.resample_track([-60,-60],[20,20]),np.r_[np.full(16,-60),np.full(16,20)])
assert np.allclose(aa.resample_track([-85,-85,-75,-60,-55],[12,12,25,38,40]),expected)
assert np.ptp(aa.resample_track([179,-179],[20,20])[:16]) < 3

# Controlled decomposition cases isolate composition and within-type movement.
ca=np.array([30.,10.]);cb=np.array([10.,30.]);means=np.array([[-80.,20.],[-40.,40.]])
value=aa.component(ca,ca[:,None]*means,cb,cb[:,None]*means)
assert np.allclose(value[:,2],0)
assert np.allclose(value[:,0],[-20,-10])
assert np.allclose(value,-aa.component(cb,cb[:,None]*means,ca,ca[:,None]*means))
shift=np.array([3.,2.]);value=aa.component(ca,ca[:,None]*(means+shift),ca,ca[:,None]*means)
assert np.allclose(value[:,1],0) and np.allclose(value[:,2],shift)

# Instrument the fitted estimator to catch duplicate-record train/test leakage.
class NoLeakEstimator:
    def fit(self,x,y):
        self.ids=set(x[:,0]); return self
    def predict_proba(self,x):
        assert not self.ids.intersection(x[:,0])
        p=(x[:,0]+1)/50
        return np.c_[1-p,p]
factory=aa.make_pipeline
try:
    aa.make_pipeline=lambda *args:NoLeakEstimator()
    groups=np.repeat(np.arange(15),2)
    x=np.arange(len(groups),dtype=float)[:,None];y=groups%2
    idx=np.r_[np.arange(len(groups)),np.arange(10)]
    for seed in range(3):
        aa.cv_auc(x[idx],y[idx],groups[idx],seed)
finally:
    aa.make_pipeline=factory
print(f'PASS: {len(code)} executed code cells, 7 inline figures, 21 exported figures, input hashes and statistical consistency.')
