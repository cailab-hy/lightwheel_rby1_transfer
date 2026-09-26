"""Render existing task scenes without changing their USD files or task state."""
import project_paths as paths
paths.prepare_assets()
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--tasks', nargs='+', type=int, default=list(range(1, 11)))
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/front_views'
OUT.mkdir(parents=True, exist_ok=True)
from isaacsim import SimulationApp
app = SimulationApp({'headless': True, 'width': 1280, 'height': 800, 'renderer': 'RayTracedLighting'})
import numpy as np
import omni.usd
import omni.replicator.core as rep
from isaacsim.core.utils.stage import open_stage
from pxr import Gf, UsdGeom
from PIL import Image

records = []
try:
    for ti in args.tasks:
        source = ROOT / f'environments/T{ti:02d}.usd'
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        open_stage(str(source))
        for _ in range(30):
            app.update()
        stage = omni.usd.get_context().get_stage()
        stage.SetEditTarget(stage.GetSessionLayer())
        from front_camera import author_front_camera, EYE, TARGET
        cam = author_front_camera(stage)
        eye, target = list(EYE), list(TARGET)
        rp = rep.create.render_product(str(cam.GetPath()), (1280, 800))
        rgb = rep.AnnotatorRegistry.get_annotator('rgb')
        rgb.attach([rp])
        for _ in range(80):
            app.update()
        rep.orchestrator.step(rt_subframes=16, delta_time=0.0, pause_timeline=True)
        data = np.asarray(rgb.get_data())
        assert data.shape[:2] == (800, 1280), data.shape
        path = OUT / f'T{ti:02d}_front.png'
        Image.fromarray(data[..., :3]).save(path)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        records.append({'task': f'T{ti}', 'image': str(path), 'source': str(source), 'source_sha256': digest, 'eye': eye, 'target': target, 'resolution': [1280, 800], 'physics': 'authored initial scene; timeline not advanced'})
        print('RENDERED', path, flush=True)
        rgb.detach([rp.path])
        rp.destroy()
    (OUT / ('render_manifest_' + '_'.join(map(str, args.tasks)) + '.json')).write_text(json.dumps(records, indent=2))
except BaseException:
    import traceback
    traceback.print_exc()
    raise
finally:
    app.close()
