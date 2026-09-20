"""Two bounded passive trace replays of the completed precision150 checkpoints."""
import os
import sys
import traceback
from collections import Counter
sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process
from benchmark_b2w import sha256, write_json, utc_now
from run_rough_r0 import own_child, PYTHON, read


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    from run_reference_transfer import assert_idle_project
    assert_idle_project(__file__)
    name = 'rough_corridor_trace_20260920'
    out = ROOT/'logs/rough'/name
    out.mkdir(parents=True, exist_ok=False)
    parent_path = ROOT/'docs/results/rough_precision_training_20260920.json'
    parent = read(parent_path)
    if parent['status'] != 'stopped_quality_gate' or parent['stopped_at'] != 150:
        raise ValueError('Expected completed precision150 evidence')
    milestone = parent['milestones'][-1]
    names = ('run_rough_corridor_trace.py','trace_rough_b2w.py','rough_wheel_corridor.py',
        'rough_curriculum.py','replay_rough_b2w.py','rough_evaluation.py','rough_metrics.py',
        'b2w_rough_runtime.py','b2w_rough_terrain.py','physical_evaluation.py','b2w_runtime.py',
        'run_rough_r0.py','benchmark_b2w.py')
    frozen = {f'scripts/{n}':sha256(ROOT/'scripts'/n) for n in names}
    frozen[str(parent_path.relative_to(ROOT))] = sha256(parent_path)
    job = dict(status='running', started_utc=utc_now(), stages=[], summaries={},
               source_sha256=frozen, training_updates=0, policy_quality_accepted=False)
    save = lambda: write_json(out/'job.json', job)
    save()
    try:
        for seed in ('61','62'):
            previous = milestone['rough'][seed]['random/0/nominal']
            before = read(ROOT/previous['report'])
            if sha256(ROOT/previous['report']) != previous['sha256']:
                raise ValueError('Historical report changed')
            actor = milestone['training'][seed]
            if sha256(ROOT/actor['policy']) != actor['policy_sha256']:
                raise ValueError('Historical policy changed')
            report = out/f's{seed}_random0_nominal.json'
            own_child([PYTHON,'-B','-u','scripts/trace_rough_b2w.py','--policy',str(ROOT/actor['policy']),
                '--report',str(report),'--family','random','--level','0','--physical_profile','nominal'],
                out/f's{seed}',job,save,timeout_seconds=1800)
            value = read(report)
            if (value['status'] != 'completed' or value['cases'] != before['cases']
                    or value['policy_sha256'] != actor['policy_sha256']
                    or value['results'] != before['results']):
                raise ValueError('Passive trace changed original evaluation results')
            trace = value['metrics']['route_trace']
            crossings = [v for v in trace['first_crossing'] if v]
            sides = Counter(side for v in crossings for side in v['sides'])
            job['summaries'][seed] = dict(report=str(report.relative_to(ROOT)), sha256=sha256(report),
                original_rows_identical=True, original_report=previous['report'],
                successes=value['summary']['success'], first_crossings=len(crossings),
                sides=dict(sides), crossings=crossings,
                scope='random level0 nominal only; exact wheel boundaries at first failure')
            save()
        job['status'] = 'completed_diagnostic'
        return 0
    except BaseException as exc:
        job.update(status='failed', error=str(exc), traceback=traceback.format_exc())
        return 1
    finally:
        job['finished_utc'] = utc_now()
        save()
        write_json(ROOT/'docs/results'/f'{name}.json', job)


if __name__ == '__main__':
    raise SystemExit(main())
