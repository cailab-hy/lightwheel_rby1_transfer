"""Build 10 explicit RB-Y1 scene adaptations. Source demonstrations are not scene states."""
import project_paths as paths
paths.prepare_assets()
import json,sys
from pathlib import Path
import numpy as np
from kinematics import build_rby,READY,world
from pxr import Usd,UsdGeom,UsdPhysics,UsdLux,Gf,Sdf
ROOT=Path(str(paths.ROOT));OUT=ROOT/'environments';OUT.mkdir(exist_ok=True)
CACHE=paths.ASSET_LINKS/'lightwheel'
RBY=str(paths.ASSET_LINKS/'rby1/assets/generated/rby1_ready_reach_table.usd')
BASE=np.array([2.44,-1.43,0.]);YAW=-np.pi/2
def matrix(t):return Gf.Matrix4d(*np.asarray(t.homogeneous).T.ravel().tolist())
def set_matrix(p,m):
 x=UsdGeom.Xformable(p);x.ClearXformOpOrder();x.AddTransformOp(opSuffix='rby1_adaptation').Set(m)
def bound(p):
 b=UsdGeom.BBoxCache(Usd.TimeCode.Default(),['default','render','proxy']).ComputeWorldBound(p).ComputeAlignedRange()
 return np.array(b.GetMin()),np.array(b.GetMax())
def xyz(x,y,z):return np.array([BASE[0]+y,BASE[1]-x,z])
def move_bottom(p,center_xy,z):
 lo,hi=bound(p);delta=np.r_[center_xy-(lo[:2]+hi[:2])/2,z-lo[2]]
 m=UsdGeom.Xformable(p).GetLocalTransformation()*Gf.Matrix4d().SetTranslate(Gf.Vec3d(*delta));set_matrix(p,m)
def add_obj(s,name,asset,x,y,surface=.72,scale=1):
 path=CACHE/f'object/{asset}/{asset}.usd';assert path.exists(),path
 p=s.DefinePrim('/World/Objects/'+name,'Xform');p.GetReferences().AddReference(str(path))
 for j in Usd.PrimRange(p):
  if j.GetTypeName()=='PhysicsFixedJoint' and not UsdPhysics.Joint(j).GetBody0Rel().GetTargets():j.SetActive(False)
 if not any(j.HasAPI(UsdPhysics.RigidBodyAPI) for j in Usd.PrimRange(p)):
  UsdPhysics.RigidBodyAPI.Apply(p).CreateRigidBodyEnabledAttr().Set(True)
  UsdPhysics.MassAPI.Apply(p).CreateMassAttr().Set(.15)
  for mesh in Usd.PrimRange(p):
   if mesh.IsA(UsdGeom.Mesh):
    UsdPhysics.CollisionAPI.Apply(mesh)
    UsdPhysics.MeshCollisionAPI.Apply(mesh).CreateApproximationAttr().Set('convexDecomposition')
 set_matrix(p,Gf.Matrix4d().SetScale(Gf.Vec3d(scale)));move_bottom(p,xyz(x,y,0)[:2],surface+.002)
 lo,hi=bound(p)
 return {'name':name,'asset':str(path),'prim':str(p.GetPath()),'aabb':[lo.tolist(),hi.tolist()],'center':((lo+hi)/2).tolist()}

def main():
 r=build_rby();q=r.q_from_dict(READY);r.fk(q)
 robot=r.stage
 # Repair empty axis token explicitly to USD schema's X default.
 robot.GetRootLayer() # original file is never saved or edited
 camera=robot.GetPrimAtPath('/RBY1/link_head_2/first_person_camera');cam=world(camera)
 origin=cam.translation;direction=cam.rotation@np.array([0,0,-1]);hit=origin+(.72-origin[2])/direction[2]*direction
 allmeta=[];inventory_audits=[]
 for i,row in enumerate(json.loads((ROOT/'selection.json').read_text())):
  ti=i+1;path=OUT/f'T{ti:02d}.usd';s=Usd.Stage.CreateNew(str(path));root=s.DefinePrim('/World','Xform');s.SetDefaultPrim(root);UsdGeom.SetStageUpAxis(s,UsdGeom.Tokens.z);UsdGeom.SetStageMetersPerUnit(s,1)
  layout=row['LIBERO 레이아웃 번호'];scene=s.DefinePrim('/World/Scene','Xform');scene.GetReferences().AddReference(str(CACHE/f'floorplan/robocasa-{layout}/scene.usd'))
  table=next(p for p in scene.GetAllChildren() if 'table_' in p.GetName());lo,hi=bound(table);old_height=float(hi[2]);ratio=.72/old_height
  m=UsdGeom.Xformable(table).GetLocalTransformation()*Gf.Matrix4d().SetScale(Gf.Vec3d(1,1,ratio));set_matrix(table,m)
  if layout=='libero-2-2':
   # The oval source table's visual bounds and contact surface differ in height.
   # Replace it with an explicit flat worktable whose collision top is exactly .72 m.
   table.SetActive(False);table=s.DefinePrim('/World/Worktable','Xform')
   def cube(name,center,size):
    c=UsdGeom.Cube.Define(s,f'/World/Worktable/{name}');c.CreateSizeAttr().Set(1);c.CreateDisplayColorAttr().Set([Gf.Vec3f(.48,.27,.12)])
    set_matrix(c.GetPrim(),Gf.Matrix4d().SetScale(Gf.Vec3d(*size))*Gf.Matrix4d().SetTranslate(Gf.Vec3d(*center)));UsdPhysics.CollisionAPI.Apply(c.GetPrim())
   cube('top',xyz(.75,0,.7025),(1.4,.8,.035))
   for a in [-.62,.62]:
    for b in [.42,1.08]:cube(f'leg_{a}_{b}'.replace('-','m').replace('.','_'),xyz(b,a,.3425),(.05,.05,.685))
  fixtures=[]
  def fixture(prefix,x,y):
   p=next(p for p in scene.GetAllChildren() if p.GetName().startswith(prefix));p.SetActive(True);move_bottom(p,xyz(x,y,0)[:2],.722)
   if prefix=='storage_furniture':
    lo,hi=bound(p);c=(lo+hi)/2
    turn=Gf.Matrix4d().SetTranslate(Gf.Vec3d(*(-c)))*Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0,0,1),-90))*Gf.Matrix4d().SetTranslate(Gf.Vec3d(*c))
    set_matrix(p,UsdGeom.Xformable(p).GetLocalTransformation()*turn)
   lo,hi=bound(p);f={'name':prefix,'prim':str(p.GetPath()),'aabb':[lo.tolist(),hi.tolist()]};fixtures.append(f);return p
  objects=[]
  def obj(name,asset,x,y,z=.72,scale=1):
   o=add_obj(s,name,asset,x,y,z,scale);objects.append(o);return o
  if ti==1:obj('bowl','Bowl008',.53,.19);obj('plate','Plate012',.60,-.17)
  elif ti==2:
   c=obj('cookie_box','Cookies002',.60,.18);obj('bowl','Bowl008',.60,.18,c['aabb'][1][2],scale=.6);obj('plate','Plate012',.54,-.20,scale=.8);obj('distractor_bowl','Bowl008',.83,-.15,scale=.6)
  elif ti==3:
   kp=fixture('ketchup',.48,.24);fixtures.pop()
   for j in Usd.PrimRange(kp):
    if j.GetTypeName()=='PhysicsFixedJoint' and not UsdPhysics.Joint(j).GetBody0Rel().GetTargets():j.SetActive(False)
   lo,hi=bound(kp);objects.append({'name':'ketchup','asset':'original layout ketchup fixture','prim':str(kp.GetPath()),'aabb':[lo.tolist(),hi.tolist()],'center':((lo+hi)/2).tolist()})
   obj('basket','Basket058',.60,-.20,scale=.85);obj('soup','AlphabetSoup001',.70,.20,scale=.8)
  elif ti==4:fixture('storage_furniture',.60,0);obj('front_bowl','Bowl008',.48,-.27,scale=.8);obj('middle_bowl','Bowl008',.68,-.27,scale=.8);obj('back_bowl','Bowl008',.88,-.27,scale=.8)
  elif ti==5:fixture('microwave',.56,-.25);obj('plate','Plate012',.55,.35)
  elif ti==6:fixture('stovetop',.60,0)
  elif ti==7:fixture('storage_furniture',.65,-.13);obj('bowl','Bowl008',.49,.22,scale=.8)
  elif ti==8:
   obj('front_bowl','Bowl008',.44,-.23,scale=.8);obj('middle_bowl','Bowl008',.53,0,scale=.8);obj('back_bowl','Bowl008',.62,.23,scale=.8);obj('plate','Plate012',.85,-.25)
  elif ti==9:
   p=fixture('storage_furniture',.66,-.12);obj('bowl','Bowl008',.50,.23,scale=.7)
   # Identify the bottom slide by its body height and open it geometrically.
   joints=[j for j in Usd.PrimRange(p) if j.GetTypeName()=='PhysicsPrismaticJoint']
   if joints:
    from kinematics import se3
    def anchor_z(p):
     j=UsdPhysics.Joint(p);return (world(s.GetPrimAtPath(j.GetBody0Rel().GetTargets()[0]))*se3(j.GetLocalPos0Attr().Get(),j.GetLocalRot0Attr().Get())).translation[2]
    joint=min(joints,key=anchor_z);j=UsdPhysics.PrismaticJoint(joint);axis=j.GetAxisAttr().Get();body=s.GetPrimAtPath(j.GetBody1Rel().GetTargets()[0]);amount=float(j.GetUpperLimitAttr().Get())*.75
    # Store an initial target. Runtime initializes articulation DOF to it as well.
    UsdPhysics.DriveAPI.Apply(joint,'linear').CreateTargetPositionAttr().Set(amount)
    joint.CreateAttribute('state:linear:physics:position',Sdf.ValueTypeNames.Float).Set(amount)
    joint.AddAppliedSchema('PhysicsJointStateAPI:linear')
    b0=s.GetPrimAtPath(j.GetBody0Rel().GetTargets()[0]);from kinematics import se3
    direction=(world(b0)*se3(j.GetLocalPos0Attr().Get(),j.GetLocalRot0Attr().Get())).rotation@np.eye(3)['XYZ'.index(axis)];direction/=np.linalg.norm(direction)
    # Convert the world displacement to the parent local frame for nested bodies.
    parent_m=UsdGeom.Xformable(body.GetParent()).ComputeLocalToWorldTransform(Usd.TimeCode.Default());delta=parent_m.GetInverse().TransformDir(Gf.Vec3d(*(direction*amount)))
    set_matrix(body,UsdGeom.Xformable(body).GetLocalTransformation()*Gf.Matrix4d().SetTranslate(delta))
  elif ti==10:obj('alphabet_soup','AlphabetSoup001',.48,.22,scale=.8);obj('tomato_sauce','Ketchup003',.52,0,scale=.8);obj('basket','Basket058',.63,-.22,scale=.85)
  from complete_scene_inventory import complete
  inventory_audits.append(complete(s,ti,objects,fixtures,table,scene,BASE,bound,move_bottom,add_obj,set_matrix))
  # Reposition world anchors together with fixtures, otherwise PhysX snaps them back.
  for p in Usd.PrimRange(scene):
   if p.GetTypeName()!='PhysicsFixedJoint':continue
   j=UsdPhysics.Joint(p)
   if j.GetBody0Rel().GetTargets() or not j.GetBody1Rel().GetTargets():continue
   body=s.GetPrimAtPath(j.GetBody1Rel().GetTargets()[0]);local=Gf.Matrix4d().SetRotate(Gf.Quatd(j.GetLocalRot1Attr().Get()));local.SetTranslateOnly(Gf.Vec3d(j.GetLocalPos1Attr().Get()));anchor=local*UsdGeom.Xformable(body).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
   j.GetLocalPos0Attr().Set(Gf.Vec3f(anchor.ExtractTranslation()));j.GetLocalRot0Attr().Set(Gf.Quatf(anchor.ExtractRotationQuat()))
  rp=s.DefinePrim('/World/Robot','Xform');rp.GetReferences().AddReference(RBY)
  m=Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0,0,1),-90))*Gf.Matrix4d().SetTranslate(Gf.Vec3d(*BASE));set_matrix(rp,m)
  # All links use the exact USD joint graph at the requested arm ready pose.
  for b,(ji,local) in r.body.items():
   old=r.stage.GetPrimAtPath(b);dest=s.GetPrimAtPath(b.replace('/RBY1','/World/Robot',1));parent=old.GetParent()
   pose=r.pose(b)
   if str(parent.GetPath())!='/RBY1':
    parent_world=world(parent);pose=parent_world.inverse()*pose
   set_matrix(dest,matrix(pose))
  for side in ['left','right']:
   for n in range(7):
    p=s.GetPrimAtPath(f'/World/Robot/joints/{side}_arm_{n}')
    if not p.GetAttribute('physics:axis').Get():p.GetAttribute('physics:axis').Set('X')
    angle=float(np.rad2deg(READY[f'{side}_arm_{n}']));d=UsdPhysics.DriveAPI.Apply(p,'angular');d.CreateTargetPositionAttr().Set(angle);d.CreateStiffnessAttr().Set(3000);d.CreateDampingAttr().Set(120);p.CreateAttribute('state:angular:physics:position',Sdf.ValueTypeNames.Float).Set(angle)
    p.AddAppliedSchema('PhysicsJointStateAPI:angular')
   for p in Usd.PrimRange(s.GetPrimAtPath(f'/World/Robot/{side}_gripper')):
    if p.GetTypeName()=='PhysicsPrismaticJoint':
     drive=UsdPhysics.DriveAPI.Apply(p,'linear');drive.CreateTargetPositionAttr().Set(0);drive.CreateStiffnessAttr().Set(2000);drive.CreateDampingAttr().Set(100);drive.CreateMaxForceAttr().Set(50)
  # World-fixed root anchor must follow the robot placement, not remain at origin.
  fixed=UsdPhysics.FixedJoint(s.GetPrimAtPath('/World/Robot/joints/fixed_base'));fixed.GetLocalPos0Attr().Set(Gf.Vec3f(*BASE));fixed.GetLocalRot0Attr().Set(Gf.Quatf(np.cos(YAW/2),0,0,np.sin(YAW/2)))
  physics=UsdPhysics.Scene.Define(s,'/World/Physics');physics.CreateGravityDirectionAttr().Set(Gf.Vec3f(0,0,-1));physics.CreateGravityMagnitudeAttr().Set(9.81)
  light=UsdLux.DomeLight.Define(s,'/World/Light');light.CreateIntensityAttr().Set(800)
  overview=UsdGeom.Camera.Define(s,'/World/OverviewCamera');overview.CreateProjectionAttr().Set('orthographic');overview.CreateHorizontalApertureAttr().Set(22.0);overview.CreateVerticalApertureAttr().Set(16.5);overview.CreateClippingRangeAttr().Set(Gf.Vec2f(.01,100));set_matrix(overview.GetPrim(),Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0,0,1),180))*Gf.Matrix4d().SetTranslate(Gf.Vec3d(2.44,-2.13,4.0)))
  root.CreateAttribute('task:name',Sdf.ValueTypeNames.String).Set(row['Task 이름']);root.CreateAttribute('task:instruction',Sdf.ValueTypeNames.String).Set(row['Language Instruction'])
  from portable_usd import make_layer_portable
  make_layer_portable(s.GetRootLayer())
  s.GetRootLayer().Save()
  lo,hi=bound(table);assert abs(hi[2]-.72)<1e-6
  meta={**row,'usd':str(path),'table_top_m':float(hi[2]),'original_table_top_m':old_height,'robot_base_world':BASE.tolist(),'robot_yaw_rad':YAW,'objects':objects,'fixtures':fixtures,'head_camera_ray_robot_frame':{'origin':origin.tolist(),'direction':direction.tolist(),'table_intersection':hit.tolist(),'real_head_1_deg':-35,'usd_baked_head_1_deg':35},'scene_status':'adapted deterministic task scene; not reconstruction of source episode; dynamics and task success require validation','fixed_robot_joints':['base','torso_0..5','head_0..1'],'ready_arm_joint_radians':READY}
  meta=paths.portable_metadata(meta)
  (OUT/f'T{ti:02d}.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2));allmeta.append(meta);print('SCENE',ti,old_height,hi[2],flush=True)
 (ROOT/'reports/scene_inventory_audit.json').write_text(json.dumps(inventory_audits,ensure_ascii=False,indent=2))
 (ROOT/'reports/scene_manifest.json').write_text(json.dumps(allmeta,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
