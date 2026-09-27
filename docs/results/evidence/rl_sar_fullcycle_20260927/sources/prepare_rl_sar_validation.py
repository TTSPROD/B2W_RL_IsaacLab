"""Freeze provenance and the unchanged fullcycle test before the reference run."""
import json
from pathlib import Path
import shutil

from check_policy_contract import run_checks
from evaluation_policy import ROOT, reference_identity
from fullcycle_eval_protocol import protocol_manifest
from locomotion57_protocol import sha256
from operating57_protocol import canonical_hash


def main():
    base = ROOT/'logs/rl_sar_fullcycle_20260927'
    if (base/'declared_plan.json').exists():
        raise FileExistsError('This declared run already exists')
    identity = reference_identity()
    contract = run_checks()
    export = base/'reference_export'
    export.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT/identity['source_path'], export/'policy.pt')
    (export/'manifest.json').write_text(json.dumps({'export_validation': identity,
        'interface_checks': contract}, indent=2)+'\n')
    selection = {'rl_sar': export.relative_to(ROOT).as_posix(),
                 '23999': 'policies/local/recovery_23999/export'}
    plan = protocol_manifest({key if key == 'rl_sar' else int(key): ROOT/value
                              for key, value in selection.items()})
    previous = json.loads((ROOT/'logs/fullcycle23999_validation_20260927/declared_plan.json').read_text())
    for key in ('terrain_seeds','flat_seeds','terrains','gates','flat_protocol'):
        assert canonical_hash(plan[key]) == canonical_hash(previous[key]), key
    for name, value in (('policy_map.json',selection), ('declared_plan.json',plan)):
        (base/name).write_text(json.dumps(value,indent=2)+'\n')
    names = ('evaluation_policy.py','fullcycle_eval_protocol.py','operating57_protocol.py',
             'locomotion57_protocol.py','eval_candidate_operating57_isaac.py',
             'eval_operating57_isaac.py','eval_fullcycle_terrain.py','local_b2w_assets.py',
             'b2w_runtime.py','check_policy_contract.py','run_candidate_fullcycle.ps1',
             'prepare_rl_sar_validation.py')
    (base/'sources').mkdir()
    for name in names:
        shutil.copyfile(ROOT/'scripts'/name,base/'sources'/name)
    (base/'source_manifest.json').write_text(json.dumps({name:sha256(base/'sources'/name)
        for name in names},indent=2)+'\n')
    print(json.dumps({'policies':plan['policies'],'episodes':plan['episodes_total'],
        'reference':identity,'contract_status':contract['status']},indent=2))


if __name__ == '__main__':
    main()
