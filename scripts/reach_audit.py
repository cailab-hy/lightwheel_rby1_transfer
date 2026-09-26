import project_paths as paths
import json
from pathlib import Path
import numpy as np,pinocchio as pin
from kinematics import build_rby,READY,solve_arm
ROOT=Path(str(paths.ROOT));r=build_rby();rng=np.random.default_rng(42);allrows=[]
for meta in json.loads((ROOT/'reports/scene_manifest.json').read_text()):
 base=np.array(meta['robot_base_world']);targets=[]
 required={1:['bowl','plate'],2:['bowl','plate'],3:['ketchup','basket'],4:[],5:[],6:[],7:['bowl'],8:['middle_bowl','back_bowl'],9:['bowl'],10:['alphabet_soup','tomato_sauce','basket']}[int(meta['Task'][1:])]
 for o in meta['objects']:
  if o['name'] not in required:continue
  p=np.array(o['center']);p[2]+=.025
  targets.append((o['name'],np.array([base[1]-p[1],p[0]-base[0],p[2]]),'object centre + 25 mm; position-only feasibility, not a grasp certificate'))
 for f in meta['fixtures']:
  lo,hi=np.array(f['aabb']);p=(lo+hi)/2;p[1]=hi[1]+.015
  if 'storage' in f['name']:p[2]=hi[2]-.06
  targets.append((f['name']+'_front',np.array([base[1]-p[1],p[0]-base[0],p[2]]),'front-centre proxy; actual articulated handle and sweep need collision validation'))
 rows=[]
 for name,target,note in targets:
  best=None
  for side in ['left','right']:
   for pitch in [0,.5,-.5]:
    for yaw in [0,np.pi/2,np.pi,-np.pi/2]:
     R=pin.rpy.rpyToMatrix(0,pitch,yaw)
     q=r.q_from_dict(READY);q,ep,er=solve_arm(r,side,pin.SE3(R,target),q,max_iters=100)
     score=ep+.05*er
     if best is None or score<best[0]:best=(score,side,q.copy(),ep,er,yaw)
  _,side,q,ep,er,yaw=best
  row={'target':name,'position_robot_frame_m':target.tolist(),'arm':side,'position_error_m':ep,'orientation_error_deg':float(np.rad2deg(er)),'reachable_1cm_5deg':bool(ep<.01 and er<np.deg2rad(5)),'note':note,'joint_solution':{n:float(q[r.model.joints[r.model.getJointId(n)].idx_q]) for n in READY}}
  rows.append(row)
 summary={'Task':meta['Task'],'tested_targets':len(rows),'reachable_targets':sum(x['reachable_1cm_5deg'] for x in rows),'collision_checked':False,'language_task_success_verified':False,'targets':rows};allrows.append(summary);print(meta['Task'],summary['reachable_targets'],'/',len(rows),flush=True)
(ROOT/'reports/reachability.json').write_text(json.dumps(allrows,indent=2))
