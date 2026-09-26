"""Structural, statistics, source-image alignment and official LeRobot read checks."""
import project_paths as paths
import json,subprocess,shutil,time
from pathlib import Path
import numpy as np,pandas as pd,pyarrow.parquet as pq,av
ROOT=Path(str(paths.ROOT));DST=Path(str(paths.X7S_SUBSET));SRC=Path(str(paths.SOURCE_DATASET))

def frame_at(path,seconds):
 with av.open(str(path)) as c:
  st=c.streams.video[0];c.seek(max(0,int(seconds/st.time_base)),stream=st,backward=True)
  for f in c.decode(st):
   if float(f.pts*st.time_base)>=seconds-.009:
    return f.to_ndarray(format='rgb24')
 raise ValueError((path,seconds))

def main():
 info=json.loads((DST/'meta/info.json').read_text());eps=pd.read_parquet(DST/'meta/episodes');orig=pd.read_parquet(SRC/'meta/episodes').set_index('episode_index');mapping=json.loads((DST/'meta/source_episode_mapping.json').read_text());keys=[k for k,v in info['features'].items() if v['dtype']=='video'];checks=[];image_acc={k:[] for k in keys}
 for key in keys:
  for stat in ['min','max','mean','std','count']:eps[f'stats/{key}/{stat}']=pd.Series([None]*len(eps),dtype=object)
 assert len(eps)==500 and eps.length.sum()==info['total_frames']==499643
 assert np.array_equal(eps.episode_index,np.arange(500))
 for ti in range(10):
  d=pd.read_parquet(DST/f'data/chunk-000/file-{ti:03d}.parquet');ee=eps[eps['data/file_index']==ti]
  assert len(d)==ee.length.sum() and np.all(d.task_index==ti)
  assert np.array_equal(d['index'],np.arange(ee.iloc[0].dataset_from_index,ee.iloc[-1].dataset_to_index))
  for eid,ep in d.groupby('episode_index'):
   assert np.array_equal(ep.frame_index,np.arange(len(ep)))
   assert np.allclose(ep.timestamp,np.arange(len(ep))/info['fps'],atol=1e-5)
  for key in keys:
   out=DST/f'videos/{key}/chunk-000/file-{ti:03d}.mp4'
   deadline=time.monotonic()+7200
   while True:
    try:
     probe=json.loads(subprocess.check_output([paths.executable('ffprobe'),'-v','error','-select_streams','v:0','-show_entries','stream=nb_frames','-of','json',str(out)],stderr=subprocess.DEVNULL))
     if int(probe['streams'][0]['nb_frames'])==len(d):break
    except (subprocess.CalledProcessError,KeyError,ValueError,IndexError):pass
    if time.monotonic()>deadline:raise TimeoutError(out)
    time.sleep(3)
   # Verify first, middle, and final episode image alignment against original data.
   errors=[]
   for ri in [0,24,49]:
    e=ee.iloc[ri];eid=int(e.episode_index);o=orig.loc[mapping[eid]['source_episode_index']]
    source=SRC/f'videos/{key}/chunk-{int(o[f"videos/{key}/chunk_index"]):03d}/file-{int(o[f"videos/{key}/file_index"]):03d}.mp4'
    for fi in [0,int(e.length)-1]:
     a=frame_at(source,float(o[f'videos/{key}/from_timestamp'])+fi/info['fps']);b=frame_at(out,float(e[f'videos/{key}/from_timestamp'])+fi/info['fps'])
     mse=float(np.mean((a.astype(float)-b.astype(float))**2));errors.append(mse)
     assert mse<150,(key,ti,ri,fi,mse)
   # Per-episode RGB statistics sampled at the temporal midpoint, using all pixels.
   for ri,e in ee.iterrows():
    image=frame_at(out,float(e[f'videos/{key}/from_timestamp'])+int(e.length//2)/info['fps'])
    a=image.astype(np.float64)/255;mu=a.mean((0,1));var=a.var((0,1));image_acc[key].append((mu,var,a.min((0,1)),a.max((0,1)),image.shape[0]*image.shape[1]))
    sampled={'mean':mu,'std':np.sqrt(var),'min':a.min((0,1)),'max':a.max((0,1))}
    for stat,value in sampled.items():eps.at[ri,f'stats/{key}/{stat}']=value.reshape(3,1,1).tolist()
    eps.at[ri,f'stats/{key}/count']=[1]
   checks.append({'Task':f'T{ti+1}','camera':key,'compared_frames':len(errors),'max_reencoding_mse':max(errors)})
  print('CHECKED',f'T{ti+1}',flush=True)
 stats=json.loads((DST/'meta/stats.json').read_text())
 for k,items in image_acc.items():
  mu=np.array([v[0] for v in items]);var=np.array([v[1] for v in items]);w=np.array([v[4] for v in items]);mean=np.average(mu,axis=0,weights=w)
  stats[k]={'mean':mean.reshape(3,1,1).tolist(),'std':np.sqrt(np.average(var+(mu-mean)**2,axis=0,weights=w)).reshape(3,1,1).tolist(),'min':np.min([v[2] for v in items],axis=0).reshape(3,1,1).tolist(),'max':np.max([v[3] for v in items],axis=0).reshape(3,1,1).tolist(),'count':[len(items)]}
 (DST/'meta/stats.json').write_text(json.dumps(stats,indent=2));shutil.copy2(ROOT/'selected_tasks.csv',DST/'selected_tasks.csv')
 eps.to_parquet(DST/'meta/episodes/chunk-000/file-000.parquet',index=False)
 from lerobot.datasets.lerobot_dataset import LeRobotDataset
 dataset=LeRobotDataset('local/Lightwheel-Tasks-X7S-T1-T10',root=DST,video_backend='pyav',download_videos=False)
 for ti in range(10):
  for eidx in [ti*50,ti*50+49]:
   e=eps.iloc[eidx]
   for idx in [int(e.dataset_from_index),int(e.dataset_to_index)-1]:
    item=dataset[idx];assert int(item['episode_index'])==eidx and int(item['task_index'])==ti
    assert item['task']==e.tasks[0]
    for key in keys:assert tuple(item[key].shape)==(3,480,640)
 report={'episodes':len(eps),'frames':len(dataset),'tasks':len(dataset.meta.tasks),'official_lerobot_samples':40,'source_video_alignment':checks,'rgb_stats_method':'one midpoint frame per episode; full-resolution pixels; 500 sampled frames per camera','numeric_stats_method':'all frames; recomputed after index remapping'}
 (ROOT/'reports/dataset_validation.json').write_text(json.dumps(report,indent=2));print('VALIDATION COMPLETE',len(dataset),flush=True)

if __name__=='__main__':main()
