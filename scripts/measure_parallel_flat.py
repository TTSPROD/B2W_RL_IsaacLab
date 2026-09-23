"""Read-only throughput comparison around the seed43/44 parallel handoff."""
from pathlib import Path
from datetime import datetime
import json
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

root=Path(__file__).resolve().parents[1]
job=json.loads((root/'logs/baselines/flat_parallel_20260917/job.json').read_text())
handoff=datetime.fromisoformat(job['started_utc']).timestamp()
paths={43:next((root/'logs/rsl_rl/unitree_b2w_flat').glob('*_flat_3seeds_20260917_seed43')),44:next((root/'logs/rsl_rl/unitree_b2w_flat').glob('*_flat_parallel_20260917_seed44'))}
records={}
for seed,path in paths.items():
    events=EventAccumulator(str(path),size_guidance={'scalars':0})
    events.Reload()
    records[seed]=events.Scalars('Perf/collection time')
if not records[44] or len(records[44])<=10:
    print(json.dumps({'status':'warming_up','record_counts':{k:len(v) for k,v in records.items()}}))
    raise SystemExit(0)
start=max(handoff+60,records[44][10].wall_time)
end=min(records[43][-1].wall_time,records[44][-1].wall_time)
solo=[r for r in records[43] if r.wall_time < handoff][-100:]
parallel={seed:[r for r in rows if start <= r.wall_time <= end] for seed,rows in records.items()}
def rate(rows):
    return (len(rows)-1)*49152/(rows[-1].wall_time-rows[0].wall_time) if len(rows)>1 else None
rates={seed:rate(rows) for seed,rows in parallel.items()}
result={'status':'measured' if all(len(v)>=50 for v in parallel.values()) else 'warming_up',
        'window_seconds':end-start,'updates_sampled':{seed:len(rows) for seed,rows in parallel.items()},
        'solo_seed43_transitions_per_s':rate(solo),'parallel_transitions_per_s':rates,
        'current_updates':{seed:rows[-1].step+1 for seed,rows in records.items()},
        'note':'Short contemporaneous wall-time observation; not a controlled 200-update benchmark or convergence comparison.'}
if all(v is not None for v in rates.values()):
    result['aggregate_transitions_per_s']=sum(rates.values())
    result['aggregate_speedup']=sum(rates.values())/rate(solo)
    remaining={seed:5000-result['current_updates'][seed] for seed in paths}
    # Initially assume measured contention until the earlier seed finishes, then
    # the surviving trainer returns to solo rate. Does not include evaluation.
    finish={seed:remaining[seed]*49152/rates[seed] for seed in paths}
    first=min(finish,key=finish.get)
    other=44 if first==43 else 43
    result['parallel_training_remaining_seconds_estimate']=finish[first]+max(0.,remaining[other]*49152-finish[first]*rates[other])/rate(solo)
    result['sequential_remaining_seconds_counterfactual']=sum(remaining.values())*49152/rate(solo)
output=root/'logs/baselines/flat_parallel_20260917/throughput_comparison.json'
output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
