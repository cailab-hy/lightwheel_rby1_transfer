# RB-Y1의 원본 성공 판정

T1~T10은 LW-BenchHub 커밋 `b2bcb2d00edef691f9fcc49039cbf0bcc7464605`의 `_check_success()`와 공통 판정 함수, fixture 열림/닫힘 함수, `check_success_caller()`를 사용합니다. `success_verified`는 구현하거나 사용하지 않습니다.

이것은 확인 가능한 공개 코드 버전의 원본 조건을 RB-Y1에 연결한 것입니다. 모든 X7S 시연의 수집 당시 task 코드 커밋이 확인된 것은 아니므로 역사적 수집 코드와의 완전 동일성을 주장하지 않습니다. 물체 배치·책상 높이는 기존 RB-Y1 적응 장면을 유지합니다.

## 실행과 저장

```bash
~/lightwheel_rby1_transfer/collect_t1_keyboard.sh
~/lightwheel_rby1_transfer/collect_keyboard.sh --task T7
```

`B`로 기록 시작 → 작업 수행 → 양손을 물체에서 충분히 뒤로 이동 → 원본 성공 판정이 True가 되면 자동 저장하고 장면 초기화.
`Enter`는 성공을 만들어 주지 않습니다. 성공이 아니면 저장을 거부하고 수집을 계속합니다. `P`는 물리·기록·판정 카운트를 함께 멈춥니다. `Backspace` 또는 `R`은 미저장 기록을 폐기하고 장면을 초기화합니다.

기본 출력: `~/datasets/Lightwheel-Tasks-RBY1-T<n>-Keyboard-Original/` (LeRobot data/meta/videos).
기존 수동 성공 라벨 데이터에는 이어 쓰지 않습니다. 출력 task·판정 버전·장면 매핑·fps·영상 크기의 호환성을 검사합니다.

## 원본 조건

| Task | 조건 요약 |
|---|---|
| T1 | 그릇–접시 수평 거리 < 접시 horizontal_radius, 양손–그릇 > 0.25 m |
| T2 | 목표 그릇–접시 수평 거리 < 0.08 m, 높이 차 0.01~0.15 m, 속도 벡터 norm < 0.05, 양손–그릇 > 0.25 m |
| T3 | 케첩–바구니 수평 거리 < 작은 수평 크기×0.4, 절대 수직축 내적 > 0, 속도 norm < 0.5, 양손–두 대상 > 0.25 m |
| T4 | 위 서랍 열림 비율 ≥ 0.5, 양손–fixture 모든 body COM > 0.4 m |
| T5 | microjoint 열림 비율 ≥ 0.6, 양손–fixture 모든 body COM > 0.25 m |
| T6 | 노브 각도 modulo 2π가 [0.35, 2π−0.35] 안에 있음, 양손–fixture 모든 body COM > 0.3 m |
| T7 | 첫 서랍 관절 열림 비율 ≥ 0.3, 그릇 bbox의 fixture 내부 영역 판정 통과, 양손–그릇 > 0.25 m |
| T8 | 가운데–뒤 그릇 수평 거리 < 받침 그릇 작은 수평 크기×1.0, 절대 수직축 내적 > 0.5, 속도 norm < 0.5, 양손–두 대상 > 0.3 m |
| T9 | 마지막 서랍 관절 열림 비율 ≤ 0.005, 그릇 bbox의 fixture 내부 영역 판정 통과, 양손–그릇 > 0.25 m |
| T10 | 수프와 토마토소스 각각에 T3와 같은 바구니 배치 조건을 적용하여 AND |

공통 gripper_obj_far는 양손 모두와 대상의 모든 body COM을 검사하며, 왼쪽·오른쪽 대표 손가락의 net contact force norm < 0.1 N도 검사합니다. X7S의 left_gripper_contact/right_gripper_contact에 대응하도록 RB-Y1 finger_l1/finger_r1의 실제 PhysX 접촉력을 사용합니다. 두 번째 손가락에 대한 추가 조건은 넣지 않습니다.

원본 `horizontal_radius`는 reg_main/reg_bbox 수평 반크기 벡터의 norm입니다. 렌더된 원형 접시의 반지름이나 AABB 반폭으로 바꾸지 않았습니다. 현재 USD의 물체 스케일을 적용합니다.
원본 속도 계산도 유지합니다. rigid object 경로는 `[선속도3, 각속도3]`의 norm을 사용하며, T3의 fixture 경로는 root 선속도만 사용합니다.

T1 및 T3/T8/T10에 원본에 없는 높이·지지 접촉 검사를 추가하지 않았습니다. T7/T9는 원본 StorageFurniture가 제공하는 int0..int4 영역을 검사합니다. 이 클래스는 서랍 관절에 따른 per_env_offset 업데이트를 구현하지 않으므로 초기 fixture 기준 영역을 유지하며, 대상 서랍 내부만으로 제한하는 보정도 하지 않습니다. 원본의 내부 영역 bbox 허용 오차 계산까지 그대로 사용합니다.

## 시간 처리

- 첫 10 control step은 성공 결과 억제.
- TELEOP에서 원본처럼 `int(1 / physics_dt / 2)`회 지연: 현재 physics_dt=0.01 → 50회.
- 한 번 조건이 참이면 latch하여 카운트를 진행. 연속 참 조건으로 변경하지 않음.
- 50 Hz에서는 약 1초, 25 Hz에서는 약 2초에 해당. 판정은 control tick마다 한 번 진행.
- 새 episode 시작·장면 리셋 시 카운터 초기화. 일시정지·영상 인코딩 중에는 진행하지 않음.

## 구현과 재현

- `scripts/vendor/original_predicates.py`: 원본 함수 본문을 AST로 추출. Apache-2.0 원저작권 및 라이선스 유지.
- `scripts/vendor/source_manifest.json`: 소스 커밋 및 파일 SHA256.
- `scripts/success_original.py`: standalone USD/PhysX 상태를 원본 함수 입력으로 변환. COM/관성 프레임 quaternion, 선·각속도, 양손 TCP, fixture 관절, 접촉력 사용.
- `scripts/collect_keyboard.py`: T1~T10 수집 및 자동 저장.
- `scripts/run_environment.py`: ready pose로 장면 실행하면서 자동 판정 상태 출력.
- `scripts/replay_success_original.py`: 저장된 raw `success_state.jsonl`로 성공 판정 재계산.

LeRobot의 프레임별 `success_original`은 int64 `[0/1]`입니다. `meta/keyboard_episodes.json`의 `success_original`과 호환용 `success`는 같은 값이며, `success_label_source=success_original`입니다. 별도 수동 라벨이나 두 번째 성공 기준은 없습니다. 판정 입력 snapshot은 raw journal에 저장하고, 원본 함수 SHA256 및 물체·관절·영역 매핑은 metadata에 저장합니다.

## 검사

- `scripts/test_success_original.py`: 각 task의 성공/실패/임계값·힘·양손 거리·원본 latch 처리 검사.
- `scripts/validate_success_sim.py`: T1~T10의 실제 PhysX 상태 읽기, 초기 실패 확인, 실제 장면 geometry를 사용한 합성 성공/실패 검사.
- `--smoke-test`: 실제 키보드 callback으로 이동·회전·일시정지·저장/폐기 경로 검사. 테스트에서만 실패 episode 내보내기를 허용하며 라벨은 False로 유지.
- `--smoke-success-test`: T1 물체를 합성 성공 배치로 이동하여, 성공 전 Enter 저장 거부와 성공 후 자동 저장 확인. 실제 파지 시연이 아니며 is_smoke_test=true로 분리.

검증 결과는 `reports/success_original_validation.json`에 요약합니다. 모든 task의 실제 사람 시연 성공이나 RB-Y1 실기 배포를 검증한 것은 아닙니다.
