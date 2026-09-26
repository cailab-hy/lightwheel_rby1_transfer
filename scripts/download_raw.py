import project_paths as paths
import json,concurrent.futures as cf
from pathlib import Path
from huggingface_hub import hf_hub_download
ROOT=Path(str(paths.ROOT));names={r['Task 이름'] for r in json.loads((ROOT/'selection.json').read_text())}
files=[r for r in json.loads((ROOT/'reports/raw_repo_inventory.json').read_text()) if r['path'].startswith('lightwheel_libero_tasks_x7s/') and r['path'].split('/')[1] in names and r['path'].endswith(('trajectories.hdf5','running_args.json'))]
print('DOWNLOAD',len(files),'bytes',sum(x['size'] for x in files),flush=True)
def download(row):
 return hf_hub_download('LightwheelAI/lightwheel_tasks',repo_type='dataset',revision='c22c3ce6969be62103c8c82f090006147dac2fda',filename=row['path'],local_dir=ROOT/'raw_hdf5')
with cf.ThreadPoolExecutor(max_workers=8) as pool:
 for i,_ in enumerate(pool.map(download,files),1):
  if i%100==0:print('DOWNLOADED',i,flush=True)
(ROOT/'reports/raw_download_manifest.json').write_text(json.dumps(files,indent=2));print('RAW_COMPLETE',flush=True)
