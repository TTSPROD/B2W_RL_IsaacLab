"""Locate the robot during the first declared zero window; no new rollouts."""
import json
import numpy as np
from fullcycle_eval_protocol import ROOT, TERRAINS, POLICIES, cases_for
from locomotion57_protocol import sha256, DT


def main():
    base=ROOT/'logs/fullcycle21999_validation_20260927'
    out=ROOT/'docs/results/evidence/fullcycle_21999_20260927/stair_stop_position_audit.json'
    rows=[]; hashes={}
    for terrain in TERRAINS:
        if not terrain.startswith('stairs_'):continue
        path=base/f'{terrain}.json'; data=json.loads(path.read_text())
        hashes[terrain]=data['trace_sha256']
        assert sha256(path.with_suffix('.npz'))==data['trace_sha256']
        with np.load(path.with_suffix('.npz')) as archive:
            trace=archive['trace']
            for case in cases_for(terrain):
                if not case.name.startswith('stair_stop_'):continue
                start=sum(s.seconds for s in case.segments[:2])
                lo,hi=round((start+2)/DT),round((start+12)/DT)
                for policy in POLICIES:
                    ids=[i for i,r in enumerate(data['records']) if r['policy']==policy and r['case']==case.name]
                    x=trace[lo:hi,ids,3]
                    finite=np.isfinite(x)
                    per_seed=np.nanmedian(x[:,finite.any(axis=0)],axis=0)
                    rows.append({'terrain':terrain,'case':case.name,'policy':policy,
                        'zero_window_s':[start+2,start+12],'root_x_median':float(np.nanmedian(x)) if finite.any() else None,
                        'root_x_per_seed_median_p10_p90':np.quantile(per_seed,[.1,.9]).tolist() if len(per_seed) else None,
                        'root_on_stair_x_fraction':float(np.mean(finite & (x>=.8) & (x<4.1))),
                        'valid_samples_fraction':float(finite.mean())})
    out.write_text(json.dumps({'interpretation':'position is diagnostic exposure only, not a navigation gate',
                              'first_riser_x':.8,'last_riser_x':4.1,'trace_sha256':hashes,'rows':rows},indent=2,allow_nan=False)+'\n')
    print(out)


if __name__=='__main__':main()
