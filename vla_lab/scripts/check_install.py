"""One-shot install check for a new PC: packages, paths, GPU driver, assets, weights, disk. Starts no simulator.

  ./vla_lab/check_install.sh

Each FAIL names the section of the manual that fixes it. Exit code 1 if anything failed.
"""
import os
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import project_paths as p
from fetch_assets import FLOORPLANS, OBJECTS

DATA_GB = 200  # datasets + checkpoints + evaluation of the full lab (TA PC: raw 159, LeRobot 7, runs 7, HF 8, shader cache 8)
fails = 0


def check(name, ok, detail="", fix=""):
    global fails
    fails += not ok
    hint = f"  -> {fix}" if fix and not ok else ""
    print(f"[{'OK' if ok else 'FAIL'}] {name}  {detail}{hint}")


BASE = "기본 환경 설치"
PATHS = "추가 설치 (2)"
GPU = "추가 설치 (3)"
NUMPY = "추가 설치 (4)"
ASSETS = "추가 설치 (5)"
WEIGHTS = "추가 설치 (6)"

# Packages
check("python 3.11", sys.version_info[:2] == (3, 11), sys.version.split()[0], BASE)
for package, wanted in [("isaacsim", "5.1.0.0"), ("torch", "2.7.0+cu128"), ("lerobot", "0.4.3"), ("lightwheel_sdk", "1.0.1")]:
    try:
        found = version(package)
    except PackageNotFoundError:
        found = "없음"
    check(f"{package}=={wanted}", found == wanted, found, BASE)
try:
    import pinocchio
    check("pinocchio", True, pinocchio.__version__)
except Exception as e:
    check("pinocchio", False, repr(e), BASE)

# Folders
check("IsaacLab_RS", (p.ISAACLAB / "VERSION").is_file(), str(p.ISAACLAB), PATHS)
check("rby1-sim-isaac", p.RBY_USD.is_file(), str(p.RBY_SIM), PATHS)

# GPU driver
smi = None
if shutil.which("nvidia-smi"):
    smi = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], capture_output=True, text=True)
check("nvidia-smi", smi is not None and smi.returncode == 0,
      (smi.stdout or smi.stderr).strip().splitlines()[0] if smi else "not found", GPU)

# NumPy / SciPy
try:
    import numpy
    import scipy
    from scipy.spatial.transform import Rotation  # noqa: F401
    from scipy.sparse.linalg import LinearOperator, svds  # noqa: F401
    check("numpy==1.26.0", numpy.__version__ == "1.26.0", f"{numpy.__version__}  {numpy.__file__}", NUMPY)
    check("scipy==1.15.3", scipy.__version__ == "1.15.3", f"{scipy.__version__}  {scipy.__file__}", NUMPY)
except Exception as e:
    check("numpy/scipy import", False, repr(e), NUMPY)

# Lightwheel USD assets
need = [f"floorplan/robocasa-libero-{n}/scene.usd" for n in FLOORPLANS] + [f"object/{n}/{n}.usd" for n in OBJECTS]
missing = [n for n in need if not (p.LIGHTWHEEL_CACHE / n).is_file()]
check(f"Lightwheel USD {len(need) - len(missing)}/{len(need)}", not missing,
      str(p.LIGHTWHEEL_CACHE) + (f"  없음: {missing[0]} ..." if missing else ""), ASSETS)

# SmolVLA weights
hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub"
for model in ("lerobot/smolvla_base", "HuggingFaceTB/SmolVLM2-500M-Video-Instruct"):
    check(model, (hub / f"models--{model.replace('/', '--')}").is_dir(), "", WEIGHTS)

# Disk: data already written counts as available.
root = p.DATASETS
while not root.exists():
    root = root.parent
free = shutil.disk_usage(root).free / 1e9
done = 0.0
lab = p.DATASETS / "vla_lab"
if lab.is_dir():
    done = int(subprocess.run(["du", "-sk", str(lab)], capture_output=True, text=True).stdout.split()[0]) * 1024 / 1e9
check(f"디스크 {DATA_GB}GB", free + done >= DATA_GB, f"여유 {free:.0f}GB, 수집한 데이터 {done:.0f}GB", "기본 환경 설치의 요구 사항")

print("\n모두 OK입니다." if not fails else f"\nFAIL {fails}개: 표시된 항목을 먼저 해결하십시오.")
sys.exit(1 if fails else 0)
