"""Restore every object and fixture in the 50-episode source inventory per task."""
import project_paths as paths
import json
import numpy as np
from pathlib import Path
from pxr import Usd,UsdGeom,UsdPhysics,Gf
ROOT=Path(str(paths.ROOT))
ALIASES={
1:{'akita_black_bowl':'bowl'},2:{'cookies':'cookie_box','bowl_target':'bowl','bowl':'distractor_bowl'},
3:{'alphabet_soup':'soup'},4:{'akita_black_bowl_front':'front_bowl','akita_black_bowl_middle':'middle_bowl','akita_black_bowl_back':'back_bowl'},
7:{'akita_black_bowl':'bowl'},8:{'akita_black_bowl_front':'front_bowl','akita_black_bowl_middle':'middle_bowl','akita_black_bowl_back':'back_bowl'},9:{'akita_black_bowl':'bowl'}}
def complete(s,ti,objects,fixtures,table,scene,base,bound,move_bottom,add_obj,set_matrix):
 source=json.loads((ROOT/'reports/source_scene_inventory.json').read_text())[f'T{ti}'];aliases=ALIASES.get(ti,{})
 byname={o['name']:o for o in objects};pending=[];mapping=[]
 for name,cfg in source['objects'].items():
  alias=aliases.get(name,name)
  if alias in byname:
   o=byname[alias];o['source_name']=name;mapping.append({'kind':'object','source_name':name,'prim':o['prim'],'restored':False});continue
  asset=cfg['info']['name'];scale=float(cfg.get('object_scale',1))*float(cfg['info'].get('scale',1))
  o=add_obj(s,name,asset,0,0,.72,scale);o['source_name']=name;objects.append(o);byname[name]=o
  pending.append(('object',o,np.array([.60,0.])));mapping.append({'kind':'object','source_name':name,'prim':o['prim'],'restored':True})
 existing_fixture_paths={f['prim'] for f in fixtures};object_paths={o['prim'] for o in objects}
 for name,cfg in source['fixtures'].items():
  p=s.GetPrimAtPath(str(scene.GetPath())+'/'+name);assert p,name
  if cfg['cls']=='Table':
   # Existing standardized 0.72 m worktable represents this source table.
   mapping.append({'kind':'fixture','source_name':name,'prim':str(table.GetPath()),'restored':False,'adaptation':'0.72m standardized table; layout 2 uses the documented flat replacement'});continue
  if str(p.GetPath()) in existing_fixture_paths or str(p.GetPath()) in object_paths:
   mapping.append({'kind':'fixture','source_name':name,'prim':str(p.GetPath()),'restored':False});continue
  was_active=p.IsActive();p.SetActive(True);UsdGeom.Imageable(p).MakeVisible();lo,hi=bound(p);size=hi-lo
  f={'name':name,'source_name':name,'prim':str(p.GetPath()),'aabb':[lo.tolist(),hi.tolist()]}
  # Background cabinets, TV, walls and floor remain in their original location.
  tabletop=cfg['cls'] in ['StorageFurniture','Stovetop','WineRack','Ketchup','Microwave'] and max(size)<1.0
  if tabletop:
   centre=(lo+hi)/2;preferred=np.array([base[1]-centre[1],centre[0]-base[0]])
   fixtures.append(f);pending.append(('fixture',f,preferred))
   if cfg['cls']=='StorageFurniture':
    turn=Gf.Matrix4d().SetTranslate(Gf.Vec3d(*(-centre)))*Gf.Matrix4d().SetRotate(Gf.Rotation(Gf.Vec3d(0,0,1),-90))*Gf.Matrix4d().SetTranslate(Gf.Vec3d(*centre));set_matrix(p,UsdGeom.Xformable(p).GetLocalTransformation()*turn)
   if cfg['cls']=='Ketchup':
    for j in Usd.PrimRange(p):
     if j.GetTypeName()=='PhysicsFixedJoint' and not UsdPhysics.Joint(j).GetBody0Rel().GetTargets():j.SetActive(False)
  mapping.append({'kind':'fixture','source_name':name,'prim':str(p.GetPath()),'restored':not was_active,'background':not tabletop})
 # Pack new props on the table, respecting every existing task-object footprint.
 def rect(p):
  lo,hi=bound(p);return np.array([base[1]-hi[1],lo[0]-base[0]]),np.array([base[1]-lo[1],hi[0]-base[0]])
 tl,th=rect(table);pending_paths={v[1]['prim'] for v in pending};occupied=[]
 for o in objects+fixtures:
  if o['prim'] not in pending_paths:occupied.append((*rect(s.GetPrimAtPath(o['prim'])),o['name']))
 pending.sort(key=lambda v: -np.prod(rect(s.GetPrimAtPath(v[1]['prim']))[1]-rect(s.GetPrimAtPath(v[1]['prim']))[0]))
 for kind,o,preferred in pending:
  p=s.GetPrimAtPath(o['prim']);lo,hi=rect(p);half=(hi-lo)/2;edge=.015;gap=.018
  xs=np.arange(tl[0]+half[0]+edge,th[0]-half[0]-edge+.001,.0125);ys=np.arange(tl[1]+half[1]+edge,th[1]-half[1]-edge+.001,.0125)
  candidates=sorted((np.array([x,y]) for x in xs for y in ys),key=lambda c:np.linalg.norm(c-preferred))
  chosen=None
  for c in candidates:
   a,b=c-half,c+half
   if all(np.any(b+gap<=ol) or np.any(a-gap>=oh) for ol,oh,_ in occupied):chosen=c;break
  if chosen is None:raise RuntimeError(f'T{ti}: no nonoverlapping table placement for {o["name"]}; occupied={occupied}')
  move_bottom(p,np.array([base[0]+chosen[1],base[1]-chosen[0]]),.722);lo,hi=bound(p);o['aabb']=[lo.tolist(),hi.tolist()];o['center']=((lo+hi)/2).tolist();o['restored_from_source_inventory']=True
  occupied.append((*rect(p),o['name']))
 # Existence, activation, visibility and mesh presence are mandatory.
 for row in mapping:
  p=s.GetPrimAtPath(row['prim']);assert p and p.IsActive(),row
  visible=UsdGeom.Imageable(p).ComputeVisibility()!=UsdGeom.Tokens.invisible
  has_geometry=any(q.IsA(UsdGeom.Mesh) or q.IsA(UsdGeom.Cube) for q in Usd.PrimRange(p))
  assert visible and has_geometry,(row,visible,has_geometry)
  row.update(active=True,visible=True,has_geometry=True)
 return {'Task':f'T{ti}','source_episodes_checked':source['episodes_checked'],'source_object_count':len(source['objects']),'source_fixture_count':len(source['fixtures']),'missing':[],'mapping':mapping,'scope':'all object/fixture identities across 50 source episodes; deterministic RB-Y1 placements, not exact episode reconstruction'}
