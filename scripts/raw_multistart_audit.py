"""Separate local IK failures from point reachability; diagnostic, never training labels."""
import project_paths as paths
import json
from pathlib import Path
import numpy as np,pinocchio as pin,h5py
from kinematics import build_rby,READY,solve_arm
ROOT=Path(str(paths.ROOT));r=build_rby();rng=np.random.default_rng(42);out=[]
C=np.array([[0,0,-1],[1,0,0],[0,-1,0]],float)
def quat(q):return pin.Quaternion(float(q[0]),float(q[1]),float(q[2]),float(q[3])).matrix()
for row in json.loads((ROOT/'reports/raw_retarget_pilot.json').read_text()):
 with h5py.File(paths.project_artifact(row['source_hdf5'])) as h:
  g=h['data/demo_0'];ee=g['obs/ee_pose'][:-1];root=g['states/articulation/robot/root_pose'][0];R0=quat(root[3:]);pos=(ee[:,:,:3]-root[:3])@R0
  indices=np.unique(np.r_[np.arange(0,len(ee),max(1,len(ee)//12)),len(ee)-1]);q=r.q_from_dict(READY);errors=[];qs=[];targets=[];restarts=0
  flip=np.diag([-1.,-1.,1.]) if row['gripper_symmetry_pi'] else np.eye(3)
  for fi in indices:
   frame_errors=[];frame_targets=[]
   for side in row['active_arms']:
    ai=['left','right'].index(side);target=pin.SE3(R0.T@quat(ee[fi,ai,3:])@C@flip,pos[fi,ai]+row['best_translation']);ids=np.array([r.model.joints[r.model.getJointId(f'{side}_arm_{i}')].idx_q for i in range(7)])
    best=solve_arm(r,side,target,q,150)
    if best[1]>.01 or best[2]>np.deg2rad(5):
     for attempt in range(16):
      seed=q.copy();seed[ids]=rng.uniform(r.model.lowerPositionLimit[ids]+1e-4,r.model.upperPositionLimit[ids]-1e-4);candidate=solve_arm(r,side,target,seed,150);restarts+=1
      if candidate[1]+.15*candidate[2]<best[1]+.15*best[2]:best=candidate
      if best[1]<.01 and best[2]<np.deg2rad(5):break
    q,pe,re=best;frame_errors.append([pe,re]);frame_targets.append(target.homogeneous)
   errors.append(frame_errors);qs.append(q.copy());targets.append(frame_targets)
  a=np.array(errors);ok=(a[:,:,0]<.01)&(a[:,:,1]<np.deg2rad(5))
  rec={**row,'method':'same best pilot translation; warm start + up to 16 random bounded IK starts per failed arm pose; seed 42; 150 iterations; point reachability only','sampled_frames':len(indices),'valid_fraction':float(ok.mean()),'all_sampled_poses_valid':bool(ok.all()),'max_position_error_m':float(a[:,:,0].max()),'max_orientation_error_deg':float(np.rad2deg(a[:,:,1].max())),'random_restart_attempts':restarts,'collision_checked':False,'task_success_checked':False}
  out.append(rec);np.savez_compressed(ROOT/f'reports/T{int(row["Task"][1:]):02d}_ik_diagnostic.npz',source_frame_index=indices,q=qs,error_m_rad=a,targets=targets,joint_names=np.array(list(r.model.names)[1:],dtype=str))
  (ROOT/'reports/raw_multistart_audit.json').write_text(json.dumps(out,indent=2));print(row['Task'],rec['valid_fraction'],rec['max_position_error_m'],restarts,flush=True)
