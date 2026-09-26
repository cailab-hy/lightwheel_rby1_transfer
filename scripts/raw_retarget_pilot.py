"""Recorded world EE poses, active-arm selection, gripper symmetry and base alignment search."""
import project_paths as paths
import json
from pathlib import Path
import numpy as np,pinocchio as pin,h5py
from huggingface_hub import hf_hub_download
from kinematics import build_rby,READY,solve_arm
ROOT=Path(str(paths.ROOT));r=build_rby();selection=json.loads((ROOT/'selection.json').read_text());inventory=json.loads((ROOT/'reports/raw_repo_inventory.json').read_text());C=np.array([[0,0,-1],[1,0,0],[0,-1,0]],float)
def quat(q):return pin.Quaternion(float(q[0]),float(q[1]),float(q[2]),float(q[3])).matrix()
out=[]
for row in selection:
 name=row['Task 이름'];source_paths=sorted(v['path'] for v in inventory if v['path'].startswith('lightwheel_libero_tasks_x7s/'+name+'/') and v['path'].endswith('trajectories.hdf5'));f=hf_hub_download('LightwheelAI/lightwheel_tasks',repo_type='dataset',revision='c22c3ce6969be62103c8c82f090006147dac2fda',filename=source_paths[0],local_dir=ROOT/'raw_hdf5')
 with h5py.File(f) as h:
  g=h['data/demo_0'];ee=g['obs/ee_pose'][:];actions=g['actions'][:];root=g['states/articulation/robot/root_pose'][0];env=json.loads(h['data'].attrs['env_args']);R0=quat(root[3:]);pos=(ee[:,:,:3]-root[:3])@R0
  active=[i for i in range(2) if len(np.unique(actions[:,19+i]))>1]
  if not active:
   change=np.ptp(pos,axis=0);active=[int(np.argmax(np.linalg.norm(change,axis=1)))]
  # Optimize a single rigid planar alignment per episode. No scale deformation.
  dz=float(root[2])+.72-(.6967464369 if env['layout_id']==2 else .7509999702)
  indices=np.unique(np.r_[np.arange(0,len(ee),max(1,len(ee)//12)),len(ee)-1]);best=None
  for dx in [-.4,-.3,-.2,-.1]:
   for dy in [-.15,0,.15]:
    for symmetry in [0,1]:
     q=r.q_from_dict(READY);errors=[];flip=np.diag([-1.,-1.,1.]) if symmetry else np.eye(3)
     for fi in indices:
      for ai in active:
       side=['left','right'][ai];target=pin.SE3(R0.T@quat(ee[fi,ai,3:])@C@flip,pos[fi,ai]+[dx,dy,dz]);q,pe,re=solve_arm(r,side,target,q,max_iters=80);errors.append([pe,re])
     a=np.array(errors);valid=(a[:,0]<.01)&(a[:,1]<np.deg2rad(5));score=np.mean(valid)-.1*np.mean(a[:,0])-.01*np.mean(a[:,1])
     if best is None or score>best[0]:best=(score,dx,dy,symmetry,float(valid.mean()),float(a[:,0].max()),float(np.rad2deg(a[:,1].max())))
  _,dx,dy,symmetry,valid,pe,re=best
  rec={'Task':row['Task'],'source_hdf5':str(Path(f).relative_to(ROOT)),'active_arms':[['left','right'][i] for i in active],'sampled_frames':len(indices),'best_translation':[dx,dy,dz],'gripper_symmetry_pi':symmetry,'valid_fraction':valid,'max_position_error_m':pe,'max_orientation_error_deg':re,'source_layout_id':env['layout_id'],'source_style_id':env['style_id'],'scope':'one episode per task; optimized constant planar translation; recorded EE poses; no collisions/dynamics/task-success validation'};out.append(rec);print(rec,flush=True)
 (ROOT/'reports/raw_retarget_pilot.json').write_text(json.dumps(out,indent=2))
