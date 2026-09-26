"""Regenerate the pinned Apache-2.0 LW-BenchHub predicates; no semantic rewriting."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_paths as paths
import ast, json, hashlib, csv
from pathlib import Path
BASE=Path(str(paths.BENCHHUB))
OUT=Path(__file__).parent
sources={}
def extract(path, names, cls=None, rename=None):
    p=BASE/path; text=p.read_text(); sources[str(path)]=hashlib.sha256(p.read_bytes()).hexdigest()
    tree=ast.parse(text)
    nodes=tree.body if cls is None else next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls).body
    result=[]
    for name in names:
        node=next(n for n in nodes if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name)
        node.decorator_list=[]
        if rename: node.name=rename
        result.append(ast.unparse(node))
    return '\n\n'.join(result)
parts=['''# Copyright 2025 Lightwheel Team; extracted from LW-BenchHub under Apache-2.0.
# Source commit b2bcb2d00edef691f9fcc49039cbf0bcc7464605. See source_manifest.json and LICENSE.
# Generated predicate bodies: do not change semantics here.
from __future__ import annotations
import sys
import numpy as np
import torch
from scipy.spatial.transform import Rotation
from types import SimpleNamespace
T = SimpleNamespace(convert_quat=lambda q,to: np.roll(q,-1) if to=='xyzw' else np.roll(q,1))
OU = sys.modules[__name__]
def matrix_from_quat(q):
    # IsaacLab convention wxyz; SciPy conversion is algebraically equivalent.
    return torch.as_tensor(Rotation.from_quat(q.detach().cpu().numpy()[..., [1,2,3,0]]).as_matrix(),dtype=q.dtype,device=q.device)
''']
parts.append(extract(Path('lw_benchhub/utils/object_utils.py'),['obj_inside_of','check_obj_in_receptacle_no_contact','gripper_obj_far','check_place_obj1_on_obj2','normalize_joint_value']))
parts.append(extract(Path('lw_benchhub/core/models/fixtures/fixture.py'),['get_joint_state','is_open','is_closed'],cls='Fixture'))
parts.append(extract(Path('lw_benchhub/core/tasks/base.py'),['check_success_caller'],cls='LwTaskBase'))
for row in csv.DictReader(open(OUT.parents[1]/'selected_tasks.csv',encoding='utf-8-sig')):
    cls=row['Task 이름']; path=next(p for p in (BASE/'lw_benchhub_tasks/lightwheel_libero_tasks').rglob('*.py') if 'class '+cls+'(' in p.read_text())
    parts.append(extract(path.relative_to(BASE),['_check_success'],cls=cls,rename='check_'+row['Task']))
(OUT/'original_predicates.py').write_text('\n\n'.join(parts)+'\n')
(OUT/'source_manifest.json').write_text(json.dumps({'repository':'https://github.com/LightwheelAI/LW-BenchHub','commit':'b2bcb2d00edef691f9fcc49039cbf0bcc7464605','files':sources,'historical_dataset_code_equivalence':'not established; pinned public implementation'},indent=2))
# Apache-2.0 license is retained in this directory.
