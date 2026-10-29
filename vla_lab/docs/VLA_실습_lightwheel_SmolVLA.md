# RB-Y1 T1~T10에서 SmolVLA 학습 및 평가

---

# 0️⃣ VLA와 SmolVLA란?

<https://huggingface.co/blog/smolvla>
<https://huggingface.co/lerobot/smolvla_base>
<https://github.com/huggingface/lerobot>

**VLA(Vision-Language-Action) 모델**은 카메라 영상(Vision)과 언어 지시문(Language)을 함께 보고 로봇 동작(Action)을 바로 출력하는 정책입니다. IL 실습의 BC 정책은 task 하나만 배웠지만, VLA는 지시문을 바꿔 가며 **모델 하나로 여러 task**를 수행합니다.

**SmolVLA**는 Hugging Face LeRobot 팀이 공개한 작은 VLA입니다(전체 4.5억 파라미터). 영상·언어를 이해하는 VLM(SmolVLM2-500M의 앞 16층)과, 그 정보를 받아 로봇 동작을 만드는 **action expert**로 이루어져 있습니다. action expert는 flow matching으로 한 번에 50 step 분량의 동작 묶음(**action chunk**)을 만듭니다. `lerobot/smolvla_base`는 커뮤니티 로봇 데이터로 미리 학습된 가중치이고, 이번 실습에서는 이것을 우리 RB-Y1 시뮬레이션 데이터로 **미세조정(fine-tuning)** 합니다.

이번 실습의 입력과 출력은 다음과 같습니다.

![SmolVLA 입력과 출력](assets/smolvla_io.png)

| 구분 | 내용 |
|---|---|
| 입력 영상 | `front`(머리 카메라 480×640), `left`·`right`(손목 카메라 640×480 세로) |
| 입력 상태 | 16차원: 오른팔 관절 7, 왼팔 관절 7, 오른손·왼손 그리퍼 열림 정도(0~1) |
| 입력 언어 | task의 지시문 (예: `put the black bowl on the plate.`) |
| 출력 | 16차원 action × 50 step. 팔은 다음 step의 절대 관절 목표(rad), 그리퍼는 열기 1 / 닫기 0 |

전체 흐름: **오라클로 시범 수집 → LeRobot 데이터셋 변환·검증 → SmolVLA 학습 → task마다 50회 평가**

---

# 0️⃣ 환경 확인

1. **Course version이 고정되었는가?**

    ```bash
    conda activate lerobot-arena
    cd ~/lightwheel_rby1_transfer
    git checkout vla-lab-v1
    ./vla_lab/check_env.sh
    ```

    조교 PC 출력:

    ```text
    ⟪ENV_CHECK⟫
    ```

    - GPU 이름과 메모리는 PC마다 다릅니다. 나머지 버전이 같으면 됩니다.
    - `SmolVLA weights`가 `MISSING`이면 아래 **추가 설치**를 먼저 하십시오.

2. **경로 설정 확인**

    ```bash
    conda activate lerobot-arena
    cd ~/lightwheel_rby1_transfer
    ./run_python.sh scripts/project_paths.py
    ```

    `RBY_USD`, `LIGHTWHEEL_CACHE`가 실제 있는 경로로 나오면 됩니다. 레포 위치가 다르면 README의 `RBY1_*` 환경변수를 설정합니다.

# 추가 설치

⟪EXTRA_INSTALL⟫

---

# 1️⃣ Task 소개

10개 task를 **모델 하나**로 학습합니다. 모델은 지시문을 보고 어떤 task인지 구분합니다.

![T1~T10 초기 장면](assets/T1-T10_front_2x5.jpg)

| Task | 지시문 (모델 입력) | 작업 | 역할 |
|---|---|---|---|
| T1 | `put the black bowl on the plate.` | 검은 그릇을 접시에 놓기 | Basic Pick-and-Place |
| T2 | `Pick the akita black bowl on the cookies box and place it on the plate.` | 쿠키 상자 위의 그릇을 접시에 놓기 | Spatial Relational Pick-and-Place |
| T3 | `Pick up the ketchup, and put it in the basket.` | 케첩을 바구니에 넣기 | Object-Variation Pick-and-Place |
| T4 | `Open the top drawer of the cabinet.` | 수납장 위 서랍 열기 | Single-Step Articulated Manipulation |
| T5 | `Open the microwave.` | 전자레인지 문 열기 | Articulated Appliance Manipulation |
| T6 | `Turn on the stove.` | 스토브 켜기 | Contact / Actuation |
| T7 | `Open the top layer of the drawer and put the bowl inside.` | 위 서랍을 열고 그릇 넣기 | Compositional Manipulation |
| T8 | `Stack the black bowl in the middle on the black bowl at the back.` | 가운데 그릇을 뒤쪽 그릇 위에 쌓기 | Precision Stacking |
| T9 | `Put the black bowl in the bottom drawer of the cabinet and close it.` | 그릇을 아래 서랍에 넣고 닫기 | Long-Horizon Sequential Manipulation |
| T10 | `Pick up the alphabet soup and the tomato sauce, and put them in the basket.` | 알파벳 수프와 토마토 소스를 바구니에 넣기 | Multi-Object Sequential Manipulation |

- 물체 위치와 방향은 에피소드마다 `environments/Txx.json`의 `randomization` 범위 안에서 바뀝니다. 같은 seed는 항상 같은 배치입니다.
- 성공 판정은 레포의 `success_original`(LW-BenchHub 원본 판정)입니다. 조건을 만족한 뒤 약 3.5초(52 step)가 지나야 성공으로 확정됩니다. 대부분의 task는 **그리퍼가 물체에서 멀어져야** 성공입니다.

---

# 2️⃣ 오라클 데이터 수집

사람이 키보드로 500개 시범을 모으기는 어렵습니다. 그래서 시뮬레이터의 **정답 상태**(물체·손잡이·서랍의 실제 위치)를 읽어 움직이는 스크립트, 즉 **오라클(oracle)**로 시범을 모읍니다.

## (1) 동작 원리

- 시범 하나 = 하위 동작의 고정된 순서입니다. 예: T1은 `접근 → 파지 전 자세 → 파지 → 들기 → 운반 → 놓기 → 놓은 뒤 위로 → 준비 자세로 복귀`.
- 각 하위 동작을 시작할 때 정답 상태로 목표 위치를 계산하고, 그리퍼 끝(TCP)을 부드러운 직선 경로로 움직입니다.
- 제어 경로는 키보드/VR 수집기와 같습니다: **Differential IK(DLS) → 18개 관절 절대 목표**, 관절 속도 제한 0.8 rad/s, 15fps(물리 1/105초 × 7).
- 기록 형식도 키보드 수집기와 같은 raw 형식(`<output>_raw/episode-*/`)입니다. 그래서 기존 `export_dataset.sh`, `--validate`, `replay_dataset.sh`가 그대로 동작합니다.
- **복구 동작은 없습니다.** 재파지, 노이즈, 재시도를 하지 않습니다. 첫 시도가 실패한 seed는 저장하지 않고 다음 seed로 넘어갑니다(실패 수와 원인만 기록).
- 오라클 자체에는 무작위성이 없습니다. 물체 배치만 seed(`numpy.random.default_rng(seed)`)로 정해집니다.
- 성공 판정 후 저장 직전에 원래 조건이 아직 성립하는지 한 번 더 확인합니다. `success_original`은 조건이 한 번 성립하면 3.5초 뒤 확정되므로, 그사이 물체가 미끄러져 조건이 깨진 시범도 성공으로 남을 수 있기 때문입니다(실패 원인 `latched_then_undone`).

| Task | 사용하는 팔 | 하위 동작 |
|---|---|---|
| T1 | 왼팔 | 그릇의 로봇 쪽 테두리 집기 → 들기 → 접시 위로 운반 → 놓기 → 위로 → 준비 자세 |
| T2 | 왼팔 | T1과 같음 (쿠키 상자 위 그릇, 더 얕게 집기) |
| T3 | 왼팔 | 케첩 위에서 수직으로 집기 → 바구니 테두리 위로 들기 → 바구니 안에 놓기 → 준비 자세 |
| T4 | 왼팔 | 손잡이에 접근 → 손가락 하나를 손잡이 뒤 틈에 걸어 잡기 → 14cm 당기기 → 놓고 위·뒤로 → 준비 자세 |
| T5 | 오른팔 | 손잡이(세로 막대) 잡기 → 경첩 중심으로 원호를 따라 68° 열기 → 놓고 뒤로 → 준비 자세 |
| T6 | 왼팔 | 손잡이 능선을 위에서 집기 → 수직축으로 0.9 rad 돌리기 → 놓고 위로 → 준비 자세 |
| T7 | 왼팔 | 위 서랍 끝까지 당기기 → 그릇 테두리 집기 → 높이 들어 서랍 위로 → 서랍 앞쪽에 놓기 → 서랍에서 떨어진 자세 |
| T8 | 왼팔 | 가운데 그릇 테두리 집기 → 뒤쪽 그릇 위로 운반 → 놓기 → 준비 자세 |
| T9 | 왼팔 | 그릇을 열린 아래 서랍에 넣기 → 손끝으로 손잡이를 밀어 닫기(2단계) → 준비 자세 |
| T10 | 왼팔 → 오른팔 | 수프(왼팔)를 바구니에 넣고 복귀 → 토마토 소스(오른팔)를 바구니에 넣고 복귀 |

## (2) 수집 명령어

conda 환경 활성화

```bash
conda activate lerobot-arena
```

task 하나 수집 (T1, 성공 시범 50개, seed 0부터)

```bash
cd ~/lightwheel_rby1_transfer
./vla_lab/collect_oracle.sh --task T1 --num-demos 50 --seed-start 0
```

T1~T10 전부 순서대로 수집

```bash
cd ~/lightwheel_rby1_transfer
for T in T1 T2 T3 T4 T5 T6 T7 T8 T9 T10; do
    ./vla_lab/collect_oracle.sh --task $T --num-demos 50 --seed-start 0
done
```

| 인자 | 기본값 | 설명 |
|---|---|---|
| `--task` | (필수) | T1~T10 |
| `--num-demos` | 50 | 저장할 **성공** 시범 수 |
| `--seed-start` | 0 | 첫 시도의 배치 seed. 시도 k는 seed `seed-start + k` |
| `--max-attempts` | 3 × num-demos | 이 횟수만큼 시도하면 멈춤 |
| `--output` | `~/datasets/vla_lab/<task>/oracle` | LeRobot 데이터셋 폴더. raw는 `<output>_raw` |
| `--joint-speed` | 0.8 | 관절 속도 제한(rad/s), 수집기 기본값과 같음 |
| `--video` | 없음 | 첫 성공 시범을 정면 카메라 mp4로 저장 |

- 학습 seed는 0~9999 범위만 씁니다. 평가 seed는 100000번대라 겹치지 않습니다.
- 수집이 중간에 끊기면 같은 명령을 다시 실행하십시오. `<output>_raw/oracle_attempts.jsonl`을 읽고 마지막 seed 다음부터 이어서 수집합니다.

## (3) 출력 예시

```text
⟪ORACLE_LOG⟫
```

- `<output>_raw/oracle_attempts.jsonl`: 시도마다 seed, 저장 여부, 길이, 실패한 하위 동작.
- `<output>_raw/oracle_summary.json`: 시도 수, 성공 수, 오라클 성공률, 실패 원인별 횟수.

## (4) 오라클 결과 (조교 PC)

⟪ORACLE_RESULTS⟫

⟪ORACLE_VIDEOS⟫


---

# 3️⃣ 변환·검증·재생

수집기는 raw 기록만 저장합니다. 학습에 쓰려면 레포의 기존 도구로 **LeRobot v3 데이터셋**으로 바꾸고, 원본과 일치하는지 검증합니다. 변환 형식은 실제 RB-Y1 데이터셋과 같은 `rby1` 형식입니다(15fps, state/action 16차원, 카메라 3대 AV1 영상).

## (1) task별 변환 + 검증

```bash
conda activate lerobot-arena
cd ~/lightwheel_rby1_transfer
for T in T1 T2 T3 T4 T5 T6 T7 T8 T9 T10; do
    ./export_dataset.sh --output ~/datasets/vla_lab/$T/oracle --format rby1 --validate
done
```

- `--validate`는 LeRobot 로딩, raw 기록과 숫자 완전 일치, 영상 프레임 수, 성공 판정 재계산을 확인합니다. 마지막에 다음과 같이 나오면 됩니다(T1 예시).

```text
⟪VALIDATE_T1⟫
```

- 변환 시간: ⟪EXPORT_TIME⟫
- 검증 결과는 `~/datasets/vla_lab/<task>/validation.json`에 저장됩니다.

## (2) 10개 task를 데이터셋 하나로 합치기

SmolVLA를 **모델 하나**로 학습하려면 10개 데이터셋을 하나로 합칩니다. 에피소드마다 원래 지시문이 그대로 task 문자열로 남고, 스크립트가 `selected_tasks.csv`의 지시문과 같은지 확인합니다.

```bash
conda activate lerobot-arena
cd ~/lightwheel_rby1_transfer
./run_python.sh vla_lab/scripts/merge_datasets.py \
    --inputs ~/datasets/vla_lab/T{1,2,3,4,5,6,7,8,9,10}/oracle \
    --output ~/datasets/vla_lab/merged/RBY1-T1-T10-Oracle
```

```text
⟪MERGE_LOG⟫
```

## (3) 데이터 요약

IL 실습의 `summarize_demos.py`처럼 task별로 시범 길이와 그리퍼 사용을 확인합니다.

```bash
conda activate lerobot-arena
cd ~/lightwheel_rby1_transfer
./run_python.sh vla_lab/scripts/summarize_dataset.py --root ~/datasets/vla_lab/merged/RBY1-T1-T10-Oracle
```

```text
⟪SUMMARY_TABLE⟫
```

- `len` — 시범 길이(step 수). `sec`는 15fps 기준 초(len / 15).
- `switch` — 그리퍼 열기/닫기 전환 횟수(두 손 합).
- `idle` — 팔 관절 목표가 모든 관절에서 0.001 rad 미만으로 바뀐 step의 비율. 파지·놓기 대기와, 마지막에 성공 판정이 확정되기까지 기다리는 약 3.5초가 포함됩니다.

## (4) 재생으로 확인

변환한 시범을 시뮬레이터에서 다시 실행해 성공이 재현되는지 봅니다. `--mode action`은 기록된 관절 목표를 수집 때와 같은 물리 step으로 다시 실행합니다.

```bash
conda activate lerobot-arena
cd ~/lightwheel_rby1_transfer
./replay_dataset.sh --root ~/datasets/vla_lab/T1/oracle --episode 0,1 --mode action --headless --video ~/vla_lab_runs/replay/
```

```text
⟪REPLAY_LOG⟫
```

`replayed_success_original: true`이면 재현된 것입니다. `--headless`를 빼면 창으로 볼 수 있습니다.

[▶ T1 시범 재생 (episode 0, action 모드)](assets/replay/T1_episode_0_action.mp4)


---

# 4️⃣ SmolVLA 학습

## (1) 학습 명령어

conda 환경 활성화

```bash
conda activate lerobot-arena
```

학습 실행 (T1~T10 멀티태스크 모델 1개)

```bash
cd ~/lightwheel_rby1_transfer
./vla_lab/train_smolvla.sh --output_dir ~/vla_lab_runs/smolvla_t1_t10
```

- `vla_lab/train_smolvla.sh`는 LeRobot의 `lerobot-train`을 그대로 부르는 래퍼입니다. 아래 표의 값을 넣고, PyTorch가 GPU 메모리를 **7.0GB까지만** 쓰도록 막습니다(`torch.cuda.set_per_process_memory_fraction`). 넘으면 학습이 OOM으로 멈추므로, 끝까지 돌면 8GB GPU에서도 돈다는 뜻입니다.
- 뒤에 붙인 인자는 기본값을 덮어씁니다. 예: `--steps=300`(짧은 시험), `--batch_size=8`.
- `--output_dir`이 이미 있으면 LeRobot이 에러를 냅니다. 다른 이름을 쓰십시오.
- 데이터셋 위치가 다르면 `VLA_DATASET_ROOT=/path/to/RBY1-T1-T10-Oracle`를 앞에 붙입니다.

⟪TRAIN_TIME⟫

## (2) 학습 결과 폴더

```text
⟪RUN_TREE⟫
```

- `checkpoints/last`는 마지막 체크포인트를 가리키는 링크입니다. **평가는 `checkpoints/last/pretrained_model`로 합니다.**
- 5000 step마다 `checkpoints/005000` 같은 폴더가 생깁니다. 비교해 보고 싶을 때 쓰십시오.

## (3) 학습 로그 보기

로그는 터미널에 100 step마다 나옵니다. 파일로 남기려면 명령 뒤에 `2>&1 | tee ~/vla_lab_runs/train.log`를 붙입니다.

```text
⟪TRAIN_LOG⟫
```

| 항목 | 의미 |
|---|---|
| `loss` | flow matching 손실(정규화된 action 공간) |
| `grdn` | gradient norm (clip 10) |
| `lr` | 학습률 (warmup 1000 step 후 cosine 감소) |
| `updt_s` | step 하나의 학습 시간(초) |
| `data_s` | step 하나의 데이터 로딩 시간(초). `updt_s`보다 크면 `--num_workers`를 늘리십시오 |

W&B를 쓰려면 `--wandb.enable=true --wandb.project=<프로젝트>`를 붙입니다(로그인 필요).

## (4) 하이퍼파라미터

⟪HPARAM_TABLE⟫

## (5) CLI에서 바로 바꿀 수 있는 주요 인자

| 인자 | 예시 | 설명 |
|---|---|---|
| `--output_dir` | `~/vla_lab_runs/exp1` | 결과 폴더 (없어야 함) |
| `--steps` | `--steps=30000` | 학습 step 수 |
| `--batch_size` | `--batch_size=8` | 배치 크기. VRAM이 부족하면 줄이기 |
| `--save_freq` | `--save_freq=2000` | 체크포인트 간격 |
| `--seed` | `--seed=7` | 학습 seed |
| `--num_workers` | `--num_workers=8` | 데이터 로딩 프로세스 수 |
| `--policy.optimizer_lr` | `--policy.optimizer_lr=5e-5` | 학습률 |
| `--policy.scheduler_decay_steps` | `--policy.scheduler_decay_steps=30000` | cosine 감소 길이 (보통 `--steps`와 같게) |
| `--policy.train_expert_only` | `false` | VLM까지 학습 (VRAM 크게 증가) |
| `--policy.n_action_steps` | `--policy.n_action_steps=10` | chunk 50개 중 실제로 실행할 step 수 |
| `--resume` | `--resume=true --config_path=<RUN_FOLDER>/checkpoints/last/pretrained_model/train_config.json` | 끊긴 학습 이어서 |
| `--wandb.enable` | `true` | W&B 로깅 |


---

# 5️⃣ 평가

레포에는 학습한 정책을 시뮬레이터에서 돌리는 스크립트가 없어서 `vla_lab/eval_smolvla.sh`를 만들었습니다.

- 수집과 **같은** 장면, 카메라, 15fps 제어, `success_original`을 씁니다.
- task마다 고정된 seed 50개(`vla_lab/eval_seeds/Txx.json`, 100000~100049)로 시작 배치를 정합니다. 같은 명령이면 같은 배치입니다.
- 한 에피소드는 `success_original`이 참이 되거나 최대 step에 도달하면 끝납니다. 최대 step은 **오라클 시범 중 가장 긴 것의 2배**입니다(`vla_lab/eval_horizons.json`).
- 정책 출력의 팔 관절 목표는 그대로, 그리퍼는 0.5 기준 열기/닫기 명령으로 씁니다(수집기와 같은 손가락 속도 제한).

## (1) 평가 명령어

conda 환경 활성화

```bash
conda activate lerobot-arena
```

10개 task × 50회 평가

```bash
cd ~/lightwheel_rby1_transfer
./vla_lab/eval_smolvla.sh \
    --policy-path ~/vla_lab_runs/smolvla_t1_t10/checkpoints/last/pretrained_model \
    --output ~/vla_lab_runs/eval_smolvla_t1_t10
```

일부 task만, 적은 횟수로 빠르게 확인

```bash
cd ~/lightwheel_rby1_transfer
./vla_lab/eval_smolvla.sh \
    --policy-path ~/vla_lab_runs/smolvla_t1_t10/checkpoints/last/pretrained_model \
    --output ~/vla_lab_runs/eval_quick --tasks "T1 T4" --episodes 3
```

| 인자 | 기본값 | 설명 |
|---|---|---|
| `--policy-path` | (필수) | `<RUN_FOLDER>/checkpoints/last/pretrained_model` |
| `--output` | (필수) | 결과 폴더 |
| `--tasks` | `"T1 ... T10"` | 평가할 task (따옴표 안에 공백으로 구분) |
| `--episodes` | 50 | task당 에피소드 수 (seed 목록의 앞에서부터) |
| `--no-video` | 꺼짐 | 성공·실패 영상을 남기지 않음 (조금 빨라짐) |
| `--n-action-steps` | 체크포인트 설정(50) | chunk 50개 중 몇 step을 실행하고 다시 추론할지 |

⟪EVAL_TIME⟫

## (2) 출력 예시

```text
⟪EVAL_LOG⟫
```

## (3) 결과 (조교 baseline)

⟪EVAL_TABLE⟫

## (4) 성공·실패 영상

⟪EVAL_VIDEOS⟫

## (5) 결과 파일 위치

```text
⟪EVAL_TREE⟫
```

- `results.json`: task별 성공 수, 성공률, 95% 신뢰구간(Clopper-Pearson), 10개 task 평균.
- `Txx/episodes.json`: 에피소드별 seed, 성공 여부, step 수, 시간.
- `Txx/episode_seedNNNNNN.npz`: 정책 action과 매 step의 관측 신호(TCP, 그리퍼, 물체 위치, 관절). 실패 분석에 씁니다.


---

# 6️⃣ VRAM 확인 방법

모든 단계는 **VRAM 8GB 이하**에서 돌도록 맞췄습니다. 각자 PC에서 직접 확인하는 방법입니다.

## (1) 다른 터미널에서 1초마다 보기

```bash
nvidia-smi --query-compute-apps=pid,used_memory --format=csv -l 1
```

## (2) 명령을 감싸서 최대값 기록하기

`vla_lab/scripts/vram_monitor.py`는 위 명령을 1초마다 실행해 모든 프로세스의 합계를 CSV로 남기고, 끝나면 최대값을 출력합니다.

```bash
conda activate lerobot-arena
cd ~/lightwheel_rby1_transfer
python vla_lab/scripts/vram_monitor.py --out ~/vla_lab_runs/vram_train.csv -- \
    ./vla_lab/train_smolvla.sh --output_dir ~/vla_lab_runs/vram_test --steps=200
```

```text
⟪VRAM_LOG⟫
```

- `peak_total_mib`: 1초 간격으로 잰 **모든 GPU 프로세스 합계**의 최대값. 다른 프로그램(다른 시뮬레이터, 브라우저 등)이 GPU를 쓰면 함께 더해지므로 측정할 때는 끄십시오.
- `peak_mib_per_pid`: 프로세스별 최대값.
- 이미 있는 CSV의 최대값만 보려면 `python vla_lab/scripts/vram_monitor.py --summary <csv>`.

## (3) 조교 PC 측정값

⟪VRAM_TABLE⟫


---

# 7️⃣ 문제 해결 FAQ

⟪SECTION_FAQ⟫

---

# 8️⃣ 더 발전시키려면

이번 baseline에는 일부러 넣지 **않은** 것들이 있습니다. 정답은 주지 않습니다. 질문과 단서만 적습니다.

1. **복구 시범이 없다.** 오라클은 항상 첫 시도에 성공한 깨끗한 시범만 보여 줍니다.
    - 정책이 그릇을 살짝 놓쳤을 때, 학습 데이터에 그 상황에서 어떻게 해야 하는지가 있었나요?
    - 단서: 평가 실패 영상에서 "처음 실수 직후" 장면을 보십시오. 그 상태에서 시작하는 시범을 만들 수 있을까요?
2. **노이즈 주입이 없다.** 오라클 경로는 매번 같은 모양입니다.
    - 학습 때 본 적 없는 약간 어긋난 상태에서 정책은 어떻게 행동할까요?
    - 단서: DART(Laskey et al., 2017). 시범을 기록할 때 실행 동작에만 작은 노이즈를 넣고, 기록하는 action은 원래 오라클의 것으로 두면 무엇이 달라질까요?
3. **다양성 조절.** 물체 배치 범위는 레포 기본값(`randomization`) 그대로입니다.
    - 범위를 넓히면 평가가 쉬워질까요, 어려워질까요? 시범 수는 얼마나 더 필요할까요?
4. **시범 수.** task당 50개입니다.
    - 25개, 100개로 바꾸면 성공률 곡선이 어떻게 변하나요? 어떤 task가 데이터에 가장 민감한가요?
5. **학습 설정.**
    - 평가 때 `--n-action-steps 10`으로 더 자주 다시 계획하면 접촉이 많은 T5, T9에서 결과가 달라질까요?
    - 체크포인트 5000/10000/15000/20000 중 어느 것이 가장 좋은가요? 손실(loss)이 낮을수록 성공률도 높은가요?
6. **실패 분석.** `vla_lab/scripts/failure_analysis.py`로 실패를 단계(접근·파지·운반·배치·시간 초과)별로 나눠 보고, 가장 많이 실패하는 단계를 먼저 공략하십시오.

