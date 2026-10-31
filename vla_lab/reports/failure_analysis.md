# 실패 분석 (조교용)

- 평가: `~/vla_lab_runs/smolvla_t1_t10/checkpoints/last/pretrained_model` (25,000 step), task당 50회, seed 100000~100049, `success_original`
- 결과: 286/500 성공, 10개 task 평균 57.2% (`vla_lab/reports/eval_results.txt`)
- 데이터·물리: 로봇 자기충돌이 켜진 asset(`rby1-sim-isaac` `selfcollision-hulls`)으로 다시 수집·학습·평가한 결과. 이전(자기충돌 꺼짐) 결과는 253/500, 50.6%였다.
- 도구: `python vla_lab/scripts/failure_analysis.py --eval ~/vla_lab_runs/eval_smolvla_t1_t10`

## 분류 기준 (관측 가능한 신호만 사용)

매 step 기록한 TCP 위치(양손), 그리퍼 열림 정도, 물체 중심, 서랍·문·손잡이 관절 값, 시작 시 손잡이·노브 위치로 판정합니다. 위에서부터 처음 해당하는 단계로 분류합니다.

| 단계 | 기준 |
|---|---|
| 접근 | 두 TCP 모두 목표 물체(또는 손잡이·노브)에 8cm 이내로 온 적이 없고, 물체가 2cm 이상 움직이지 않음 |
| 파지 | 물체 중심이 3cm 이상 올라간 적이 없음(밀거나 넘어뜨림 포함). 관절 task는 필요한 변화량의 10% 미만으로 움직임 |
| 운반 | 들어 올렸지만 끝났을 때 목표에서 성공 반경의 1.5배보다 멀거나 바닥에 떨어짐 |
| 배치·조작 | 목표 근처지만 성공 반경 밖. 관절 task는 움직였지만 기준(T4 0.115m, T5 0.942rad, T9 0.00115m 이하)에 못 미침 |
| 시간 초과 | 끝났을 때 목표 조건은 만족하지만 그리퍼가 덜 물러났거나 3.5초 확정 시간이 모자람 |

성공 반경: T1 0.065m(접시), T2 0.08m, T3·T10 0.10m(바구니), T8 0.14m(뒤쪽 그릇). T7·T9는 서랍 단계를 먼저 판정합니다.

## 단계별 실패 수

| Task | 실패/전체 | 접근 | 파지 | 운반 | 배치·조작 | 시간 초과 |
|---|---|---|---|---|---|---|
| T1 | 8/50 | 0 | 4 | 4 | 0 | 0 |
| T2 | 25/50 | 0 | 17 | 6 | 1 | 1 |
| T3 | 34/50 | 4 | 26 | 4 | 0 | 0 |
| T4 | 25/50 | 0 | 0 | 0 | 24 | 1 |
| T5 | 5/50 | 0 | 0 | 0 | 5 | 0 |
| T6 | 1/50 | 0 | 0 | 0 | 1 | 0 |
| T7 | 39/50 | 0 | 9 | 4 | 26 | 0 |
| T8 | 11/50 | 0 | 7 | 1 | 1 | 2 |
| T9 | 27/50 | 0 | 17 | 3 | 7 | 0 |
| T10 | 39/50 | 0 | 30 | 9 | 0 | 0 |
| 합계 | 214/500 | 4 | 110 | 31 | 65 | 4 |

## task별 관찰

- **파지 실패가 가장 많습니다(110/214, 51%).** 그리퍼가 물체에 다가가 닫히지만 물체를 들지 못하고 밀거나 놓칩니다. 특히 T10(캔 30회), T3(케첩 26회), T2·T9(그릇 각 17회). 오라클 시범에는 파지에 실패한 뒤 다시 잡는 장면이 없으므로, 첫 접촉이 조금만 어긋나도 정책이 회복하지 못합니다.
- **T7 실패 39회 중 25회는 위 서랍을 충분히 열지 못한 경우**입니다(끝났을 때 열림 중앙값 0.028m, 최대 0.064m, 필요 0.069m). 서랍을 연 뒤 그릇을 들지 못한 경우가 9회입니다.
- **T4 실패 25회 중 24회는 서랍을 움직였지만 기준(0.115m)에 못 미친 경우**입니다. 17회는 0.106m 이상으로 아슬아슬했고, 7회는 0.05~0.106m였습니다.
- **T5 실패 5회는 모두 문을 덜 연 경우**입니다(최종 각도 0.58~0.84 rad, 중앙값 0.72, 필요 0.942 rad). 이전 데이터(손잡이를 따라 68° 여는 시범)로 학습했을 때는 12회였습니다.
- **T9는 그릇 파지 17, 운반 3, 서랍을 덜 닫음 7**(남은 간격 중앙값 0.011m)입니다.
- **T6 49/50, T5 45/50, T1 42/50, T8 39/50**: 짧고 단일 접촉인 task는 잘 됩니다.
- **접근 실패는 4회(모두 T3), 시간 초과는 4회**입니다. 대부분 시간이 남은 채로 실패 상태에서 멈춰 있습니다(재시도 없음).
- **평가 500회 중 로봇 링크끼리 닿은 에피소드는 0회**입니다(`eval_smolvla.py`가 PhysX 접촉 보고로 기록).

## 대표 영상

`eval_smolvla.py`가 task마다 첫 성공·첫 실패 에피소드를 정면 카메라로 저장한 것입니다.

| Task | 영상 |
|---|---|
| T1 | [성공](../docs/assets/eval/T1_success_seed100000.mp4) · [실패](../docs/assets/eval/T1_failure_seed100001.mp4) |
| T2 | [성공](../docs/assets/eval/T2_success_seed100003.mp4) · [실패](../docs/assets/eval/T2_failure_seed100000.mp4) |
| T3 | [성공](../docs/assets/eval/T3_success_seed100004.mp4) · [실패](../docs/assets/eval/T3_failure_seed100000.mp4) |
| T4 | [성공](../docs/assets/eval/T4_success_seed100001.mp4) · [실패](../docs/assets/eval/T4_failure_seed100000.mp4) |
| T5 | [성공](../docs/assets/eval/T5_success_seed100000.mp4) · [실패](../docs/assets/eval/T5_failure_seed100009.mp4) |
| T6 | [성공](../docs/assets/eval/T6_success_seed100000.mp4) · [실패](../docs/assets/eval/T6_failure_seed100012.mp4) |
| T7 | [성공](../docs/assets/eval/T7_success_seed100005.mp4) · [실패](../docs/assets/eval/T7_failure_seed100000.mp4) |
| T8 | [성공](../docs/assets/eval/T8_success_seed100000.mp4) · [실패](../docs/assets/eval/T8_failure_seed100009.mp4) |
| T9 | [성공](../docs/assets/eval/T9_success_seed100000.mp4) · [실패](../docs/assets/eval/T9_failure_seed100001.mp4) |
| T10 | [성공](../docs/assets/eval/T10_success_seed100016.mp4) · [실패](../docs/assets/eval/T10_failure_seed100000.mp4) |

## 비결정성 메모

정책 추론은 같은 입력·같은 seed에서 완전히 같습니다(차이 0). 하지만 RTX 렌더러가 같은 장면을 두 번 그려도 픽셀이 조금 다르고, 이 차이로 첫 action부터 달라집니다. 그래서 같은 seed를 다시 평가해도 에피소드별 결과가 바뀔 수 있습니다. 측정 결과는 `vla_lab/reports/eval_determinism.md`에 있습니다.
