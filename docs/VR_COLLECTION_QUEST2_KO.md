# Meta Quest 2로 RB-Y1 T1~T10 데이터 수집하기 — 단계별 진행 가이드

이 문서는 `lightwheel_rby1_transfer`에 Meta Quest 2 VR 조작을 추가하여 T1~T10 시연을 **LeRobot v3 형식**으로 수집하기 위한 계획과 절차입니다. 단계마다 **완료 기준**이 있으며, 앞 단계가 통과해야 다음 단계로 넘어갑니다.

> 작성 기준: 2026-09-29, 로컬 코드 확인 결과(Isaac Sim 5.1.0 / IsaacLab 2.3.0 / Python 3.11 / vuer 0.0.70 / lerobot 0.4.3).
> 실제 Quest 2 기기 연결은 아직 시험하지 않았습니다. 기기에서 확인할 항목은 **[기기 확인 필요]**로 표시했습니다.

---

## 0. 요약

| 항목 | 결정 |
|---|---|
| VR 입력 방식 | **Quest 브라우저 WebXR + Vuer**. Lightwheel이 X7S 원본 데이터를 수집할 때 쓴 LW-BenchHub의 VR 장치와 같은 방식이며, `lerobot-arena`에 `vuer 0.0.70`이 이미 설치되어 있습니다. |
| PC–Quest 연결 | **USB 케이블 + `adb reverse`**를 기본으로 사용합니다. Quest는 `http://localhost`에 접속하고, localhost는 보안 컨텍스트로 취급되어 **HTTPS 인증서 없이 WebXR을 사용할 수 있습니다.** Wi-Fi + HTTPS는 대안입니다. |
| 로봇 제어 | 그립 버튼을 누르고 있는 동안만 팔이 따라오는 **클러치 방식의 상대 자세 추종**을 사용하며, **양팔을 동시에** 제어합니다. IK는 기존 IsaacLab `DifferentialIKController`를 절대 자세 모드로 사용합니다. |
| 재사용 | 장면, 카메라 3대, `success_original`, `EpisodeRecorder`, LeRobot export, 검증 스크립트를 그대로 사용합니다. |
| 데이터 호환성 | `observation.state`·`action`(18차원)과 카메라 구성이 키보드 데이터와 같으므로, 두 데이터를 함께 학습에 쓸 수 있습니다. 조작 장치는 메타데이터와 `robot_type`으로 구분합니다. |

### 다른 방식을 기본으로 택하지 않은 이유

| 방식 | 판단 |
|---|---|
| IsaacLab OpenXR + CloudXR | IsaacLab의 XR 텔레오퍼레이션은 CloudXR 런타임과 `ManagerBasedEnv` 구조를 전제로 합니다. 현재 수집기는 `World`와 `SingleArticulation`을 직접 사용하므로 수집기 전체를 다시 작성해야 하고, Quest 2가 공식 지원 기기인지도 불확실합니다. |
| ALVR + SteamVR (Linux) | Linux에서 설정과 안정성 부담이 큽니다. |
| `oculus_reader` APK ([rail-berkeley/oculus_reader](https://github.com/rail-berkeley/oculus_reader)) | DROID 등에서 Quest 2 컨트롤러 pose를 읽는 데 검증된 방식입니다. 다만 헤드셋 안에 영상을 띄울 수 없어 모니터를 보며 조작해야 합니다. **2단계에서 WebXR 양손 입력이 불안정할 때 쓰는 대안**으로 둡니다. |

---

## 1. 전체 구조

```text
┌──────────── Meta Quest 2 ────────────┐
│ Quest Browser (http://localhost:8012) │
│  - WebXR: 좌/우 컨트롤러 pose, 버튼   │
│  - 시뮬레이션 카메라 영상 패널 표시    │
└───────────────┬───────────────────────┘
                │ USB-C (adb reverse tcp:8012)
                ▼
┌───────── PC: vr_bridge 프로세스 ────────┐
│ Vuer 서버 (asyncio, 별도 프로세스)       │
│  CONTROLLER_MOVE / CAMERA_MOVE 수신      │
│  → 공유 메모리 (pose, 버튼, 수신 시각)   │
│  ← 공유 메모리 (JPEG로 보낼 카메라 영상) │
└───────────────┬─────────────────────────┘
                ▼
┌──────── PC: collect_vr.py (Isaac Sim) ────────┐
│ 좌표 변환 → 방향 보정 → 클러치 → 양팔 IK      │
│ → 18개 관절 목표 → World.step                  │
│ EpisodeRecorder → success_original 자동 저장   │
│ → export (LeRobot v3: data/ meta/ videos/)     │
└────────────────────────────────────────────────┘
```

Vuer 서버는 **별도 프로세스**로 실행합니다. Isaac Sim의 Kit도 메인 스레드에서 자체 이벤트 루프를 돌리므로, 두 asyncio 루프를 한 프로세스에 넣으면 충돌하거나 멈출 수 있습니다. LW-BenchHub의 `OpenTeleVision`도 `multiprocessing.Process`와 공유 `Array`로 같은 방식을 씁니다. 브리지는 `SimulationApp` 생성 **전에** `spawn` 방식으로 시작합니다.

---

## 2. 단계별 로드맵

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| **0** | 기존 키보드 파이프라인 점검 | T1 한 episode 저장 후 `validate_keyboard_dataset.py` 통과 |
| **1** | Quest 2 기기 설정 | `adb devices`에 `device`로 표시되고, WebXR 예제에서 양손 추적 확인 |
| **2** | PC–Quest 연결과 입력 확인 (시뮬레이터 없이) | 좌/우 pose와 버튼이 5분 이상 끊김 없이 수신 |
| **3** | 좌표 변환과 클러치 로직 작성 (시뮬레이터 없이) | 손을 앞/왼쪽/위로 움직이면 로봇 기준 +x/+y/+z로 변환됨. 단위 테스트 통과 |
| **4** | `collect_vr.py`: Isaac Sim에서 양팔 VR 제어 (기록 없이) | 양팔 동시 조작, 그리퍼 동작, 튐 없음. 모니터를 보며 T1 수행 가능 |
| **5** | 헤드셋 안에 시뮬레이션 영상 표시 | 헤드셋을 쓴 채로 T1 수행 가능, 체감 지연 허용 범위 |
| **6** | 기록·저장 연결, export 일반화 | VR로 T1 episode 저장, 검증 스크립트 통과, LeRobot 로더로 읽힘 |
| **7** | T1 파일럿 → T1~T10 본 수집 | Task별 목표 수량 달성 |

---

## 3. 단계 0 — 기존 키보드 파이프라인 점검

VR 작업 중 문제가 생겼을 때 원인이 VR 쪽인지 기존 수집 경로인지 구분하려면, 기존 경로부터 확인해 둡니다.

```bash
conda activate lerobot-arena
cd /home/cai/lightwheel_rby1_transfer
./run_python.sh scripts/project_paths.py
./collect_keyboard.sh --task T1 --fps 20 --output "$HOME/datasets/RBY1-T1-Keyboard-Pilot"
./run_python.sh scripts/validate_keyboard_dataset.py --root "$HOME/datasets/RBY1-T1-Keyboard-Pilot"
```

그리고 루프 한 번의 실제 소요 시간(실시간 대비 속도)을 기록해 둡니다. VR 조작감은 이 값에 크게 좌우됩니다. 시뮬레이션이 실시간보다 느리면 로봇이 손을 늦게 따라옵니다. 4단계에서 이 값을 화면에 표시합니다.

---

## 4. 단계 1 — Meta Quest 2 설정

### 1-1. 기본 준비
1. 헤드셋 펌웨어와 Meta Quest Browser를 최신으로 업데이트합니다. 헤드셋은 스마트폰의 **Meta Horizon 앱**(구 Oculus 앱)과 연결되어 있어야 합니다.
2. 컨트롤러 배터리를 확인합니다. 배터리가 약하면 추적이 끊깁니다.
3. 경계(Guardian)는 **고정형(Stationary) 경계**로 설정합니다. 앉거나 서서 제자리에서 조작하면 됩니다.

### 1-2. 개발자 모드 (USB 연결에 필요)
1. <https://developers.meta.com> 에 로그인하여 **조직(Organization)**을 만듭니다(무료). 계정 인증(전화번호 등)을 요구할 수 있습니다.
2. Meta Horizon 앱 → 기기 → 헤드셋 설정 → **개발자 모드** 켜기 → 헤드셋 재부팅.

### 1-3. PC에 adb 설치 (현재 이 PC에는 설치되어 있지 않음)
```bash
sudo apt update
sudo apt install -y adb android-sdk-platform-tools-common   # 두 번째 패키지는 udev 권한 규칙
sudo usermod -aG plugdev $USER                              # 적용하려면 로그아웃 후 다시 로그인
```
USB-C **데이터** 케이블로 Quest를 연결합니다(충전 전용 케이블은 인식되지 않습니다). 헤드셋 안에 뜨는 **"USB 디버깅 허용"** 창에서 "이 컴퓨터에서 항상 허용"을 선택합니다.
```bash
adb devices
# 1WMHH8xxxxxxx   device     ← 'unauthorized'이면 헤드셋 안의 허용 창 확인
#                            ← 'no permissions'이면 udev/plugdev 설정 확인
```

### 1-4. 헤드셋 설정 (조작 편의)
- **손 추적 자동 전환 끄기**: 설정 → 움직임 추적 → 손 및 바디 추적에서 "손과 컨트롤러 자동 전환"을 끕니다. 컨트롤러를 내려놓는 순간 손 추적으로 바뀌어 pose가 끊기는 일을 막습니다. 메뉴 이름은 펌웨어마다 다를 수 있습니다.
- **자동 절전 시간 늘리기**: 설정 → 시스템 → 전원.
- (선택) **근접 센서 끄기**: 헤드셋을 이마 위로 올리고 모니터를 볼 때(4단계) 화면이 꺼지지 않게 합니다. 재부팅하면 원래대로 돌아옵니다. **[기기 확인 필요]**
  ```bash
  adb shell am broadcast -a com.oculus.vrpowermanager.prox_close        # 끄기
  adb shell am broadcast -a com.oculus.vrpowermanager.automation_disable # 되돌리기
  ```

### 1-5. WebXR 자체 동작 확인
Quest Browser에서 <https://immersive-web.github.io/webxr-samples/input-tracking.html> 을 열고 **Enter VR**을 누릅니다. 양쪽 컨트롤러 모델이 손을 따라 움직이면 됩니다. 이 단계에는 Quest의 인터넷 연결이 필요합니다.

**완료 기준:** `adb devices`에 `device`가 표시되고, WebXR 예제에서 양손이 추적됩니다.

---

## 5. 단계 2 — PC–Quest 연결과 입력 확인 (시뮬레이터 없이)

`~/quest2-webxr-test/quest_input_check.py`는 이미 방향이 맞습니다. **`MotionControllers` 컴포넌트 하나에 `left=True, right=True`**를 지정하는 방식입니다. LW-BenchHub의 `opentelevision.py`는 컨트롤러 컴포넌트를 두 개 만들며, 그 코드에 "Quest에서는 브라우저가 멈춘다"는 주석이 있습니다. 이 단계의 핵심은 **양손 동시 입력이 안정적인지 확인하는 것**입니다.

### 2-A. USB 연결 (권장)
```bash
adb reverse tcp:8012 tcp:8012     # Quest의 localhost:8012 → PC의 8012 포트
adb reverse --list                # 확인
```
USB 모드에서는 인증서가 필요 없으므로, 테스트 스크립트의 `Vuer(...)`에서 `cert`/`key` 인자를 빼고 실행합니다.
```bash
conda activate lerobot-arena
cd ~/quest2-webxr-test
python quest_input_check.py
```
Quest Browser에서 다음 주소를 엽니다. vuer 0.0.70은 웹 클라이언트를 같은 포트의 `/` 경로로 제공하므로 **Quest에 인터넷 연결이 없어도 됩니다.**
```text
http://localhost:8012/?ws=ws://localhost:8012
```
페이지가 열리면 **Enter VR**을 누릅니다. **[기기 확인 필요]** `?ws=` 없이 `http://localhost:8012`만으로도 연결되는지 확인합니다.

### 2-B. Wi-Fi 연결 (대안)
PC(현재 `192.168.1.7`, Wi-Fi)와 Quest를 같은 공유기에 연결하고, IP가 포함된 인증서를 사용합니다.
```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout key.pem -out cert.pem -subj "/CN=rby1-vr" \
  -addext "subjectAltName=IP:192.168.1.7"
```
Quest에서 `https://192.168.1.7:8012/?ws=wss://192.168.1.7:8012`에 접속하고 인증서 경고를 수락합니다. 무선 연결은 지연과 끊김이 생길 수 있고, 연구실 공유기의 단말 간 격리 설정이나 방화벽(`sudo ufw allow 8012/tcp`)도 확인해야 합니다. 따라서 **본 수집은 USB 연결을 권장합니다.**

### 2-C. 확인 항목

| 항목 | 기준 |
|---|---|
| 이벤트 수신율 | `Controller events` 약 60~90/s(헤드셋 주사율 수준), 양쪽 모두 `age` < 0.1s |
| 좌/우 구분 | 왼손만 움직이면 `left`만 변함 |
| 위치 단위와 축 | 손을 위로 10cm 올리면 `position[1]`(WebXR의 y)이 약 +0.1 증가 |
| 버튼 이름 | 트리거 → `triggerValue`, 그립 → `squeezeValue`, 오른손 A/B → `aButton`/`bButton`, 왼손 X/Y → 왼손 상태의 `aButton`/`bButton`으로 들어오는지 **[기기 확인 필요]** |
| 안정성 | 양손을 5분간 계속 움직여도 브라우저가 멈추지 않음 |
| 복구 | 컨트롤러를 가렸다가 다시 보이게 해도 수신이 재개됨. 브라우저를 새로 고쳐도 서버가 다시 연결됨 |

양손 입력이 안정적이지 않으면, WebXR 경로를 계속 조정하기보다 `oculus_reader` 대안을 검토합니다. 이 경우 4단계의 모니터 보기 방식으로 수집합니다.

**완료 기준:** 위 표의 항목을 모두 통과합니다.

---

## 6. 단계 3 — 좌표 변환과 클러치 (Isaac 없이 작성·테스트)

Isaac Sim 없이 테스트할 수 있도록 순수 NumPy 모듈 `scripts/vr_teleop.py`로 작성합니다.

### 3-1. 좌표계

| 좌표계 | 축 |
|---|---|
| WebXR (Vuer가 전달) | 오른손 좌표계, **Y 위, −Z 앞**, 단위 m, 4×4 행렬을 열 우선(column-major) 16개 값으로 전달 → `np.reshape(v, (4,4), order="F")` |
| RB-Y1 로봇 기준 | **X 앞, Y 왼쪽, Z 위**. 키보드 수집기의 IK와 같은 좌표계입니다. Pinocchio 모델의 기준 좌표계이며, [collect_keyboard.py:372-377](../scripts/collect_keyboard.py#L372-L377)의 `LOCAL_WORLD_ALIGNED` 자코비안이 이 좌표계를 씁니다. |

```python
M = np.array([[0, 0, -1, 0],     # robot x = -xr z (앞)
              [-1, 0, 0, 0],     # robot y = -xr x (왼쪽)
              [0, 1, 0, 0],      # robot z =  xr y (위)
              [0, 0, 0, 1]])     # LW-BenchHub consts.grd_yup2grd_zup과 같은 행렬
T_robot = M @ T_xr @ M.T         # pose 전체(위치와 회전)를 로봇 축으로 변환
```

### 3-2. 정면 방향 보정
WebXR의 "앞"은 VR에 들어간 순간 헤드셋이 향한 방향입니다. 조작자가 비스듬히 앉아 있으면, 손을 앞으로 뻗어도 로봇 팔은 대각선으로 움직입니다.
- 기본: 조작자가 정면을 본 상태에서 **Meta 버튼을 길게 눌러 재중심(recenter)**합니다.
- 소프트웨어 보정: 보정 버튼을 누른 순간의 헤드 pose(`CAMERA_MOVE`)에서 yaw만 뽑아 `Rz(-yaw)`를 이후 모든 컨트롤러 pose에 곱합니다. 로봇 좌표로 변환한 뒤 `yaw = atan2(R[1,0], R[0,0])`으로 구합니다.

### 3-3. 클러치 기반 상대 추종 (팔마다 독립 적용)
컨트롤러의 방 안 절대 위치를 로봇 손 위치로 그대로 쓰지 않습니다.

```text
그립을 누르는 순간(t0):  C0 = 컨트롤러 pose,  E0 = 현재 목표 말단 pose (self.target의 FK)
그립을 누르고 있는 동안:  p* = p_E0 + s · (p_C − p_C0)
                        R* = (R_C · R_C0ᵀ) · R_E0        ← 로봇 기준 좌표계에서의 회전 변화량
그립을 떼면:            목표 유지 (팔 정지). 손을 편한 곳으로 옮긴 뒤 다시 잡으면 이어서 조작
```
- 회전 변화량을 로봇 기준 좌표계에서 적용하므로, **컨트롤러와 그리퍼 사이의 자세 오프셋 상수가 필요 없습니다.** LW-BenchHub `consts.py`의 `controller2gripper_*` 같은 값을 따로 맞출 필요가 없습니다.
- `s`(동작 배율)의 기본값은 1.0이며, 정밀 작업을 위해 `--motion-scale` 인자로 조정할 수 있게 합니다.
- 안전장치:
  - 입력 수신 후 **0.2s 이상** 지나거나 값이 NaN이거나 추적이 끊기면 클러치를 자동으로 해제하고 목표를 유지합니다.
  - 목표 위치를 작업 공간 상자 안으로 제한합니다.
  - 손떨림을 줄이도록 필요하면 약한 저역통과 필터를 적용합니다(위치 EMA α≈0.5, 회전은 slerp).
  - 관절 속도 제한은 기존 수집기와 같습니다.
- 버튼은 **에지 검출**(눌림 순간 1회)과 **길게 누르기**(≥1s) 판정을 이 모듈에서 처리합니다.

### 3-4. 단위 테스트 (`scripts/test_vr_teleop.py`)
- WebXR에서 앞/왼쪽/위로 0.1m 이동하면 로봇 좌표로 +x/+y/+z 0.1m가 됩니다.
- 클러치를 누른 순간에는 목표가 변하지 않습니다(점프 없음).
- 클러치를 놓았다가 다시 잡아도 목표가 연속적입니다.
- yaw 보정 후 비스듬한 방향에서 앞으로 이동해도 +x로 변환됩니다.
- 입력이 오래되면 클러치가 해제됩니다.

**완료 기준:** 단위 테스트를 통과합니다. 또한 2단계 스크립트에 변환 결과를 출력하게 하여, 실제 손동작과 로봇 좌표계 방향이 일치하는지 확인합니다.

---

## 7. 단계 4 — `collect_vr.py`: Isaac Sim에서 양팔 VR 제어

기존 [collect_keyboard.py](../scripts/collect_keyboard.py)는 **수정하지 않고**, 이를 바탕으로 `scripts/collect_vr.py`를 새로 만듭니다. 기능이 안정된 뒤 공통 부분을 모듈로 분리합니다.

### 4-1. 기존 코드에서 바꿀 부분

| 기존 위치 | 변경 |
|---|---|
| `Keyboard` 클래스와 `self.keyboard` (L119-160, L227-248) | `VRInput`(브리지 공유 메모리 읽기와 `vr_teleop`)으로 교체합니다. 보조자용 명령(ESC 종료 등)을 위해 키보드는 남겨 둡니다. |
| IK 설정 (L206-215) | `use_relative_mode=False`로 절대 자세 목표를 사용합니다. **팔마다 컨트롤러 인스턴스를 하나씩** 둡니다. |
| `action()` (L364-399) | 한쪽 팔(`self.side`)만 처리하던 것을 **양팔 모두 매 스텝 처리**하도록 바꿉니다. 클러치가 눌린 팔만 IK를 풀고, 나머지 팔은 목표를 유지합니다. 관절 속도 제한과 손가락 처리 코드는 그대로 사용합니다. |
| 그리퍼 | 트리거 **히스테리시스**(닫힘 > 0.6, 열림 < 0.4)로 `grip_open[side]`를 설정합니다. 이후의 손가락 목표 처리 코드는 그대로 사용합니다. |
| `command()` (L481-520) | 같은 명령 이름(`start`/`discard`/`pause`/`stop`/`quit`)을 VR 버튼으로 호출합니다. `recenter`를 추가하고, `switch`는 쓰지 않습니다. |
| 출력 이름과 호환성 검사 (L43-87) | 기본 출력은 `Lightwheel-Tasks-RBY1-{task}-VR-Quest2`, `robot_type`은 `rby1_isaac_vr`로 정합니다. |
| UI 라벨 (L308-321, L653) | 양팔의 클러치·그리퍼 상태, 입력 지연, 실시간 대비 속도를 표시합니다. |

`action()`의 핵심 변경 예시(개념 코드):
```python
for side in ("left", "right"):
    goal = self.vr.target_pose(side, current=self.target_pose(side))  # 클러치 해제 시 None
    if goal is None:
        continue
    ids = self.arms[side]
    jac = pin.getFrameJacobian(self.model.model, self.model.data,
                               self.model.frame[side], pin.LOCAL_WORLD_ALIGNED)[:, self.qidx[ids]]
    pose = self.model.pose(side)                       # ee()에서 측정 q로 FK/자코비안 계산 완료
    self.ik[side].set_command(goal_pos_quat)           # 절대 자세 (x,y,z,qw,qx,qy,qz)
    cand = self.ik[side].compute(cur_pos, cur_quat, jac, q[ids])
    limit = a.joint_speed / a.fps
    self.target[ids] = np.clip(cand, self.target[ids] - limit, self.target[ids] + limit)
```

### 4-2. 권장 초기 설정
- `--fps 20`으로 시작합니다. 50fps에서는 루프마다 20ms(시뮬레이션 시간)에 한 번씩 렌더링하므로, 카메라 3대와 레이트레이싱 렌더링이 따라가지 못하면 시뮬레이션이 실시간보다 느려집니다. 화면에 표시한 실시간 대비 속도를 보고 결정합니다.
- `--joint-speed`는 키보드 기본값 0.8 rad/s가 VR에서는 느리게 느껴질 수 있으므로 1.0~1.5 rad/s 범위에서 조정합니다.

### 4-3. 이 단계의 조작 방식: 모니터 보기
헤드셋 안에 영상을 띄우는 기능(5단계)이 없으므로, 먼저 **모니터를 보며** 제어부만 검증합니다.
- 헤드셋을 이마 위로 올리거나, 책상 위에 손 쪽을 향하게 둡니다. 컨트롤러는 헤드셋 카메라에 보이는 범위에서만 추적됩니다.
- 근접 센서를 끄지 않으면 화면이 꺼지면서 WebXR 세션이 일시정지됩니다(1-4 참고).

**완료 기준:** 양팔을 동시에 움직일 수 있고, 클러치를 다시 잡아도 팔이 튀지 않으며, 추적이 끊기면 팔이 정지합니다. 모니터를 보며 T1을 끝까지 수행할 수 있습니다. 이 단계에서는 기록하지 않습니다.

---

## 8. 단계 5 — 헤드셋 안에 시뮬레이션 영상 표시

- 시뮬레이터가 매 스텝 렌더링한 카메라 이미지를 공유 메모리에 쓰고, 브리지 프로세스가 JPEG(quality 60~80)로 압축해 Vuer로 약 15~30Hz로 보냅니다. 방식은 `ImageBackground`(머리에 고정) 또는 `ImagePlane`(공간에 고정)입니다. LW-BenchHub `opentelevision.py`의 `main_image`에 주석 처리된 예시 코드가 있습니다.
- 권장 구성: 헤드 카메라 640×480을 크게, 좌/우 손목 카메라를 320×240으로 작게 붙여 **1280×480 한 장**으로 보냅니다. 머리를 돌려도 따라오지 않는 **공간 고정 패널**(약 1.5m 앞)이 멀미가 덜합니다.
- 헤드 카메라는 한 대이므로 입체 영상이 아닌 2D 패널로 표시합니다. 로봇 머리는 헤드셋 움직임을 따라 돌리지 않습니다. 현재 모델에서 제어하는 관절은 양팔 14개와 손가락 4개, 총 18개입니다.
- 현재 `capture()`는 기록 중에만 호출되고, 시각이 어긋나면 예외를 냅니다. 영상 표시용으로는 기록 중이 아닐 때도 이미지를 가져오되, 예외를 내지 않는 별도 경로를 둡니다.
- 녹화 중, 성공, 저장 중, 추적 끊김 같은 상태를 영상 위에 글자로 겹쳐 표시합니다. 저장·변환 중에는 시뮬레이션이 멈추므로, 헤드셋 안에서도 알 수 있어야 합니다.

**완료 기준:** 헤드셋을 쓴 채로 T1을 수행할 수 있고, 조작자가 영상 지연을 불편하지 않다고 판단합니다.

---

## 9. 단계 6 — 기록·저장 연결과 export 일반화

### 6-1. 기록 순서 (키보드 수집기와 동일하게 유지)
시점 t의 측정 상태와 카메라 3대 영상을 기록하고, 같은 시점의 VR 입력으로 계산한 action을 적용한 뒤, 1/fps초만큼 시뮬레이션을 진행합니다. VR 입력은 **제어 스텝마다 한 번 가져와서** 기록합니다. 헤드셋 주사율(72/90Hz)을 데이터 FPS로 쓰지 않습니다.

### 6-2. 저장 feature (기존 feature 모두 유지 + 조작 입력 변경)

| feature | 내용 |
|---|---|
| `observation.state`, `action`, `observation.velocity`, `observation.ee_pose`, `success_original`, `observation.sim_time`, `observation.camera_time`, 카메라 3대 | **기존과 동일** |
| `teleop.command` (VR 스키마) | 팔별 [클러치, 트리거 값, 그리퍼 열림, 목표 위치 xyz, 목표 쿼터니언 wxyz] = 2×10 = **20차원** |
| raw 기록에만 저장 | 컨트롤러와 헤드의 원시 4×4 행렬, 버튼 전체, 입력 수신 지연, 보정 yaw |

학습용 `action`에는 기존과 마찬가지로 **시뮬레이터에 실제로 보낸 18차원 관절 목표**를 저장합니다. 컨트롤러 pose는 조작 입력 기록으로만 보관합니다.

### 6-3. export 코드 수정 (키보드 데이터와 호환 유지)
[export_keyboard_episode.py](../scripts/export_keyboard_episode.py)는 `robot_type`과 이름이 키보드로 고정되어 있습니다.

| 위치 | 수정 |
|---|---|
| L56 `repo_id=f"local/RBY1-{task}-Keyboard-Original"` | episode 메타데이터에서 읽습니다 |
| L78 `assert ... robot_type == "rby1_isaac_keyboard"` | `m.get("robot_type", "rby1_isaac_keyboard")`과 비교합니다 |
| L92 `robot_type="rby1_isaac_keyboard"` | 위와 같은 값을 사용합니다 |
| L134-155 `keyboard_collection.json` | `teleop_device`, `motion_scale`, 보정값을 추가합니다 |
| L156-158 README 문구 | 조작 장치에 따라 문구를 바꿉니다 |

`meta/keyboard_episodes.json`과 `meta/keyboard_collection.json` 파일 이름은 **당분간 그대로 둡니다.** 그래야 [validate_keyboard_dataset.py](../scripts/validate_keyboard_dataset.py)를 수정 없이 재사용할 수 있습니다. 이름 정리는 VR 수집이 안정된 뒤 진행합니다.

### 6-4. 검증
```bash
./run_python.sh scripts/validate_keyboard_dataset.py --root "$HOME/datasets/Lightwheel-Tasks-RBY1-T1-VR-Quest2"
```
검증 스크립트는 raw 기록과 LeRobot 데이터의 일치, 영상 프레임 수와 시각, `success_original` 재계산을 확인합니다. 저장된 영상도 몇 개 직접 열어 실제로 작업을 완료했는지 확인합니다.

**완료 기준:** VR로 T1 episode 3개 이상을 저장하고, 검증 스크립트를 통과하며, `LeRobotDataset`으로 로드됩니다.

---

## 10. 단계 7 — 수집 절차

### 10-1. 실행 (구현 완료 후 예상 명령)
```bash
conda activate lerobot-arena
cd /home/cai/lightwheel_rby1_transfer
adb reverse tcp:8012 tcp:8012
./collect_vr.sh --task T1 --fps 20
# Quest Browser: http://localhost:8012/?ws=ws://localhost:8012 → Enter VR
```

### 10-2. 버튼 매핑 (제안, 4단계에서 확정)

| Quest 2 입력 | 기능 | 키보드 대응 |
|---|---|---|
| 왼/오른 **그립** 누르는 동안 | 해당 팔 클러치(손을 따라 움직임) | W/S/A/D/Q/E + 회전 키 |
| 왼/오른 **트리거** | 해당 그리퍼 닫기(떼면 열림) | K |
| 오른손 **A** | 기록 시작 | B |
| 오른손 **B** 1초 길게 | 기록 폐기 + 장면 초기화 | Backspace / R |
| 왼손 **X** | 일시정지 / 재개 | P |
| 왼손 **Y** 1초 길게 | 정면 방향 재보정 | — |
| (자동) | `success_original` 충족 시 자동 저장 | Enter |
| PC 키보드 ESC | 종료 | ESC |

Meta 버튼은 시스템이 사용하므로 매핑하지 않습니다.

### 10-3. episode 진행 순서
1. 장면이 초기화되면 정면을 보고 방향을 보정합니다(Y 길게 누르기 또는 Meta 버튼 재중심).
2. 그립을 잡고 양팔을 조금씩 움직여 방향이 맞는지 확인한 뒤, 그립을 놓아 팔을 준비 자세 근처에 둡니다.
3. **A로 기록을 시작합니다.** 물체에 접근하기 전에 시작해야 접근·파지·운반·놓기가 모두 기록됩니다.
4. 작업을 수행합니다. 손이 불편한 위치에 오면 그립을 놓고 손을 옮긴 뒤 다시 잡습니다.
5. `success_original`이 충족되면 자동으로 저장되고 장면이 초기화됩니다. 실패한 시도는 B를 길게 눌러 폐기합니다.

### 10-4. 수집 순서

| 순서 | Task | 확인할 점 |
|---|---|---|
| 1 | **T1** 그릇 → 접시 (파일럿 5~10개) | 전체 경로, 조작감, fps와 속도 파라미터 확정 |
| 2 | T2, T3 | 물체 높이와 파지 자세 |
| 3 | T4, T5, T6 (서랍·전자레인지·스토브) | 접촉하며 당기거나 돌리는 동작 |
| 4 | T8 그릇 쌓기 | 정밀 배치 (`--motion-scale` 0.5~0.7 검토) |
| 5 | T7, T9, T10 | 긴 episode, 여러 단계로 된 작업 |

한 출력 폴더에는 같은 task, fps, 해상도, 데이터 스키마만 추가할 수 있습니다(기존 수집기 규칙). **파일럿 이후 fps와 스키마를 고정한 다음** 본 수집을 시작합니다.

주의: 현재 자동 저장은 성공 조건을 **처음 충족한 프레임**에서 바로 이루어집니다. 물체를 놓은 뒤 팔이 빠지는 구간까지 학습에 필요하면, 성공 후 N초를 더 기록하는 옵션(`--post-success-seconds`)을 6단계에 추가합니다.

---

## 11. 추가·수정할 파일

| 파일 | 구분 | 내용 |
|---|---|---|
| `scripts/vr_bridge.py` | 신규 | Vuer 서버 프로세스와 공유 메모리 인터페이스. 단독으로 실행하면 2단계 입력 확인 모드로 동작 |
| `scripts/vr_teleop.py` | 신규 | 좌표 변환, 방향 보정, 클러치, 버튼 에지와 길게 누르기 판정 (Isaac 비의존) |
| `scripts/test_vr_teleop.py` | 신규 | 3단계 단위 테스트 |
| `scripts/collect_vr.py` | 신규 | `collect_keyboard.py`를 바탕으로 만든 VR 수집기 |
| `collect_vr.sh` | 신규 | 실행 스크립트 (`collect_keyboard.sh`와 같은 형식) |
| `scripts/export_keyboard_episode.py` | 수정 | `robot_type`, `repo_id`, README, 수집 메타데이터를 episode 메타데이터에서 읽도록 변경 (키보드 데이터와 호환 유지) |
| `README.md` | 수정 | VR 수집 절 추가 |

---

## 12. 위험 요소와 대응

| 위험 | 대응 |
|---|---|
| Quest 브라우저에서 양손 입력 시 멈춤 (LW-BenchHub 주석) | 2단계에서 컨트롤러 컴포넌트 하나로 5분 이상 시험. 실패하면 `oculus_reader`로 전환 |
| 시뮬레이션이 실시간보다 느려 로봇이 늦게 따라옴 | fps 20, 뷰포트 해상도 낮추기, 실시간 대비 속도 표시. 클러치 방식이라 늦게 따라와도 목표 위치는 정확함 |
| 특이점 근처나 관절 한계에서 IK가 흔들림 | DLS(λ=0.03)와 관절 한계·속도 제한은 이미 있음. 필요하면 작업 공간 제한과 영공간 자세 유지 추가 |
| 추적 끊김으로 팔이 튐 | 입력 수신 시각 검사와 클러치 자동 해제, 다시 잡을 때 기준 재설정 |
| 모니터 보기 단계에서 헤드셋 화면 꺼짐 | 근접 센서 끄기(1-4) |
| 멀미와 피로 | 공간 고정 영상 패널, 앉아서 조작, 30~45분마다 휴식 |

---

## 다음 할 일

**단계 0**(키보드 T1 한 episode 저장·검증)과 **단계 1**(Quest 개발자 모드 켜기, `adb` 설치, `adb devices` 확인)을 진행합니다. 두 단계가 끝나면 2단계의 `quest_input_check.py`를 USB 모드로 실행하고, 3단계 코드(`vr_teleop.py`, `vr_bridge.py`) 작성으로 넘어갑니다.
