"""Machine-independent paths. External locations can be overridden with RBY1_* variables."""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def configured(name, default):
    return Path(os.path.expandvars(os.environ.get(name, str(default)))).expanduser().resolve()

REPOS = configured('RBY1_REPOS_ROOT', ROOT.parent)
ISAACLAB = configured('RBY1_ISAACLAB_ROOT', REPOS / 'IsaacLab_RS')
RBY_SIM = configured('RBY1_SIM_ROOT', REPOS / 'rby1-sim-isaac')
BENCHHUB = configured('RBY1_BENCHHUB_ROOT', REPOS / 'lw_benchhub')
LEROBOT = configured('RBY1_LEROBOT_ROOT', REPOS / 'lerobot')
LIGHTWHEEL_CACHE = configured('RBY1_LIGHTWHEEL_CACHE', Path.home() / '.cache/lightwheel_sdk')
DATASETS = configured('RBY1_DATASETS_ROOT', Path.home() / 'datasets')
SOURCE_DATASET = configured('RBY1_SOURCE_DATASET', DATASETS / 'Lightwheel-Tasks-X7S')
X7S_SUBSET = configured('RBY1_X7S_SUBSET', DATASETS / 'Lightwheel-Tasks-X7S-T1-T10')
RBY_DATASET = configured('RBY1_DATASET', DATASETS / 'Lightwheel-Tasks-RBY1-T1-T10')
RBY_USD = RBY_SIM / 'assets/generated/rby1_ready_reach_table.usd'
X7_USD = BENCHHUB / 'lw_benchhub/data/assets/x7s.usd'
ASSET_LINKS = ROOT / '.assets'

def executable(name):
    override = os.environ.get('RBY1_' + name.upper())
    if override:
        return str(Path(override).expanduser())
    sibling = Path(sys.executable).parent / name
    return str(sibling) if sibling.is_file() else (shutil.which(name) or name)

def prepare_assets():
    """Create local ignored links, never modify the external assets themselves."""
    for name, target in [('lightwheel', LIGHTWHEEL_CACHE), ('rby1', RBY_SIM)]:
        if not target.is_dir():
            raise FileNotFoundError(f'Missing external asset directory: {target}. See PORTABILITY_KO.md')
        ASSET_LINKS.mkdir(exist_ok=True)
        link = ASSET_LINKS / name
        if link.is_symlink():
            if link.resolve() == target:
                continue
            link.unlink()
        elif link.exists():
            raise FileExistsError(f'Refusing to replace non-symlink: {link}')
        link.symlink_to(target, target_is_directory=True)
    if not RBY_USD.is_file():
        raise FileNotFoundError(RBY_USD)

def scene_metadata(task):
    """Metadata stores repository-relative USD paths; resolve only at runtime."""
    ti = int(str(task).removeprefix('T'))
    meta = json.loads((ROOT / f'environments/T{ti:02d}.json').read_text())
    meta['usd'] = str(ROOT / meta['usd'])
    return meta

def project_artifact(value):
    """Resolve new relative paths and legacy raw-HDF5 paths after relocation."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        return ROOT / path
    if path.exists():
        return path
    if 'raw_hdf5' in path.parts:
        return ROOT.joinpath(*path.parts[path.parts.index('raw_hdf5'):])
    return path

def portable_metadata(value):
    if isinstance(value, dict):
        return {k: portable_metadata(v) for k, v in value.items()}
    if isinstance(value, list):
        return [portable_metadata(v) for v in value]
    if isinstance(value, str):
        for prefix, replacement in [(str(LIGHTWHEEL_CACHE), '.assets/lightwheel'), (str(RBY_SIM), '.assets/rby1'), (str(ROOT), '.')]:
            if value.startswith(prefix + '/'):
                return replacement + value[len(prefix):]
    return value

if __name__ == '__main__':
    prepare_assets()
    print(json.dumps({k: str(v) for k, v in globals().copy().items() if isinstance(v, Path)}, indent=2))
