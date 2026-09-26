# Lightwheel X7S → RB-Y1 환경·데이터 수집 구현 종합 보고서

- 작성일: 2026-09-25 (KST)
- 작업 디렉터리: `/home/cai/lightwheel_rby1_transfer`
- 범위: 대표 task 선정, X7S 데이터 추출, RB-Y1 장면 구성 및 누락 물체 복원, 리매핑 검토, 키보드 수집, 원본 성공 판정 연결, GUI 키 이벤트 오류 수정
- 기준: 현재 코드·데이터 경로와 기존 검증 기록. 이 문서는 새 실험 결과나 실제 사람의 성공 시연을 추가 생성한 보고서가 아니다.

## 1. 구현 결과와 현재 상태

**현재 구현은 RB-Y1의 T1~T10 장면에서 키보드로 조작하고, `success_original`로 자동 성공 판정한 시연을 LeRobot 형식으로 저장할 수 있는 단계이다.** X7S 원본 시연을 RB-Y1 시연으로 일괄 리매핑하는 작업은 아직 완료되지 않았다.

| 항목 | 상태 | 완료 범위와 제한 |
|---|---|---|
| 대표 task 10개 선정 | 완료 | PaMQR-chunk 선정 PDF의 역할 배분을 유지한 LIBERO 10개 |
| X7S 데이터 추출 | 완료·검증 | 500 episode, 499,643프레임, LeRobot v3, task별 MP4 |
| 원시 HDF5 대응 | 완료·검증 | 500 episode의 수치 배열 대응 및 객체·fixture 상태 확보 |
| RB-Y1 USD 장면 | 완료 | 10개 standalone 장면, 상판 0.72 m, 준비 자세·카메라 반영 |
| 누락 물체 보완 | 완료·목록 검증 | 누락 물체 17개, fixture 9개 복원. 원시 목록 대비 누락 0개 |
| 작업 영역 검토 | 부분 검증 | 대표 목표·손잡이 경로의 IK 검사. 전 구간 충돌·파지 성공 검증은 아님 |
| X7S → RB-Y1 리매핑 | 진단·검토 단계 | 연속성·접촉·물리 성공이 검증된 최종 RB-Y1 시연 미생성 |
| 키보드 조작·수집 | 구현·시험 | 양팔·그리퍼, 기록·일시정지·폐기·자동 저장, 카메라 3개 |
| `success_original` | T1~T10 구현·시험 | 확인한 LW-BenchHub 버전의 원본 조건 및 지연 처리 적용 |
| 문자열 키 이벤트 오류 | 수정·회귀 검사 | 문자열과 enum형 키를 모두 처리하도록 수정 |
| 실제 사람의 task 수행 | 미검증 | 모든 task의 실제 파지·완료 성공을 확인한 것은 아님 |
| 실제 RB-Y1 연결·배포 | 범위 외 | 시뮬레이션 전용. 실기 드라이버 명령으로 바로 사용 불가 |

초기 [전환 검토 보고서](REPORT_KO.md)의 “성공 판정기 미연결” 및 “runner에 성공 판정기 없음”이라는 설명은 이후 구현으로 대체되었다. 반면 “검증된 X7S 리매핑 데이터 미완성”이라는 결론은 현재도 유효하다. 상세 수집 설명은 [키보드 수집 안내서](KEYBOARD_COLLECTION_KO.md), 판정 설명은 [success_original 안내서](SUCCESS_ORIGINAL_KO.md)를 따른다.

## 2. 대표 task 선정

### 2.1 선정 원칙

사용자 제공 `/home/cai/Downloads/task_선정.pdf`의 역할 배분을 유지했다. 기본 집기·놓기, 공간 관계, 물체 변화, 서랍 조작, 회전문 조작, 접촉 작동, 동작 조합, 적층, 긴 순차 동작, 다중 물체 순차 동작을 각각 포함한다. PDF에 없는 추가 정량 선정 기준을 임의로 도입하지 않았다.

LIBERO를 선택한 이유는 기존 PaMQR-chunk 10개 중 8개가 X7S에 동일 task 이름으로 존재하며, 나머지 2개도 같은 실험 역할을 유지하는 대체 task를 선정할 수 있었기 때문이다. 현재의 0.72 m 책상 및 고정 베이스·몸통 환경에서는 기존 실험과의 연속성이 유리하다. RoboCasa의 이동·넓은 주방 조작은 향후 베이스·몸통을 사용하는 별도 실험에서 검토할 수 있다.

### 2.2 선정 목록

모든 task는 50 episode씩 추출했다. T1~T10은 이번 실험에서 부여한 번호이며 원본 전체 데이터셋의 task_index와 다르다.

| Task | Task 이름 | Language Instruction | 역할 | 레이아웃 | 프레임 |
|---|---|---|---|---|---:|
| T1 | L90K1PutTheBlackBowlOnThePlate | put the black bowl on the plate. | Basic Pick-and-Place | libero-1-1 | 25,137 |
| T2 | LSPickUpTheBlackBowlOnTheCookieBoxAndPlaceItOnThePlate | Pick the akita black bowl on the cookies box and place it on the plate. | Spatial Relational Pick-and-Place | libero-8-8 | 42,746 |
| T3 | L90L1PickUpTheKetchupAndPutItInTheBasket | Pick up the ketchup, and put it in the basket. | Object-Variation Pick-and-Place | libero-2-2 | 61,009 |
| T4 | L90K2OpenTheTopDrawerOfTheCabinet | Open the top drawer of the cabinet. | Single-Step Articulated Manipulation | libero-1-1 | 44,498 |
| T5 | L90K7OpenTheMicrowave | Open the microwave. | Articulated Appliance Manipulation | libero-1-1 | 40,753 |
| T6 | LGTurnOnTheStove | Turn on the stove. | Contact / Actuation | libero-8-8 | 11,249 |
| T7 | LGOpenTheTopDrawerAndPutTheBowlInside | Open the top layer of the drawer and put the bowl inside. | Compositional Manipulation | libero-8-8 | 74,724 |
| T8 | L90K2StackTheMiddleBlackBowlOnTheBackBlackBowl | Stack the black bowl in the middle on the black bowl at the back. | Precision Stacking | libero-1-1 | 33,232 |
| T9 | L10K4PutTheBlackBowlInTheBottomDrawerOfTheCabinetAndCloseIt | Put the black bowl in the bottom drawer of the cabinet and close it. | Long-Horizon Sequential Manipulation | libero-1-1 | 88,389 |
| T10 | L10L2PutBothTheAlphabetSoupAndTheTomatoSauceInTheBasket | Pick up the alphabet soup and the tomato sauce, and put them in the basket. | Multi-Object Sequential Manipulation | libero-2-2 | 77,906 |

- T3: 기존 케첩→바구니 task 대신 `L90L1PickUpTheKetchupAndPutItInTheBasket`를 선정했다. 목표 물체·목적지는 같지만 배치·방해 물체가 완전히 같지는 않다.
- T9: 머그를 전자레인지에 넣고 닫는 task 대신, 그릇을 아래 서랍에 넣고 닫는 task를 선정했다. 내부 배치 후 닫는 순차 의존성을 유지하지만 물체와 관절 종류는 다르다.
- 레이아웃은 500개 원시 HDF5의 `layout_id/style_id`로 확인했다. task 이름의 `K2` 등을 레이아웃 번호로 해석하지 않았다.

산출물: [selected_tasks.csv](selected_tasks.csv), [selection.json](selection.json). CSV에는 Task, Task 이름, Language Instruction, 역할, 역할 상세 설명, LIBERO 레이아웃 번호를 포함한다.

## 3. X7S 데이터 추출 및 원시 자료 확보

### 3.1 현재 저장 위치와 구성

원본은 `~/datasets/Lightwheel-Tasks-X7S`이며, **현재 추출본은 `~/datasets/Lightwheel-Tasks-X7S-T1-T10`에 있다.** 이전 보고서와 일부 과거 스크립트의 `~/dataset/Lightwheel-Tasks-X7S-T1-T10` 경로는 현재 존재하지 않는다. 과거 추출 스크립트를 재실행할 때는 출력 경로를 확인해야 한다. 이번 보고서 작성 과정에서 데이터를 이동하지 않았다.

```text
~/datasets/Lightwheel-Tasks-X7S-T1-T10/
├── data/chunk-000/file-000.parquet ... file-009.parquet
├── meta/
│   ├── info.json / stats.json / tasks.parquet
│   ├── episodes/
│   └── 원본 episode 대응 및 선정 메타데이터
└── videos/
    ├── observation.images.first_person/chunk-000/file-000.mp4 ... file-009.mp4
    ├── observation.images.left_hand/chunk-000/file-000.mp4 ... file-009.mp4
    └── observation.images.right_hand/chunk-000/file-000.mp4 ... file-009.mp4
```

| 항목 | 값 |
|---|---:|
| Task | 10개 |
| Episode | 500개 |
| 프레임 | 499,643개 |
| 기록 주파수 | 50 Hz |
| 카메라 | 머리·왼손·오른손 3개 |
| 영상 크기 | 640×480 |
| MP4 | 30개 |
| 데이터 형식 | LeRobot v3.0 |

각 카메라의 `file-000.mp4`는 T1, `file-009.mp4`는 T10이다. 각 MP4에 해당 task의 50 episode가 연결되며 구간 정보는 episode 메타데이터에 저장했다.

X7S의 state 25차원, action 21차원, processed_action 23차원의 값과 순서를 보존했다. episode/task/global index와 파일·영상 offset은 추출본에 맞춰 재계산했다. 영상은 프레임 경계를 맞추기 위해 재인코딩했으므로 원본 MP4와 바이트 단위로 같지는 않다.

### 3.2 검증 결과

전체 수치 배열과 시간·프레임 인덱스의 원본 일치, 30개 MP4의 프레임 수, 원본·추출 영상의 180개 프레임 쌍을 검사했다. 영상 비교의 최대 MSE는 0~255 RGB 척도에서 6.4358이었다. 공식 LeRobot 로더로 데이터셋 길이와 task 경계의 40개 관측을 읽었다. 별도 train/validation/test 분할은 만들지 않았으며 추출본은 전체 train이다.

근거: [수치 일치](reports/numeric_source_validation.json), [데이터셋 검증](reports/dataset_validation.json), [영상 추출 검사](reports/extraction_video_checks.json).

### 3.3 원시 HDF5 대응

공개 `LightwheelAI/lightwheel_tasks`에서 대응 원시 HDF5 500개와 부가 JSON을 확보했다. 원시 파일에는 world EE pose, 객체·fixture 상태, 초기 상태, 장면 메타데이터가 있다. 원시 자료의 부재가 현재 리매핑의 장애물은 아니다.

LeRobot 변환에서 제외된 마지막 HDF5 프레임 1개를 고려하여 전체 state/action/processed_action 배열로 대응시켰다. 원시 episode의 `success` 속성은 500개 모두 True였지만, 이것이 정책 평가 성공률 100%를 뜻하지는 않는다. episode 327·328은 운동학 배열이 동일하여 원본 파일 이름 대응에 중복 모호성이 남는다. 향후 평가 분할 시 이 둘은 같은 split으로 처리해야 한다.

근거: [원시 자료 검증 요약](reports/raw_validation_summary.json), [episode 대응](reports/raw_episode_mapping.json).

## 4. RB-Y1 장면 구현과 물체 복원

### 4.1 로봇·초기 자세·테이블

`environments/T01.usd`~`T10.usd`는 `/home/cai/rby1-sim-isaac/assets/generated/rby1_ready_reach_table.usd`를 참조한다. 원본 로봇 자산 자체를 수정하지 않고 별도 장면에 배치했다. USD 자산의 절대 경로 참조를 사용하므로 다른 PC로 옮길 때는 자산 경로도 함께 처리해야 한다.

초기 자세는 v1.1 코드의 `READY_*` 준비 자세를 반영했다. **전 관절을 0으로 설정한 자세가 아니다.**

| 항목 | 반영 값 |
|---|---|
| 왼팔 7관절 | `[15, 65, 15, -115, -75, -65, -5]`° |
| 오른팔 7관절 | `[15, -65, -15, -115, 75, -65, -5]`° |
| 몸통 | 제공 ready USD에 반영된 30° 구성 유지 |
| 머리 | 실기 설정 −35°와 USD +35°의 부호 차이 확인. 광축이 책상을 바라봄 |
| 베이스 위치 | 월드 `[2.44, -1.43, 0]` m, yaw −90° |
| 조작 자유도 | 양팔 14개 회전 관절 + 손가락 4개 직선 관절 |
| 베이스·몸통·머리 | 제공 ready USD의 고정 상태 유지 |
| 테이블 상판 | 모든 task 0.72 m |

layout 1·8은 기존 테이블 높이를 조정했다. layout 2는 기존 둥근 테이블의 시각적 경계와 접촉면 차이 때문에 평평한 작업 테이블로 교체했다. 물체·가전의 높이와 위치, fixture의 월드 고정 joint anchor도 함께 조정했다. T9는 아래 서랍이 이동 범위의 약 75% 열린 적응 장면으로 시작한다.

### 4.2 누락 물체 보완

사용자가 미리보기에서 지적한 누락에 대응하여 task별 원시 50 episode의 객체·fixture 목록을 대조했다. 기존에 생략했던 물체 17개와 fixture 9개를 복원했다. 원시 목록에서 확인한 객체 38개·fixture 38개는 task별 인스턴스를 합산한 수이며, 10개 장면 전체에 대응 항목이 존재한다.

누락 검사는 물체 정체성·활성화·가시성·기하를 기준으로 했다. **원본 500 episode 각각의 무작위 배치를 재현한 것은 아니다.** 머리 카메라 시야 밖에 있는 항목도 있으므로 전체 배치 확인에는 위쪽 시점 이미지를 함께 사용한다.

근거: [목록 대응](reports/scene_inventory_audit.json), [복원 검증](reports/restoration_validation.json).

![RB-Y1 T1~T10 전체 배치 미리보기](reports/scene_overview_contact_sheet.png)

[머리 카메라 모음](reports/scene_contact_sheet.png)과 `reports/T01_overview.png`~`T10_overview.png`도 제공한다.

### 4.3 작업 영역 검토의 범위

대표 목표 좌표에 대한 IK와 서랍·문·노브 손잡이 경로의 점별 IK를 검사했다. T4/T5/T6/T7/T9의 손잡이 경로는 각각 21개 검사점에서 해를 찾았으나, T5에는 인접 해 사이 약 5.02 rad의 큰 관절 변화가 있었다. 점별 해의 존재만으로 실행 가능한 연속 궤적이라고 볼 수 없다.

준비 자세의 물리 초기화와 렌더링은 검증했다. USD 기반 FK와 시뮬레이터의 TCP 위치 차이는 검사에서 최대 약 4.11×10⁻⁷ m였다. TCP는 손가락 CAD 표면의 중간 깊이를 기준으로 한 명목값 `[0, 0, -0.1045]` m이며 실제 파지 보정은 별도이다.

근거: [작업 영역 검사](reports/reachability.json), [손잡이 경로 검사](reports/fixture_sweep_audit.json). 전 궤적의 자기충돌·환경 충돌·물체 파지·작업 완료를 검증한 결과는 아니다.

## 5. X7S 데이터를 RB-Y1에 리매핑하는 작업

X7S와 RB-Y1은 관절 축·길이·순서·제어 의미, TCP, 손가락 형상, 카메라 위치가 다르다. 따라서 관절값의 이름이나 배열만 바꾸어 RB-Y1 시연으로 사용할 수 없다. 원본 X7S RGB도 RB-Y1 관측 영상으로 그대로 표시할 수 없다.

초기 명목 정렬·국소 IK baseline에서는 500개 중 모든 검사 지점을 통과한 episode가 없었다. 후속 task당 대표 episode의 정렬 탐색·다중 초기값 IK에서도 실패 지점이 남았다. 이는 검사한 고정 몸통·TCP·정렬·자세 보존 조건의 결과이며, 다른 배치나 몸통 사용·접촉 재계획까지 불가능하다는 의미는 아니다.

`~/datasets/Lightwheel-Tasks-RBY1-T1-T10`에는 현재 **README와 diagnostics만 존재**한다. 이 경로에 검증된 리매핑 LeRobot 시연을 완성했다고 보고하지 않는다. 이후 추가한 키보드 수집 데이터는 별도 경로에 생성되는 새로운 시연이며 X7S 리매핑 결과와 구분한다.

향후 리매핑 단계는 다음과 같다.

1. 원시 episode별 물체·fixture 초기 상태와 0.72 m 높이 변환을 재구성한다.
2. TCP·그리퍼·카메라·시간축을 보정한다.
3. 원본 동작을 접근·접촉·운반·해제 구간으로 나누어 물체 기준 경로로 변환한다.
4. RB-Y1의 연속 IK, 관절 제한, 충돌 검사, 속도·가속도 제한을 적용한다.
5. 실제 시뮬레이션 컨트롤러로 물리 재생하고 현재 구현된 `success_original`로 채택 여부를 판정한다.
6. RB-Y1의 머리·양손 카메라를 렌더링하고 측정 state 및 실제 발행 action과 함께 LeRobot으로 저장한다.

[기존 리매핑 계획](REMAPPING_PLAN_KO.md)은 단계별 참고 자료이다. 그 문서에서 추가 안정성·유지 조건을 성공 기준으로 제안한 부분은 이후 사용자의 선택으로 대체되었으며, **현재 공식 저장 성공 기준은 `success_original` 하나**이다. 경로 품질이나 실패 원인은 별도 진단으로 기록할 수 있지만 두 번째 성공 기준을 도입하지 않았다.

## 6. 키보드 조작 및 데이터 수집 구현

### 6.1 실행 환경과 방식

설치된 IsaacLab 2.3.0의 `Se3Keyboard`, `DifferentialIKController`를 사용한다. 실행 환경은 Isaac Sim 5.1.0과 conda `lerobot-arena`이다. 기존 standalone USD에 제어·기록기를 연결한 구현이며, 새로운 Gym/EnvHub task 등록이나 공식 `record_demos.py` 자체의 수정은 아니다.

키 입력의 상대 위치·회전 명령을 로봇 기준 좌표계에서 해석하고, USD 기반 Pinocchio FK/Jacobian과 DLS IK로 선택 팔의 관절 목표를 계산한다. 관절 위치 제한과 목표 변화율 제한을 적용한다. 다른 팔은 마지막 목표를 유지하며, 그리퍼는 팔별로 독립 제어한다.

기본값은 이동 0.08 m/s, 회전 0.5 rad/s, 팔 관절 목표 변화율 제한 0.8 rad/s, 손가락 목표 변화율 제한 0.06 m/s이다. 실제 벽시계 속도는 렌더링 성능에 따라 더 느릴 수 있다. 충돌 회피 경로 계획기를 추가한 것은 아니다.

### 6.2 실행 명령

```bash
cd /home/cai/lightwheel_rby1_transfer
conda activate lerobot-arena
./collect_keyboard.sh --task T1
```

T1 전용 호환 명령은 `./collect_t1_keyboard.sh`이며, 다른 task는 `--task T7`처럼 지정한다. 실행 스크립트가 해당 conda Python 경로와 필요한 라이브러리 환경 변수를 설정한다.

속도·저장 위치 변경 예:

```bash
./collect_keyboard.sh --task T1 \
  --pos-speed 0.05 --rot-speed 0.3 \
  --output ~/datasets/RBY1-T1-keyboard-session2
```

기본 50 Hz·640×480·3카메라를 사용한다. `--fps 25` 등을 선택할 수 있으나 기존 출력 데이터와 주파수·영상 크기가 다르면 새 출력 경로를 사용해야 한다.

### 6.3 조작 키와 수집 절차

Isaac Sim 창이 열리면 viewport를 클릭하여 키보드 포커스를 준다.

| 키 | 동작 |
|---|---|
| W / S | 로봇 기준 손 앞으로 / 뒤로 |
| A / D | 손 왼쪽 / 오른쪽 |
| Q / E | 손 위 / 아래 |
| Z / X | x축 양/음 회전 |
| T / G | y축 양/음 회전 |
| C / V | z축 양/음 회전 |
| K | 선택 팔 그리퍼 열기/닫기 |
| Tab | 왼팔/오른팔 전환 |
| B | 새 episode 기록 시작 |
| Enter | 성공 판정이 True일 때만 저장 요청. False이면 기록 유지 |
| P | 물리·기록·판정 카운트를 함께 일시정지/재개 |
| Backspace / R | 미저장 기록 폐기 후 장면 초기화 |
| L | 키 입력 해제, 팔 목표를 현재 자세로 설정 |
| Esc / 창 닫기 | 종료. 미저장 기록은 폐기 |

일반 수집 흐름은 `R → B → 조작 → 물체를 놓고 양손 후퇴 → success_original=True → 자동 저장·초기화`이다. 초기에는 왼팔이 선택되고 양쪽 그리퍼는 열린다. 저장 중 영상 인코딩이 끝날 때까지 물리는 정지한다. 최소 2프레임이 있어야 저장한다.

### 6.4 저장 위치와 데이터 의미

```text
~/datasets/Lightwheel-Tasks-RBY1-T1-Keyboard-Original/
├── data/
├── meta/
│   ├── info.json / stats.json / tasks.parquet / episodes/
│   ├── keyboard_collection.json
│   └── keyboard_episodes.json
└── videos/
    ├── observation.images.first_person/
    ├── observation.images.left_hand/
    └── observation.images.right_hand/

~/datasets/Lightwheel-Tasks-RBY1-T1-Keyboard-Original_raw/
└── episode-<ID>/
    ├── trajectory.npz
    ├── initial_state.json
    ├── episode.json
    ├── success_state.jsonl
    ├── first_person/ / left_hand/ / right_hand/   # lossless PNG
    └── export.log
```

Task별로 기본 경로의 T1 부분이 달라진다. 첫 저장이 성공하면 LeRobot 출력 폴더가 만들어진다. 재실행하면 호환되는 기존 데이터에 추가한다. 이전 수동 성공 라벨 데이터는 같은 출력에 섞지 않는다.

| Feature | 형상·단위 | 의미 |
|---|---|---|
| `observation.state` | 18, 팔 rad·손가락 m | 실제 측정 관절 위치 |
| `observation.velocity` | 18, rad/s·m/s | 측정 관절 속도 |
| `action` | 18, rad·m | 동일 관절 순서의 실제 발행 절대 위치 목표 |
| `observation.ee_pose` | 14 | 양손 TCP, 각 xyz+qwxyz, 로봇 기준 |
| `teleop.command` | 8 | delta pose 6개, 선택 팔, 그리퍼 열림 상태 |
| `observation.sim_time` | 1, s | 초기 안정화 후 기준의 시뮬레이션 시각 |
| `observation.camera_time` | 3, s | 같은 기준의 세 카메라 렌더 시각 |
| `observation.images.*` | 640×480 RGB | 머리·왼손·오른손 영상 |
| `success_original` | int64 `[0/1]` | 해당 프레임의 원본 자동 성공 판정 |

관절 순서는 simulator DOF 이름을 그대로 metadata에 저장하며 양팔이 교차 배치된 순서일 수 있다. 한 프레임의 의미는 `관측 → action 발행 → 다음 1/fps초 물리 진행`이다. IK 목표를 측정 state에 복사하지 않는다.

이 18차원 action은 시뮬레이션 명령이며 실제 RB-Y1 드라이버의 명령 형식과 자동으로 호환되지 않는다. 그리퍼 4차원도 원본 X7S의 두 개 이진 명령과 다르다.

### 6.5 시간 동기화와 내보내기

물리 dt는 0.01 s로 고정하고 필요한 물리 substep을 수행한 뒤 렌더링한다. 추가 물리 진행을 유발하지 않도록 physics step과 render 호출을 구분했다. 카메라의 `ReferenceTime`을 읽어 측정 state와 세 카메라 시각이 일치하는지 검사한다. 렌더링이 느리면 벽시계 실행이 느려질 수 있지만 프레임을 임의로 건너뛰지 않는다.

원시 기록을 먼저 보존하고 별도 프로세스에서 공식 LeRobot writer로 H.264 MP4 및 메타데이터를 생성한다. 내보내기 실패 시 저장된 원시는 유지한다. 원시 episode ID로 중복 내보내기를 방지하며, 중단 표시가 남은 출력에는 무조건 이어 쓰지 않는다. 복구는 [수집 안내서](KEYBOARD_COLLECTION_KO.md)의 새 출력 폴더 내보내기 절차를 따른다.

## 7. `success_original` 자동 성공 판정

### 7.1 적용 원칙

사용자의 선택에 따라 `success_original`만 적용한다. `success_verified`나 사람의 Enter 승인으로 성공 라벨을 만드는 방식은 사용하지 않는다.

원본 LW-BenchHub 커밋 `b2bcb2d00edef691f9fcc49039cbf0bcc7464605`의 task별 `_check_success()`, 공통 배치·거리 함수, fixture 열림/닫힘 함수, 공통 지연 처리 본문을 추출하여 고정했다. 원저작권 및 Apache-2.0 라이선스를 유지하고 소스 파일 SHA256을 보존했다.

원본 함수에 입력할 물체 COM·관성 프레임 자세·속도, fixture 관절값·한계값, 양손 TCP, PhysX 접촉력을 RB-Y1 장면에서 읽는다. 객체 이름→USD prim, 영역 크기, 관절 이름·순서 등의 대응은 metadata에 저장한다.

모든 X7S 시연의 수집 당시 task 코드 커밋을 확인한 것은 아니다. 따라서 여기서 “원본”은 **확인한 공개 LW-BenchHub 버전의 판정 구현**을 뜻하며, 수집 당시 역사적 코드와의 완전 동일성을 단정하지 않는다.

### 7.2 Task별 조건

| Task | 원본 조건 요약 |
|---|---|
| T1 | 그릇–접시 수평 거리 < 접시 horizontal_radius, 양손–그릇 > 0.25 m |
| T2 | 목표 그릇–접시 수평 거리 < 0.08 m, 높이 차 >0.01 m 및 <0.15 m, 속도 norm <0.05, 양손–그릇 >0.25 m |
| T3 | 케첩–바구니 수평 거리 < 바구니의 작은 수평 크기×0.4, 절대 수직축 내적 >0, 속도 norm <0.5, 양손–두 대상 >0.25 m |
| T4 | 위 서랍 열림 비율 ≥0.5, 양손–fixture 모든 body COM >0.4 m |
| T5 | 전자레인지 microjoint 열림 비율 ≥0.6, 양손–fixture 모든 body COM >0.25 m |
| T6 | 하나 이상의 노브 각도 modulo 2π가 [0.35, 2π−0.35] 안에 있음, 양손–fixture 모든 body COM >0.3 m |
| T7 | 첫 서랍 관절 열림 비율 ≥0.3, 그릇 bbox가 fixture 내부 영역 판정을 통과, 양손–그릇 >0.25 m |
| T8 | 두 그릇 수평 거리 < 받침 그릇의 작은 수평 크기×1.0, 절대 수직축 내적 >0.5, 속도 norm <0.5, 양손–두 대상 >0.3 m |
| T9 | 마지막 서랍 관절 열림 비율 ≤0.005, 그릇 bbox가 fixture 내부 영역 판정을 통과, 양손–그릇 >0.25 m |
| T10 | 수프·토마토소스가 각각 T3와 같은 바구니 배치 조건을 만족하는지 AND |

공통 거리 함수는 양손 모두를 검사한다. 원본의 대표 왼쪽·오른쪽 손가락 센서에 대응하도록 RB-Y1 finger_l1/finger_r1의 net contact force norm <0.1 N도 검사한다.

원본의 계산상 특징을 유지했다. `horizontal_radius`는 bounding region 수평 반크기 벡터의 norm이다. rigid object의 속도 norm은 선속도·각속도 6개를 포함하고, T3 fixture 경로는 root 선속도만 사용한다. T1 및 T3/T8/T10에 원본에 없는 높이·지지 접촉 조건을 추가하지 않았다. T7/T9는 원본 StorageFurniture의 내부 영역 목록과 bbox 허용 오차를 사용하며 특정 서랍 내부만으로 제한하는 보정을 추가하지 않았다.

### 7.3 지연과 라벨 저장

처음 10 control step에는 성공을 억제한다. TELEOP 모드의 지연은 `int(1 / physics_dt / 2)`이므로 현재 50회이다. 한 번 조건이 참이면 상태를 기억하여 카운트를 진행하며, 조건이 50회 연속 참이어야 하는 방식으로 바꾸지 않았다. 50 Hz에서는 약 1초, 25 Hz에서는 약 2초에 해당한다. 일시정지 및 내보내기 중에는 카운트가 진행하지 않는다.

프레임별 `success_original`을 저장하고 episode metadata의 `success_original`과 호환용 `success`를 동일하게 기록한다. `success_label_source`는 `success_original`이다. `success_state.jsonl`에는 판정에 사용한 상태를 저장하여 시뮬레이터를 다시 실행하지 않고도 판정 결과를 재계산할 수 있다.

```bash
LD_LIBRARY_PATH=/home/cai/miniforge3/envs/lerobot-arena/lib \
/home/cai/miniforge3/envs/lerobot-arena/bin/python \
  /home/cai/lightwheel_rby1_transfer/scripts/replay_success_original.py \
  --raw <저장된-raw-episode-폴더>
```

## 8. 실제 GUI 키 입력 오류와 수정

사용자가 `B`를 눌렀을 때 다음 오류를 보고했다.

```text
AttributeError: 'str' object has no attribute 'name'
```

추가한 키보드 wrapper가 `event.input.name`을 가정했지만, 해당 GUI 이벤트에서는 `event.input`이 문자열이었다. 설치된 IsaacLab 부모 콜백도 `.name`을 사용하므로 wrapper의 한 줄만 바꾸는 것으로는 충분하지 않았다.

수정은 키 값을 문자열 또는 enum형 `.name`에서 추출하고, 부모 콜백에 전달하기 전에 `input.name`을 갖는 형식으로 정규화하는 방식이다. 키 중복 누름 억제, 해제 처리, 리셋·팔 전환 뒤의 오래된 release 무시 동작도 유지했다. smoke 이벤트 주입 역시 문자열 입력을 사용하도록 변경했다.

실제 설치된 IsaacLab 및 수집기 클래스 본문을 대상으로 문자열·enum형 44개 회귀 검사를 수행했다. 시뮬레이터에서도 문자열 키 이벤트를 주입하여 2 episode·77프레임의 기록·저장·폐기를 확인했다. 이 검사는 사용자의 물리 키보드 및 GUI 포커스를 직접 조작한 검사는 아니다.

수정 전 프로세스에는 변경 사항이 적용되지 않으므로 창을 닫고 동일 명령으로 재실행해야 한다. 패키지 재설치는 필요 없다. 함께 출력된 GPU 메모리 인터페이스 관련 성능 경고는 이 AttributeError의 원인이 아니다.

근거: [키 이벤트 회귀 검사](reports/keyboard_event_regression.json), [문자열 이벤트 smoke 결과](reports/keyboard_string_event_fix/smoke_result.json).

## 9. 검증 결과와 해석

| 검증 항목 | 결과 | 해석 범위 |
|---|---|---|
| X7S 추출본 | 500 episode·499,643프레임, 30 MP4 검사 | 원본 수치·영상 구간과의 정합 |
| 장면 복원 | 10개 장면, 누락 항목 0개 | 객체 정체성·장면 구성. 원본 episode 배치 재현은 아님 |
| 원본 성공 조건 | 49개 조건 검사 통과 | 임계값·양손 거리·힘·원본 latch 처리 |
| 실제 장면 판정 연결 | T1~T10 모두 실행 | 초기 상태 False, 실제 geometry를 이용한 합성 성공·실패·지연 검사 |
| 자동 성공 수집 | 6개 테스트 episode·274프레임 | LeRobot 로딩, 수치·영상·시각, 성공 라벨 재계산 일치 |
| 성공 자동 저장 | T1 합성 성공 배치와 재실행 검사 | 성공 전 Enter 거부, 성공 후 자동 저장·추가 저장 |
| 서랍 장면 수집 | T7 smoke 검사 | 기록·저장·폐기·초기화 경로 |
| GUI 문자열 키 오류 | 44개 회귀 검사 + 2 episode·77프레임 | 문자열/enum 입력과 실제 시뮬레이터 콜백 경로 |
| 정적 확인 | Python compile, undefined-name 검사, shell 문법 검사 | 해당 구현 변경 시 수행한 코드 검사 |

6개·274프레임의 자동 판정 수집 검사와 이후 문자열 키 오류 수정의 2개·77프레임 검사는 별도 실행이다. 이를 실제 task 성공 시연 수나 학습 데이터 수로 해석하지 않는다. T1의 합성 성공 시험은 물체를 테스트용으로 이동시킨 것이며 로봇이 실제로 집어 옮긴 시연이 아니다. 테스트 데이터는 `reports/` 아래에 두고 `is_smoke_test=true`로 구분했다.

핵심 근거: [자동 성공 구현 검증](reports/success_original_validation.json), [실제 장면 연결](reports/success_original_live.json), [성공 조건 검사](reports/success_original_semantics.json). 초기 수동 라벨 버전의 [키보드 검증](reports/keyboard_implementation_validation.json)은 과거 기록으로 보존한다.

## 10. 주요 구현 파일

| 파일 | 역할 |
|---|---|
| [collect_keyboard.sh](collect_keyboard.sh) | T1~T10 실행 환경 설정 및 수집기 실행 |
| [collect_t1_keyboard.sh](collect_t1_keyboard.sh) | 기존 T1 실행 명령 유지 |
| [collect_keyboard.py](scripts/collect_keyboard.py) | 키보드 입력, 양팔 IK, 카메라 동기화, 자동 저장 |
| [keyboard_recorder.py](scripts/keyboard_recorder.py) | 원시 PNG·NPZ·상태 journal, episode 저장·폐기 |
| [export_keyboard_episode.py](scripts/export_keyboard_episode.py) | 공식 LeRobot writer로 내보내기 및 중복 방지 |
| [success_original.py](scripts/success_original.py) | RB-Y1 실제 상태→원본 성공 함수 입력 연결 |
| [original_predicates.py](scripts/vendor/original_predicates.py) | 고정 버전 원본 판정 함수 본문 |
| [source_manifest.json](scripts/vendor/source_manifest.json) | 원본 커밋·소스 파일 해시 |
| [replay_success_original.py](scripts/replay_success_original.py) | 저장된 상태에서 성공 판정 재계산 |
| [run_environment.py](scripts/run_environment.py) | 장면·준비 자세 실행 및 성공 판정 출력 |
| [kinematics.py](scripts/kinematics.py) | USD joint frame 기반 FK/Jacobian/IK |
| [build_scenes.py](scripts/build_scenes.py) | RB-Y1 장면 생성 |
| [complete_scene_inventory.py](scripts/complete_scene_inventory.py) | 원시 목록 기반 물체·fixture 보완 |
| [validate_keyboard_dataset.py](scripts/validate_keyboard_dataset.py) | LeRobot 로딩·원시 수치·영상·시각·판정 검사 |
| [test_keyboard_events.py](scripts/test_keyboard_events.py) | 문자열/enum 키 입력 회귀 검사 |

## 11. 남은 작업

1. **실제 키보드 시연 수집:** T1부터 사람이 파지·배치를 수행하고 자동 저장 결과를 검토한다. 현재 자동 시험은 전체 실제 조작의 성공을 보증하지 않는다.
2. **Task별 수행 검증:** T4·T5·T6의 관절 조작과 T7·T9·T10의 순차 작업이 현재 배치·고정 몸통 조건에서 수행 가능한지 확인한다.
3. **리매핑 파이프라인 완성:** 원본 episode별 장면 재구성, 접촉 구간 변환, 연속 IK·충돌·물리 재생, RB-Y1 재렌더링을 연결한다. 현재 성공 판정기와 LeRobot exporter는 재사용할 수 있다.
4. **실험용 데이터 관리:** 실제 성공 episode 수, task별 분포, 실패 원인, train/validation/test 분할을 확정한다. smoke 및 중복 원시 시연을 실험 데이터와 구분한다.
5. **실기 적용이 필요할 때:** 현재 18 DOF action을 실제 RB-Y1 드라이버 제어 정의에 맞게 변환하고 TCP·그리퍼·카메라를 별도로 보정한다.

보고서 작성 시점의 `~/datasets/Lightwheel-Tasks-RBY1-T1-T10`은 진단 자료 경로이다. `…-T1-Keyboard-Original_raw`는 존재하지만 해당 기본 LeRobot 출력의 `meta/info.json`은 확인되지 않았다. 따라서 기본 출력에 실제 사용자 성공 episode가 이미 저장되었다고 단정하지 않는다. 이 파일 존재 상태는 사용자가 이후 수집하면서 달라질 수 있다.

## 12. 참고 자료와 버전

| 항목 | 확인한 버전·커밋 |
|---|---|
| IsaacLab | `/home/cai/IsaacLab_RS`, 2.3.0 |
| Isaac Sim | 5.1.0 |
| Python 환경 | `/home/cai/miniforge3/envs/lerobot-arena/bin/python` |
| LW-BenchHub | `b2bcb2d00edef691f9fcc49039cbf0bcc7464605` |
| LeRobot | `0b067df57d21d3a02d6c511f1609172fa39ac29b` |
| rby1-sim-isaac | `ba5249629d6f34f8a83c6a5cb2cca90df767e749` |
| cai-rby1-lerobot v1.1 | `eca93215893e2523148881839868d11bcea17701` |
| 원시 HDF5 데이터 revision | `c22c3ce6969be62103c8c82f090006147dac2fda` |
| RB-Y1 판정 연결 버전 | `lw-benchhub-b2bcb2d-rby1-adapter-v1` |

저장소 커밋은 앞선 구현·검증에서 기록한 기준 버전이다. 작업 디렉터리의 로컬 수정 전체를 Git 커밋으로 묶었다는 의미는 아니다.

- [LeRobot Arena 공식 문서](https://huggingface.co/docs/lerobot/envhub_isaaclab_arena)
- [Lightwheel-Tasks-X7S 데이터셋](https://huggingface.co/datasets/LightwheelAI/Lightwheel-Tasks-X7S)
- [Lightwheel 원시 데이터셋](https://huggingface.co/datasets/LightwheelAI/lightwheel_tasks)
- [IsaacLab 2.3.0 Teleoperation / Imitation Learning](https://isaac-sim.github.io/IsaacLab/v2.3.0/source/overview/imitation-learning/teleop_imitation.html)
- [LW-BenchHub 고정 버전](https://github.com/LightwheelAI/LW-BenchHub/tree/b2bcb2d00edef691f9fcc49039cbf0bcc7464605)
- [RB-Y1 v1.1 브랜치](https://github.com/cailab-hy/cai-rby1-lerobot/tree/v1.1)
