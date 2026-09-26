import project_paths as paths
import json
from pathlib import Path
import pandas as pd

ROOT = Path(str(paths.ROOT))
SRC = Path(str(paths.SOURCE_DATASET))
NAMES = [
 'L90K1PutTheBlackBowlOnThePlate',
 'LSPickUpTheBlackBowlOnTheCookieBoxAndPlaceItOnThePlate',
 'L90L1PickUpTheKetchupAndPutItInTheBasket',
 'L90K2OpenTheTopDrawerOfTheCabinet',
 'L90K7OpenTheMicrowave',
 'LGTurnOnTheStove',
 'LGOpenTheTopDrawerAndPutTheBowlInside',
 'L90K2StackTheMiddleBlackBowlOnTheBackBlackBowl',
 'L10K4PutTheBlackBowlInTheBottomDrawerOfTheCabinetAndCloseIt',
 'L10L2PutBothTheAlphabetSoupAndTheTomatoSauceInTheBasket']
ROLES = ['Basic Pick-and-Place','Spatial Relational Pick-and-Place','Object-Variation Pick-and-Place','Single-Step Articulated Manipulation','Articulated Appliance Manipulation','Contact / Actuation','Compositional Manipulation','Precision Stacking','Long-Horizon Sequential Manipulation','Multi-Object Sequential Manipulation']
DETAILS = [
 '집기, 운반, 놓기의 기본 조작 능력을 평가하는 기준 task. 기존 PaMQR-chunk T1과 동일.',
 '쿠키 상자 위라는 물체 간 공간 관계로 목표 그릇을 식별하고 접시에 옮긴다. 기존 T2와 동일.',
 '그릇과 다른 형상 및 파지 특성의 케첩을 바구니에 옮겨 물체 변화 대응을 평가한다. 원본 LO task가 X7S에 없어 동일 물체·목적지의 L90L1 task로 대체. 배치와 distractor는 다를 수 있다.',
 '서랍 손잡이에 접근하여 직선 관절을 여는 접촉 조작. T7의 서랍 열기 primitive이며 기존 T4와 동일.',
 '전자레인지의 회전식 문을 열어 서랍과 다른 관절 기하 및 손잡이 상호작용을 평가한다. 기존 T5와 동일.',
 '물체 운반 없이 스토브 조작부를 접촉하여 켜는 정밀 접근 및 작동 task. 기존 T6와 동일.',
 '위 서랍 열기, 그릇 집기, 운반, 내부 배치를 순서대로 연결하여 action chunk와 critic의 시간 의존성 평가. 기존 T7과 동일.',
 '여러 유사 그릇의 가운데·뒤 관계를 구분하고 정밀 적층하여 위치 정확도와 물체 상호작용을 평가한다. 기존 T8과 동일.',
 '그릇 집기, 아래 서랍 내부 배치, 서랍 닫기의 순차 의존성을 평가한다. X7S에 없는 머그 넣고 전자레인지 닫기 T9를 대체하며 회전문 대신 직선 서랍을 사용하므로 완전 동일 조건은 아니다.',
 '알파벳 수프와 토마토 소스를 각각 바구니에 옮기며 물체 전환과 반복적 조작 순서를 평가한다. 기존 T10과 동일.'
]
LAYOUTS = ['libero-1-1','libero-8-8','libero-2-2','libero-1-1','libero-1-1','libero-8-8','libero-8-8','libero-1-1','libero-1-1','libero-2-2']

def main():
 tasks = pd.read_parquet(SRC/'meta/tasks.parquet')
 eps = pd.read_parquet(SRC/'meta/episodes')
 rows=[]
 for i,(name,role,detail,layout) in enumerate(zip(NAMES,ROLES,DETAILS,LAYOUTS)):
  old=int(tasks.loc[name,'task_index'])
  selected=eps[eps['stats/task_index/min'].map(lambda v:int(v[0])==old)]
  instructions=sorted({s for arr in selected.tasks for s in arr})
  assert len(instructions)==1
  rows.append({'Task':f'T{i+1}','Task 이름':name,'Language Instruction':instructions[0],'역할':role,'역할에 대한 상세 설명':detail,'LIBERO 레이아웃 번호':layout,'source_task_index':old,'episodes':len(selected),'frames':int(selected.length.sum()),'match':'similar' if i in [2,8] else 'exact','layout_evidence':'LW-BenchHub configs/layout_task_mapping/layout_task_mapping.csv and teleop_ci_libero_tasks.txt; source episodes do not store layout IDs'})
 (ROOT/'selection.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
 print([(r['Task'],r['episodes'],r['frames']) for r in rows])

if __name__=='__main__':main()
