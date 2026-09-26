import project_paths as paths
import json
from pathlib import Path
import numpy as np,pandas as pd,pyarrow.parquet as pq,pyarrow as pa
ROOT=Path(str(paths.ROOT));SRC=Path(str(paths.SOURCE_DATASET));DST=Path(str(paths.X7S_SUBSET));mapping=json.loads((DST/'meta/source_episode_mapping.json').read_text());eps=pd.read_parquet(SRC/'meta/episodes').set_index('episode_index');checks=[]
for ti in range(10):
 old=[m['source_episode_index'] for m in mapping if m['task']==f'T{ti+1}'];ee=eps.loc[old];parts=[]
 for chunk,fi in ee[['data/chunk_index','data/file_index']].drop_duplicates().itertuples(index=False,name=None):
  parts.append(pq.read_table(SRC/f'data/chunk-{int(chunk):03d}/file-{int(fi):03d}.parquet',filters=[('episode_index','in',old)]))
 source=pa.concat_tables(parts).sort_by([('episode_index','ascending'),('frame_index','ascending')]);out=pq.read_table(DST/f'data/chunk-000/file-{ti:03d}.parquet')
 assert len(source)==len(out)
 keys=['observation.state','action','processed_action','timestamp','frame_index']
 for key in keys:assert source[key].combine_chunks().equals(out[key].combine_chunks()),(ti,key)
 checks.append({'Task':f'T{ti+1}','frames':len(out),'exactly_preserved':keys});print('NUMERIC_EXACT',ti+1,len(out),flush=True)
(ROOT/'reports/numeric_source_validation.json').write_text(json.dumps({'total_frames':sum(x['frames'] for x in checks),'checks':checks},indent=2))
