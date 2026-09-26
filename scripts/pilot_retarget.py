import project_paths as paths
import json
from pathlib import Path
import numpy as np,pandas as pd,pinocchio as pin
from kinematics import build_rby,build_x7,READY,solve_arm
ROOT=Path(str(paths.ROOT));SRC=Path(str(paths.X7S_SUBSET))
r=build_rby();x=build_x7();info=json.loads((SRC/'meta/info.json').read_text());names=info['features']['observation.state']['names'];sel=json.loads((ROOT/'selection.json').read_text())
C=np.array([[0,0,-1],[1,0,0],[0,-1,0]],float)
rows=[]
for ti in range(10):
 d=pd.read_parquet(SRC/f'data/chunk-000/file-{ti:03d}.parquet');d=d[d.episode_index==d.episode_index.min()].iloc[::10]
 q=r.q_from_dict(READY);errs=[]
 dz=.07+(.72-(.6967464369 if sel[ti]['LIBERO 레이아웃 번호']=='libero-2-2' else .7509999702))
 for state in d['observation.state']:
  xq=x.q_from_dict(dict(zip(names,state)));x.fk(xq)
  for side in ['left','right']:
   p=x.pose(side);target=pin.SE3(p.rotation@C,p.translation+np.array([-.20,0,dz]))
   q,ep,er=solve_arm(r,side,target,q);errs.append([ep,er])
 a=np.array(errs);row={'Task':f'T{ti+1}','samples':len(a),'within_1cm_5deg':float(np.mean((a[:,0]<.01)&(a[:,1]<np.deg2rad(5)))),'position_error_p50_m':float(np.median(a[:,0])),'position_error_max_m':float(a[:,0].max()),'orientation_error_p50_deg':float(np.rad2deg(np.median(a[:,1])))};rows.append(row);print(row,flush=True)
(ROOT/'reports/retarget_pilot.json').write_text(json.dumps(rows,indent=2))
