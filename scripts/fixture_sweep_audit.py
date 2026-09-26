"""Kinematic handle sweep checks using USD collision geometry and joint anchors.
No collision/contact certificate. Drawer handle = frontmost bar collider.
"""
import project_paths as paths
paths.prepare_assets()
import json,argparse
from pathlib import Path
import numpy as np,pinocchio as pin
from kinematics import build_rby,READY,solve_arm,world,se3
from pxr import Usd,UsdGeom,UsdPhysics
parser=argparse.ArgumentParser();parser.add_argument('--tasks',type=int,nargs='+',default=[4,5,6,7,9]);args=parser.parse_args()
ROOT=Path(str(paths.ROOT));r=build_rby();rng=np.random.default_rng(123);out=[]
def mesh_center(p):
 a=np.asarray(UsdGeom.Mesh(p).GetPointsAttr().Get());t=world(p);a=a@t.rotation.T+t.translation
 return (a.min(0)+a.max(0))/2
for ti in args.tasks:
 meta=json.loads((ROOT/f'environments/T{ti:02d}.json').read_text());s=Usd.Stage.Open(str(ROOT / meta['usd']));fixture=s.GetPrimAtPath(meta['fixtures'][0]['prim']);base=np.array(meta['robot_base_world']);Rbase=pin.rpy.rpyToMatrix(0,0,meta['robot_yaw_rad'])
 if ti in [4,7,9]:
  part='003' if ti==9 else '001';body=next(p for p in Usd.PrimRange(fixture) if p.GetName()=='StorageFurniture136_Drawer'+part);jp=next(p for p in body.GetAllChildren() if p.IsA(UsdPhysics.Joint));meshes=list(body.GetChild('Collisions').GetAllChildren());handle=min(meshes,key=lambda p:((mesh_center(p)-base)@Rbase)[0]);p0=mesh_center(handle);j=UsdPhysics.Joint(jp);b0=s.GetPrimAtPath(j.GetBody0Rel().GetTargets()[0]);anchor=world(b0)*se3(j.GetLocalPos0Attr().Get(),j.GetLocalRot0Attr().Get());axis=anchor.rotation@np.eye(3)['XYZ'.index(jp.GetAttribute('physics:axis').Get())];axis/=np.linalg.norm(axis);end=float(jp.GetAttribute('physics:upperLimit').Get())*.75
  amounts=np.linspace(-end,0,21) if ti==9 else np.linspace(0,end,21)
  # T9 USD starts 75% open: move from that authored state toward closed.
  if ti==9:amounts=np.linspace(0,-end,21)
  positions=np.array([p0+v*axis for v in amounts]);rotations=[np.eye(3)]*len(amounts);Rtool=np.array([[0,0,-1],[0,1,0],[1,0,0]],float);scope='frontmost drawer bar collider, 75% slide travel'
 else:
  handle=next(p for p in Usd.PrimRange(fixture) if p.GetName()==('door_handle_main' if ti==5 else 'knob_center_main'));p0=mesh_center(handle);jp=next(p for p in Usd.PrimRange(fixture) if p.GetName()==('microjoint' if ti==5 else 'knob_center_joint'));j=UsdPhysics.Joint(jp);b0=s.GetPrimAtPath(j.GetBody0Rel().GetTargets()[0]);anchor=world(b0)*se3(j.GetLocalPos0Attr().Get(),j.GetLocalRot0Attr().Get());axis=anchor.rotation@np.eye(3)['XYZ'.index(jp.GetAttribute('physics:axis').Get())];axis/=np.linalg.norm(axis);amounts=np.linspace(0,np.deg2rad(75 if ti==5 else 90),21);rotations=[pin.exp3(axis*a) for a in amounts];positions=np.array([anchor.translation+rot@(p0-anchor.translation) for rot in rotations]);Rtool=np.array([[0,0,-1],[1,0,0],[0,-1,0]],float) if ti==5 else np.eye(3);scope='named collision mesh centre; 75 deg door / 90 deg knob; nominal grasp orientation'
 if ti==5:
  lo,hi=np.array(meta['fixtures'][0]['aabb']);centre=(lo+hi)/2;normal=p0-centre;normal[2]=0;normal/=np.linalg.norm(normal);approach=-normal;closing=np.cross(approach,np.array([0.,0,1.]));closing/=np.linalg.norm(closing);Rworld=np.column_stack([closing,np.cross(-approach,closing),-approach]);Rtool=Rbase.T@Rworld
 best=None
 for side in ['left','right']:
  ids=np.array([r.model.joints[r.model.getJointId(f'{side}_arm_{i}')].idx_q for i in range(7)])
  for symmetry,tilt in [(v,t) for v in [1,-1] for t in [0,-.5,.5,-1.,1.]]:
   q=r.q_from_dict(READY);errors=[];qs=[]
   for p,rot in zip(positions,rotations):
    target=pin.SE3(Rbase.T@rot@Rbase@Rtool@pin.rpy.rpyToMatrix(0,tilt,0)@np.diag([symmetry,symmetry,1]),Rbase.T@(p-base));cand=solve_arm(r,side,target,q,150)
    if cand[1]>.01 or cand[2]>np.deg2rad(5):
     for _ in range(8):
      seed=q.copy();seed[ids]=rng.uniform(r.model.lowerPositionLimit[ids]+1e-4,r.model.upperPositionLimit[ids]-1e-4);a=solve_arm(r,side,target,seed,150)
      if a[1]+.15*a[2]<cand[1]+.15*cand[2]:cand=a
      if cand[1]<.01 and cand[2]<np.deg2rad(5):break
    q,pe,re=cand;errors.append([pe,re]);qs.append(q.copy())
   a=np.array(errors);valid=(a[:,0]<.01)&(a[:,1]<np.deg2rad(5));score=valid.mean()-.1*np.mean(a[:,0])
   if best is None or score>best[0]:best=(score,side,symmetry,tilt,a,valid,np.array(qs))
 _,side,symmetry,tilt,a,valid,qs=best
 rec={'Task':f'T{ti}','joint':str(jp.GetPath()),'handle_mesh':str(handle.GetPath()),'scope':scope,'tested_waypoints':len(a),'reachable_waypoints':int(valid.sum()),'arm':side,'gripper_symmetry':symmetry,'grasp_tilt_rad':tilt,'max_position_error_m':float(a[:,0].max()),'max_orientation_error_deg':float(np.rad2deg(a[:,1].max())),'max_joint_step_rad':float(np.abs(np.diff(qs,axis=0)).max()),'collision_checked':False,'contact_checked':False,'task_success_checked':False};out.append(rec);print(rec,flush=True);existing=json.loads((ROOT/'reports/fixture_sweep_audit.json').read_text()) if (ROOT/'reports/fixture_sweep_audit.json').exists() else [];merged={v['Task']:v for v in existing};merged.update({v['Task']:v for v in out});(ROOT/'reports/fixture_sweep_audit.json').write_text(json.dumps(sorted(merged.values(),key=lambda v:int(v['Task'][1:])),indent=2))
