# VLA 실습 자료 제작 계획 (vla-lab-v1)

목표: T1~T10 오라클 시범 → SmolVLA 멀티태스크 미세조정 → task당 50회 평가. 모든 단계 VRAM 8GB 이하.

## 0. 확인한 환경 (2026-10-29)

| 항목 | 값 |
|---|---|
| GPU / 드라이버 | RTX 3090 24GB / 580.178.04 (CUDA 13.0 드라이버) |
| CPU / RAM | i5-8500 6코어 / 64GB |
| Python / PyTorch | 3.11.16 / 2.7.0+cu128 |
| Isaac Sim / IsaacLab | 5.1.0 / 2.3.0 (`~/IsaacLab_RS`, e83a5d2) |
| LeRobot | 0.4.3 (`~/lerobot`, v0.4.3 = 0b067df5, editable) |
| lightwheel_rby1_transfer | 1178454 (main) → 작업 브랜치 `vla-lab-v1` (완료 후 `main`에 합침) |
| rby1-sim-isaac | 146bec3 (ba52496 위에 자기충돌 asset. 작업 브랜치 `selfcollision-hulls`를 `main`에 합침) |

- 이 PC에는 `~/lerobot`, `~/rby1-sim-isaac`, `~/lightwheel_rby1_transfer`가 지워져 있어서 다시 clone했다.
  conda 환경(`lerobot-arena`)의 editable 설치 경로(`~/lerobot/src`)가 그대로라 패키지 재설치는 하지 않았다.
- 기존 키보드 수집기 T1 headless smoke test: `SMOKE_OK` (41초, 최대 VRAM 3.2GB).
- `lerobot/smolvla_base`, `HuggingFaceTB/SmolVLM2-500M-Video-Instruct`는 HF 캐시에 이미 있다(추가 다운로드 없음).

## 1. SmolVLA 기본값 (설치된 `lerobot/policies/smolvla/configuration_smolvla.py`)

| 항목 | 기본값 |
|---|---|
| chunk_size / n_action_steps | 50 / 50 |
| 이미지 | `resize_imgs_with_padding=(512,512)` |
| freeze_vision_encoder / train_expert_only / train_state_proj | True / True / True |
| VLM | SmolVLM2-500M, 앞 16층만 사용 (`num_vlm_layers=16`), VLM 가중치 bf16 로드 |
| 최적화 | AdamW lr 1e-4, warmup 1000, cosine decay 30000 → 2.5e-6, grad clip 10 |
| 학습 기본 batch / steps | 8 / 100000 (`TrainPipelineConfig`) |
| AMP | `policy.use_amp=false` (smolvla_base 설정) |

8GB 학습 초안: 동결 범위는 기본(전문가 + state proj만 학습), 카메라 3대, 512 패딩 유지, batch를 줄이며 실측.
예상: VLM bf16 가중치 ~1GB + 전문가 fp32 가중치·Adam 상태 ~1.5GB + 활성값. batch 8~16에서 7.5GB 이하가 목표.

## 2. 단계별 계획과 예상 시간

| 단계 | 내용 | 예상 시간 |
|---|---|---|
| 1 | 오라클 구현 (`vla_lab/scripts/oracle.py`, 공용 환경 `sim_env.py`) + task별 성공률 80% 이상 | 1일 |
| 2 | 시범 500개 수집(seed 0부터, 성공만 저장) → `export_dataset.sh --validate` → 병합 → 요약 → replay | 수집 ~6h + 변환 ~4h (task 병렬) |
| 3 | SmolVLA 학습 (VRAM 실측 후 step 수 결정, 12h 이내) | 8~12h |
| 4 | 평가 500회 (seed 100000~100049, `success_original`), 결정성 재확인 | ~6h |
| 5 | 실패 분석 | 2h |
| 6 | 학생 문서 (md + html) | 3h |
| 7 | 새 폴더 clone → 문서 명령만으로 축소판 재현 | 3h |

## 3. 정한 규칙

- seed: 학습 장면 0~9999 (task마다 0부터 시도 순서대로), 평가 장면 100000~100049 (task마다 같은 목록).
- 오라클: 무작위성 없음. 첫 시도만 기록, 실패 seed는 건너뜀(실패 원인만 기록). 복구·노이즈·재시도 없음.
- 제어: 수집기와 같은 absolute Differential IK(DLS λ=0.03) → 18D 관절 목표, 관절 속도 제한 0.8 rad/s, 15fps.
- raw 형식: 키보드 수집기와 같은 `episode-*/` 구조 → 기존 `export_dataset.sh --format rby1 --validate` 그대로 사용.
- 평가: 같은 장면·카메라·15fps·`success_original`. 최대 step은 task별 오라클 시범 길이 최대값의 2배.
- 체크포인트: 마지막 체크포인트(`checkpoints/last`)를 평가.

## 4. 결과 (2026-10-31, 로봇 자기충돌 켠 asset으로 재수집·재학습)

| 단계 | 결과 | 소요 (조교 PC) | 최대 VRAM |
|---|---|---|---|
| 오라클 수집 | 500/509 시도 저장 (98.2%), task별 90.9~100%, 로봇 자기 몸 접촉 0회 | 약 9시간 (task 3~4개 + 변환 동시) | 3.1~3.4GB |
| 변환·검증 | 10개 task `--validate` 통과, 병합 500 ep / 188,315 step | 변환 합계 약 8.4시간 (동시 실행), 병합 10분 | - |
| 학습 | 25,000 step, batch 16, loss 0.007 | 3시간 20분 | 6.50GB |
| 평가 | 286/500, 평균 57.2%, 자기 몸 접촉 0회 | 약 11시간 10분 (4~5개 동시) | 5.2GB |

- 첫 결과(자기충돌 꺼진 asset, 2026-10-30): 오라클 93.6%, 평가 253/500(50.6%). T5 오라클 시범 50개 모두 팔이 몸통을 통과해 asset과 오라클을 고치고 처음부터 다시 했다(`reports/self_collision_review.md`).
- 평가는 RTX 렌더링 픽셀 노이즈 때문에 에피소드 단위로 재현되지 않음(`reports/eval_determinism.md`). 수집은 비트 단위로 재현됨.
