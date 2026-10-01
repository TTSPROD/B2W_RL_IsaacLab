"""Dashboard-owned repeat of existing pilot stair actors, without training."""
import argparse
import os
from pathlib import Path

from run_support import ROOT, managed_entrypoint, read_json, write_json, sha256

SOURCE_JOB = 'd3c316481f4b4954b65656b82dc00e67'
SOURCE_SUMMARY_SHA = '53430332bb4ac0864d39ab27969ff8090b07eba6dc773917417942258f635711'


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--order', choices=('same', 'reverse'), required=True)
    args = parser.parse_args()
    job = Path(os.environ['B2W_JOB_DIR']).resolve()
    if not job.is_relative_to(ROOT / 'logs/dashboard/jobs'):
        raise ValueError('Invalid job directory')
    source = ROOT / 'logs/dashboard/jobs' / SOURCE_JOB / 'evaluation'
    if sha256(source / 'analysis/summary.json') != SOURCE_SUMMARY_SHA:
        raise ValueError('Original pilot evidence changed')
    from summarize_locomotion import validate_terrain, summarize_run
    from run_tracking_pilot import freeze
    from run_core_locomotion_eval import run
    from evaluation_policy import policy_id
    plan = read_json(source / 'declared_plan.json')
    for terrain in ('stairs_up_18', 'stairs_down_18'):
        validate_terrain(source, terrain, plan)
    exports = list(read_json(source / 'policy_map.json').items())
    if args.order == 'reverse':
        exports.reverse()
    exports = {policy_id(p): ROOT / path for p, path in exports}
    for p, path in exports.items():
        if sha256(path / 'policy.pt') != plan['exports'][str(p)]['export_sha256']:
            raise ValueError(f'Actor changed: {p}')
    write_json(job / 'replay_manifest.json', {
        'source_job': SOURCE_JOB, 'source_summary_sha256': SOURCE_SUMMARY_SHA,
        'runner_sha256': sha256(Path(__file__)), 'order': args.order,
        'policies': list(exports), 'planned_episodes': 140,
        'purpose': 'Diagnose repeatability and actor slot/order sensitivity; no promotion or training',
        'predeclared_comparison': 'All 140 paired outcomes, unsafe joint/time/margin, trajectory differences; report both orders regardless of outcome'})
    base = job / 'evaluation'
    module = 'locomotion_v2_stair_replay_protocol'
    freeze(base, exports, module)
    run(base, module, max_parallel=1)
    summary = summarize_run(base)
    print('REPLAY_COMPLETE', args.order, {p: (r['success'], r['unsafe']) for p, r in summary['overall'].items()}, flush=True)


if __name__ == '__main__':
    main()
