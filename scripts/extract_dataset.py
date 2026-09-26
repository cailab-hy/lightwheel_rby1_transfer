"""Extract complete tasks into LeRobot v3 with exact per-camera task video files."""
import project_paths as paths
import concurrent.futures as cf
import json, subprocess
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT=Path(str(paths.ROOT))
SRC=Path(str(paths.SOURCE_DATASET))
DST=Path(str(paths.X7S_SUBSET))
FFMPEG=paths.executable('ffmpeg')
FFPROBE=paths.executable('ffprobe')

def dump(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(obj,ensure_ascii=False,indent=2))

def video_job(job):
 key,ti,rows,fps=job
 out=DST/f'videos/{key}/chunk-000/file-{ti:03d}.mp4'
 out.parent.mkdir(parents=True,exist_ok=True)
 total=int(rows.length.sum())
 groups=[]
 for _,r in rows.iterrows():
  src=SRC/f'videos/{key}/chunk-{int(r[f"videos/{key}/chunk_index"]):03d}/file-{int(r[f"videos/{key}/file_index"]):03d}.mp4'
  start=round(float(r[f'videos/{key}/from_timestamp'])*fps)
  n=int(r.length)
  if groups and groups[-1][0]==src and groups[-1][1]+groups[-1][2]==start:
   groups[-1][2]+=n
  else:groups.append([src,start,n])
 if not out.exists():
  parts=[]
  for gi,(src,start,n) in enumerate(groups):
   part=out if len(groups)==1 else out.with_name(out.stem+f'.part{gi}.mp4')
   cmd=[FFMPEG,'-v','error','-y','-ss',f'{start/fps:.8f}','-i',str(src),'-an','-frames:v',str(n),'-vf','setpts=PTS-STARTPTS','-r',str(fps),'-c:v','libx264','-preset','fast','-crf','18','-threads','4','-g',str(fps),'-pix_fmt','yuv420p',str(part)]
   subprocess.run(cmd,check=True);parts.append(part)
  if len(parts)>1:
   listing=out.with_suffix('.concat.txt');listing.write_text(''.join(f"file '{p}'\n" for p in parts))
   subprocess.run([FFMPEG,'-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(out)],check=True)
   for p in parts:p.unlink()
   listing.unlink()
 probe=json.loads(subprocess.check_output([FFPROBE,'-v','error','-select_streams','v:0','-show_entries','stream=nb_frames,r_frame_rate,duration,width,height','-of','json',str(out)]))['streams'][0]
 assert int(probe['nb_frames'])==total,(out,probe,total)
 print('VIDEO',key,f'T{ti+1}',total,flush=True)
 return {'task':f'T{ti+1}','key':key,'frames':total,'segments':len(groups),'probe':probe}

def main():
 selected=json.loads((ROOT/'selection.json').read_text())
 info=json.loads((SRC/'meta/info.json').read_text());fps=info['fps']
 eps=pd.read_parquet(SRC/'meta/episodes')
 keys=[k for k,v in info['features'].items() if v['dtype']=='video']
 numeric=[k for k in info['features'] if k not in keys]
 all_meta=[];provenance=[];jobs=[];global_index=0;ep_index=0
 accum={k:[] for k in numeric}
 for ti,sel in enumerate(selected):
  rows=eps[eps['stats/task_index/min'].map(lambda v:int(v[0])==sel['source_task_index'])].sort_values('episode_index')
  frames=[];task_frame=0
  # Read each source shard once for this task. Filter by real episode IDs.
  wanted=set(int(x) for x in rows.episode_index)
  tables=[]
  for chunk,fi in rows[['data/chunk_index','data/file_index']].drop_duplicates().itertuples(index=False,name=None):
   table=pq.read_table(SRC/f'data/chunk-{int(chunk):03d}/file-{int(fi):03d}.parquet',filters=[('episode_index','in',list(wanted))])
   tables.append(table)
  data=pa.concat_tables(tables).to_pandas()
  for _,r in rows.iterrows():
   old=int(r.episode_index); d=data[data.episode_index==old].sort_values('frame_index').copy();n=len(d)
   assert n==int(r.length) and np.array_equal(d.frame_index,np.arange(n))
   assert np.all(d.task_index==sel['source_task_index'])
   d['episode_index']=ep_index;d['task_index']=ti;d['index']=np.arange(global_index,global_index+n,dtype=np.int64)
   m={'episode_index':ep_index,'data/chunk_index':0,'data/file_index':ti,'dataset_from_index':global_index,'dataset_to_index':global_index+n,'tasks':[sel['Language Instruction']],'length':n,'meta/episodes/chunk_index':0,'meta/episodes/file_index':0}
   for key in keys:
    m.update({f'videos/{key}/chunk_index':0,f'videos/{key}/file_index':ti,f'videos/{key}/from_timestamp':task_frame/fps,f'videos/{key}/to_timestamp':(task_frame+n)/fps})
   for key in numeric:
    a=np.stack(d[key].to_numpy()) if isinstance(d[key].iloc[0],(list,np.ndarray)) else d[key].to_numpy()[:,None]
    af=a.astype(np.float64)
    st={s:getattr(af,s)(axis=0).tolist() for s in ['min','max','mean','std']};st['count']=[n]
    for s,v in st.items():m[f'stats/{key}/{s}']=v
    accum[key].append(st)
   provenance.append({'episode_index':ep_index,'source_episode_index':old,'task':sel['Task'],'source_task_index':sel['source_task_index'],'source_dataset_from_index':int(r.dataset_from_index),'length':n})
   all_meta.append(m);frames.append(d);ep_index+=1;global_index+=n;task_frame+=n
  out=DST/f'data/chunk-000/file-{ti:03d}.parquet';out.parent.mkdir(parents=True,exist_ok=True)
  pq.write_table(pa.Table.from_pandas(pd.concat(frames,ignore_index=True),schema=tables[0].schema,preserve_index=False),out)
  jobs.extend((k,ti,rows,fps) for k in keys)
  print('DATA',sel['Task'],len(rows),task_frame,flush=True)
 metap=DST/'meta/episodes/chunk-000/file-000.parquet';metap.parent.mkdir(parents=True,exist_ok=True)
 pd.DataFrame(all_meta).to_parquet(metap,index=False)
 pd.DataFrame({'task_index':range(10)},index=pd.Index([s['Language Instruction'] for s in selected])).to_parquet(DST/'meta/tasks.parquet')
 info.update(total_episodes=ep_index,total_frames=global_index,total_tasks=10,splits={'train':f'0:{ep_index}'})
 stats={}
 for key,ss in accum.items():
  w=np.array([s['count'][0] for s in ss]);mu=np.array([s['mean'] for s in ss]);sd=np.array([s['std'] for s in ss]);mean=np.average(mu,axis=0,weights=w)
  stats[key]={'min':np.min([s['min'] for s in ss],axis=0).tolist(),'max':np.max([s['max'] for s in ss],axis=0).tolist(),'mean':mean.tolist(),'std':np.sqrt(np.average(sd**2+(mu-mean)**2,axis=0,weights=w)).tolist(),'count':[int(w.sum())]}
 dump(DST/'meta/info.json',info);dump(DST/'meta/stats.json',stats)
 dump(DST/'meta/task_selection.json',selected);dump(DST/'meta/source_episode_mapping.json',provenance)
 with cf.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(video_job,jobs))
 dump(ROOT/'reports/extraction_video_checks.json',results)
 dump(ROOT/'reports/extraction_summary.json',{'episodes':ep_index,'frames':global_index,'tasks':10,'cameras':len(keys),'video_files':len(results),'destination':str(DST)})
 print('EXTRACTION COMPLETE',ep_index,global_index,flush=True)

if __name__=='__main__':main()
