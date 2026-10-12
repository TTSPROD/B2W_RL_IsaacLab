"""Managed bounded local A/B, using unchanged Robot Lab training and full v2."""
from __future__ import annotations
import argparse
import copy
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import yaml
from run_support import ROOT, managed_entrypoint, read_json, write_json, sha256, utc_now, local_command, stop_process_tree

PLAN_PATH = ROOT/'configs/24650_native_continuation_20261012.json'


def decision(records, plan):
    def indexed(policy):
        return {(r['terrain'], r['case'], r['seed']): r for r in records if str(r['policy']) == policy}
    parent, control, focus = (indexed(p) for p in plan['evaluation']['actors'])
    if len(parent) != 160 or set(parent) != set(control) or set(parent) != set(focus):
        raise ValueError('Full matched comparison incomplete')
    def paired(reference, candidate):
        values = [int(candidate[k]['covered_scenario_success'])-int(reference[k]['covered_scenario_success']) for k in reference]
        return {'wins': values.count(1), 'losses': values.count(-1), 'ties': values.count(0)}
    def saturation(rows):
        return max(max(r['safety']['torque_saturation_fraction'][12:]) for r in rows.values())
    vs_parent, vs_control = paired(parent, focus), paired(control, focus)
    unsafe = sum(r['outcome'] == 'unsafe' for r in focus.values())
    accepted = (unsafe == 0 and vs_parent['losses'] == 0 and vs_control['losses'] == 0
                and vs_parent['wins'] >= 2 and vs_control['wins'] >= 1
                and saturation(focus) <= min(saturation(parent), saturation(control)) + 1e-9)
    return {'selected': 'stdfocus_24799' if accepted else None, 'focus_vs_parent': vs_parent,
            'focus_vs_control': vs_control, 'unsafe': unsafe,
            'wheel_saturation_max': {name: saturation(rows) for name, rows in zip(plan['evaluation']['actors'], (parent, control, focus))},
            'automatic_promotion': False, 'simulation_qualified': False, 'hardware_enabled': False,
            'budget_extension': False, 'gate_passed': accepted}


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training-job', help='Reuse completed arms; perform zero additional PPO updates')
    parser.add_argument('--evaluation-job', help='Reuse a completed, validated parent baseline without new episodes')
    args = parser.parse_args()
    def cancelled(signum, frame):
        raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM, cancelled)
    signal.signal(signal.SIGINT, cancelled)
    job = Path(os.environ['B2W_JOB_DIR'])
    output = job/'native_continuation'
    output.mkdir(exist_ok=False)
    plan = read_json(PLAN_PATH)
    from run_locomotion import SOURCES as EVAL_SOURCES
    sources = tuple(dict.fromkeys((*EVAL_SOURCES, 'scripts/run_native_continuation.py',
              'scripts/run_isaac_continuation_child.py', 'scripts/b2w_native_continuation_cfg.py',
              'scripts/b2w_native_continuation_env.py', 'scripts/native_continuation_sampling.py',
              'scripts/isaac_physics_snapshot.py', 'scripts/job_manager.py', 'scripts/job_worker.py',
              'scripts/manage_runs.py', 'tests/test_native_continuation.py',
              'configs/24650_native_continuation_20261012.json', plan['standard_train'])))
    runtime = read_json(ROOT/'.runtime/isaac-ubuntu-runtime.json')
    if plan['hardware_enabled'] or plan['server_training'] or not runtime['eula_accepted']:
        raise ValueError('Local simulation-only continuation')
    artifacts = ('policies/local/core_24650/model_24650.pt', 'policies/local/core_24650/agent.yaml',
                 'policies/local/core_24650/env.yaml', 'policies/local/core_24650/export/policy.pt',
                 'policies/server/upstream_19999/export/policy.pt', 'vendor/manifest.json')
    if sha256(ROOT/plan['parent']) != plan['parent_sha256'] or sha256(ROOT/artifacts[3]) != plan['parent_export_sha256']:
        raise ValueError('Parent changed')
    for name in sources:
        destination = output/'sources'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, destination)
    manifest = {'created_utc': utc_now(), 'plan': plan, 'runtime_installation': runtime,
                'source_sha256': {n: sha256(ROOT/n) for n in sources},
                'artifact_sha256': {n: sha256(ROOT/n) for n in artifacts},
                'hardware_enabled': False, 'server_training': False}
    write_json(output/'preflight_manifest.json', manifest)
    progress = {'status': 'running', 'phase': 'preflight', 'arms': {}, 'log_arms': ['control', 'focus'],
                'updated': utc_now(), 'plan_sha256': sha256(PLAN_PATH)}

    def phase(name):
        progress.update(phase=name, updated=utc_now())
        write_json(job/'pilot_progress.json', progress)
        print('CONTINUATION_PHASE', name, flush=True)

    def guard():
        for name, digest in {**manifest['source_sha256'], **manifest['artifact_sha256']}.items():
            if sha256(ROOT/name) != digest:
                raise ValueError('Frozen input changed: '+name)

    def child(mode, arm='control', arguments=(), log=None):
        guard()
        label = log or mode+'_'+arm
        env = dict(os.environ)
        libraries = ROOT/'.runtime/isaac-native-libs/usr/lib/x86_64-linux-gnu'
        env['LD_LIBRARY_PATH'] = str(libraries)+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
        with (output/(label+'.stdout.log')).open('w') as out, (output/(label+'.stderr.log')).open('w') as err:
            process = subprocess.Popen(local_command('scripts/run_isaac_continuation_child.py',
                           ['--mode', mode, '--arm', arm, *arguments]), cwd=ROOT, stdout=out, stderr=err, env=env)
            try:
                code = process.wait(timeout=plan['training']['max_seconds_per_child'])
            finally:
                stop_process_tree(process)
        if code:
            raise RuntimeError(f'{label} exit {code}; see {output}/{label}.stderr.log')

    error = None
    try:
        for pattern in ('test_native_continuation.py', 'test_policy_contract.py', 'test_evaluation_policy.py'):
            subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', pattern, '-q'], cwd=ROOT, check=True)
        subprocess.run([sys.executable, 'scripts/vendor_materials.py', 'verify'], cwd=ROOT, check=True)
        if args.training_job:
            from job_manager import job_path, ACTIVE
            prior_job = job_path(args.training_job)
            prior = prior_job/'native_continuation'
            if read_json(prior_job/'state.json')['status'] in ACTIVE:
                raise ValueError('Wait for original job to finish before reusing weights')
            prior_manifest = read_json(prior/'manifest.json')
            if prior_manifest['plan'] != plan:
                raise ValueError('Reused training plan differs')
            differences = {n for n, digest in manifest['source_sha256'].items()
                           if prior_manifest['source_sha256'].get(n) != digest}
            if differences - {'scripts/run_native_continuation.py'}:
                raise ValueError('Training implementation changed: '+repr(differences))
            for name, digest in prior_manifest['raw_sha256'].items():
                if sha256(prior/name) != digest:
                    raise ValueError('Original raw changed: '+name)
            for arm in plan['arms']:
                receipt = read_json(prior/arm/'completion.json')
                if (receipt['ppo_updates'] != 150 or receipt['num_envs'] != 4000
                        or sha256(ROOT/receipt['checkpoint']) != receipt['checkpoint_sha256']):
                    raise ValueError('Incomplete reused arm: '+arm)
                if read_json(prior/arm/'preflight/result.json')['status'] != 'passed':
                    raise ValueError('Reused preflight failed')
                shutil.copytree(prior/arm, output/arm)
            shutil.copytree(prior/'sources', output/'reused_executed_sources')
            shutil.copyfile(prior/'manifest.json', output/'reused_training_manifest.json')
            write_json(output/'training_recovery.json', {'source_job': args.training_job,
                'source_manifest_sha256': sha256(prior/'manifest.json'), 'reused_ppo_updates': 300,
                'additional_ppo_updates': 0, 'implementation_changes': sorted(differences),
                'reason': 'Remove unsupported diagnostic_only metadata before full v2 validation; training bytes unchanged'})
        else:
            for arm in plan['arms']:
                phase('preflight_'+arm)
                child('preflight', arm)
        # Source-model equality between arms, except job log folders and seed.
        configurations = []
        for arm in plan['arms']:
            cfg = yaml.load((output/arm/'preflight/resolved_env.yaml').read_text(), Loader=yaml.BaseLoader)
            for key in ('log_dir', 'seed'):
                cfg.pop(key, None)
            cfg['sim'].pop('log_dir', None)
            configurations.append(cfg)
        if configurations[0] != configurations[1]:
            raise ValueError('Undeclared A/B environment difference')
        write_json(output/'common_mdp_audit.json', {'same_resolved_config': True, 'only_sampling_probabilities_differ': True,
                   'historical_runner_hooks': False, 'declared_common_changes': plan['common_mdp']})
        for arm in plan['arms']:
            if args.training_job:
                receipt = read_json(output/arm/'completion.json')
                progress['arms'][arm] = receipt
                phase('export_'+arm)
                child('export', arm)
                continue
            experiment = ROOT/'logs/rsl_rl'/f"b2w_native_standard_{arm}_{plan['training']['seed']}"
            staging = experiment/'_parent'
            staging.mkdir(parents=True, exist_ok=True)
            for source, name in ((ROOT/plan['parent'], 'model_24650.pt'), (ROOT/artifacts[1], 'agent.yaml')):
                target = staging/name
                if target.exists() and sha256(target) != sha256(source):
                    raise ValueError('Conflicting parent staging')
                if not target.exists():
                    shutil.copyfile(source, target)
            phase('training_'+arm)
            child('train', arm)
            stdout = (output/f'train_{arm}.stdout.log').read_text()
            clean = re.sub(r'\x1b\[[0-9;]*m', '', stdout)
            iterations = [int(n) for n in re.findall(r'Learning iteration\s+(\d+)/', clean)]
            if iterations != list(range(24650, 24800)):
                raise ValueError('Incomplete or repeated PPO iterations: '+arm)
            runs = list(experiment.glob('*_'+job.name))
            if len(runs) != 1:
                raise ValueError('Ambiguous training run: '+arm)
            checkpoint = runs[0]/'model_24799.pt'
            if not checkpoint.is_file():
                raise ValueError('Final checkpoint absent')
            receipt = {'run': runs[0].relative_to(ROOT).as_posix(), 'checkpoint': checkpoint.relative_to(ROOT).as_posix(),
                       'checkpoint_sha256': sha256(checkpoint), 'ppo_updates': 150, 'num_envs': 4000,
                       'num_steps_per_env': 24, 'seed': plan['training']['seed'],
                       'final_iteration': 24799, 'standard_runner': True, 'custom_runner_hooks': False}
            write_json(output/arm/'completion.json', receipt)
            progress['arms'][arm] = receipt
            phase('export_'+arm)
            child('export', arm)
        phase('full_v2_comparison')
        from locomotion_v2_protocol import TERRAINS, protocol_manifest
        from summarize_locomotion import summarize_run, validate_terrain
        exports = {'24650': ROOT/'policies/local/core_24650/export',
                   **{f'std{arm}_24799': output/'exports'/f'std{arm}_24799' for arm in plan['arms']}}
        summaries, records = {}, []
        for policy, export in exports.items():
            folder = output/'evaluation'/policy
            if policy == '24650' and args.evaluation_job:
                from job_manager import job_path
                old = job_path(args.evaluation_job)/'native_continuation/evaluation/24650'
                old_plan = read_json(old/'declared_plan.json')
                drift = {n for n, digest in old_plan['source_sha256'].items()
                         if manifest['source_sha256'].get(n) != digest}
                if drift - {'scripts/run_native_continuation.py'}:
                    raise ValueError('Reused evaluation source drift: '+repr(drift))
                for terrain in TERRAINS:
                    validate_terrain(old, terrain, old_plan)
                shutil.copytree(old, folder)
                summaries[policy] = summarize_run(folder)
                for terrain in TERRAINS:
                    records.extend(validate_terrain(folder, terrain, old_plan)['records'])
                write_json(output/'baseline_recovery.json', {'source_job': args.evaluation_job,
                    'original_declared_plan_sha256': sha256(old/'declared_plan.json'),
                    'original_summary_sha256': sha256(old/'analysis/summary.json'),
                    'reused_episodes': 160, 'implementation_changes': sorted(drift),
                    'reason': 'Canonical JSON plan for record validation; evaluator/scoring/actor bytes unchanged'})
                continue
            folder.mkdir(parents=True)
            write_json(folder/'policy_map.json', {policy: export.relative_to(ROOT).as_posix()})
            pkey = 24650 if policy == '24650' else policy
            declared = protocol_manifest({pkey: export})
            declared.update(protocol_module='locomotion_v2_protocol', source_sha256=manifest['source_sha256'],
                            policy_map_sha256=sha256(folder/'policy_map.json'))
            write_json(folder/'declared_plan.json', declared)
            shutil.copytree(output/'sources', folder/'sources')
            for terrain in TERRAINS:
                phase('evaluate_'+policy+'_'+terrain)
                child('evaluate', arguments=['--terrain', terrain, '--output', str(folder/(terrain+'.json')),
                      '--seeds', '5', '--policy-map', str(folder/'policy_map.json'), '--protocol-module', 'locomotion_v2_protocol'],
                      log='eval_'+policy+'_'+terrain)
            summaries[policy] = summarize_run(folder)
            canonical_plan = read_json(folder/'declared_plan.json')
            for terrain in TERRAINS:
                records.extend(validate_terrain(folder, terrain, canonical_plan)['records'])
        # Orchestration-only repair may give the reused parent a different frozen
        # source manifest. Preserve each manifest; require all simulation/scoring
        # sources, runtime, model, full case order and resets to match exactly.
        first = summaries['24650']
        ignored = {'policies', 'exports', 'policy_map_sha256', 'source_sha256'}
        template = {k: v for k, v in first['plan'].items() if k not in ignored}
        for policy, summary in summaries.items():
            if ({k: v for k, v in summary['plan'].items() if k not in ignored} != template
                    or summary['runtime'] != first['runtime'] or summary['compiled_model'] != first['compiled_model']):
                raise ValueError('Comparison physics/protocol/runtime differs: '+policy)
            old_sources = first['plan']['source_sha256']
            changed = {n for n, digest in old_sources.items() if summary['plan']['source_sha256'].get(n) != digest}
            if changed - {'scripts/run_native_continuation.py'}:
                raise ValueError('Comparison simulation/scoring sources differ: '+repr(changed))
        combined = {key: first[key] for key in ('schema', 'runtime', 'compiled_model', 'qualification', 'hardware_approval')}
        combined.update(plan=template, candidate_recommendation=None,
                        comparison_layout='fresh isolated actor; identical full case/reset slots',
                        executed_source_sha256_by_actor={p: s['plan']['source_sha256'] for p, s in summaries.items()},
                        input_sha256={k: v for s in summaries.values() for k, v in s['input_sha256'].items()})
        for key in ('overall', 'conditions', 'cells', 'all_cells_pass'):
            combined[key] = {p: s[key][p] for p, s in summaries.items()}
        write_json(output/'comparison.json', combined)
        result = decision(records, plan)
        result['overall'] = combined['overall']
        write_json(output/'decision.json', result)
        guard()
        progress.update(status='completed', decision=result)
        phase('completed')
    except BaseException as failure:
        error = repr(failure)
        progress.update(status='failed', error=error)
        phase('failed')
        raise
    finally:
        manifest.update(error=error, raw_sha256={p.relative_to(output).as_posix(): sha256(p) for p in output.rglob('*')
                        if p.is_file() and p.name != 'manifest.json'})
        write_json(output/'manifest.json', manifest)


if __name__ == '__main__':
    main()
