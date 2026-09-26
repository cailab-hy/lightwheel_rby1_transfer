"""Write delivery report from verified artifacts; never label IK candidates as demonstrations."""
import project_paths as paths
import json,shutil,subprocess
from pathlib import Path
R=Path(str(paths.ROOT));X=Path(str(paths.X7S_SUBSET));B=Path(str(paths.RBY_DATASET))
def read(n):return json.loads((R/'reports'/n).read_text())
sel=json.loads((R/'selection.json').read_text());val=read('dataset_validation.json');raw=read('raw_validation_summary.json');sim=read('sim_scene_checks.json');reach=read('reachability.json');pilot=read('raw_multistart_audit.json');sweep=read('fixture_sweep_audit.json');fk=read('fk_sim_validation.json')
assert len(sim)==10 and all(v.get('head_render') and v.get('finite') and 'error' not in v for v in sim)
repos={'lw_benchhub':str(paths.BENCHHUB),'rby1-sim-isaac':str(paths.RBY_SIM),'lerobot':str(paths.LEROBOT),'cai-rby1-lerobot-v1.1':str(R/'references/cai-rby1-lerobot')}
commits={k:subprocess.check_output(['git','-C',v,'rev-parse','HEAD'],text=True).strip() for k,v in repos.items()}
status={'selection':'complete','source_subset':'validated','rby1_scenes':'10 adapted standalone USD scenes; 0.72 m tables; specified ready robot; physics initialization and head renders verified','rby1_reachability':'representative point IK and articulated handle waypoint checks; collision/contact/task success NOT verified','rby1_dataset_exported':False,'rby1_dataset_reason':'No validated RB-Y1 demonstrations: recorded active-arm trajectories still fail some sampled IK targets after alignment search and multi-start IK. Source RGB is X7S imagery. Contact-aware object-centric replanning, dynamic replay and RB-Y1 camera rendering remain necessary. This does not prove general retargeting impossible.','raw_hdf5_found':True,'raw_hdf5_episodes':500,'raw_kinematic_matching':'500 episodes; one duplicate pair has filename ambiguity','source_dataset':str(X),'rby1_requested_destination':str(B),'commits':commits}
(R/'reports/completion_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2))
B.mkdir(exist_ok=True,parents=True);D=B/'diagnostics';D.mkdir(exist_ok=True)
for n in ['source_transfer_summary.json','source_transfer_episodes.json','raw_retarget_pilot.json','raw_multistart_audit.json','raw_validation_summary.json','raw_episode_mapping.json','reachability.json','fixture_sweep_audit.json','fk_sim_validation.json','completion_status.json']:
 shutil.copy2(R/'reports'/n,D/n)
for p in (R/'reports').glob('T*_ik_diagnostic.npz'):shutil.copy2(p,D/p.name)
(B/'README.md').write_text('''# RB-Y1 변환 검토 결과 — 학습 데이터셋 아님

이 폴더에는 리매핑 진단 결과만 있습니다. 검증된 RB-Y1 시연을 확보하지 못해
LeRobot data/meta/videos를 생성하지 않았습니다.

원본 500 episode와 수치가 일치하는 공개 HDF5 500개를 확보했습니다.
HDF5에는 실제 말단 자세, 물체 상태, fixture 관절, 초기 장면 정보가 있으므로
재계획에 사용할 자료는 존재합니다. 원시 자료가 없어서 중단한 것은 아닙니다.

하지만 기록된 말단 경로의 좌표 정렬과 다중 초기값 IK 검사에서는
각 task의 시험 episode마다 일부 구간이 위치 1 cm / 자세 5° 기준을 통과하지 못했습니다.
이 결과는 시험한 정렬·TCP·IK 조건의 결과이며 모든 retargeting의 불가능성 증명이 아닙니다.

NPZ의 q는 샘플 위치에 대한 진단용 IK 후보입니다. 실패 해와 불연속이 포함될 수 있습니다.
로봇 명령으로 재생하거나 학습 정답으로 사용해서는 안 됩니다.
이 값은 충돌·속도·접촉·작업 성공을 검증한 궤적이 아닙니다.
원본 X7S 영상을 RB-Y1 영상으로 재사용하지 않았습니다.

후속 변환에 필요한 작업: 물체별 접촉 구간 정렬, RB-Y1 파지와 이동 경로 재계획,
충돌·관절 속도·물리 재생·작업 성공 검사, RB-Y1 카메라 재렌더링 후 성공 episode만 내보내기.

상세 보고서: ./REPORT_KO.md
원시 HDF5: ./raw_hdf5/
''')
lines=['# X7S T1–T10 선정·추출 및 RB-Y1 전환 검토','',
'**확정 결과:** 10개 task 선정, X7S 500 episode의 LeRobot 추출·검증, RB-Y1용 10개 독립 USD 장면 제작을 완료했습니다. **RB-Y1 LeRobot 시연 데이터는 생성하지 않았습니다.** 시험한 말단 궤적 변환이 모든 검사 구간을 통과하지 못했고, 충돌·접촉·작업 성공과 새 로봇 영상까지 검증한 시연이 없기 때문입니다. 아래에서 장면 생성, 기구학적 도달성, 실제 작업 성공을 구분합니다.','',
'## 1. 선정 결과','',
'`~/Downloads/task_선정.pdf`의 역할 배분을 유지했습니다. 기본 집기·놓기, 공간 관계, 물체 변화, 서랍, 회전식 가전, 접촉 작동, 동작 조합, 정밀 적층, 긴 순차 동작, 다중 물체 순차 동작을 각각 담당하도록 선정했습니다. PDF 이외의 미제공 PaMQR-chunk 정량 기준을 임의로 추가하지 않았습니다.','',
'이번 실험에는 **LIBERO를 권합니다.** 기존 10개 중 8개가 X7S에 같은 task 이름으로 존재하고, 나머지 2개도 역할을 유지하는 유사 task가 있습니다. 0.72 m 책상 조작과 기존 PaMQR-chunk 비교를 중심으로 보면 이 연속성이 유리합니다. RoboCasa는 이동·넓은 주방·다양한 가전 조작을 포함하는 후속 RB-Y1 실험의 후보지만, 로봇 크기만으로 더 적합하다고 판단할 수는 없습니다. 현재 제공 USD는 베이스와 몸통이 고정되어 있어 이동 작업의 이점도 바로 활용할 수 없습니다.','',
'선정 CSV: `selected_tasks.csv` — UTF-8 BOM, 요청한 6개 열만 포함. Language Instruction은 원본 episode의 실제 문자열입니다.','',
'| Task | 선정 task | 원본 task_index | episode | 프레임 | 기존 task와 관계 | layout/style |','|---|---|---:|---:|---:|---|---|']
for s in sel:lines.append(f"| {s['Task']} | {s['Task 이름']} | {s['source_task_index']} | {s['episodes']} | {s['frames']:,} | {'동일' if s['match']=='exact' else '유사 대체'} | {s['LIBERO 레이아웃 번호']} |")
lines+=['',
'T3는 없는 `LOPickUpTheKetchupAndPlaceItInTheBasket` 대신 `L90L1PickUpTheKetchupAndPutItInTheBasket`를 사용했습니다. 케첩→바구니 의미는 유지하지만 배치와 distractor까지 같지는 않습니다. T9는 없는 `L10K6PutTheYellowAndWhiteMugInTheMicrowaveAndCloseIt` 대신 그릇을 아래 서랍에 넣고 닫는 task를 사용했습니다. 내부 배치 후 닫기의 순서 의존성은 유지하지만 물체와 관절 종류가 다릅니다.','',
'레이아웃은 로컬 LW-BenchHub 매핑을 확인한 뒤, 공개 원시 HDF5 500개의 `data.attrs.env_args`에 기록된 `layout_id/style_id`로 전수 확인했습니다. `L90K2`의 K2가 layout 2를 뜻하지는 않습니다. T4·T8은 `libero-1-1`입니다.','',
'Arena 문서의 요약 표에는 X7S 117개 task가 표시되지만, 현재 로컬 `meta/info.json`·`tasks.parquet`에는 206개(LIBERO 117, RoboCasa 89)가 있습니다. 추출에는 로컬의 실제 index를 사용했습니다.','',
'## 2. X7S LeRobot 데이터','',
f'출력: `{X}`. 요청대로 추출 경로는 단수 `~/dataset`, 원본과 RB-Y1 결과 경로는 복수 `~/datasets`로 구분했습니다.','',
'500 episode, 499,643프레임, 50 Hz, 카메라 3개(640×480), LeRobot v3.0입니다. task당 50개 episode를 모두 보존했습니다.','',
'```text','Lightwheel-Tasks-X7S-T1-T10/','├── selected_tasks.csv','├── data/chunk-000/file-000.parquet ... file-009.parquet','├── meta/','│   ├── info.json, stats.json, tasks.parquet','│   ├── episodes/chunk-000/file-000.parquet','│   ├── source_episode_mapping.json','│   └── raw_hdf5_episode_mapping.json','└── videos/','    ├── observation.images.first_person/chunk-000/file-000.mp4 ... file-009.mp4','    ├── observation.images.left_hand/chunk-000/file-000.mp4 ... file-009.mp4','    └── observation.images.right_hand/chunk-000/file-000.mp4 ... file-009.mp4','```','',
'각 카메라에서 `file-000.mp4`는 T1, `file-009.mp4`는 T10입니다. 한 MP4 안에 해당 task의 50개 episode가 이어지며 시작·끝은 episode 메타데이터에 기록했습니다.','',
'원본 state(25차원), action(21차원), processed_action(23차원)의 값과 순서를 유지했습니다. episode/task/global index, 데이터 파일 포인터, 카메라별 영상 offset을 다시 계산했습니다. 원본의 카메라마다 task 시작 offset이 달라 각각의 메타데이터를 사용했습니다. MP4는 정확한 프레임 경계를 위해 H.264 CRF 18로 재인코딩했으므로 원본 바이트와 동일하지 않습니다.','',
'검증: 전체 499,643프레임의 state/action/processed_action/timestamp/frame_index가 원본과 정확히 일치했습니다. MP4 30개의 프레임 수가 모두 일치했습니다. 원본·추출 영상 180개 프레임 쌍 비교의 최대 픽셀 MSE는 6.4358(0–255 RGB 척도)입니다. LeRobot 공식 로더로 499,643프레임 길이와 task 경계의 40개 관측을 실제로 읽었습니다.','',
'수치 통계는 모든 프레임으로 재계산했고, RGB 통계는 episode 중간 프레임 1개씩 카메라당 500장의 전체 픽셀로 계산했습니다. 500개 모두 train에 포함하며 별도 평가 분할이나 성공률 필터를 추가하지 않았습니다. 언어 문자열은 `tasks.parquet`, class 이름은 CSV와 `meta/task_selection.json`에 보존했습니다.','',
'검증 증거: `reports/numeric_source_validation.json`, `reports/dataset_validation.json`, `reports/extraction_video_checks.json`.','',
'## 3. RB-Y1 장면과 작업 영역','',
'`environments/T01.usd`–`T10.usd`는 지정한 `rby1_ready_reach_table.usd`를 참조하는 독립 USD 장면입니다. 원본 데이터·로봇 USD·기존 저장소 파일은 수정하지 않았습니다. 자산은 프로젝트의 `.assets/` 링크를 상대경로로 참조합니다. 다른 PC에서는 PORTABILITY_KO.md에 따라 외부 자산 위치를 설정하십시오.','',
'초기 자세는 v1.1 브랜치의 `READY_*` 상수를 사용했습니다. 전 관절 0이 아니라 실제 코드가 준비 자세로 사용하는 값입니다. 제공 USD의 v1.2 모델에 맞춰 torso [0,0,0,30,0,0]°, 왼팔 [15,65,15,-115,-75,-65,-5]°, 오른팔 [15,-65,-15,-115,75,-65,-5]°를 반영했습니다.','',
'이 ready USD는 베이스·몸통·머리가 고정되어 있고, torso 30°와 head +35°가 joint frame에 이미 반영되어 있습니다. 이를 관절각으로 중복 적용하지 않았습니다. 실제 설정의 head -35°와 USD +35° 부호 차이를 확인했습니다. 헤드 광축은 로봇 좌표 [0.4226,0,-0.9063]이고, 0.72 m 평면과 [0.6588,-0.00034,0.72]에서 교차합니다. 렌더링에서도 책상을 봅니다.','',
'상판 높이는 모두 0.72 m입니다. layout 1·8은 기존 테이블 높이를 조정했습니다. layout 2는 기존 둥근 테이블의 시각적 경계와 실제 접촉면 높이가 달라 평평한 작업 테이블로 교체했습니다. 물체와 fixture를 작업 범위 안으로 옮겼고, 서랍은 손잡이가 로봇을 향하게 회전했습니다. fixture의 world 고정 joint anchor도 같이 옮겼습니다. T9의 아래 서랍은 이동 범위의 75% 열린 상태로 시작합니다.','',
'원시 HDF5에서 확인한 크기를 반영했습니다. 예를 들어 T2 목표·비목표 그릇은 원본 자산의 0.6배, 접시는 0.8배이고, T3·T10 바구니는 자산 기본 scale 0.85를 반영했습니다.','',
'**장면의 범위:** 작업 의미를 유지한 고정 배치의 실험용 변형입니다. 원본 500 episode의 무작위 장면을 재구성한 것은 아닙니다. 2026-09-23에 원시 500 episode의 물체·fixture 목록을 전수 대조하여 생략된 항목을 복원했습니다. 모든 항목의 대응은 `reports/scene_inventory_audit.json`에 있습니다. 배치 조건은 기존 LIBERO benchmark와 다릅니다. LW-BenchHub task 성공 판정기·EnvHub/Gym 등록·정책은 연결하지 않았습니다.','',
f"10개 장면을 Isaac Sim에서 물리 실행하고 헤드 영상을 렌더링했습니다. 준비 자세 1초 후 최대 팔 관절 편차는 {max(v['max_arm_joint_drift_rad'] for v in sim):.6f} rad입니다. 물체가 상판 위에서 안정화되는 위치도 기록했습니다. 이미지: `reports/T01_head.png`–`T10_head.png`, `reports/scene_contact_sheet.png`.",'',
f"USD joint frame으로 구성한 FK와 Isaac Sim TCP 위치 차이는 최대 {max(v['error_m'] for v in fk):.3g} m입니다. RB-Y1 TCP는 finger 표면 z 범위 -0.0735..-0.1355 m의 중간(-0.1045 m)으로 정한 명목 접촉점입니다. 실제 파지의 접촉점 보정은 별도입니다.",'',
'대표 물체·조작부 좌표에 대한 IK 결과(위치 1 cm, 자세 5° 기준):','',
'| Task | 도달 가능한 대표 목표 / 검사 목표 |','|---|---:|']
for v in reach:lines.append(f"| {v['Task']} | {v['reachable_targets']} / {v['tested_targets']} |")
lines+=['','위 표는 대표 좌표의 도달성입니다. 그 자체로 파지·충돌 회피·작업 성공을 의미하지 않습니다. 추가로 실제 충돌 mesh의 손잡이 위치와 fixture joint axis를 사용해 관절 이동 경로를 검사했습니다.','',
'| Task | 손잡이 경로에서 IK 통과한 지점 | 최대 위치 오차 | 인접 검사점의 최대 관절 변화 |','|---|---:|---:|---:|']
for v in sweep:lines.append(f"| {v['Task']} | {v['reachable_waypoints']} / {v['tested_waypoints']} | {v['max_position_error_m']*1000:.1f} mm | {v['max_joint_step_rad']:.3f} rad |")
lines+=['',
'서랍은 75% 열림/닫힘, 전자레인지 문은 75°, 스토브 노브는 90° 회전의 21개 지점을 검사했습니다. 파지 기울기와 그리퍼 180° 대칭을 탐색했으며 실제 접촉이 성립하는지는 확인하지 않았습니다. IK 해가 지점별로 존재하더라도 불연속 해·충돌·힘 제어 문제가 남을 수 있습니다. 특히 T5는 위치 조정 후 모든 지점에 해가 있지만 인접 해 사이 약 5 rad의 큰 관절 변화가 있어 연속 실행 경로로 채택할 수 없습니다. 세부 오차와 최대 관절 변화는 `reports/fixture_sweep_audit.json`에 있습니다.','',
'**검토 결론:** 현재 배치에서 대표 목표에 접근할 기구학적 여유는 확인했습니다. 그러나 10개 언어 명령의 완전한 성공을 보장하지는 못합니다. 특히 그릇 림 파지, 서랍 내부 진입, 가전 손잡이를 잡은 동안의 자세·접촉 유지, 물체와 손목 카메라의 충돌은 추가 검증 대상입니다.','',
'2026-09-23 물체 복원으로 장애물 구성이 바뀌었습니다. 위 IK 수치는 목표 위치의 기구학적 검사이며, 복원된 물체를 포함하는 충돌 검사나 물리적 작업 성공 검증은 아닙니다. 후속 작업 순서는 `REMAPPING_PLAN_KO.md`에 정리했습니다.','',
'## 4. 원시 데이터 확보와 리매핑 판정','',
'로컬 LeRobot 변환본에는 물체 궤적이 없지만, 공개 `LightwheelAI/lightwheel_tasks` 저장소에서 선택된 500개 원시 HDF5와 500개 실행 설정을 추가 확보했습니다. 총 다운로드 크기는 935,882,181 bytes입니다. **원시 자료가 없다는 이유로 내린 판정이 아닙니다.**','',
f"원시 저장소 revision: `{raw['revision']}`. 위치: `raw_hdf5/lightwheel_libero_tasks_x7s/`. HDF5에는 실제 world EE pose, robot/fixture joint와 root state, rigid object pose/velocity, 초기 상태, 장면 metadata가 있습니다. `data/demo_0.attrs.success`는 500개 모두 true로 기록되어 있습니다. 이는 원본 X7S 수집 결과이며 RB-Y1 성공 판정은 아닙니다.",'',
'원시 HDF5마다 마지막 1프레임을 제외하면 추출 데이터와 state/action/processed_action 배열이 정확히 일치했습니다. 500개를 모두 대응시켰습니다. 단 T7의 추출 episode 327·328은 이 세 배열이 동일하므로 두 원시 파일 이름과의 대응은 해당 쌍 내부에서 유일하지 않습니다. 이 쌍의 영상 동일성까지 주장하지 않습니다. 파일 해시와 매핑은 `reports/raw_episode_mapping.json` 및 추출 데이터의 `meta/raw_hdf5_episode_mapping.json`에 저장했습니다.','',
'재사용 가능한 정보는 언어·task 정의, X7S 시각 데이터, 기록된 물체·말단 궤적과 장면 초기 상태입니다. **X7S 관절값을 RB-Y1 관절값으로 복사하는 직접 변환은 성립하지 않습니다.** 관절 수·축·순서·제어 의미가 다르고, 현재 RB-Y1 USD의 베이스와 몸통은 고정되어 있습니다. 새로운 배치로 물체를 각각 옮겼으므로 한 개의 공통 좌표 이동으로 모든 접촉 관계가 보존되지도 않습니다.','',
'검사 순서는 다음과 같습니다.','',
'1. 전체 500 episode를 25프레임 간격으로 명목 FK/IK 변환했습니다. 이 초기 검사는 한 개의 가정된 정렬과 양팔 보존을 요구한 보수적인 기준이며 통과 episode는 0/500이었습니다. 정확한 원시 정보 확보 전의 baseline이므로 일반적 불가능성의 근거로 쓰지 않습니다.',
'2. 원시 HDF5를 사용해 task당 1개 episode에서 기록된 world EE pose와 초기 robot root pose를 사용했습니다. 그리퍼 작동으로 사용 팔을 추정하고, 12가지 평면 이동과 그리퍼 180° 대칭을 조합한 24가지 정렬을 시험했습니다. 높이 변환에는 로컬 원본 USD의 상판 경계를 사용해 0.72 m로 맞추는 명목 offset을 적용했습니다. 원본 자산 버전과 접촉면 차이까지 보정한 object-centric 변환은 아닙니다.',
'3. 가장 나은 정렬에서 실패한 지점마다 최대 16개의 무작위 관절 초기값으로 150회 반복 IK를 수행했습니다. 관절 제한을 적용했고, 판정 기준은 위치 1 cm·자세 5°입니다. 이는 약 13–14개 시점의 기구학 검사이며 전체 프레임·충돌·동역학 검사가 아닙니다.','',
'| Task | 검사한 팔 자세의 통과율 | 최대 위치 오차 | 최대 자세 오차 |','|---|---:|---:|---:|']
for v in pilot:lines.append(f"| {v['Task']} | {100*v['valid_fraction']:.1f}% | {1000*v['max_position_error_m']:.1f} mm | {v['max_orientation_error_deg']:.1f}° |")
lines+=['',
'다중 초기값을 사용해도 이 시험 episode 10개 중 모든 검사 지점이 통과한 것은 없었습니다. 이것은 선택한 고정 몸통, 명목 TCP, 좌표 정렬, 자세 보존, 국소 IK 방식의 결과입니다. 베이스 배치·몸통 자유도·접촉점·파지 자세를 바꾼 재계획까지 모두 불가능하다는 뜻은 아닙니다.','',
f'따라서 `{B}`에는 README와 diagnostics만 저장했습니다. NPZ의 q는 실패 해와 불연속이 포함될 수 있는 진단 후보이며 로봇 명령이나 학습 정답이 아닙니다. 검증되지 않은 수치와 X7S 영상을 묶어 RB-Y1 LeRobot 데이터로 내보내지 않았습니다.','',
'**추가로 필요한 변환 작업:** 원시 시연을 물체·fixture별 접촉 구간으로 나누고 새 장면의 물체 좌표에 맞춰 경로를 재계획해야 합니다. RB-Y1의 파지·충돌·관절 속도를 검사한 뒤 물리 재생에서 작업 성공을 확인하고, 실제 RB-Y1 카메라를 렌더링해야 합니다. 그 과정을 통과한 episode만 LeRobot data/meta/videos로 저장할 수 있습니다. 이 물리적으로 검증된 데이터 생성 단계는 이번 산출물에 포함되어 있지 않습니다.','',
'## 실행과 재현','',
'```bash','LD_PRELOAD=$CONDA_PREFIX/lib/libstdc++.so.6 \\','  python \\','  ./scripts/run_environment.py --task T1','```','',
'`--headless --steps 100`을 추가하면 GUI 없이 실행합니다. 이 runner는 장면을 열고 준비 자세를 유지하며 정책이나 task 성공 판정기를 실행하지 않습니다. FK/IK 스크립트는 같은 Python에 `LD_LIBRARY_PATH=$CONDA_PREFIX/lib OPENBLAS_NUM_THREADS=1`을 사용했습니다. `usd-core`는 작업 폴더의 `usd_deps`에만 별도로 설치했습니다.','',
'CSV 생성: `scripts/select_tasks.py`와 `selection_csv.mjs`. 추출·검증: `scripts/extract_dataset.py`, `scripts/check_numeric_source.py`, `scripts/validate_dataset.py`. 장면: `scripts/build_scenes.py`, `scripts/validate_scenes_sim.py`. 원시 자료: `scripts/download_raw.py`, `scripts/match_raw_episodes.py`, `scripts/summarize_raw.py`. 기구학 검토: `scripts/raw_retarget_pilot.py`, `scripts/raw_multistart_audit.py`, `scripts/fixture_sweep_audit.py`.','',
'## 출처','',
'- [LeRobot Arena 공식 문서](https://huggingface.co/docs/lerobot/envhub_isaaclab_arena)',
'- [X7S LeRobot 데이터셋](https://huggingface.co/datasets/LightwheelAI/Lightwheel-Tasks-X7S)',
'- [Lightwheel 원시 HDF5 데이터셋](https://huggingface.co/datasets/LightwheelAI/lightwheel_tasks)',
'- [RB-Y1 v1.1 브랜치](https://github.com/cailab-hy/cai-rby1-lerobot/tree/v1.1)',
'- 사용자 기준 PDF: `~/Downloads/task_선정.pdf`',
'- 로컬 task 코드·레이아웃 매핑: `$RBY1_BENCHHUB_ROOT/`','']
for name,sha in commits.items():lines.append(f'- {name}: `{sha}`')
(R/'REPORT_KO.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(status,ensure_ascii=False,indent=2))
