"""Bounded two-seed, one-update reproduction; outputs are discarded for training."""
from pathlib import Path
import argparse, json, os, sys
sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import write_json, sha256, utc_now, device_sample
from run_reference_transfer import guarded_supervise, assert_idle_project

OUT = ROOT / 'logs/diagnostics/reference_resume_20260919'
PRIOR = ROOT / 'logs/transfer/flat_reference_transfer_20260919/job.json'
PYTHON = str(ROOT / '.venv/Scripts/python.exe')

def main():
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--upright", action="store_true")
    args = parser.parse_args()
    if args.upright:
        OUT = ROOT / "logs/diagnostics/reference_resume_upright_20260919"
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    assert_idle_project(Path(__file__))
    previous = json.loads(PRIOR.read_text(encoding='utf-8'))
    assert previous['status'] == 'failed'
    assert previous['milestones'][-1]['cumulative_updates'] == 150
    assert previous['milestones'][-1]['all_gates_pass']
    if device_sample('nvidia-smi')['gpu_headroom_fraction'] < .5:
        raise RuntimeError('Less than50% free VRAM')
    OUT.mkdir(parents=True, exist_ok=False)
    job = {'status': 'running', 'started': utc_now(), 'prior_sha256': sha256(PRIOR),
           'scope': 'Two discarded one-update runs. Original drift limit unchanged.', 'runs': []}
    save = lambda: write_json(OUT / 'job.json', job)
    save()
    try:
        for seed in (53, 52):
            prior = next(r for r in previous['train_to_150']['runs'] if r['seed'] == seed)
            parent = ROOT / prior['final_checkpoint']
            assert sha256(parent) == prior['final_checkpoint_sha256']
            label = f'ref_resume_probe_s{seed}_20260919' + ('_upright' if args.upright else '')
            command = [PYTHON, '-B', '-u', 'scripts/train_b2w_desktop.py', '--headless', '--device', 'cuda:0',
                       '--num_envs', '4096', '--seed', str(seed), '--max_iterations', '1', '--run_name', label,
                       '--resume', str(parent), '--reference_init', 'vendor/rl_sar/policy/b2w/robot_lab/policy.pt',
                       '--critic_warmup_updates', '50', '--reference_drift_limit', '.25',
                       '--pure_yaw_fraction', '.25', '--reference_update_probe']
            if args.upright:
                command.append('--flat_upright_resets')
            run = {'name': label, 'seed': seed, 'parent': str(parent.relative_to(ROOT)),
                   'parent_sha256': sha256(parent)}
            job['runs'].append(run)
            try:
                guarded_supervise(command, OUT / label, 300, run, save)
            except RuntimeError:
                if run.get('external_exit_code') != 1:
                    raise
            matches = list((ROOT / 'logs/rsl_rl/unitree_b2w_flat').glob('*_' + label + '/manifest.json'))
            assert len(matches) == 1
            manifest = json.loads(matches[0].read_text(encoding='utf-8'))
            probe_path = matches[0].parent / 'reference_update_probe.json'
            probe = json.loads(probe_path.read_text(encoding='utf-8'))
            assert probe['iteration'] == 150 and probe['same_observations']
            if manifest['status'] != 'completed' and 'Reference action drift exceeded registered limit' not in manifest.get('error', ''):
                raise RuntimeError(manifest.get('error', 'Unexpected failure'))
            run.update(manifest=str(matches[0].relative_to(ROOT)), manifest_sha256=sha256(matches[0]),
                       probe=str(probe_path.relative_to(ROOT)), probe_sha256=sha256(probe_path),
                       result=probe, initial_reference_drift=manifest['reference_transfer']['initial_reference_drift'],
                       expected_guard_stop=manifest['status'] == 'failed')
            save()
        job['status'] = 'completed'
    finally:
        job['finished'] = utc_now()
        save()
        write_json(ROOT / ('docs/results/2026-09-19-reference-resume-upright-diagnosis.json' if args.upright else 'docs/results/2026-09-19-reference-resume-diagnosis.json'), job)

if __name__ == '__main__':
    main()
