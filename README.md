# Lightwheel RB-Y1 Transfer

Lightwheel의 **Lightwheel-Tasks-X7S에서 선정한 LIBERO task 10개를 RB-Y1 로봇용 Isaac Sim 환경으로 구성**한 프로젝트입니다. T1\~T10 장면 실행, 양팔 키보드 조작, 원본 기준의 자동 성공 판정, LeRobot 형식의 시연 데이터 수집을 지원합니다.

- RB-Y1 모델: `rby1_ready_reach_table.usd`
- 작업대 높이: **0.72m**
- 조작: IsaacLab의 SE(3) 키보드 입력과 Differential IK
- 저장: **LeRobot v3**, 기본은 **실제 RB-Y1 데이터셋과 같은 형식**(15fps, 16차원 state/action, front/right/left AV1 영상), 그리고 검증용 원시 기록
- 성공 판정: 고정된 LW-BenchHub 코드에 기반한 `success_original`

현재 장면은 원본 task의 의미를 유지하도록 구성한 고정 배치 환경입니다. 원본 X7S episode를 그대로 복원한 환경이나, X7S 시연을 RB-Y1으로 리매핑 완료한 데이터셋을 제공하는 것은 아닙니다. 자동 성공 라벨과 별개로 시연의 실제 파지·배치 품질은 확인해야 합니다.

## T1\~T10 환경

아래는 각 환경의 초기 정면 뷰입니다. **윗줄 T1\~T5, 아랫줄 T6\~T10** 순서이며, 환경 실행과 키보드 수집의 기본 뷰도 이 카메라를 사용합니다.

이 이미지는 토르소를 고정한 RB-Y1의 작업 영역에 맞춰 조정한 **기본(고정) 배치**입니다(2026-09-30 재촬영). 수집할 때는 초기화마다 물체 위치가 랜덤으로 바뀝니다. 배치를 바꾼 이유와 검증 결과는 [T1 보고서](reports/t1_layout_check/README.md)와 [T2\~T10 보고서](reports/t2_t10_layout_check/README.md)에 있습니다.

![RB-Y1 T1\~T10 초기 환경](docs/images/T1-T10_front_2x5.jpg)

| Task | 작업 | LIBERO 레이아웃 | 개별 이미지 |
|---|---|---|---|
| T1 | 검은 그릇을 접시에 놓기 | libero-1-1 | [T1](docs/images/T01_front.jpg) |
| T2 | 쿠키 상자 위의 검은 그릇을 접시에 놓기 | libero-8-8 | [T2](docs/images/T02_front.jpg) |
| T3 | 케첩을 바구니에 넣기 | libero-2-2 | [T3](docs/images/T03_front.jpg) |
| T4 | 수납장의 위 서랍 열기 | libero-1-1 | [T4](docs/images/T04_front.jpg) |
| T5 | 전자레인지 문 열기 | libero-1-1 | [T5](docs/images/T05_front.jpg) |
| T6 | 스토브 켜기 | libero-8-8 | [T6](docs/images/T06_front.jpg) |
| T7 | 위 서랍을 열고 그릇 넣기 | libero-8-8 | [T7](docs/images/T07_front.jpg) |
| T8 | 가운데 검은 그릇을 뒤쪽 검은 그릇 위에 쌓기 | libero-1-1 | [T8](docs/images/T08_front.jpg) |
| T9 | 검은 그릇을 아래 서랍에 넣고 닫기 | libero-1-1 | [T9](docs/images/T09_front.jpg) |
| T10 | 알파벳 수프와 토마토 소스를 바구니에 넣기 | libero-2-2 | [T10](docs/images/T10_front.jpg) |

원본 언어 명령과 선정 역할은 [selected_tasks.csv](selected_tasks.csv), 상세 정보는 [selection.json](selection.json)에 있습니다. 정면 미리보기 카메라는 수집용 헤드·손목 카메라와 별도입니다.

## 실행 환경과 경로 설정

검증에 사용한 환경은 **Isaac Sim 5.1.0 / IsaacLab 2.3.0 / Python 3.11**입니다. 실행 Python에 IsaacLab, LeRobot, Pinocchio, PyTorch, NumPy, SciPy, Pillow, PyAV 등 필요한 패키지가 설치되어 있어야 합니다. 이 저장소만으로 외부 시뮬레이터와 에셋이 설치되지는 않습니다.

기본 폴더 구성은 다음과 같습니다.

```text
작업폴더/
├── lightwheel_rby1_transfer/
├── IsaacLab_RS/
├── rby1-sim-isaac/
│   └── assets/generated/rby1_ready_reach_table.usd
├── lerobot/
└── lw_benchhub/                  # 원본 분석·리매핑 도구 사용 시

~/.cache/lightwheel_sdk/          # 장면·물체·재질 에셋
~/datasets/                      # 기본 데이터 저장 위치
```

다른 위치에 설치했다면 필요한 환경변수만 지정합니다. Lightwheel 에셋의 하위 폴더와 텍스처 구조도 유지해야 합니다.

```bash
conda activate lerobot-arena
cd /path/to/lightwheel_rby1_transfer

# 기본 위치와 다를 때만 설정
export RBY1_ISAACLAB_ROOT="/path/to/IsaacLab_RS"
export RBY1_SIM_ROOT="/path/to/rby1-sim-isaac"
export RBY1_LIGHTWHEEL_CACHE="/path/to/lightwheel_sdk"
export RBY1_DATASETS_ROOT="$HOME/datasets"

# 현재 경로 출력 및 외부 에셋 링크 준비
./run_python.sh scripts/project_paths.py
```

공통 상위 경로는 `RBY1_REPOS_ROOT`로 지정할 수 있습니다. Python을 직접 선택하려면 `RBY1_PYTHON=/path/to/env/bin/python`을 설정합니다. 실행기는 활성 Conda 환경(base 제외) 또는 virtualenv를 우선 사용하며, 둘 다 없으면 로컬 `~/miniforge3/envs/lerobot-arena`를 찾습니다. 전체 경로 설정은 [project_paths.py](scripts/project_paths.py)를 참고하십시오.

외부 에셋은 프로젝트의 `.assets/` 심볼릭 링크로 연결됩니다. 이 링크는 각 PC에서 생성하는 로컬 설정이며, 원본 에셋을 프로젝트에 복사하지 않습니다.

## 키보드 데이터 수집

### 1. 실행

```bash
conda activate lerobot-arena
cd /path/to/lightwheel_rby1_transfer
./collect_keyboard.sh --task T1
```

`--task`를 `T2`\~`T10`으로 바꾸면 해당 환경을 실행합니다. 출력 위치나 프레임률을 지정할 수도 있습니다.

```bash
./collect_keyboard.sh --task T1 \
  --output "$HOME/datasets/RBY1-T1-Keyboard" \
  --fps 50
```

장면을 초기화할 때마다 물체 위치와 방향이 `environments/Txx.json`의 `randomization` 범위 안에서 랜덤으로 바뀝니다(기본값 `--layout random`). T1\~T10 모두 범위가 지정되어 있습니다. 목표 물체는 RB-Y1 작업 영역 안에서만 뽑고, 나머지 물체는 fixture 자리와 서랍·문이 움직이는 영역을 피해 테이블 위에 흩어 놓습니다. 수납장, 전자레인지, 스토브 같은 fixture는 고정입니다. T2\~T10의 배치 변경 내용과 검증 결과는 [reports/t2_t10_layout_check](reports/t2_t10_layout_check/README.md)에 있습니다. 재현하려면 `--seed`를 지정하고, 고정 배치로 수집하려면 `--layout fixed`를 사용합니다. 각 episode의 초기 배치는 `meta/keyboard_episodes.json`의 `initial_layout`에 기록됩니다.

| T1 (로봇 기준, 물체 중심) | x (앞) | y (왼쪽) | yaw |
|---|---|---|---|
| 그릇 | 0.52 \~ 0.58 m | 0.27 \~ 0.35 m | ±180° |
| 접시 | 0.52 \~ 0.60 m | 0.01 \~ 0.09 m | ±180° |

두 물체 중심 사이는 0.25m 이상 떨어지도록 합니다. 이 범위는 토르소를 고정한 상태의 왼팔 작업 영역과 헤드 카메라 가시성을 기준으로 정했습니다(근거: [reports/t1_layout_check](reports/t1_layout_check/README.md)).

기본 수집 설정(`--profile rby1`)은 실제 RB-Y1 데이터셋([rainbowrobotics/icra_0526_compound_rel](https://huggingface.co/datasets/rainbowrobotics/icra_0526_compound_rel))에 맞춰져 있습니다.

- **fps**: 15fps로 수집합니다. 물리는 1/105초 스텝 7번으로 정확히 1/15초씩 진행합니다.
- **카메라**:
  - 헤드 카메라: 640×480
  - 좌·우 손목 카메라: **480×640 세로**. 왼쪽은 180° 돌려서 두 카메라 모두 손가락이 이미지 아래쪽에 오게 합니다.

이전 방식은 `--profile sim`입니다. 이때는 기본 50fps이고, 모든 카메라가 `--width`×`--height`(640×480)입니다. `--fps`는 10, 15, 20, 25, 50을 지원합니다. 일반 키보드 수집은 GUI에서 진행합니다.

### 2. 조작

시뮬레이션 뷰포트를 클릭해 키보드 포커스를 둡니다. 처음 선택된 팔은 **왼팔**이며, 이동 축은 **로봇 기준 좌표계**입니다. 정면 화면에서 보이는 좌우와 로봇의 좌우는 반대일 수 있습니다.

| 키 | 기능 |
|---|---|
| `W` / `S` | 선택한 팔의 전진 / 후진 (x축) |
| `A` / `D` | 왼쪽 / 오른쪽 이동 (y축) |
| `Q` / `E` | 위 / 아래 이동 (z축) |
| `Z` / `X` | x축 회전 |
| `T` / `G` | y축 회전 |
| `C` / `V` | z축 회전 |
| `K` | 선택한 팔의 그리퍼 열기 / 닫기 |
| `Tab` | 왼팔 / 오른팔 전환 |
| `B` | 현재 상태에서 기록 시작 |
| `P` | 시뮬레이션·기록 일시정지 / 재개 |
| `L` | 이동 입력 해제 및 현재 관절 위치 유지 |
| `Enter` | 성공 조건을 충족한 기록 저장 요청 |
| `R` / `Backspace` | 저장 전 기록 폐기 및 장면 초기화 |
| `Esc` | 종료; 저장 전 기록은 폐기 |

### 3. 기록과 저장

1. 초기 장면과 선택된 팔을 확인하고 **`B`**를 눌러 기록을 시작합니다. 전체 작업을 담으려면 물체 조작 전에 시작합니다.
2. 팔과 그리퍼를 조작해 언어 명령을 수행합니다. 필요하면 `Tab`으로 팔을 전환합니다.
3. **`success_original`이 참이 되고 최소 2프레임이 기록되면 자동 저장**됩니다. 성공하지 않은 기록은 `Enter`로 강제 저장할 수 없습니다.
4. 저장되면 `Saved raw episode`가 출력되고 **장면이 바로 초기화**됩니다. 수집기는 raw 기록만 저장하고 LeRobot 변환은 하지 않으므로, 기다리지 않고 바로 다음 시연을 할 수 있습니다. 다음 시연은 다시 `B`를 눌러 시작합니다.
5. 실패한 시도는 `R` 또는 `Backspace`로 폐기하고 다시 시작합니다. 수집을 마치면 `Esc`로 종료하고, 아래 [LeRobot 변환](#5-lerobot-변환)을 실행합니다.

`success_original`은 [scripts/vendor](scripts/vendor)의 고정된 LW-BenchHub 성공 판정 코드와 RB-Y1 상태 어댑터를 사용합니다. 어댑터 v2부터 T1에는 원본 조건(그릇–접시 xy 0.1945m 이내, 그리퍼 0.25m 이상 이탈)에 더해 **그릇이 접시 위에 평평하게 놓였는지**(무게중심 xy < 0.065m, 높이 차 > 0.032m)를 함께 확인합니다. 원본 조건만으로는 접시 가장자리에 걸치거나 옆에 놓인 그릇도 성공으로 판정되기 때문입니다([reports/t1_layout_check](reports/t1_layout_check/README.md)). 원본 판정식에 포함되지 않은 파지 안정성이나 전체 동작 품질까지 보장하는 지표는 아닙니다. `--smoke-test` 계열 옵션은 개발 검증용이며 실제 시연 수집에 사용하지 않습니다.

### 4. 저장 데이터

T1 기본 출력은 다음과 같습니다. `RBY1_DATASETS_ROOT` 또는 `--output`으로 위치를 변경할 수 있습니다.

```text
~/datasets/
├── Lightwheel-Tasks-RBY1-T1-Keyboard-Original/
│   ├── data/                   # 상태, action, 시간, 성공 라벨
│   ├── meta/                   # LeRobot 메타데이터와 episode 매핑
│   └── videos/                 # 헤드·왼손·오른손 카메라 영상
└── Lightwheel-Tasks-RBY1-T1-Keyboard-Original_raw/
    └── episode-.../             # PNG, trajectory.npz, 성공 판정 상태 기록, export.log 등
```

LeRobot 변환 형식은 두 가지입니다.

| 항목 | `--format rby1` (기본, 실제 RB-Y1과 동일) | `--format sim` |
|---|---|---|
| fps | 15 (다른 fps로 수집한 raw는 15fps로 재표본화) | 수집 fps |
| `observation.state` | 16차원: `right_arm_0..6`, `left_arm_0..6`, `right_gripper_0`, `left_gripper_0` | 18차원: 시뮬레이터 관절 순서 (왼팔·오른팔 교대, 손가락 4개) |
| `action` | 16차원, 같은 순서. 팔은 다음 스텝의 절대 관절 목표(rad), 그리퍼는 열기 1 / 닫기 0 명령 | 18차원: 시뮬레이터에 보낸 절대 관절 목표 (손가락은 m) |
| 그리퍼 state | 열린 정도 0(닫힘)\~1(열림) | 손가락 변위 (m) |
| 영상 | `front` 640×480, `right`·`left` 480×640 세로, AV1 | `first_person`·`left_hand`·`right_hand`, H.264 |
| 기타 feature | 없음 (실제 데이터셋과 동일) | 속도, 말단 자세, 키보드 입력, 성공 라벨, 시간 |
| robot_type | `rby1` | `rby1_isaac_keyboard` |

- 관절 각도의 부호와 0점은 실제 RB-Y1과 같습니다. 실제 데이터의 시작 자세가 이 레포의 준비 자세와 일치합니다.
- 그리퍼 action은 수집 중 손가락 목표의 움직임에서 복원한 0/1 명령입니다. 실제 데이터도 대부분 0/1입니다.
- `profile sim`으로 수집한 raw를 `rby1` 형식으로 변환할 때는 두 가지를 추가로 합니다.
  - 가로 손목 영상을 3:4로 가운데 잘라 세로로 바꿉니다.
  - 50fps 등은 15fps로 재표본화합니다. 이 경우 동작이 거칠어져 replay 시 성공이 재현되지 않을 수 있으므로, 새 데이터는 기본 프로필(15fps)로 수집하십시오.
- 두 형식 모두 raw 기록에는 18차원 전체 값이 남아 있습니다.

기존 출력 폴더에는 task·fps·영상 크기·데이터 스키마가 호환되는 경우에만 추가 수집할 수 있습니다.

### 5. LeRobot 변환

수집과 변환은 분리되어 있습니다. 수집기는 `<output>_raw/episode-*`에 raw 기록만 저장하고, LeRobot v3 변환은 `export_dataset.sh`로 따로 실행합니다.

```bash
# 수집할 때 쓴 --output을 그대로 지정 (raw 폴더는 <output>_raw로 자동 결정)
./export_dataset.sh --output "$HOME/datasets/RBY1-T1-Keyboard-Random"

# 기본 출력 경로로 수집한 경우
./export_dataset.sh --task T1

# 변환 후 검증까지 실행
./export_dataset.sh --output "$HOME/datasets/RBY1-T1-Keyboard-Random" --validate
```

- 이미 변환된 episode는 건너뛰므로 언제든 다시 실행할 수 있습니다. 수집기가 켜져 있는 동안에도 실행할 수 있습니다(저장이 끝난 `episode-*`만 변환하고, 녹화 중인 `pending-*`는 무시).
- 터미널에는 진행 상황(`[i/N] … done in N s`)만 표시됩니다. 영상 인코더 로그는 각 episode의 `export.log`에 저장됩니다.
- 변환 시간은 1분 분량 episode 기준으로 `rby1` 형식(15fps)이 약 1분, `sim` 형식 50fps가 약 3분입니다. `--format sim`으로 이전 형식을 선택할 수 있습니다.
- 변환이 중간에 끊기면 출력 폴더에 중단 표시(`meta/keyboard_export_in_progress.json`)가 남습니다. 이때는 출력 폴더를 다른 이름으로 옮긴 뒤 다시 실행하면, raw에서 처음부터 변환합니다.
- raw 폴더를 직접 지정하려면 `--raw-root`를 사용합니다.
- 수집하면서 백그라운드로 바로 변환하고 싶다면 수집기에 `--auto-export`를 붙입니다(이전 방식).

`--validate`와 같은 검증을 단독으로 실행할 수도 있습니다. LeRobot 로딩, 원시 기록과의 일치, 영상 프레임·시간, 성공 판정 재연산을 검사하며 `_raw` 기록이 필요합니다.

```bash
./run_python.sh scripts/validate_keyboard_dataset.py \
  --root "$HOME/datasets/RBY1-T1-Keyboard-Random"
```

### 6. 수집 데이터 replay

수집한 episode를 Isaac Sim에서 다시 재생합니다. 기본은 GUI이며, `--headless`로 창 없이 확인만 할 수도 있습니다.

```bash
# LeRobot 데이터셋의 episode 0을 재생 (여러 개: --episode 0,3,5 / 전체: --episode all)
./replay_dataset.sh --root "$HOME/datasets/RBY1-T1-Keyboard-Random" --episode 0

# 기록된 그대로 보기 (물리 없이 로봇 관절과 물체 자세를 프레임마다 복원)
./replay_dataset.sh --root "$HOME/datasets/RBY1-T1-Keyboard-Random" --episode 0 --mode state

# raw episode를 직접 지정, 2배속
./replay_dataset.sh --raw "$HOME/datasets/RBY1-T1-Keyboard-Random_raw/episode-<id>" --speed 2
```

- **재생 방식 (`--mode`)**
  - `action`(기본): 기록 시작 시점의 장면(물체 자세, 서랍·문 관절, 로봇 관절)을 복원합니다. 그다음 기록된 18차원 관절 목표를 수집 때와 같은 물리 스텝으로 다시 실행합니다. 끝나면 성공 판정이 재현됐는지와 기록된 관절 상태와의 최대 오차를 출력합니다.
  - `state`: 물리 없이 기록된 값을 프레임마다 그대로 옮겨 놓는, 영상 재생에 가까운 방식입니다.
- **raw 기록이 없을 때**: LeRobot 데이터만 남아 있으면 `meta/keyboard_episodes.json`의 `initial_layout`으로 물체를 배치하고, 서랍·문은 장면의 기본 상태를 씁니다. 이 경우 `state` 모드는 로봇만 움직입니다.
- **장면 변경 경고**: 수집 후 장면 USD가 바뀌었으면 경고를 출력합니다. 배치를 바꾼 뒤에는 이전 데이터를 재생해도 같은 결과가 나오지 않을 수 있습니다.

**mp4로 녹화하기**

```bash
# 정면 카메라로 녹화 (창 없이; 파일 이름을 직접 지정)
./replay_dataset.sh --raw "$HOME/datasets/Lightwheel-Tasks-RBY1-T1-Keyboard-Original_raw/episode-<id>" \
  --headless --video videos/t1_ep0.mp4

# 모든 episode를 정면·헤드·왼손·오른손 2x2 화면으로 녹화 (폴더를 지정하면 episode마다 파일 생성)
./replay_dataset.sh --root "$HOME/datasets/RBY1-T1-Keyboard-Random" --episode all \
  --mode state --headless --video videos/ --video-camera grid
```

- **옵션**
  - `--video-camera`: `front`(기본), `head`, `left_hand`, `right_hand`, `grid` 중 하나입니다.
  - `--video-size`: 해상도로, 기본값은 `1280x720`입니다. `grid`는 각 칸이 이 크기의 절반입니다.
  - `--no-overlay`: 영상 위의 글자(episode, 프레임, 시간, 성공 판정)를 끕니다.
- **영상 길이와 소요 시간**
  - 영상은 기록 fps로 저장되므로 실제 시간 길이와 같습니다. `action` 모드에서는 끝난 뒤 `--hold` 구간도 포함됩니다.
  - 창 없이(`--headless`) 녹화하면 1분짜리 episode 기준 약 2분 걸립니다.
  - 창을 띄운 채로도 녹화할 수 있습니다.

## VR(Meta Quest 2) 데이터 수집

Meta Quest 2를 USB로 PC에 연결하고, 컨트롤러로 RB-Y1의 **양팔을 동시에** 조작해 데모를 수집합니다.
- 그립을 쥐고 있는 동안 해당 팔이 손을 따라 움직입니다.
- 트리거를 당기면 그리퍼가 닫힙니다.
- 헤드셋 안에는 로봇 카메라 영상이 보입니다.

기록, 성공 시 자동 저장, 랜덤 배치, LeRobot(RB-Y1 형식) 변환, replay는 키보드 수집과 같습니다. 저장되는 state/action도 키보드 데이터와 같은 형식입니다.

| 문서 | 내용 |
|---|---|
| [docs/VR_QUICKSTART_KO.md](docs/VR_QUICKSTART_KO.md) | **요약 가이드**: PC·헤드셋 설정, 명령, 버튼, 문제 해결 |
| [docs/VR_STEP1_QUEST2_SETUP_KO.md](docs/VR_STEP1_QUEST2_SETUP_KO.md) | 헤드셋 초기 설정(개발자 모드, adb, WebXR 확인) 상세 |
| [docs/VR_COLLECTION_QUEST2_KO.md](docs/VR_COLLECTION_QUEST2_KO.md) | 설계와 검증 기록(좌표 변환, 클러치, IK, 영상, X7S 속도 비교) |

### 1. PC 설정 (최초 1회)

키보드 수집과 같은 `lerobot-arena` 환경을 씁니다. VR 기능용으로 추가할 Python 패키지는 없습니다. 헤드셋 연결에 필요한 adb와 USB 권한 규칙만 설치합니다.

```bash
sudo apt install -y adb android-sdk-platform-tools-common

# Meta 기기(USB vendor 2833) 권한 규칙. 기본 규칙에는 없어서 반드시 추가합니다
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="2833", MODE="0660", GROUP="plugdev", TAG+="uaccess"' | sudo tee /etc/udev/rules.d/51-meta-quest.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
adb kill-server

conda activate lerobot-arena
python -m pytest -q scripts/vr        # VR 코드 단위 테스트
```

계정이 `plugdev` 그룹에 있어야 합니다(`id`로 확인).

### 2. Quest 2 설정 (최초 1회)

1. 헤드셋 소프트웨어와 **Meta Quest Browser**를 업데이트합니다.
2. **개발자 모드**를 켭니다.
   - developers.meta.com에서 조직(무료)을 만듭니다.
   - 휴대폰 Meta Horizon 앱 → 기기 → 헤드셋 설정 → 개발자 모드를 켭니다.
   - 헤드셋을 재부팅합니다.
3. USB **데이터** 케이블로 PC에 연결합니다. 헤드셋 안 "USB 디버깅 허용" 창에서 **"이 컴퓨터에서 항상 허용"**을 체크합니다. `adb devices`가 `device`로 나오면 됩니다.
4. 헤드셋 설정을 바꿉니다.
   - **고정형(Stationary) 경계**
   - **"컨트롤러에서 손으로 자동 전환" 끄기**
   - 자동 절전 시간 늘리기

연결 점검(시뮬레이터 없이, 처음 한 번):

```bash
./scripts/vr/quest_check.sh --teleop                  # 손 방향·버튼·트리거 확인
./run_python.sh scripts/vr/vr_server.py --test-video  # 헤드셋 안 카메라 패널을 테스트 그림으로 확인
```

두 명령 모두 헤드셋 브라우저에 페이지를 자동으로 엽니다. **Enter VR**을 누르고 확인한 뒤, PC에서 Ctrl+C로 종료합니다.

### 3. 실행

```bash
cd ~/lightwheel_rby1_transfer
conda activate lerobot-arena
adb devices                                                   # device 확인
./collect_vr.sh --task T1 --joint-speed 1.5 --output ~/datasets/RBY1-T1-VR
```

`collect_vr.sh`가 하는 일:
1. adb 연결(권한, 인증, 배터리)을 점검합니다.
2. 포트 8012를 헤드셋으로 연결합니다(`adb reverse`).
3. 수집기를 VR 모드(`collect_keyboard.py --input vr`)로 실행합니다.
4. 헤드셋 브라우저에 수집 페이지를 엽니다.

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--task` | T1 | T1부터 T10 |
| `--output` | `~/datasets/Lightwheel-Tasks-RBY1-{task}-VR` | 데이터 폴더. raw episode는 `<output>_raw`에 저장됩니다 |
| `--joint-speed` | 0.8 | 관절 속도 제한(rad/s). **X7S 원본과 비슷한 속도를 내려면 1.5 권장** |
| `--motion-scale` | 1.0 | 손 이동 대비 로봇 손 이동 비율. 정밀 작업은 0.6\~0.8 |
| `--vr-no-rotation` | 꺼짐 | 그리퍼 방향을 고정하고 위치만 따라감 |
| `--vr-record FILE` | 없음 | 헤드셋 입력 전체를 JSONL로 저장(분석, `--vr-replay` 재생용) |
| `--layout fixed` | random | 물체 배치 고정 |
| `--vr-no-video` | 꺼짐 | 헤드셋 패널 영상 끄기 |

### 4. 헤드셋 접속

1. Isaac Sim 창이 뜨고 터미널에 `[vr] opened http://localhost:8012/?v=...`가 나오면, 헤드셋에 페이지가 열려 있습니다.
   - 열리지 않았으면 헤드셋 브라우저에 `http://localhost:8012/?v=1`을 직접 입력합니다.
2. 페이지에서 확인합니다.
   - OK 3개(`secure context`, `navigator.xr`, `immersive-vr supported`)
   - **connected to the collector**
3. **Enter VR**을 누릅니다. 터미널에 `[vr] IDLE | VR page: in VR, ~80 reports/s ...`가 나오면 준비가 끝난 것입니다.

### 5. 조작

번호는 Quest 2 컨트롤러 그림 기준입니다(L1/R1 썸스틱, L2/R2 트리거, L3/R3 그립).

| 입력 | 기능 |
|---|---|
| **그립** L3 / R3 (가운뎃손가락) 누르는 동안 | 해당 팔이 컨트롤러를 따라 움직임. 떼면 정지(손을 옮긴 뒤 다시 쥐면 이어서 조작) |
| **트리거** L2 / R2 (검지) | 해당 그리퍼 닫기 (놓으면 열림) |
| **A** | 기록 시작 |
| **B** 1초 | 기록 폐기 + 장면 초기화 |
| **X** | 일시정지 / 재개 |
| **Y** 1초 | 정면 재보정: 지금 바라보는 방향이 로봇 정면이 되고, 카메라 패널도 앞으로 옮겨집니다 |
| **오른쪽 스틱** 위아래 / 좌우 | 카메라 패널 거리 / 크기 |
| 메뉴 / Meta 버튼 | 누르지 않음 (Meta 버튼은 VR에서 나감) |
| PC 키보드 (Isaac Sim 화면 클릭 후) | ESC 종료, ENTER 저장(성공했을 때만), BACKSPACE 폐기, R 초기화 |

### 6. 기록과 저장

1. 정면을 보고 **Y 1초** → 기록 없이 잠깐 움직여 봅니다 → **A**로 기록을 시작합니다. 물체에 다가가기 전에 시작합니다.
2. 작업을 수행합니다. T1은 왼팔로 그릇을 접시 위에 놓은 뒤, **그리퍼를 그릇에서 떼어 물러나야** 성공입니다.
3. 성공 판정을 만족하면 **자동으로 저장되고 장면이 초기화됩니다.** 저장 버튼은 따로 없습니다. 다음 episode는 **A**로 시작합니다.
4. 실패한 시도는 **B 1초**로 폐기합니다. 성공하지 못한 episode는 저장되지 않습니다.

헤드셋 패널 위쪽의 상태 줄을 읽는 법(PC 터미널의 `[vr]` 줄에도 같은 정보가 나옵니다):

| 줄 | 표시 |
|---|---|
| 1줄 | `IDLE - A: start recording`(회색) / `REC 12.3 s`(빨강) / `PAUSED`(노랑), 팔별 `GRIP`·`hold`·`LOST`, 그리퍼 `open`·`closed` |
| 2줄 | `Task: not done | 조건별 OK/no`(T1) → `Task condition met - hold still...` → **`SUCCESS! Episode saved (N this session)`**(초록) / `DISCARDED (not saved)` |

VR 데이터에는 키보드 데이터의 feature에 더해 다음이 저장됩니다.
- `teleop.command`(20차원): 팔별 클러치, 트리거, 그리퍼, 목표 자세
- `teleop.vr_input`(20차원): 컨트롤러 자세, 트리거, 그립

메타데이터에는 `teleop_device: quest2_webxr`가 기록됩니다. 기본 RB-Y1 형식 변환에서는 이 항목들이 빠지므로, 키보드 데이터와 같은 16차원 state/action이 됩니다. 한 출력 폴더에는 같은 조작 장치, task, fps로 모은 episode만 넣을 수 있습니다.

### 7. 변환·검증·replay

```bash
./export_dataset.sh --output ~/datasets/RBY1-T1-VR --validate          # --output 없이 수집했다면: --task T1 --input vr
./replay_dataset.sh --root ~/datasets/RBY1-T1-VR --episode all --headless --video ~/vr_replay_videos/
```

### 8. 문제 해결

| 증상 | 조치 |
|---|---|
| `adb devices`에 `no permissions` | 1장의 udev 규칙 추가 → `adb kill-server` → 케이블 다시 꽂기 |
| `unauthorized` | 헤드셋을 쓰고 "USB 디버깅 허용"에서 "항상 허용" |
| 헤드셋에 페이지가 안 열림, `old page` 경고 | 헤드셋 브라우저에 `http://localhost:8012/?v=2`처럼 숫자를 바꿔 직접 열기 |
| `Port 8012 is busy` | 다른 터미널의 `quest_check.sh`, `vr_server.py`, 수집기 종료 |
| 패널에 `LOST` | 컨트롤러를 헤드셋 시야 안으로, 배터리 확인, 손 추적 자동 전환 끄기 |
| 팔이 다른 방향으로 감 | 정면을 보고 Y 1초 |
| 팔이 느리게 따라옴 | `--joint-speed` 1.5\~2.0. 터미널 `sim speed`가 1.0보다 많이 낮으면 시뮬레이션 자체가 느린 것 |
| 성공했는데 저장 안 됨 | `REC` 상태였는지 확인(IDLE이면 A 먼저). 패널 2줄의 `no` 조건 확인 |

## 장면만 실행하기

```bash
./run_python.sh scripts/run_environment.py --task T1
```

이 명령은 준비 자세를 유지하며 장면과 성공 판정을 확인합니다. 키보드로 팔을 조작하고 데이터를 수집하려면 `collect_keyboard.sh`를 사용하십시오.

## 주요 파일

| 경로 | 내용 |
|---|---|
| `environments/T01.usd`\~`T10.usd` | RB-Y1 task 장면 |
| `environments/T01.json`\~`T10.json` | 물체, 배치, 로봇 자세 정보 |
| `scripts/collect_keyboard.py` | 키보드/VR(`--input vr`) 조작·기록·자동 저장 |
| `collect_vr.sh` | VR 수집 실행 (adb 점검, 포트 연결, `collect_keyboard.py --input vr`) |
| `scripts/vr/vr_teleop.py` | VR 좌표 변환, 정면 재보정, 그립 클러치, 버튼 판정 |
| `scripts/vr/vr_server.py` | 헤드셋 WebXR 페이지, 입력 수신·영상 전송(WebSocket) |
| `scripts/vr/vr_video.py` | 헤드셋 카메라 패널 영상 합성·압축 |
| `scripts/vr/quest_check.sh`, `quest_check.py` | 헤드셋 연결·입력 점검 도구 |
| `scripts/vr/scripted_operator.py` | 헤드셋 없는 VR 시험용 자동 조작자와 입력 재생 |
| `export_dataset.sh`, `scripts/export_dataset.py` | 저장된 raw episode 일괄 LeRobot 변환 |
| `scripts/export_keyboard_episode.py` | episode 1개 LeRobot 변환 |
| `replay_dataset.sh`, `scripts/replay_episode.py` | 수집 데이터 replay |
| `scripts/rby1_format.py` | 실제 RB-Y1 데이터 형식과의 변환 규칙 |
| `scripts/success_original.py` | 원본 성공 판정 어댑터 |
| `scripts/front_camera.py` | 기본 정면 카메라 설정 |
| `docs/images/` | README용 T1\~T10 이미지 |

이미지는 Isaac Sim의 초기 장면(기본 배치) 렌더이며 성공 시연을 나타내지 않습니다. 다음 명령으로 원본 PNG와 합본을 다시 생성할 수 있습니다. 출력 위치는 `reports/front_views/`이며, README용 JPEG는 `docs/images/`에 둡니다(개별 1280×800, 합본 가로 3000px).

```bash
./run_python.sh scripts/render_front_views.py
./run_python.sh scripts/compose_front_views.py
```

원본 성공 판정 코드의 출처·커밋은 [source_manifest.json](scripts/vendor/source_manifest.json), 해당 라이선스는 [scripts/vendor/LICENSE](scripts/vendor/LICENSE)에 보존되어 있습니다.
