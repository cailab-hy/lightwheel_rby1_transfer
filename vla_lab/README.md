# vla_lab — 오라클 시범 + SmolVLA 실습 (T1~T10)

학생용 매뉴얼: [docs/VLA_실습_lightwheel_SmolVLA.md](docs/VLA_실습_lightwheel_SmolVLA.md) (HTML: `docs/VLA_실습_lightwheel_SmolVLA.html`)

| 파일 | 내용 |
|---|---|
| `collect_oracle.sh`, `scripts/collect_oracle.py`, `scripts/oracle.py` | 오라클 시범 수집 (정답 상태 사용, 첫 시도만, 키보드 수집기와 같은 raw 형식) |
| `scripts/sim_env.py` | 수집기와 같은 headless 환경 (수집·평가 공용) |
| `scripts/merge_datasets.py`, `scripts/summarize_dataset.py` | 10개 데이터셋 병합, task별 요약 |
| `train_smolvla.sh`, `scripts/train_smolvla.py` | `lerobot-train` 래퍼 (VRAM 7.0GB 상한) |
| `eval_smolvla.sh`, `scripts/eval_smolvla.py`, `scripts/eval_summary.py` | 시뮬레이터 평가 (task당 50회, Clopper-Pearson 95% 구간) |
| `eval_seeds/Txx.json`, `eval_horizons.json` | 평가 seed(100000~100049), task별 최대 step(오라클 최장 시범 × 2) |
| `scripts/failure_analysis.py` | 실패 단계 분류 (접근·파지·운반·배치·시간 초과) |
| `scripts/vram_monitor.py`, `check_env.sh` | VRAM 측정, 버전 확인 |
| `reports/` | 환경, 데이터 요약, 평가 결과, 실패 분석, 평가 결정성 |
| `PLAN.md` | 작업 계획과 결과 요약 |

조교 baseline: 시범 500개(오라클 성공률 93.6%) → SmolVLA 25,000 step → 253/500 성공, 10개 task 평균 50.6%.
