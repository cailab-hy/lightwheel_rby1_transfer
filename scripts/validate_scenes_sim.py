import project_paths as paths
paths.prepare_assets()
import argparse,json
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--tasks',nargs='+',type=int,default=list(range(1,11)));args=parser.parse_args()
from isaacsim import SimulationApp
app=SimulationApp({'headless':True,'width':960,'height':720,'renderer':'RayTracedLighting'})
import numpy as np
import omni.usd
import omni.replicator.core as rep
from pxr import Usd,UsdGeom,UsdPhysics,Gf
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.stage import open_stage
from isaacsim.core.utils.types import ArticulationAction
from PIL import Image
ROOT=Path(str(paths.ROOT));reports=[]
for ti in args.tasks:
 try:
  World.clear_instance();open_stage(str(ROOT/f'environments/T{ti:02d}.usd'))
  for _ in range(8):app.update()
  w=World(physics_dt=1/100,rendering_dt=1/50,stage_units_in_meters=1)
  robot=w.scene.add(SingleArticulation(prim_path='/World/Robot',name='rby1'))
  w.reset();names=robot.dof_names;meta=json.loads((ROOT/f'environments/T{ti:02d}.json').read_text());q=np.array([meta['ready_arm_joint_radians'].get(n,0.) for n in names]);robot.set_joint_positions(q);robot.apply_action(ArticulationAction(joint_positions=q))
  for _ in range(100):w.step(render=True)
  measured=robot.get_joint_positions();armids=[j for j,n in enumerate(names) if '_arm_' in n];gripids=[j for j,n in enumerate(names) if 'finger' in n];rec={'Task':f'T{ti}','dof_names':names,'initial_target':q.tolist(),'position_after_1s':measured.tolist(),'max_arm_joint_drift_rad':float(np.max(np.abs(q[armids]-measured[armids]))),'max_gripper_joint_drift_m':float(np.max(np.abs(q[gripids]-measured[gripids]))),'finite':bool(np.isfinite(measured).all())}
  camera='/World/Robot/link_head_2/first_person_camera';rp=rep.create.render_product(camera,(640,480));rgb=rep.AnnotatorRegistry.get_annotator('rgb');rgb.attach([rp])
  for _ in range(8):w.step(render=True)
  data=rgb.get_data()
  if data.size:
   Image.fromarray(np.asarray(data)[...,:3]).save(ROOT/f'reports/T{ti:02d}_head.png');rec['head_render']=True
  else:rec['head_render']=False
  rgb.detach([rp.path]);rp.destroy()
  rp=rep.create.render_product('/World/OverviewCamera',(960,720));rgb=rep.AnnotatorRegistry.get_annotator('rgb');rgb.attach([rp])
  for _ in range(8):w.step(render=True)
  overview=rgb.get_data()
  if overview.size:Image.fromarray(np.asarray(overview)[...,:3]).save(ROOT/f'reports/T{ti:02d}_overview.png')
  rec['overview_render']=bool(overview.size);rgb.detach([rp.path]);rp.destroy()
  # Inspect settled object transforms so falls through the table cannot look like success.
  stage=omni.usd.get_context().get_stage();rec['object_world_positions']={}
  for o in meta['objects']:
   bodies=[p for p in Usd.PrimRange(stage.GetPrimAtPath(o['prim'])) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
   rec['object_world_positions'][o['name']]={str(p.GetPath()):list(UsdGeom.Xformable(p).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).ExtractTranslation()) for p in bodies}
  reports.append(rec);print('SCENE_VALIDATED',json.dumps(rec),flush=True);w.stop()
 except Exception as e:
  import traceback;traceback.print_exc();reports.append({'Task':f'T{ti}','error':str(e)})
 (ROOT/'reports/sim_scene_checks.json').write_text(json.dumps(reports,indent=2))
app.close()
