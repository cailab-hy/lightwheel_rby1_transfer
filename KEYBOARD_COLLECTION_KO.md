> 경로 설정 업데이트: 다른 PC에서 실행할 때는 [PORTABILITY_KO.md](PORTABILITY_KO.md)를 먼저 참고하십시오. 현재 USD는 상대경로를 사용하며, 아래 과거 절대경로 예시는 당시 PC 기준입니다.

# RB-Y1 T1~T10 키보드 시연 수집 — success_original

IsaacLab 2.3.0의 실제 `Se3Keyboard`, `DifferentialIKController`를 사용합니다.
기존 standalone USD 장면에 기록 기능을 연결한 도구이며, IsaacLab의 `record_demos.py`를 수정하거나 Gym task로 등록한 것은 아닙니다.
실제 로봇에는 연결하지 않습니다. T1~T10을 지원하며, 성공 판정은 고정 버전 LW-BenchHub의 `success_original`만 사용합니다.

## 실행

일반 데스크톱 터미널에서 실행합니다.

```bash
/home/cai/lightwheel_rby1_transfer/collect_t1_keyboard.sh
```

다른 task는 다음과 같이 실행합니다.

```bash
~/lightwheel_rby1_transfer/collect_keyboard.sh --task T7
```

기본 저장 위치 (T1):

```text
~/datasets/Lightwheel-Tasks-RBY1-T1-Keyboard-Original/       # LeRobot v3: data/meta/videos
~/datasets/Lightwheel-Tasks-RBY1-T1-Keyboard-Original_raw/   # 원시 PNG·NPZ 및 수집 provenance
```

`B`로 기록을 시작하고 `success_original=True`가 되면 자동 저장 후 초기화하며 LeRobot 폴더가 생성됩니다. 같은 명령을 다시 실행하면 기존 저장 episode 뒤에 추가합니다. 기존 데이터와 fps/영상 크기가 다르면 새 출력 폴더를 지정해야 합니다. 기존 수동 성공 라벨 데이터와 섞이지 않도록 `-Original` 폴더를 기본값으로 사용합니다. task·판정 버전·물체 매핑이 다른 데이터에는 추가 저장하지 않습니다. 자동 업로드는 하지 않습니다.

```bash
/home/cai/lightwheel_rby1_transfer/collect_t1_keyboard.sh \
  --output ~/datasets/RBY1-T1-keyboard-session2 \
  --pos-speed 0.05 --rot-speed 0.3
```

속도는 각각 시뮬레이션 기준 m/s, rad/s입니다. 기본값은 0.08 m/s, 0.5 rad/s입니다.
기록은 기본 50 Hz, 640×480 RGB 카메라 3개입니다. 렌더링이 느리면 벽시계 기준 실행이 느려질 수 있지만, 프레임을 건너뛰지 않고 고정된 시뮬레이션 시간 간격으로 기록합니다. 필요하면 새 출력 경로와 함께 `--fps 25`를 사용할 수 있습니다.

## 조작

Isaac Sim 창이 뜨면 **시뮬레이션 viewport를 클릭하여 키보드 포커스를 줍니다.** `RB-Y1 T1 keyboard collector` 창에서 선택 팔, 그리퍼, 기록 상태와 프레임 수를 확인할 수 있습니다.

| 키 | 동작 |
|---|---|
| W / S | 선택한 손을 로봇 기준 앞으로 / 뒤로 |
| A / D | 로봇 기준 왼쪽 / 오른쪽 |
| Q / E | 위 / 아래 |
| Z / X | 로봇 x축 기준 양/음 방향 회전 |
| T / G | 로봇 y축 기준 양/음 방향 회전 |
| C / V | 로봇 z축 기준 양/음 방향 회전 |
| K | 선택 팔의 그리퍼 열기/닫기 전환 |
| Tab | 왼팔 ↔ 오른팔 전환; 다른 팔은 마지막 목표를 유지 |
| B | 현재 상태에서 새 episode 기록 시작 |
| Enter | `success_original=True`일 때만 저장 요청; False이면 기록을 계속하고 저장 거부 이유 표시 |
| P | 일시정지 / 재개 — 물리와 기록을 함께 멈춰 시간축 공백 방지 |
| Backspace | 현재 미저장 episode 폐기 후 장면 리셋 |
| R | 장면 리셋; 미저장 episode가 있으면 폐기 |
| L | 현재 키 입력을 해제하고 팔 목표를 현재 자세로 설정 |
| Esc / 창 닫기 | 종료; 미저장 episode는 폐기, 저장한 episode는 유지 |

손 이동·회전 키는 누르고 있는 동안 적용됩니다. 처음에는 왼팔이 선택되고 양쪽 그리퍼가 열려 있습니다. 몸통·머리·베이스는 제공 ready USD의 고정 상태를 유지합니다. R 또는 Tab 뒤에는 이동 키를 다시 눌러야 합니다.

수집 예: `R`로 초기화 → `B`로 기록 시작 → 왼손으로 검은 그릇을 집어 접시에 놓기 → 물체를 놓고 양손을 충분히 뒤로 이동 → 원본 조건과 지연 처리가 충족되면 자동 저장. 실패했다면 `Backspace`로 폐기합니다. 저장·영상 인코딩 중에는 잠시 기다립니다. 최소 2프레임이 있어야 저장할 수 있습니다.

**성공 기준은 `success_original` 하나입니다.** 추가 `success_verified` 조건이나 수동 성공 승인은 사용하지 않습니다. 원본 판정 함수가 물체 COM·자세·속도, fixture 관절값, 양손 TCP 거리, 손가락 접촉력을 읽습니다. 원본이 검사하지 않는 높이·지지 접촉·연속 안정성 조건은 추가하지 않았습니다.

원본 공통 처리대로 첫 10 control step에는 성공을 억제하고, teleoperation 모드에서는 물리 dt=0.01 기준 50회 판정 지연을 적용합니다. 이는 한 번 참이 되면 기억하는 방식이며, 조건이 계속 참이어야 한다는 추가 조건은 없습니다. 50 Hz에서 약 1초입니다. `P` 동안에는 판정 카운트도 멈춥니다. 새 기록을 시작하거나 장면을 초기화하면 판정 상태를 초기화합니다. 화면에서 현재 조건식과 `success_original` 결과를 확인할 수 있습니다.

양손 거리 조건 때문에 물체를 놓은 뒤 손을 물체·접시·바구니 또는 fixture에서 충분히 물려야 합니다. 정확한 task별 조건은 [원본 판정 구현 안내](SUCCESS_ORIGINAL_KO.md)를 참고하세요. 충돌 회피 경로 계획기는 연결되어 있지 않습니다.

## 기록되는 값

- `success_original`: 프레임별 원본 자동 성공 판정, int64 `[0/1]`.
- `observation.state`: 시뮬레이터가 측정한 관절 위치 18개. 양팔 14개는 rad, 손가락 4개는 m.
- `observation.velocity`: 같은 순서의 측정 관절 속도.
- `action`: 같은 18개 관절에 실제 발행한 절대 위치 목표. 다음 `1/fps`초 동안 적용.
- `observation.ee_pose`: 로봇 기준 양손 TCP 위치·자세, 각각 xyz + qwxyz.
- `teleop.command`: 키보드 delta pose, 선택 팔, 그리퍼 열림 상태.
- `observation.sim_time`, `observation.camera_time`: 실제 물리 시각과 세 카메라의 렌더 시각. 매 기록 프레임에서 일치 여부를 검사.
- `observation.images.first_person/left_hand/right_hand`: RGB 영상 3개.

한 프레임은 `관측(state·RGB) → action 발행 → 물리 진행` 순서입니다. state에 IK 목표값을 복사하지 않습니다.
이 action은 **시뮬레이션의 18 DOF 명령**입니다. 실제 RB-Y1 드라이버의 action 정의와 자동으로 호환되는 형식은 아니므로, 실기 배포 때는 별도의 변환이 필요합니다.

원시 기록은 lossless PNG·NPZ, 최종 영상은 H.264 MP4입니다. 원시 episode의 `success_state.jsonl`에는 매 프레임 판정에 사용한 물체·관절·TCP·접촉력 상태를 저장합니다. `meta/keyboard_episodes.json`에는 `success_original`, 동일 값의 호환용 `success`, 판정 버전을 저장합니다. `success_label_source`는 `success_original`입니다. 원시 episode에는 초기 물체 상태, 관절 이름·단위, 장면 SHA256, 기록 설정도 보존합니다. 원시 기록이 있으므로 영상·메타데이터 변환 실패 시 다시 내보낼 수 있습니다.

## 실패한 내보내기 복구

저장한 원시 episode는 LeRobot 변환에 실패해도 유지됩니다. 중단된 export 표시가 있으면 중복·불완전 추가 저장을 피하기 위해 후속 export를 중단합니다. 이 경우 **새로운 출력 폴더**에 모든 저장 원시 episode를 다시 내보냅니다.

```bash
LD_LIBRARY_PATH=/home/cai/miniforge3/envs/lerobot-arena/lib \
HF_HUB_OFFLINE=1 \
/home/cai/miniforge3/envs/lerobot-arena/bin/python \
  /home/cai/lightwheel_rby1_transfer/scripts/export_keyboard_episode.py \
  --raw-root ~/datasets/Lightwheel-Tasks-RBY1-T1-Keyboard-Original_raw \
  --output ~/datasets/Lightwheel-Tasks-RBY1-T1-Keyboard-Original-recovered
```

완료된 원시 episode ID는 추적하므로 같은 정상 출력에 다시 내보내도 중복 추가하지 않습니다. LeRobot 데이터나 원시 폴더를 자동으로 업로드하거나 기존 사용자 데이터셋을 지우지 않습니다.

## 검증 방법

GUI 없이 실제 키보드 이벤트 콜백에 입력을 주입하여 양팔 이동·회전·그리퍼·일시정지·저장·폐기·종료를 검사할 수 있습니다.

```bash
/home/cai/lightwheel_rby1_transfer/collect_t1_keyboard.sh --smoke-test
```

기본 smoke 출력은 작업 폴더의 `reports/keyboard_smoke_<시각>/` 아래로 분리됩니다. 일반 smoke 데이터는 `is_smoke_test=true`, `success_original=false`입니다. `--smoke-success-test`는 T1 물체를 테스트용 성공 배치로 이동해 자동 저장을 검사하며 `success_original=true`일 수 있습니다. 모든 smoke 데이터는 실제 시연으로 사용하면 안 됩니다. 화면 포커스와 실제 사용자의 파지 성공까지 검증하는 테스트는 아닙니다.

```bash
LD_LIBRARY_PATH=/home/cai/miniforge3/envs/lerobot-arena/lib \
HF_HUB_OFFLINE=1 \
/home/cai/miniforge3/envs/lerobot-arena/bin/python \
  /home/cai/lightwheel_rby1_transfer/scripts/validate_keyboard_dataset.py \
  --root <검증할-LeRobot-폴더>
```

검증기는 공식 LeRobot 로더, 원시 수치 일치, 시각 정합, MP4 프레임 수 및 원시 PNG/MP4 영상 대응을 검사합니다.

## 초기 키보드 구현의 검증 결과 (수동 라벨 버전의 과거 기록)

2026-09-25, 기본 50 Hz·640×480·3카메라 설정으로 새 수집과 재실행 후 추가 저장을 검사했습니다. 테스트 데이터 6개 episode, 총 231프레임에서 공식 LeRobot 로딩, 원시 수치의 완전 일치, 카메라/물리 시각 정합, 영상 프레임 수를 확인했습니다. 같은 원시 episode를 다시 내보내도 중복 저장되지 않았습니다. 키보드 콜백 주입으로 이동·회전·팔 전환·그리퍼·일시정지·저장·폐기를 검사했습니다.

- [검증 결과](reports/keyboard_implementation_validation.json)
- [기록된 머리·양손 카메라 예시](reports/keyboard_cameras.png)

테스트 데이터는 `reports/`에만 저장했습니다. 실제 사용자 GUI 포커스와 T1 파지·놓기 성공은 아직 검증하지 않았습니다.

## 성공 판정 재계산

```bash
LD_LIBRARY_PATH=/home/cai/miniforge3/envs/lerobot-arena/lib \
/home/cai/miniforge3/envs/lerobot-arena/bin/python \
  ~/lightwheel_rby1_transfer/scripts/replay_success_original.py \
  --raw <저장된-raw-episode-폴더>
```

원시 상태 journal에서 성공 조건 및 지연 처리를 다시 계산하여 저장된 프레임별 라벨과 에피소드 라벨이 일치하는지 검사합니다.

## 참고한 문서·코드

- [IsaacLab v2.3.0 Teleoperation / Imitation Learning](https://isaac-sim.github.io/IsaacLab/v2.3.0/source/overview/imitation-learning/teleop_imitation.html)
- `/home/cai/IsaacLab_RS/VERSION`: 2.3.0
- `/home/cai/IsaacLab_RS/source/isaaclab/isaaclab/devices/keyboard/se3_keyboard.py`
- `/home/cai/IsaacLab_RS/source/isaaclab/isaaclab/controllers/differential_ik.py`
- `/home/cai/IsaacLab_RS/scripts/tools/record_demos.py`
- Isaac Sim 5.1 `sensors/camera/camera.py`: ReferenceTime 기반 렌더 시각 확인 방식.

IsaacLab 기본 기록기는 HDF5를 사용하지만, 이 도구는 앞선 요청의 LeRobot 형식을 유지하기 위해 설치된 공식 LeRobot writer로 내보냅니다.

## 문자열 키 이벤트 오류 수정 (2026-09-25)

`AttributeError: 'str' object has no attribute 'name'`는 GUI 키 이벤트의 문자열 입력을 객체로 가정하여 발생했던 오류입니다. 현재 수집기는 문자열과 Carb enum 형식을 모두 처리하며, IsaacLab 부모 콜백에 전달하기 전에 `.name` 형식으로 통일합니다. 수정 전 실행한 프로세스에는 코드가 반영되지 않으므로 Isaac Sim 창을 닫고 같은 명령으로 다시 실행하세요. 패키지 재설치는 필요하지 않습니다.
