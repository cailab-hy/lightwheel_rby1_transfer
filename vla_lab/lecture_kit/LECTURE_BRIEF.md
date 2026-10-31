# 강의자료 제작 브리핑 — RB-Y1 T1~T10 오라클 시범 + SmolVLA 실습

> 이 문서는 **강의자료(슬라이드)를 만들 Claude Work**를 위한 입력 자료입니다.
> 내용·수치·이미지·영상은 모두 조교 PC에서 실제로 실행해 얻은 것입니다. 여기 없는 수치는 만들지 마십시오.
> 영상까지 보려면 같은 폴더의 `LECTURE_BRIEF.html`을 브라우저로 여십시오(영상이 바로 재생됨).
> 이 폴더는 레포의 `vla_lab/` 안에 있고, 영상(mp4)은 `../docs/assets/`를 참조하므로 **`vla_lab` 폴더 전체를 함께** 받아야 합니다.

---

## 1. 강의 정보와 요청

| 항목 | 내용 |
|---|---|
| 과목 | 대학원 "로보틱스시뮬레이션" (한양대 ERICA, 박태준 교수) |
| 대상 | 대학원생. IL 실습(Robomimic BC)과 RL 실습(PPO)을 이미 해 봄 |
| 이번 회차 주제 | VLA(Vision-Language-Action) 모델: 오라클로 시범 수집 → SmolVLA 미세조정 → 시뮬레이터 평가 |
| 실습 문서 | `../docs/VLA_실습_lightwheel_SmolVLA.md` (명령어 단위의 학생용 매뉴얼. 강의자료는 이것을 **설명**하는 역할) |
| 원하는 결과물 | 강의 슬라이드(약 20~30장 권장). 개념 → 데이터 → 학습 → 평가 → 분석 → 과제 순서 |
| 문체 | 한국어, 짧은 문장. 수식은 최소. 그림·영상 위주 |

**슬라이드가 전달해야 할 핵심 메시지 (5개)**

1. VLA는 **카메라 + 로봇 상태 + 언어 지시문**을 받아 **동작 묶음(action chunk)**을 내는 정책이다. 지시문만 바꿔 **모델 하나로 10개 task**를 수행한다.
2. 시범은 사람이 아니라 **오라클**(시뮬레이터 정답 상태를 읽는 스크립트)로 500개를 모았다. 오라클은 **첫 시도에 성공한 깨끗한 시범만** 보여 주고, 실수 후 회복하는 장면은 없다. 로봇은 **자기 몸과 충돌**하며(팔이 몸통을 통과하지 못함), 로봇 링크끼리 닿은 시범은 저장하지 않았다.
3. **8GB GPU** 안에서 끝나도록 설계했다: 수집 3.4GB, 학습 6.5GB, 평가 5.2GB.
4. 결과: 10개 task 평균 **57.2%** (286/500). 짧고 단순한 task는 잘 되고(스토브 98%, 전자레인지 90%, 그릇 84%), 정밀하게 집어야 하는 task는 어렵다(서랍+그릇 22%, 캔 2개 22%, 케첩 32%).
5. 실패의 51%는 **파지 실패**다. 복구 시범·노이즈 주입이 없는 baseline의 한계이고, 학생 과제의 출발점이다.

---

## 2. 권장 슬라이드 구성과 사용할 자료

경로는 이 파일 기준입니다. GIF는 슬라이드에 바로 넣을 수 있고, mp4는 원본 고화질입니다.

| # | 슬라이드 | 핵심 내용 | 사용할 자료 |
|---|---|---|---|
| 1 | 제목 | RB-Y1 T1~T10에서 SmolVLA 학습 및 평가 | `assets/views/scene_T1.jpg` 또는 GIF 하나 |
| 2 | 오늘의 흐름 | 수집 → 변환 → 병합 → 학습 → 평가 → 분석 | `assets/diagrams/pipeline.png` |
| 3 | IL·RL 실습과의 차이 | BC는 task 하나·상태 입력, VLA는 영상+언어로 여러 task | (텍스트) |
| 4 | VLA란? | 입력 3종 → 출력 action chunk | `../docs/assets/smolvla_io.png` |
| 5 | SmolVLA 구조 | VLM(SmolVLM2-500M 앞 16층, 동결) + action expert(flow matching, 학습). 4.5억 중 1억 학습 | `../docs/assets/smolvla_io.png` |
| 6 | 로봇이 보는 것 | 머리 카메라 1 + 손목 카메라 2, 16차원 상태 | `assets/views/camera_views_T1.jpg`, `camera_views_T7.jpg`, `camera_views_T9.jpg` |
| 7~8 | 10개 task 소개 | 지시문과 역할 (3절 표) | `../docs/assets/T1-T10_front_2x5.jpg`, `assets/views/scene_T*.jpg` |
| 9 | 오라클이란? | 정답 상태로 목표를 계산, 직선 경로, Differential IK. 복구 없음 | `assets/frames/oracle_T1.jpg` |
| 10~11 | 오라클 시범 예시 | 쉬운 것(T1, T6)과 긴 것(T7, T9, T10) | `assets/gifs/oracle_T*.gif`, `assets/frames/oracle_T*.jpg` |
| 12 | 오라클 성공률 | 98.2% (task별 90.9~100%), 로봇 자기 몸 접촉 0회 | `assets/charts/oracle_success.png` |
| 13 | 데이터셋 | LeRobot v3, 500 에피소드, 188,315 step(3.5시간), 시범 길이 | `assets/charts/demo_length.png` |
| 14 | 데이터 검증·재생 | `--validate`로 raw와 완전 일치 확인, 재생으로 성공 재현 | `../docs/assets/replay/T1_episode_0_action.mp4` |
| 15 | 학습 설정 | batch 16, 25,000 step, lr 1e-4, VLM 동결. 8GB에 맞춘 이유 | (4절 표) |
| 16 | 학습 곡선 | loss 1.59 → 0.007 | `assets/charts/training_loss.png` |
| 17 | VRAM | 모든 단계 8GB 이하 | `assets/charts/vram_by_stage.png` |
| 18 | 평가 방법 | task당 50회, 고정 seed, 성공 판정 `success_original`, 최대 step = 오라클 최장 × 2 | (텍스트) |
| 19 | 평가 결과 | task별 성공률 + 95% 신뢰구간, 평균 57.2% | `assets/charts/eval_success_by_task.png` |
| 20~22 | 성공 vs 실패 영상 | 같은 task의 성공·실패 비교 (T1, T4, T5, T9 추천) | `assets/gifs/eval_T*_{success,failure}.gif`, `assets/frames/eval_T*_*.jpg` |
| 23 | 실패 분석 | 접근·파지·운반·배치·시간 초과. 파지 51% | `assets/charts/failure_stages.png` |
| 24 | 대표 실패 사례 | T10 캔을 들지 못함, T7 서랍을 충분히 열지 못함, T4 서랍을 아슬아슬하게 덜 엶 | `assets/frames/eval_T10_failure.jpg`, `eval_T7_failure.jpg`, `eval_T4_failure.jpg` |
| 25 | 재현성 | 수집은 비트 단위로 같음, 평가는 렌더링 노이즈로 에피소드별로 다를 수 있음 | (5절) |
| 26 | 과제: 더 발전시키려면 | 복구 시범, 노이즈 주입(DART), 다양성, 시범 수, n_action_steps, 체크포인트 비교 | (6절) |
| 27 | 실습 안내 | 매뉴얼 위치, 소요 시간, 8GB GPU 주의 | (7절) |

---

## 3. 10개 task

| Task | 지시문 (모델 입력, 원문 그대로) | 작업 | 역할 | 오라클 팔 |
|---|---|---|---|---|
| T1 | `put the black bowl on the plate.` | 검은 그릇을 접시에 놓기 | Basic Pick-and-Place | 왼팔 |
| T2 | `Pick the akita black bowl on the cookies box and place it on the plate.` | 쿠키 상자 위 그릇을 접시에 | Spatial Relational Pick-and-Place | 왼팔 |
| T3 | `Pick up the ketchup, and put it in the basket.` | 케첩을 바구니에 | Object-Variation Pick-and-Place | 왼팔 |
| T4 | `Open the top drawer of the cabinet.` | 수납장 위 서랍 열기 | Single-Step Articulated Manipulation | 왼팔 |
| T5 | `Open the microwave.` | 전자레인지 문 열기 | Articulated Appliance Manipulation | 오른팔 |
| T6 | `Turn on the stove.` | 스토브 켜기 | Contact / Actuation | 왼팔 |
| T7 | `Open the top layer of the drawer and put the bowl inside.` | 위 서랍 열고 그릇 넣기 | Compositional Manipulation | 왼팔 |
| T8 | `Stack the black bowl in the middle on the black bowl at the back.` | 가운데 그릇을 뒤쪽 그릇 위에 | Precision Stacking | 왼팔 |
| T9 | `Put the black bowl in the bottom drawer of the cabinet and close it.` | 그릇을 아래 서랍에 넣고 닫기 | Long-Horizon Sequential Manipulation | 왼팔 |
| T10 | `Pick up the alphabet soup and the tomato sauce, and put them in the basket.` | 캔 두 개를 바구니에 | Multi-Object Sequential Manipulation | 왼팔 → 오른팔 |

- 로봇: Rainbow Robotics RB-Y1(양팔 7자유도 + 그리퍼). 몸통·머리는 고정. 시뮬레이터: Isaac Sim 5.1 / IsaacLab 2.3.
- 로봇 자기충돌: 팔·몸통·머리·손바닥에 링크별 convex hull 충돌체를 넣고 자기충돌을 켰다(`rby1-sim-isaac` `selfcollision-hulls` 브랜치). 처음 기본 모델은 자기충돌이 꺼져 있어 T5에서 팔이 몸통을 통과했다(이전 시범 50/50).
- 물체 위치·방향은 에피소드마다 무작위(같은 seed = 같은 배치). 수납장·전자레인지·스토브 같은 고정물은 고정.
- 성공 판정 `success_original`: LW-BenchHub 원본 판정 코드. 조건 만족 후 약 3.5초(52 step) 뒤 확정. 대부분 **그리퍼가 물체에서 멀어져야** 성공.

---

## 4. 확인된 수치 (이 표의 값만 사용)

**데이터 (오라클)**

| 항목 | 값 |
|---|---|
| 시범 수 | task당 50개, 총 500개 (509회 시도, 성공률 98.2%) |
| task별 오라클 성공률 | T1 98.0, T2 100, T3 90.9, T4 100, T5 100, T6 100, T7 100, T8 98.0, T9 98.0, T10 98.0 (%) |
| 로봇 자기 몸 접촉 | 509회 시도 중 0회 (PhysX 접촉 보고로 매 step 확인, 닿으면 저장하지 않음) |
| 데이터 형식 | LeRobot v3, 15fps, 상태·action 16차원, 카메라 3대(머리 480×640, 손목 640×480 세로), AV1 영상 |
| 병합 데이터셋 | 500 에피소드, 188,315 step (209.2분) |
| 시범 길이 평균(초) | T1 17.5, T2 17.0, T3 22.7, T4 17.2, T5 27.1, T6 14.3, T7 41.3, T8 18.8, T9 33.8, T10 41.5 |
| 학습/평가 seed | 학습 장면 seed 0~54 (0~9999 범위), 평가 seed 100000~100049 (겹치지 않음) |

**학습 (SmolVLA)**

| 항목 | 값 |
|---|---|
| 시작 가중치 | `lerobot/smolvla_base` (LeRobot 0.4.3) |
| 파라미터 | 전체 450,046,176 (4.5억), 학습 99,880,992 (1억). VLM과 비전 인코더 동결, action expert만 학습 |
| 주요 설정 | batch 16, 25,000 step(약 2.2 epoch), AdamW lr 1e-4, warmup 1000, cosine 감소 25,000 step, fp32, chunk 50 |
| 기본값과 바꾼 것 | batch 8→16, steps 100,000→25,000, decay 30,000→25,000, 체크포인트 간격 20,000→5,000 |
| loss | 1.59 (100 step) → 0.007 (25,000 step) |
| 시간 | RTX 3090에서 0.49초/step, 약 3시간 20분 |
| 8GB GPU 시간 | **측정 아님, 추정**: 약 6~11.6시간 |

**VRAM (실측, GB = MiB ÷ 1024)**

| 단계 | 최대 |
|---|---|
| 오라클 수집 | 3.1~3.4GB |
| 학습 (batch 16) | 6.50GB (batch 8은 4.0GB, batch 32는 메모리 부족으로 실패) |
| 평가 (시뮬레이터 + 정책) | 4.7~5.2GB |

**평가 (task당 50회, 조교 baseline)**

| Task | 성공 | 성공률 | 95% 신뢰구간 (Clopper-Pearson) |
|---|---|---|---|
| T1 | 42/50 | 84% | 70.9~92.8% |
| T2 | 25/50 | 50% | 35.5~64.5% |
| T3 | 16/50 | 32% | 19.5~46.7% |
| T4 | 25/50 | 50% | 35.5~64.5% |
| T5 | 45/50 | 90% | 78.2~96.7% |
| T6 | 49/50 | 98% | 89.4~99.9% |
| T7 | 11/50 | 22% | 11.5~36.0% |
| T8 | 39/50 | 78% | 64.0~88.5% |
| T9 | 23/50 | 46% | 31.8~60.7% |
| T10 | 11/50 | 22% | 11.5~36.0% |
| **평균** | 286/500 | **57.2%** | 10개 task 단순 평균 |

- 평가 시간: 순서대로 돌리면 약 8~12시간(추정). 조교는 4~5개 동시 실행으로 약 11시간 10분.
- 평가 500회 중 정책이 로봇 팔을 자기 몸에 닿게 한 에피소드: 0회.
- 이전(자기충돌 꺼진 로봇) 결과는 253/500(50.6%)였다. 데이터·물리가 함께 바뀌었으므로 이 차이를 한 가지 원인으로 설명하지 말 것.

**실패 분석 (214회 실패)**

| 단계 | 기준 (관측 신호) | 횟수 |
|---|---|---|
| 접근 | TCP가 목표 8cm 이내로 온 적 없고 물체도 안 움직임 | 4 |
| 파지 | 물체가 3cm 이상 들린 적 없음(밀기·넘어뜨림 포함) / 관절이 거의 안 움직임 | **110 (51%)** |
| 운반 | 들었지만 목표에서 멀리 끝남(또는 떨어뜨림) | 31 |
| 배치·조작 | 목표 근처지만 기준 미달 (서랍·문을 덜 열고 닫음 등) | 65 |
| 시간 초과 | 끝났을 때 조건은 만족했지만 확정 전에 시간이 끝남 | 4 |

- 파지 실패가 많은 task: T10 30회, T3 26회, T2·T9 각 17회.
- T7: 실패 39회 중 25회가 위 서랍을 충분히 열지 못함(열림 중앙값 0.028m, 필요 0.069m).
- T4: 실패 25회 중 24회가 서랍을 열긴 했지만 기준(0.115m) 미달. 그중 17회는 0.106m 이상으로 아슬아슬함.
- T5: 실패 5회 모두 문을 덜 엶(최종 0.58~0.84 rad, 필요 0.94 rad).
- T9: 파지 17, 운반 3, 서랍 덜 닫음 7.

---

## 5. 재현성 (슬라이드 1장 분량)

- **오라클 수집은 완전히 재현된다.** 새 폴더에 다시 clone해서 같은 seed로 수집하면 관절 값까지 처음과 같다(최대 차이 0).
- **평가는 에피소드 단위로 재현되지 않는다.** 정책 추론은 같은 입력·seed에서 완전히 같지만, RTX 렌더러가 같은 장면을 두 번 그려도 픽셀이 조금씩 다르다(평균 2~3/255). 이 차이로 첫 action부터 달라진다.
- 같은 체크포인트로 두 번 평가: T1 45→46, T5 38→39 (성공 수는 거의 같음). seed별로는 T1 5개, T5 11개 결과가 바뀜.
- 강의 포인트: "50회 평가의 신뢰구간(±10~15%p)과 재평가 차이를 함께 보고 결과를 해석하자."

---

## 6. 학생 과제 방향 (정답은 주지 않음, 질문과 단서만)

이번 baseline에는 일부러 넣지 않은 것들입니다.

1. **복구 시범이 없다** — 그릇을 살짝 놓친 상황을 정책이 본 적이 있나? 실패 직후 상태에서 시작하는 시범을 만들 수 있을까?
2. **노이즈 주입이 없다** — DART(Laskey et al., 2017): 실행 동작에만 노이즈를 넣고 기록은 원래 오라클 action으로 하면?
3. **다양성** — 물체 배치 범위를 넓히면 쉬워질까 어려워질까?
4. **시범 수** — 25개, 100개로 바꾸면? 어떤 task가 데이터에 민감한가?
5. **학습·추론 설정** — 평가 때 `--n-action-steps 10`으로 더 자주 다시 계획하면? 5000~25000 체크포인트 중 어느 것이 가장 좋은가? loss가 낮으면 성공률도 높은가?
6. **실패 분석부터** — `failure_analysis.py`로 가장 많은 실패 단계를 먼저 공략.

---

## 7. 실습 운영 정보 (마지막 슬라이드용)

| 단계 | 명령 (요약) | 시간 (조교 PC) |
|---|---|---|
| 수집 | `./vla_lab/collect_oracle.sh --task T1 --num-demos 50 --seed-start 0` (T1~T10) | 약 9시간 (3~4개 동시 + 변환 동시) |
| 변환·검증 | `./export_dataset.sh --output ~/datasets/vla_lab/T1/oracle --format rby1 --validate` | 합계 약 8.4시간 (동시 실행) |
| 병합 | `./run_python.sh vla_lab/scripts/merge_datasets.py ...` | 10분 |
| 학습 | `./vla_lab/train_smolvla.sh --output_dir ~/vla_lab_runs/smolvla_t1_t10` | 약 3.3시간 (RTX 3090) |
| 평가 | `./vla_lab/eval_smolvla.sh --policy-path .../checkpoints/last/pretrained_model --output ...` | 약 8~12시간 (추정) |

- 8GB GPU에서는 학습과 평가를 **동시에 돌리지 말 것**(합계 8GB 초과).
- 자세한 명령과 출력 예시는 `../docs/VLA_실습_lightwheel_SmolVLA.md`.

---

## 8. 주의: 슬라이드에 쓰면 안 되는 표현

- "8GB GPU에서 학습 X시간 걸린다"를 **측정값처럼** 쓰지 말 것 (추정임을 표시).
- 평가 결과를 "항상 같은 결과가 나온다"고 쓰지 말 것 (5절).
- 오라클 성공률을 "100%"라고 쓰지 말 것 (509회 중 9회 실패, 첫 시도만 기록).
- 성공률을 소수점까지 단정하지 말 것 (50회 기준 신뢰구간이 넓음).
- SmolVLA 내부 구조를 이 문서 이상으로 상세히 단정하지 말 것. 필요하면 공식 자료 인용: <https://huggingface.co/blog/smolvla>, <https://huggingface.co/lerobot/smolvla_base>, <https://github.com/huggingface/lerobot>.

---

## 9. 자료 목록

### 그림·차트 (`assets/`)

| 파일 | 내용 |
|---|---|
| `diagrams/pipeline.png` | 전체 흐름 6단계와 핵심 수치 |
| `../docs/assets/smolvla_io.png` | SmolVLA 입력(카메라 3·상태 16D·지시문) → 출력(50 step × 16D) |
| `charts/eval_success_by_task.png` | task별 평가 성공률 + 95% 신뢰구간 + 평균선 |
| `charts/failure_stages.png` | task별 실패 단계 누적 막대 |
| `charts/oracle_success.png` | 오라클 성공률과 목표 80% |
| `charts/demo_length.png` | 시범 길이(평균·최소·최대) |
| `charts/training_loss.png` | 학습 loss 곡선 (log 축) |
| `charts/vram_by_stage.png` | 단계별 최대 VRAM과 8GB 한도 |
| `views/camera_views_T1.jpg`, `T7`, `T9` | 정책이 보는 카메라 3대 (시작 / 작업 중) |
| `views/scene_T1.jpg` ~ `scene_T10.jpg` | task별 초기 장면(정면) |
| `../docs/assets/T1-T10_front_2x5.jpg` | 10개 장면 한 장 |

### 장면 모음 (`assets/frames/`, 6컷, 시간 표시)

| 파일 | 내용 |
|---|---|
| `oracle_T1.jpg` ~ `oracle_T10.jpg` | 오라클 시범 |
| `eval_T*_success.jpg` | SmolVLA 성공 에피소드 |
| `eval_T*_failure.jpg` | SmolVLA 실패 에피소드 |

### 움직이는 그림 (`assets/gifs/`, 360px, 슬라이드용)

| 파일 | 내용 |
|---|---|
| `oracle_T1.gif` ~ `oracle_T10.gif` | 오라클 시범 (실제 속도) |
| `eval_T*_success.gif`, `eval_T*_failure.gif` | SmolVLA 평가 (2배속) |

### 원본 영상 (`../docs/assets/`, mp4)

| 폴더 | 내용 |
|---|---|
| `oracle/oracle_T*.mp4` | 오라클 시범, 정면 카메라 1280×720 |
| `eval/T*_{success,failure}_seed*.mp4` | 평가 에피소드, 정면 카메라 960×540 |
| `replay/T1_episode_0_action.mp4` | 저장된 시범을 시뮬레이터에서 재생 |

### 근거 자료 (수치 확인용)

| 파일 | 내용 |
|---|---|
| `../reports/eval_results.txt`, `eval_results.json` | 평가 표 |
| `../reports/failure_analysis.md`, `failure_analysis.json` | 실패 분석 |
| `../reports/eval_determinism.md` | 재평가 비교 |
| `../reports/self_collision_review.md` | 로봇 자기충돌 검토와 수정 내용 |
| `../reports/oracle_summary.json`, `dataset_summary.txt` | 오라클·데이터 요약 |
| `../reports/env_check.txt` | 버전 (Python 3.11.16, PyTorch 2.7.0+cu128, Isaac Sim 5.1.0, IsaacLab 2.3.0, LeRobot 0.4.3, RTX 3090) |
| `make_assets.py` | 이 폴더의 그림을 다시 만드는 스크립트 |
