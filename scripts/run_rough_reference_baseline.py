"""Measure the original reference and Flat anchor on disclosed Rough level-0 cases."""
import os
from pathlib import Path
import shutil
import sys
import traceback
sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import sha256, write_json, utc_now
from run_rough_r0 import own_child, PYTHON, read
from rough_training_protocol import ANCHOR
from run_rough_development import verify_rough

NAME = 'rough_reference_baseline_20260920'


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    from run_reference_transfer import assert_idle_project
    assert_idle_project(__file__)
    out = ROOT/'logs/rough'/NAME
    out.mkdir(parents=True, exist_ok=False)
    sources = ('replay_rough_b2w.py', 'rough_evaluation.py', 'rough_metrics.py',
               'b2w_rough_runtime.py', 'b2w_rough_terrain.py', 'physical_evaluation.py',
               'b2w_runtime.py', 'b2w_yaw_commands.py', 'yaw_command_sampling.py',
               'run_rough_r0.py', 'benchmark_b2w.py', Path(__file__).name)
    (out/'source').mkdir()
    for name in sources:
        shutil.copyfile(ROOT/'scripts'/name, out/'source'/name)
    job = dict(status='starting', started_utc=utc_now(), supervisor_pid=os.getpid(),
               stages=[], evaluations={}, source_sha256={f'scripts/{n}':sha256(ROOT/'scripts'/n) for n in sources},
               scope='Disclosed random level0 comparator only; no training or qualification',
               policy_quality_accepted=False)
    save = lambda: write_json(out/'job.json', job)
    physics = {}
    try:
        for name, policy in [('reference', ROOT/'vendor/rl_sar/policy/b2w/robot_lab/policy.pt'), ('anchor54', ANCHOR)]:
            for profile in ('nominal', 'bounded_v1'):
                label = name+'_'+profile
                report = out/(label+'.json')
                own_child([PYTHON, '-B', '-u', 'scripts/replay_rough_b2w.py', '--policy', str(policy),
                           '--report', str(report), '--family', 'random', '--level', '0',
                           '--physical_profile', profile], out/label, job, save, timeout_seconds=1800)
                value = read(report)
                summary = verify_rough(value, {'policy_sha256':sha256(policy)}, 'random', 0, profile, physics, .95)
                job['evaluations'][label] = dict(report=str(report.relative_to(ROOT)), sha256=sha256(report),
                    policy=str(policy.relative_to(ROOT)), policy_sha256=sha256(policy), summary=summary)
                save()
        job['status'] = 'completed_diagnostic'
        return 0
    except BaseException as exc:
        job.update(status='failed', error=str(exc), traceback=traceback.format_exc())
        return 1
    finally:
        job['finished_utc'] = utc_now()
        save()
        write_json(ROOT/'docs/results'/f'{NAME}.json', job)


if __name__ == '__main__':
    raise SystemExit(main())
