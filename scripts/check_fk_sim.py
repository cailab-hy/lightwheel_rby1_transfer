import project_paths as paths
paths.prepare_assets()
from isaacsim import SimulationApp
app=SimulationApp({'headless':True})
import sys,json,numpy as np
from pathlib import Path
from pxr import UsdGeom,Usd,Gf
import omni.usd
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.stage import open_stage
from isaacsim.core.utils.types import ArticulationAction
from kinematics import build_rby,READY
ROOT=Path(str(paths.ROOT));r=build_rby();open_stage(str(ROOT/'environments/T01.usd'))
for _ in range(5):app.update()
w=World(physics_dt=.01,rendering_dt=.02);robot=w.scene.add(SingleArticulation(prim_path='/World/Robot',name='rby1'));w.reset();q=np.array([READY.get(n,0) for n in robot.dof_names]);robot.set_joint_positions(q);robot.apply_action(ArticulationAction(joint_positions=q))
for _ in range(20):w.step(render=True)
r.fk(r.q_from_dict(dict(zip(robot.dof_names,robot.get_joint_positions()))));stage=omni.usd.get_context().get_stage();base=UsdGeom.Xformable(stage.GetPrimAtPath('/World/Robot')).ComputeLocalToWorldTransform(Usd.TimeCode.Default());out=[]
for side in ['left','right']:
 ee=stage.GetPrimAtPath(f'/World/Robot/{side}_gripper/ee_{side}');m=UsdGeom.Xformable(ee).ComputeLocalToWorldTransform(Usd.TimeCode.Default())*base.GetInverse();actual=np.array(m.Transform(Gf.Vec3d(0,0,-.1045)));pred=r.pose(side).translation;error=float(np.linalg.norm(actual-pred));out.append({'arm':side,'sim_tcp_robot_frame':actual.tolist(),'pinocchio_tcp_robot_frame':pred.tolist(),'error_m':error});assert error<.002,(side,error)
(ROOT/'reports/fk_sim_validation.json').write_text(json.dumps(out,indent=2));print('FK_SIM_VALIDATED',out,flush=True);app.close()
