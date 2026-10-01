"""Dashboard-owned same-slot ascent diagnosis of parent and two control checkpoints."""
import os
from pathlib import Path
import shutil
from run_support import ROOT, managed_entrypoint, read_json, write_json, sha256, utc_now
from run_stair_replay import SOURCE_JOB, SOURCE_SUMMARY_SHA

POLICIES = (24650, 'control_24675', 'control_24750')


def main():
    managed_entrypoint()
    from run_tracking_pilot import freeze
    from run_core_locomotion_eval import run
    from summarize_locomotion import summarize_run, validate_terrain
    source = ROOT / 'logs/dashboard/jobs' / SOURCE_JOB / 'evaluation'
    if sha256(source / 'analysis/summary.json') != SOURCE_SUMMARY_SHA:
        raise ValueError('Original evidence changed')
    original_plan = read_json(source / 'declared_plan.json')
    validate_terrain(source, 'stairs_up_18', original_plan)
    job = Path(os.environ['B2W_JOB_DIR']).resolve()
    if not job.is_relative_to(ROOT / 'logs/dashboard/jobs'):
        raise ValueError('Invalid job directory')
    base = job / 'evaluation'
    base.mkdir(exist_ok=False)
    exports = read_json(source / 'policy_map.json')
    progress = {'status': 'running', 'total_jobs': 3, 'completed': [], 'active': [], 'failures': []}
    summaries = {}
    write_json(job / 'isolation_manifest.json', {'source_job': SOURCE_JOB,
        'source_summary_sha256': SOURCE_SUMMARY_SHA, 'policies': list(POLICIES),
        'episodes': 30, 'envs_per_process': 10, 'training_updates': 0,
        'comparison': 'All cases/seeds occupy identical slots for each actor; nominal physics/gates unchanged',
        'limitation': 'Restricted known selection seeds; no validation, no promotion',
        'runner_sha256': sha256(Path(__file__))})
    shutil.copyfile(Path(__file__), job / 'run_stair_isolation.py')
    def update():
        progress['updated'] = utc_now()
        write_json(base / 'evaluation_progress.json', progress)
    try:
        for policy in POLICIES:
            path = ROOT / exports[str(policy)]
            if sha256(path / 'policy.pt') != original_plan['exports'][str(policy)]['export_sha256']:
                raise ValueError('Actor changed')
            folder = base / str(policy)
            module = 'locomotion_v2_stair_isolation_protocol'
            freeze(folder, {policy: path}, module)
            progress['active'] = [f'{policy}/stairs_up_18']; update()
            print('ISOLATED_ACTOR', policy, flush=True)
            run(folder, module, max_parallel=1)
            summaries[str(policy)] = summarize_run(folder)
            progress['completed'].append(str(policy)); progress['active'] = []; update()
        first = summaries[str(POLICIES[0])]
        result = {k: first[k] for k in ('schema', 'runtime', 'compiled_model', 'qualification', 'hardware_approval')}
        if any(s['runtime'] != first['runtime'] or s['compiled_model'] != first['compiled_model'] for s in summaries.values()):
            raise ValueError('Runtime/model changed between actors')
        result.update(plan={**first['plan'], 'policies': list(POLICIES),
                           'exports': {p: s['plan']['exports'][p] for p,s in summaries.items()}},
                      candidate_recommendation=None, ranking=list(summaries),
                      diagnostic_only=True, independent_resets=5, derived_summary=True,
                      comparison_layout='Separate fresh processes, same ten case/reset slots',
                      input_sha256={ (base/p/'analysis/summary.json').relative_to(ROOT).as_posix():
                                     sha256(base/p/'analysis/summary.json') for p in summaries})
        result['plan'].pop('policy_map_sha256', None)
        for key in ('overall', 'conditions', 'cells', 'all_cells_pass'):
            result[key] = {p: s[key][p] for p,s in summaries.items()}
        write_json(base / 'analysis/summary.json', result)
        progress['status'] = 'completed'; update()
    except BaseException as error:
        progress.update(status='failed', failures=[repr(error)]); update(); raise


if __name__ == '__main__':
    main()
