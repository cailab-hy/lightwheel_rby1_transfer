import project_paths as paths
import json,hashlib
from collections import defaultdict,Counter
from pathlib import Path
import h5py,numpy as np
from huggingface_hub import HfApi
R=Path(str(paths.ROOT));rows=json.loads((R/'reports/raw_episode_mapping.json').read_text());groups=defaultdict(list)
for row in rows:
 p=paths.project_artifact(row['hdf5_path']);row['hdf5_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
 with h5py.File(p) as h:
  g=h['data/demo_0'];digest=hashlib.sha256()
  for key in ['obs/joint_pos','actions','processed_actions']:digest.update(g[key][:row['frames']].astype('<f4').tobytes())
  groups[(row['Task'],digest.hexdigest())].append(row['episode_index'])
  row['kinematic_array_sha256']=digest.hexdigest()
summary={'repo_id':'LightwheelAI/lightwheel_tasks','revision':HfApi().dataset_info('LightwheelAI/lightwheel_tasks').sha,'matched_episodes':len(rows),'matched_frames':sum(v['frames'] for v in rows),'matching_method':'one-to-one multiset of entire float32 observation.state, action, processed_action; final HDF5 frame omitted to match LeRobot conversion','all_recorded_success':all(v['recorded_success'] for v in rows),'trim_last_frames_counts':dict(Counter(v['trim_last_frames'] for v in rows)),'duplicate_kinematic_episode_groups':[v for v in groups.values() if len(v)>1],'duplicate_note':'Identical kinematic arrays make the original filename assignment ambiguous within each duplicate group. Every raw file and every extracted episode is used exactly once; no evidence of RGB identity is claimed.','layout_counts':dict(Counter(v['source_layout'] for v in rows)),'downloaded_files':1000,'downloaded_bytes':sum(v['size'] for v in json.loads((R/'reports/raw_download_manifest.json').read_text()))}
(R/'reports/raw_episode_mapping.json').write_text(json.dumps(rows,indent=2));Path(str(paths.X7S_SUBSET / 'meta/raw_hdf5_episode_mapping.json')).write_text(json.dumps(rows,indent=2));(R/'reports/raw_validation_summary.json').write_text(json.dumps(summary,indent=2));print(summary)
