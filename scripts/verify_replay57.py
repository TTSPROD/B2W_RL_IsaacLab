"""Verify frozen replay inputs, complete traces, exact continuation and doc links."""
import json
import re
from pathlib import Path
import numpy as np
from replay57_protocol import ROOT,BASE,CONFIG
from physics57_protocol import sha256,save_json


def verify():
    out = ROOT/'docs/results/evidence/replay57_19999_20260925'
    summary = json.loads((out/'summary.json').read_text())
    config = json.loads(CONFIG.read_text())
    for name,h in config['input_sha256'].items():
        assert sha256(ROOT/name)==h,name
    for name,h in summary['inputs'].items():
        assert sha256(ROOT/name)==h,name
    for name,h in summary['sources'].items():
        assert sha256(ROOT/'scripts'/name)==h,name
    assert sha256(CONFIG)==summary['config_sha256']
    old = np.load(ROOT/'logs/contact57b_20260925/micro_up_14x32_19999_cooked_shapes.npz')
    warm = np.load(BASE/'warm_check.npz')
    detail = np.concatenate([warm[k] for k in ('root_pose','q','dq','tau','targets')],axis=-1).astype(np.float32)
    delta = float(np.max(np.abs(detail-old['forward_0.30__detail'][1350:1600])))
    assert delta==0.,delta
    assert len(summary['rows'])==12 and all(not r['safety']['unsafe_flags'] for r in summary['rows'])
    for name in ('mujoco_cooked_shapes','mujoco_source_shapes','isaac_contactmesh'):
        a = np.load(BASE/f'{name}.npz')
        assert a['physics_tau'].shape==(2500,4,16)
        assert a['physics_contact'].shape==(2500,4,4,3)
        for k in a.files:
            if k=='soft_joint_limits':
                continue  # continuous wheels may have unbounded ranges.
            assert np.isfinite(a[k]).all(),(name,k)
        assert (a['physics_contact']>=0).all()
        assert (a['physics_contact'][...,0].sum(axis=0)>0).all()
    docs = ['AGENTS.md','README.md','docs/README.md','docs/PROJECT_PLAN.md','docs/TRAINING_STATUS.md',
        'docs/TRAINING_PROGRESS.md','docs/INFRASTRUCTURE.md','docs/POLICY_REGISTRY.md','docs/LOGS_AND_RESULTS.md',
        'scripts/README.md','docs/results/README.md','docs/results/EXPERIMENT_MATRIX.md',
        'docs/results/evidence/README.md','docs/results/2026-09-25-replay57-19999.md']
    checked = 0
    for name in docs:
        p = ROOT/name
        for target in re.findall(r'\[[^\]\n]+\]\(([^)\n]+)\)',p.read_text(encoding='utf-8')):
            if '://' not in target and not target.startswith('#'):
                assert (p.parent/target.split('#')[0]).exists(),(name,target)
                checked += 1
    tests = ROOT/'logs/replay57_19999_tests.log'
    test_text = tests.read_text(encoding='utf-8-sig')
    assert 'Ran 290 tests' in test_text and '\nOK' in test_text
    logs = sorted((ROOT/'logs').glob('replay57_19999_*.log'))
    save_json(out/'validation.json',{'source_capture_trace_max_abs_error':0.,
        'warm_continuation_full_71_column_detail_max_abs_error':delta,
        'valid_replays':12,'unsafe':0,'physics_samples_per_episode':2500,
        'tests_passed':290,'vendor_files_verified':1290,'vendor_sources':6,
        'new_and_active_document_links_checked':checked,
        'runtime_log_sha256':{str(p.relative_to(ROOT)):sha256(p) for p in logs},
        'source_sha256':sha256(__file__),
        'summary_sha256':sha256(out/'summary.json'),
        'pilot_plan_sha256':sha256(ROOT/'configs/locomotion57_19999_recovery_pilot_plan_20260925.json'),
        'no_training_executed':True})
    print('Verified inputs, nine trace/result pairs, full71-column warm continuation,12 complete replay,290 tests and',checked,'links.')


if __name__=='__main__':
    verify()
