# 다른 PC에서 경로 설정

프로젝트 내부 경로는 `scripts/project_paths.py`의 실제 위치를 기준으로 계산합니다. 작업 디렉터리나 사용자 이름에 의존하지 않습니다. 외부 저장소와 에셋은 별도로 설치되어 있어야 합니다. 이 변경은 설치 패키지나 에셋을 다운로드하지 않습니다.

## 현재 PC

기존 명령을 그대로 사용할 수 있습니다.

```bash
conda activate lerobot-arena
cd ~/lightwheel_rby1_transfer
./collect_keyboard.sh --task T1
```

## 다른 PC

검증된 Isaac Sim 5.1.0 / IsaacLab 2.3.0 / LeRobot 및 필요한 패키지를 설치한 Python 환경을 활성화합니다. 기본적으로 외부 저장소는 이 프로젝트의 형제 폴더, Lightwheel 에셋은 `~/.cache/lightwheel_sdk`, 데이터는 `~/datasets`를 사용합니다. 배치가 다르면 필요한 환경변수만 지정합니다.

```bash
conda activate lerobot-arena
export RBY1_REPOS_ROOT="$HOME/robotics"
export RBY1_ISAACLAB_ROOT="$HOME/robotics/IsaacLab_RS"
export RBY1_SIM_ROOT="$HOME/robotics/rby1-sim-isaac"
export RBY1_BENCHHUB_ROOT="$HOME/robotics/lw_benchhub"
export RBY1_LIGHTWHEEL_CACHE="$HOME/assets/lightwheel_sdk"
export RBY1_DATASETS_ROOT="$HOME/datasets"

./run_python.sh scripts/project_paths.py
./collect_keyboard.sh --task T1
```

`project_paths.py`를 실행하면 `.assets/lightwheel`, `.assets/rby1` 로컬 심볼릭 링크를 준비하고 적용된 설정을 출력합니다. 장면 실행·수집·렌더링 스크립트도 링크를 자동 준비합니다. 링크는 Git에서 제외되며 PC마다 다시 생성됩니다. 기존 디렉터리를 덮어쓰지 않습니다.

`environments/T01.usd`~`T10.usd`는 `../.assets/...` 상대경로를 참조합니다. JSON의 `usd`와 `asset` 필드는 프로젝트 루트 기준 상대경로입니다. USD를 Isaac Sim에서 직접 열 때는 먼저 링크 준비 명령을 실행하십시오. 원본 에셋의 디렉터리 구조와 재질/텍스처 파일도 필요합니다.

| 환경변수 | 기본값 / 용도 |
|---|---|
| `RBY1_REPOS_ROOT` | 프로젝트 상위 폴더 |
| `RBY1_ISAACLAB_ROOT` | 저장소 루트 아래 `IsaacLab_RS` |
| `RBY1_SIM_ROOT` | 저장소 루트 아래 `rby1-sim-isaac` |
| `RBY1_BENCHHUB_ROOT` | 저장소 루트 아래 `lw_benchhub` |
| `RBY1_LEROBOT_ROOT` | 저장소 루트 아래 `lerobot` (보고서용 위치; Python 패키지는 별도 설치) |
| `RBY1_LIGHTWHEEL_CACHE` | `~/.cache/lightwheel_sdk` |
| `RBY1_DATASETS_ROOT` | `~/datasets` |
| `RBY1_SOURCE_DATASET` | 데이터 루트 아래 `Lightwheel-Tasks-X7S` |
| `RBY1_X7S_SUBSET` | 데이터 루트 아래 `Lightwheel-Tasks-X7S-T1-T10` |
| `RBY1_DATASET` | 데이터 루트 아래 `Lightwheel-Tasks-RBY1-T1-T10` (리매핑 도구) |
| `RBY1_PYTHON` | 실행할 Python 바이너리 경로 또는 명령 |
| `RBY1_FFMPEG`, `RBY1_FFPROBE` | 명시하지 않으면 실행 Python의 bin 폴더, 이후 PATH에서 검색 |

키보드 수집 기본 출력은 데이터 루트 아래 `Lightwheel-Tasks-RBY1-Tn-Keyboard-Original`입니다. `--output`을 지정하면 그 경로를 우선합니다.

`run_python.sh`의 Python 선택 순서는 `RBY1_PYTHON` → 활성 Conda 환경(base 제외) → 활성 virtualenv → `~/miniforge3/envs/lerobot-arena` → PATH의 python3입니다. Conda base를 명시적으로 사용할 경우 `RBY1_PYTHON`을 지정하십시오. 다른 작업 디렉터리에서는 실행할 스크립트 경로도 지정합니다.

```bash
"$HOME/robotics/lightwheel_rby1_transfer/run_python.sh" \
  "$HOME/robotics/lightwheel_rby1_transfer/scripts/run_environment.py" --task T1
```

과거 보고서·검증 결과·수집 데이터에 기록된 절대경로와 해시는 당시 실행의 이력이므로 일괄 변경하지 않습니다. 이전 보고서의 명령 대신 이 문서의 실행 방법을 사용하십시오. `references/`에 있는 외부 저장소 사본도 수정하지 않습니다. `revisions/path_portability_before/`는 이번 변경 전 로컬 백업이며 배포 대상이 아닙니다.
