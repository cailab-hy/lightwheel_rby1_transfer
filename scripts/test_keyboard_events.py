"""Regression: real IsaacLab callback bodies must accept GUI string key inputs.
AST loading avoids launching a GUI; it executes the actual installed parent and
collector classes, not a rewritten keyboard handler. Constructors are bypassed.
"""
import project_paths as paths

import ast
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
source = Path(
    str(paths.ISAACLAB / 'source/isaaclab/isaaclab/devices/keyboard/se3_keyboard.py')
)
events = SimpleNamespace(KEY_PRESS=1, KEY_RELEASE=2, KEY_REPEAT=3)
namespace = dict(
    DeviceBase=object,
    np=np,
    torch=torch,
    Rotation=Rotation,
    SimpleNamespace=SimpleNamespace,
    carb=SimpleNamespace(input=SimpleNamespace(KeyboardEventType=events)),
)
for path, name in [
    (source, "Se3Keyboard"),
    (ROOT / "scripts/collect_keyboard.py", "Keyboard"),
]:
    node = next(
        n
        for n in ast.parse(path.read_text()).body
        if isinstance(n, ast.ClassDef) and n.name == name
    )
    tree = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__", names=[ast.alias(name="annotations")], level=0
            ),
            node,
        ],
        type_ignores=[],
    )
    exec(compile(ast.fix_missing_locations(tree), str(path), "exec"), namespace)
Keyboard = namespace["Keyboard"]
checks = []
for kind in ["string", "enum_like"]:
    keyboard = Keyboard.__new__(Keyboard)
    keyboard.held = set()
    keyboard._additional_callbacks = {}
    keyboard.pos_sensitivity = 0.01
    keyboard.rot_sensitivity = 0.02
    keyboard._sim_device = "cpu"
    keyboard.gripper_term = False
    keyboard._create_key_bindings()
    keyboard.reset()

    def send(key, event_type):
        value = key if kind == "string" else SimpleNamespace(name=key)
        return keyboard._on_keyboard_event(
            SimpleNamespace(input=value, type=event_type)
        )

    calls = []
    for key in ["B", "ENTER", "BACKSPACE", "R", "P", "TAB", "K", "ESCAPE"]:
        keyboard.add_callback(key, lambda key=key: calls.append(key))
        send(key, events.KEY_PRESS)
        send(key, events.KEY_PRESS)
        send(key, events.KEY_REPEAT)
        send(key, events.KEY_RELEASE)
        assert calls.count(key) == 1, (kind, key, calls)
        checks.append(f"{kind}: {key} callback once")
    for key in ["W", "S", "A", "D", "Q", "E", "Z", "X", "T", "G", "C", "V"]:
        send(key, events.KEY_PRESS)
        expected = keyboard.advance().clone()
        assert torch.linalg.norm(expected) > 0
        send(key, events.KEY_PRESS)
        send(key, events.KEY_REPEAT)
        assert torch.equal(keyboard.advance(), expected)
        send(key, events.KEY_RELEASE)
        assert torch.allclose(keyboard.advance(), torch.zeros(6)), (kind, key)
        checks.append(f"{kind}: {key} move and release")
    send("W", events.KEY_PRESS)
    send("L", events.KEY_PRESS)
    send("W", events.KEY_RELEASE)
    assert torch.allclose(keyboard.advance(), torch.zeros(6))
    checks.append(f"{kind}: reset ignores stale release")
    send("W", events.KEY_PRESS)
    keyboard.reset()
    send("W", events.KEY_RELEASE)
    assert torch.allclose(keyboard.advance(), torch.zeros(6))
    checks.append(f"{kind}: arm switch reset ignores stale release")
result = {
    "passed": True,
    "cases": len(checks),
    "checks": checks,
    "scope": "actual installed IsaacLab and collector class bodies; no physical GUI event injection",
}
(ROOT / "reports/keyboard_event_regression.json").write_text(
    json.dumps(result, indent=2)
)
print("PASS", len(checks), "string/enum keyboard event regression cases")
