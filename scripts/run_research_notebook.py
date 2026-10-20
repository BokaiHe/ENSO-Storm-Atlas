"""Execute the research notebook in a fresh Python kernel and save validated outputs."""
from pathlib import Path
import os
import sys
import time
import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'notebooks/enso_storm_atlas_research.ipynb'
nb = nbformat.read(path, as_version=4)
for cell in nb.cells:
    if cell.cell_type == 'code':
        cell.outputs = []
        cell.execution_count = None
os.environ['PYTHONIOENCODING'] = 'utf-8'
km = KernelManager(kernel_name='python3')
km.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
start = time.perf_counter()
def progress(cell, cell_index):
    print(f'Executing cell {cell_index+1}/{len(nb.cells)} ({time.perf_counter()-start:.0f}s)', flush=True)
class ReportingClient(NotebookClient):
    def process_message(self, msg, cell, cell_index):
        if msg['header']['msg_type'] == 'stream':
            print(msg['content'].get('text', ''), end='', flush=True)
        return super().process_message(msg, cell, cell_index)

client = ReportingClient(nb, km=km, timeout=3600, allow_errors=False,
                        resources={'metadata': {'path': str(ROOT / 'notebooks')}}, on_cell_start=progress)
try:
    client.execute()
except Exception:
    failure = ROOT / 'build/research_notebook_failed.ipynb'
    failure.parent.mkdir(exist_ok=True)
    nbformat.write(nb, failure)
    raise
finally:
    if km.has_kernel:
        km.shutdown_kernel(now=True)
nbformat.validate(nb)
assert all(c.execution_count is not None for c in nb.cells if c.cell_type == 'code')
assert not any(o.output_type == 'error' for c in nb.cells if c.cell_type == 'code' for o in c.outputs)
nbformat.write(nb, path)
print(f'Completed {len([c for c in nb.cells if c.cell_type == "code"])} code cells in {time.perf_counter()-start:.1f}s', flush=True)
