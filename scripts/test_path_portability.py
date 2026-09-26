"""Relocate a checkout and verify composed USD dependencies and executable paths."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import project_paths as paths

sys.path.insert(0, str(paths.ROOT / 'usd_deps'))
from pxr import Sdf, Usd, UsdUtils
from portable_usd import make_layer_portable

records = []
for ti in range(1, 11):
    current = paths.ROOT / f'environments/T{ti:02d}.usd'
    original = paths.ROOT / f'revisions/path_portability_before/environments/T{ti:02d}.usd'
    # Compare every authored field, with only asset paths normalized.
    if original.exists():
        before = Sdf.Layer.CreateAnonymous()
        before.TransferContent(Sdf.Layer.FindOrOpen(str(original)))
        UsdUtils.ModifyAssetPaths(before, lambda a: a.replace(str(paths.LIGHTWHEEL_CACHE), '../.assets/lightwheel').replace(str(paths.RBY_SIM), '../.assets/rby1'))
        after = Sdf.Layer.FindOrOpen(str(current))
        assert before.ExportToString() == after.ExportToString(), current
    stage = Usd.Stage.Open(str(current))
    assert not stage.GetCompositionErrors(), current
    records.append({'task': f'T{ti}', 'prim_count': sum(1 for _ in stage.Traverse())})

with tempfile.TemporaryDirectory(prefix='rby relocation ') as tmp:
    dest = Path(tmp) / 'checkout with spaces'
    dest.mkdir()
    shutil.copytree(paths.ROOT / 'scripts', dest / 'scripts', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(paths.ROOT / 'environments', dest / 'environments')
    for script in ('run_python.sh', 'collect_keyboard.sh', 'collect_t1_keyboard.sh'):
        shutil.copy2(paths.ROOT / script, dest / script)
    env = os.environ.copy()
    env.update(RBY1_SIM_ROOT=str(paths.RBY_SIM), RBY1_LIGHTWHEEL_CACHE=str(paths.LIGHTWHEEL_CACHE), RBY1_ISAACLAB_ROOT=str(paths.ISAACLAB), RBY1_DATASETS_ROOT=str(Path(tmp)/'data with spaces'), RBY1_PYTHON=sys.executable, PYTHONPATH=str(dest/'scripts')+os.pathsep+str(paths.ROOT/'usd_deps'))
    code = '''
import json, os
from pathlib import Path
import project_paths as p
from pxr import Usd, UsdUtils
p.prepare_assets()
assert str(p.ROOT).endswith('checkout with spaces')
assert str(p.DATASETS).endswith('data with spaces')
records=[]
for ti in range(1,11):
 m=p.scene_metadata(ti)
 s=Usd.Stage.Open(m['usd'])
 assert not s.GetCompositionErrors()
 layers, assets, unresolved=UsdUtils.ComputeAllDependencies(m['usd'])
 assert not (set(unresolved) - {'OmniGlass.mdl', 'OmniPBR.mdl'}), unresolved
 assert all(not ref.startswith('/') for layer in layers for ref in layer.GetExternalReferences())
 records.append({'task':f'T{ti}', 'prim_count':sum(1 for _ in s.Traverse()), 'layers':len(layers), 'assets':len(assets), 'isaac_sim_builtin_materials':unresolved})
print(json.dumps(records))
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=tmp, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    relocated = json.loads(result.stdout)
    assert [r['prim_count'] for r in records] == [r['prim_count'] for r in relocated]
    subprocess.run([str(dest/'collect_t1_keyboard.sh'), '--help'], cwd=tmp, env=env, capture_output=True, check=True)
    for row in relocated:
        print(row)
    (paths.ROOT/'reports/path_portability_validation.json').write_text(json.dumps({'authored_scenes_equal_except_paths': True, 'relocated_with_spaces': True, 'external_paths_overridden': True, 'unresolved_external_dependencies': 0, 'wrapper_help_outside_checkout': True, 'tasks': relocated}, indent=2))
print('Path portability validation passed')
