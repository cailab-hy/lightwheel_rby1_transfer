"""Exercise live state adapters in all ten stages; no demonstrated manipulation claim."""
import project_paths as paths
paths.prepare_assets()

import argparse, json

p = argparse.ArgumentParser()
p.add_argument("--tasks", nargs="+", default=[f"T{i}" for i in range(1, 11)])
a = p.parse_args()
from isaacsim import SimulationApp

app = SimulationApp({"headless": True, "width": 640, "height": 480})
import numpy as np
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation
from isaacsim.core.utils.stage import open_stage
from isaacsim.core.utils.types import ArticulationAction
from success_original import OriginalSuccess, ROOT
from replay_success_original import check_live_mapping

results = []
try:
    for task in a.tasks:
        World.clear_instance()
        m = json.loads((ROOT / f"environments/T{int(task[1:]):02}.json").read_text())
        open_stage(str(ROOT / m["usd"]))
        for _ in range(5):
            app.update()
        w = World(physics_dt=0.01, rendering_dt=0.02)
        robot = w.scene.add(SingleArticulation("/World/Robot", name="robot"))
        success = OriginalSuccess(w, m)
        w.reset()
        success.initialize()
        q = np.array([m["ready_arm_joint_radians"].get(n, 0) for n in robot.dof_names])
        robot.set_joint_positions(q)
        robot.apply_action(ArticulationAction(joint_positions=q))
        for _ in range(100):
            w.step(render=False)
        success.reset()
        for _ in range(60):
            for _ in range(2):
                w.step(render=False)
            success.update()
        record = {
            "task": task,
            "initial_predicate": success.raw_predicate,
            "initial_success_original": success.ever_success,
            "mapping": success.mapping,
            "snapshot": success.snapshot(),
        }
        assert not success.ever_success, (task, "initial scene already successful")
        record["synthetic_state_checks"] = check_live_mapping(record)
        results.append(record)
        print(
            "SUCCESS_ADAPTER",
            task,
            success.raw_predicate,
            success.ever_success,
            flush=True,
        )
        (ROOT / "reports/success_original_live.json").write_text(
            json.dumps(results, indent=2)
        )
        w.stop()
except BaseException:
    import traceback

    traceback.print_exc()
    raise
finally:
    app.close()
