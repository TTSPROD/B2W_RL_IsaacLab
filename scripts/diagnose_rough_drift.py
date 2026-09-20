"""Recompute the stopped R1 probe without training or excluding rows from its guard."""
import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
from b2w_runtime import PROJECT_ROOT as ROOT
from benchmark_b2w import sha256,write_json,utc_now


def main():
    import torch
    torch.set_num_threads(4)
    run=ROOT/'logs/rsl_rl/unitree_b2w_rough/2026-09-19_21-37-34-205004_rough_development_20260920_s57_stage1'
    path=run/'reference_update_115.pt';probe=torch.load(path,map_location='cpu',weights_only=True)
    obs=probe['observations'];before=probe['before_actions'];after=probe['after_actions'];ref=probe['reference_actions']
    delta=after-ref;energy=delta.square().sum(1);order=energy.argsort(descending=True)
    groups={}
    for name,mask in [('all',torch.ones(len(obs),dtype=torch.bool)),('gravity_z_gt_minus_0_5',obs[:,5]>-.5),('gravity_z_lt_minus_0_9',obs[:,5]<-.9)]:
        groups[name]=dict(count=int(mask.sum()),rms=float(delta[mask].square().mean().sqrt()),squared_error_fraction=float(energy[mask].sum()/energy.sum()))
    report=dict(observed_utc=utc_now(),iteration=115,probe=str(path.relative_to(ROOT)),probe_sha256=sha256(path),
                stopped_checkpoint_sha256=sha256(run/'stopped_115.pt'),
                before_rms=float((before-ref).square().mean().sqrt()),after_rms=float(delta.square().mean().sqrt()),
                update_rms=float((after-before).square().mean().sqrt()),groups=groups,
                top10_squared_error_fraction=float(energy[order[:10]].sum()/energy.sum()),
                saved_diagnostic=probe['diagnostic'],flat_bank=json.loads((run/'flat_bank_drift.json').read_text(encoding='utf-8')),
                interpretation='Guard excess existed before the last PPO update, which reduced it. Rare tilted policy observations dominate squared drift. Gravity channels contain training noise; these groups diagnose, never filter guard rows.',
                experiment='One new training terminal: true projected tilt >60 degrees continuously >0.1s, measured each physics step. No drift/evaluation threshold changes.')
    output=ROOT/'docs/results/2026-09-20-rough-drift-diagnosis.json'
    if output.exists():raise ValueError('Diagnosis already recorded')
    write_json(output,report);print(json.dumps(report,indent=2))


if __name__=='__main__':main()
