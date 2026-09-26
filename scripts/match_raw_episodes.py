"""Match public HDF5 episodes by full observation arrays, not filename order."""
import project_paths as paths
import json,hashlib,time
from pathlib import Path
import numpy as np,pandas as pd,h5py
ROOT=Path(str(paths.ROOT));DST=Path(str(paths.X7S_SUBSET))
while not (ROOT/'reports/raw_download_manifest.json').exists():time.sleep(3)
selection=json.loads((ROOT/'selection.json').read_text());results=[]
for ti,row in enumerate(selection):
 d=pd.read_parquet(DST/f'data/chunk-000/file-{ti:03d}.parquet');lookup={}
 for eid,ep in d.groupby('episode_index'):
  a=np.stack(ep['observation.state']).astype('<f4');lookup.setdefault(hashlib.sha256(a.tobytes()).hexdigest(),[]).append((int(eid),ep))
 files=sorted((ROOT/'raw_hdf5/lightwheel_libero_tasks_x7s'/row['Task 이름']).rglob('trajectories.hdf5'));matched=set()
 for file in files:
  with h5py.File(file) as h:
   g=h['data/demo_0'];a=g['obs/joint_pos'][:];found=None
   for trim in [1,0]:
    candidate=a[:-trim] if trim else a
    key=hashlib.sha256(candidate.astype('<f4').tobytes()).hexdigest()
    for eid,ep in lookup.get(key,[]):
     if eid in matched:continue
     n=len(ep)
     if np.array_equal(g['actions'][:n],np.stack(ep['action'])) and np.array_equal(g['processed_actions'][:n],np.stack(ep['processed_action'])):
      found=(trim,eid,ep);break
    if found is not None:break
   assert found is not None,file
   trim,eid,ep=found;assert eid not in matched;matched.add(eid);n=len(ep)
   assert np.array_equal(g['actions'][:n],np.stack(ep['action']))
   assert np.array_equal(g['processed_actions'][:n],np.stack(ep['processed_action']))
   env=json.loads(h['data'].attrs['env_args']);assert env['task_name']==row['Task 이름']
   expected=f"libero-{env['layout_id']}-{env['style_id']}";assert expected==row['LIBERO 레이아웃 번호']
   result={'Task':row['Task'],'episode_index':eid,'hdf5_path':str(file.relative_to(ROOT)),'frames':n,'raw_frames':len(a),'trim_last_frames':trim,'source_layout':expected,'recorded_success':bool(g.attrs.get('success',False)),'has_world_ee_pose':'obs/ee_pose' in g,'has_object_states':'states/rigid_object' in g,'has_articulation_states':'states/articulation' in g,'has_camera_frames':False};results.append(result)
 assert len(matched)==50,(row['Task'],len(matched));print('RAW_MATCHED',row['Task'],50,flush=True)
results.sort(key=lambda r:r['episode_index']);(ROOT/'reports/raw_episode_mapping.json').write_text(json.dumps(results,indent=2));(DST/'meta/raw_hdf5_episode_mapping.json').write_text(json.dumps(results,indent=2))
print('RAW_ALL_MATCHED',len(results),flush=True)
