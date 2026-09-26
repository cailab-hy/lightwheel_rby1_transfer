"""Audit all episodes at 2 Hz; never publish failed IK as robot demonstrations."""
import project_paths as paths
import json
from pathlib import Path
import numpy as np,pinocchio as pin,pandas as pd
from kinematics import build_rby,build_x7,READY,solve_arm
ROOT=Path(str(paths.ROOT));SRC=Path(str(paths.X7S_SUBSET))
r=build_rby();x=build_x7();info=json.loads((SRC/'meta/info.json').read_text());names=info['features']['observation.state']['names'];sel=json.loads((ROOT/'selection.json').read_text());C=np.array([[0,0,-1],[1,0,0],[0,-1,0]],float)
rows=[];summaries=[]
for ti in range(10):
 d=pd.read_parquet(SRC/f'data/chunk-000/file-{ti:03d}.parquet');dz=.07+(.72-(.6967464369 if sel[ti]['LIBERO 레이아웃 번호']=='libero-2-2' else .7509999702));taskrows=[]
 for eid,ep in d.groupby('episode_index'):
  q=r.q_from_dict(READY);errors=[];indices=np.unique(np.r_[np.arange(0,len(ep),25),len(ep)-1]);states=np.stack(ep['observation.state'])
  for state in states[indices]:
   x.fk(x.q_from_dict(dict(zip(names,state))));frame_errors=[]
   for side in ['left','right']:
    pose=x.pose(side);target=pin.SE3(pose.rotation@C,pose.translation+np.array([-.20,0,dz]));q,pe,re=solve_arm(r,side,target,q)
    frame_errors.append([pe,re])
   errors.append(frame_errors)
  a=np.array(errors);ok=(a[:,:,0]<.01)&(a[:,:,1]<np.deg2rad(5));base=states[:,:3]
  row={'Task':f'T{ti+1}','episode_index':int(eid),'sampled_frames':len(indices),'both_arms_valid_fraction':float(np.mean(ok.all(1))),'left_valid_fraction':float(ok[:,0].mean()),'right_valid_fraction':float(ok[:,1].mean()),'position_error_max_m':float(a[:,:,0].max()),'orientation_error_max_deg':float(np.rad2deg(a[:,:,1].max())),'all_sampled_frames_valid':bool(ok.all()),'base_xy_range_m':np.ptp(base[:,:2],axis=0).tolist(),'base_yaw_range_rad':float(np.ptp(base[:,2]))}
  rows.append(row);taskrows.append(row)
 summary={'Task':f'T{ti+1}','episodes':len(taskrows),'episodes_passing_all_sampled_frames':sum(v['all_sampled_frames_valid'] for v in taskrows),'mean_both_arms_valid_fraction':float(np.mean([v['both_arms_valid_fraction'] for v in taskrows])),'max_base_xy_range_m':np.max([v['base_xy_range_m'] for v in taskrows],axis=0).tolist(),'sample_stride':25,'scope':'single nominal frame alignment and local IK solver; failure does not prove global infeasibility; no collisions, dynamics, or task success tested'}
 summaries.append(summary);print(summary,flush=True)
 (ROOT/'reports/source_transfer_episodes.json').write_text(json.dumps(rows,indent=2));(ROOT/'reports/source_transfer_summary.json').write_text(json.dumps(summaries,indent=2))
