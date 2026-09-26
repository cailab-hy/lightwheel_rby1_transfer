import project_paths as paths
import sys,json
sys.path.insert(0,str(paths.ROOT / 'usd_deps'))
from pxr import Usd,UsdGeom,UsdPhysics
from pathlib import Path
out=Path(str(paths.ROOT / 'reports'))
for name,path in [('rby_ready',str(paths.RBY_SIM / 'assets/generated/rby1_ready_reach_table.usd')),('x7s',str(paths.BENCHHUB / 'lw_benchhub/data/assets/x7s.usd'))]+[(f'layout_{i}',f'{paths.LIGHTWHEEL_CACHE}/floorplan/robocasa-libero-{i}-{i}/scene.usd') for i in [1,2,8]]:
 stage=Usd.Stage.Open(path)
 print(name,'default',stage.GetDefaultPrim().GetPath(),flush=True)
 stage.GetRootLayer().Export(str(out/f'{name}_root.usda'))
 records=[]
 bounds=UsdGeom.BBoxCache(Usd.TimeCode.Default(),['default','render','proxy'])
 for p in stage.TraverseAll():
  if p.IsA(UsdPhysics.Joint) or p.IsA(UsdGeom.Camera) or (name.startswith('layout') and p.GetParent()==stage.GetDefaultPrim()):
   r={'path':str(p.GetPath()),'type':p.GetTypeName(),'active':p.IsActive(),'attrs':{a.GetName():str(a.Get()) for a in p.GetAttributes() if a.HasAuthoredValueOpinion()},'rels':{a.GetName():[str(x) for x in a.GetTargets()] for a in p.GetRelationships()}}
   if p.IsA(UsdGeom.Xformable):
    r['world_transform']=str(UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
    b=bounds.ComputeWorldBound(p).ComputeAlignedRange();r['aabb']=[list(b.GetMin()),list(b.GetMax())]
   records.append(r)
 (out/f'{name}_inspection.json').write_text(json.dumps(records,indent=2))
 print('records',len(records),flush=True)
