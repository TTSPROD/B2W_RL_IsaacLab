"""Explicit 1350-update comparison amendment; original experiment stays frozen."""
from copy import deepcopy
from run_support import ROOT,read_json,sha256
from stair_curriculum_contract import load_plan,PLAN_SHA

AMENDMENT_PATH=ROOT/'configs/24650_stair_comparison_1350_20260930.json'
AMENDMENT_SHA='df92541d64ec1666b9ef2c52674d910e1bbee5c56b021df91826d2937571ffef'


def load_comparison():
    original=load_plan()
    if sha256(AMENDMENT_PATH)!=AMENDMENT_SHA:raise ValueError('Comparison amendment changed')
    amendment=read_json(AMENDMENT_PATH)
    if amendment['base_plan_sha256']!=PLAN_SHA:raise ValueError('Wrong base plan')
    for path,digest in [(ROOT/amendment['checkpoint'],amendment['checkpoint_sha256']),
                        (ROOT/amendment['coverage_source'],amendment['coverage_source_sha256']),
                        (ROOT/'logs/dashboard/jobs'/amendment['origin_job']/'experiment_manifest.json',amendment['origin_manifest_sha256'])]:
        if sha256(path)!=digest:raise ValueError('Historical input changed: '+str(path))
    # Coverage is the snapshot at the retained checkpoint, never the later 1449 snapshot.
    import json
    rows=[json.loads(line.split('=',1)[1]) for line in (ROOT/amendment['coverage_source']).read_text().splitlines()
          if line.startswith('B2W_PROGRESS=')]
    matching=[r for r in rows if r['completed_updates']==1350 and r['iteration']==26000]
    if len(matching)!=1 or matching[0]['training_coverage']!=amendment['coverage_at_checkpoint']:
        raise ValueError('Coverage is not from the retained checkpoint')
    plan=deepcopy(original)
    plan.update(additional_updates=1350,probe_updates=[1350])
    plan['advancement']['eligible_updates']=[1350]
    return plan,amendment
