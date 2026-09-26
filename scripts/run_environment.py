"""Open an adapted RB-Y1 task and report pinned success_original. Holds ready pose."""
import project_paths as paths
paths.prepare_assets()

import argparse, json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--task", default="T1", choices=[f"T{i}" for i in range(1, 11)])
p.add_argument("--headless", action="store_true")
p.add_argument("--steps", type=int, default=0)
a = p.parse_args()
from isaacsim import SimulationApp

app = SimulationApp({"headless": a.headless, "width": 1280, "height": 720})
import numpy as np
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.stage import open_stage
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.core.utils.viewports import set_camera_view
from success_original import OriginalSuccess

ROOT = Path(__file__).resolve().parents[1]
try:
    meta = json.loads((ROOT / f"environments/T{int(a.task[1:]):02}.json").read_text())
    open_stage(str(ROOT / meta["usd"]))
    for _ in range(8):
        app.update()
    world = World(physics_dt=0.01, rendering_dt=0.02, stage_units_in_meters=1)
    robot = world.scene.add(SingleArticulation("/World/Robot", name="rby1"))
    success = OriginalSuccess(world, meta)
    world.reset()
    success.initialize()
    q = np.array([meta["ready_arm_joint_radians"].get(n, 0) for n in robot.dof_names])
    robot.set_joint_positions(q)
    robot.apply_action(ArticulationAction(joint_positions=q))
    set_camera_view(eye=np.array([3.8, -0.4, 2.4]), target=np.array([2.44, -2.05, 0.8]))
    print(meta["Language Instruction"])
    print("success_original active; ready-pose hold, no autonomous policy.", flush=True)
    step = 0
    last = None
    while app.is_running() and (not a.steps or step < a.steps):
        world.step(render=False)
        world.step(render=False)
        world.render()
        result = success.update()
        if result != last:
            print(f"{a.task} step={step} success_original={result}", flush=True)
            last = result
        step += 1
except BaseException:
    import traceback

    traceback.print_exc()
    raise
finally:
    app.close()
