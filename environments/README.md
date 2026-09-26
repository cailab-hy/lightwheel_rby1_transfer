> 경로 설정 업데이트: 다른 PC에서 실행할 때는 [PORTABILITY_KO.md](../PORTABILITY_KO.md)를 먼저 참고하십시오. 현재 USD는 상대경로를 사용하며, 아래 과거 절대경로 예시는 당시 PC 기준입니다.

# RB-Y1 T1–T10 scenes

Updated 2026-09-23: all object and fixture identities found across the 50 raw episodes
for each task are represented. Previously omitted 17 object instances and 9 fixture
instances have been restored. Source-name to USD-prim mapping and checks are in
`../reports/scene_inventory_audit.json`.

The scenes use deterministic adapted placements, not the exact randomized initial
state of each source episode. Table tops remain at 0.72 m; layouts 2-2 still use the
previously documented flat replacement table. Background cabinets, TV, walls and
floor remain in the scene; they may be outside the head-camera field of view.

New props are placed with non-overlapping tabletop footprints. This is an initial
placement check, not a collision-free manipulation trajectory certificate.

Preview images:
- `../reports/scene_contact_sheet.png`: actual RB-Y1 head-camera view (may crop props).
- `../reports/scene_overview_contact_sheet.png`: full tabletop overview.
- `../reports/T01_overview.png` ... `T10_overview.png`: full-resolution task images.

Launch using `../scripts/run_environment.py --task T2` with the Isaac Sim environment
shown in `../REPORT_KO.md`. The runner holds the ready pose; it does not execute a
policy. The pinned LW-BenchHub success_original evaluator is attached for all ten tasks. Original datasets and robot assets were not edited.

T1–T10 keyboard teleoperation and LeRobot data collection are now available via
`../collect_keyboard.sh --task T1` (the existing `../collect_t1_keyboard.sh` also works). See [the Korean keyboard guide](../KEYBOARD_COLLECTION_KO.md)
for controls, episode saving, output paths and validation limits.

## 기본 정면 뷰

T1~T10은 촬영 이미지와 같은 `/World/FrontPreviewCamera`를 기본 뷰로 사용합니다.
위치 `(2.44, -4.0, 2.15)`, 주시점 `(2.44, -1.90, 1.02)`, 초점거리 34mm입니다.
`run_environment.py`와 키보드 수집기 모두 시작 시 이 카메라를 선택합니다.
USD에도 기본 카메라 메타데이터를 저장했습니다. 렌더링과 재생성 설정은 `scripts/front_camera.py`에서 공유합니다.
수집용 헤드/손목 카메라 설정은 그대로입니다. 창의 종횡비에 따라 보이는 가장자리 범위는 달라질 수 있습니다.
