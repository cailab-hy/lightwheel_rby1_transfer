"""Kinematics from authored USD joint frames; no joint-name correspondence assumption."""
import project_paths as paths
import sys
sys.path.insert(0,str(paths.ROOT / 'usd_deps'))
import numpy as np
import pinocchio as pin
from pxr import Usd,UsdGeom,UsdPhysics

def se3(pos,quat):
 q=np.array([*quat.GetImaginary(),quat.GetReal()],dtype=float);q/=np.linalg.norm(q)
 return pin.SE3(pin.Quaternion(q).matrix(),np.array(pos,dtype=float))

def world(prim):
 a=np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()),dtype=float).T
 return pin.SE3(a[:3,:3],a[:3,3])

class USDModel:
 def __init__(self,path):
  self.stage=Usd.Stage.Open(str(path));self.model=pin.Model();self.body={};self.frame={};self.prims={};self.joints={}
  joints=[]
  for p in self.stage.Traverse():
   if not p.IsA(UsdPhysics.Joint):continue
   j=UsdPhysics.Joint(p);b0=j.GetBody0Rel().GetTargets();b1=j.GetBody1Rel().GetTargets()
   if not b1:continue
   joints.append((p,str(b0[0]) if b0 else None,str(b1[0])))
  children={b1 for _,_,b1 in joints};parents={b0 for _,b0,_ in joints if b0}
  roots=parents-children
  for p,b0,b1 in joints:
   if b0 is None:roots.add(b1)
  for r in roots:self.body[r]=(0,pin.SE3.Identity())
  pending=[x for x in joints if x[1] is not None]
  while pending:
   nxt=[]
   for p,b0,b1 in pending:
    if b0 not in self.body:nxt.append((p,b0,b1));continue
    j=UsdPhysics.Joint(p);t0=se3(j.GetLocalPos0Attr().Get(),j.GetLocalRot0Attr().Get());t1=se3(j.GetLocalPos1Attr().Get(),j.GetLocalRot1Attr().Get())
    parent,pf=self.body[b0];place=pf*t0
    typ=p.GetTypeName();name=p.GetName()
    if typ in ['PhysicsRevoluteJoint','PhysicsPrismaticJoint']:
     axis=p.GetAttribute('physics:axis').Get() or 'X';vec=np.eye(3)['XYZ'.index(axis)]
     jm=pin.JointModelRevoluteUnaligned(vec) if typ=='PhysicsRevoluteJoint' else pin.JointModelPrismaticUnaligned(vec)
     ji=self.model.addJoint(parent,jm,place,name)
     lo=p.GetAttribute('physics:lowerLimit').Get();hi=p.GetAttribute('physics:upperLimit').Get();scale=np.pi/180 if typ=='PhysicsRevoluteJoint' else 1
     self.model.lowerPositionLimit[self.model.joints[ji].idx_q]=(lo if lo is not None else -np.inf)*scale
     self.model.upperPositionLimit[self.model.joints[ji].idx_q]=(hi if hi is not None else np.inf)*scale
     self.body[b1]=(ji,t1.inverse());self.joints[name]=p
    else:self.body[b1]=(parent,place*t1.inverse())
   if len(nxt)==len(pending):raise RuntimeError('Disconnected joint graph '+str(nxt))
   pending=nxt
  for path,(ji,pf) in self.body.items():
   self.frame[path]=self.model.addFrame(pin.Frame(path,ji,pf,pin.FrameType.OP_FRAME))
  self.data=self.model.createData()
 def add_frame(self,name,body_path,offset):
  ji,pf=self.body[body_path];self.frame[name]=self.model.addFrame(pin.Frame(name,ji,pf*offset,pin.FrameType.OP_FRAME));self.data=self.model.createData()
 def q_from_dict(self,values):
  q=pin.neutral(self.model)
  for n,v in values.items():
   if self.model.existJointName(n):q[self.model.joints[self.model.getJointId(n)].idx_q]=v
  return q
 def fk(self,q):pin.framesForwardKinematics(self.model,self.data,q)
 def pose(self,name):return self.data.oMf[self.frame[name]].copy()

RBY=str(paths.RBY_SIM / 'assets/generated/rby1_ready_reach_table.usd')
X7=str(paths.BENCHHUB / 'lw_benchhub/data/assets/x7s.usd')
READY={**{f'left_arm_{i}':np.deg2rad(v) for i,v in enumerate([15,65,15,-115,-75,-65,-5])},**{f'right_arm_{i}':np.deg2rad(v) for i,v in enumerate([15,-65,-15,-115,75,-65,-5])}}

def build_rby():
 r=USDModel(RBY)
 for side in ['left','right']:
  body=f'/RBY1/{side}_gripper/ee_{side}'
  # CAD finger surfaces span z=-0.0735..-0.1355 m; use their mid-depth.
  r.add_frame(side,body,pin.SE3(np.eye(3),np.array([0,0,-0.1045])))
 return r

def build_x7():
 r=USDModel(X7)
 for side in ['left','right']:
  paths=[p for p in r.body if p.endswith(f'/{side}_hand_link')]
  r.add_frame(side,paths[0],pin.SE3(np.eye(3),np.array([0.16735,0,0])))
 return r

def solve_arm(r,side,target,q,max_iters=35):
 ids=np.array([r.model.joints[r.model.getJointId(f'{side}_arm_{i}')].idx_v for i in range(7)])
 fid=r.frame[side];q=q.copy();lo=r.model.lowerPositionLimit[ids]+1e-5;hi=r.model.upperPositionLimit[ids]-1e-5
 for _ in range(max_iters):
  pin.computeJointJacobians(r.model,r.data,q);pin.updateFramePlacements(r.model,r.data)
  cur=r.data.oMf[fid];ep=target.translation-cur.translation;er=pin.log3(target.rotation@cur.rotation.T)
  if np.linalg.norm(ep)<0.001 and np.linalg.norm(er)<0.01:break
  J=pin.getFrameJacobian(r.model,r.data,fid,pin.LOCAL_WORLD_ALIGNED)[:,ids].copy();e=np.r_[ep,er];J[3:]*=.15;e[3:]*=.15
  dq=J.T@np.linalg.solve(J@J.T+np.eye(6)*1e-5,e)
  q[ids]=np.clip(q[ids]+np.clip(dq,-.18,.18),lo,hi)
 r.fk(q);cur=r.pose(side)
 return q,float(np.linalg.norm(target.translation-cur.translation)),float(np.linalg.norm(pin.log3(target.rotation@cur.rotation.T)))

if __name__=='__main__':
 for name,r in [('rby',build_rby()),('x7',build_x7())]:
  q=r.q_from_dict(READY if name=='rby' else {'body_z_joint':.5});r.fk(q)
  print(name,r.model.names.tolist(),r.model.nq)
  for side in ['left','right']:print(side,r.pose(side))
