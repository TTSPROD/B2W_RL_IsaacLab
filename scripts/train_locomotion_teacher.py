"""Bounded simulation-only 247-input locomotion teacher pilot; never route acceptance."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import sys
import time
import traceback

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, configure_process, project_kit_args
from benchmark_b2w import sha256, utc_now, write_json

ANCHOR = ROOT / 'logs/qualification/flat_reference_qualification_20260919_resume1/seed54/export/policy-contract-export/policy.pt'
SOURCES = ('train_locomotion_teacher.py', 'b2w_locomotion_teacher.py', 'b2w_runtime.py',
           'b2w_rough_runtime.py', 'b2w_rough_terrain.py', 'b2w_yaw_commands.py',
           'yaw_command_sampling.py', 'reference_transfer.py', 'benchmark_b2w.py', 'smoke_b2w.py')
SCHEMA = 'b2w_locomotion_teacher_pilot_v1'


def parse_args(app_launcher):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--num_envs', type=int, default=1024)
    parser.add_argument('--updates', type=int, default=100)
    parser.add_argument('--warmup', type=int, default=25)
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--probe_steps', type=int, default=0,
                        help='Optional post-training deterministic-action diagnostic, with auto-reset; not qualification.')
    app_launcher.add_app_launcher_args(parser)
    parser.set_defaults(headless=True, device='cuda:0')
    args = parser.parse_args()
    args.output = (ROOT / args.output).resolve()
    if not args.output.is_relative_to(ROOT / 'logs') or args.output.exists():
        parser.error('--output must be a new directory inside project logs')
    if args.num_envs not in (64, 1024) or not 1 <= args.updates <= 100 or args.warmup not in (1, 25):
        parser.error('Pilot supports 64/1024 envs, 1..100 updates and warmup 1/25')
    if not 0 <= args.probe_steps <= 1000:
        parser.error('--probe_steps must lie in 0..1000')
    if args.resume:
        args.resume = (ROOT / args.resume).resolve()
        if not args.resume.is_relative_to(ROOT / 'logs') or not args.resume.is_file():
            parser.error('--resume must be an existing project logs checkpoint')
    return args


def set_training_phase(runner, iteration, warmup):
    """Avoid KL=0 increasing adaptive LR during critic-only calibration."""
    train_actor = iteration >= warmup
    for parameter in runner.alg.policy.actor.parameters():
        parameter.requires_grad_(train_actor)
        if not train_actor:
            parameter.grad = None
    runner.alg.policy.std.requires_grad_(train_actor)
    if not train_actor:
        runner.alg.policy.std.grad = None
    runner.alg.schedule = 'adaptive' if train_actor else 'fixed'


def optimizer_step(optimizer):
    return max((float(value['step']) for value in optimizer.state.values() if 'step' in value), default=0.)


def assert_finite_policy(policy, torch):
    for name, value in policy.state_dict().items():
        if not bool(torch.isfinite(value).all()):
            raise RuntimeError('Nonfinite policy tensor: ' + name)
    if not bool((policy.std > 0).all()):
        raise RuntimeError('Nonpositive learned exploration std')


def export_parity(policy, observations, output, torch):
    from isaaclab_rl.rsl_rl import export_policy_as_jit
    target = output / 'export'
    target.mkdir()
    export_policy_as_jit(policy, policy.actor_obs_normalizer, path=str(target), filename='policy.pt')
    exported = torch.jit.load(str(target / 'policy.pt'), map_location='cpu').eval()
    actor = copy.deepcopy(policy.actor).cpu().eval()
    inputs = observations['policy'].detach().cpu()
    with torch.no_grad():
        expected, actual = actor(inputs), exported(inputs)
    difference = float((expected - actual).abs().max())
    if not bool(torch.isfinite(actual).all()) or difference > 1e-5:
        raise RuntimeError('Teacher CPU export/live parity failed')
    return dict(max_abs_error=difference, tolerance=1e-5, sample_count=len(inputs),
                actor_observations=247, actions=16, path=str((target / 'policy.pt').relative_to(ROOT)),
                sha256=sha256(target / 'policy.pt'), scope='Actual teacher observations; CPU deterministic actor/export')


def suffix_action_sensitivity(policy, observations, torch):
    """Same-state input ablations measure action dependence, never route success."""
    inputs = observations['policy'].detach()
    result = {}
    with torch.no_grad():
        expected = policy.actor(inputs)
        for label, start, stop in (('linear_velocity', 57, 60), ('height_scan', 60, 247), ('all_privileged', 57, 247)):
            ablated = inputs.clone()
            ablated[:, start:stop] = 0.
            delta = policy.actor(ablated) - expected
            result[label] = dict(raw_action_rms=float(delta.square().mean().sqrt()),
                                 raw_action_max_abs=float(delta.abs().max()))
    return dict(scope='Zero suffix ablation on identical actual observations; action sensitivity only, not causal policy performance',
                samples=len(inputs), by_ablation=result)


def rollout_probe(env, runner, steps, torch):
    """Physics-rate diagnostic under training commands; deliberately no route claim."""
    base = env.unwrapped
    robot, contacts = base.scene['robot'], base.scene['contact_forces']
    forbidden = [index for index, name in enumerate(contacts.body_names) if not name.endswith('_foot')]
    if len(contacts.body_names) - len(forbidden) != 4:
        raise RuntimeError('Probe wheel contact map mismatch')
    families = torch.tensor([0, 0, 0, 1, 1, 1, 2, 3, 4, 4], device=base.device)[base.scene.terrain.terrain_types]
    sums = torch.zeros((5, 3), device=base.device)
    counts = torch.zeros(5, device=base.device)
    contact_counts = torch.zeros_like(counts)
    tilt_counts = torch.zeros_like(counts)
    moving_counts = torch.zeros_like(counts)
    terrain_exposure = torch.zeros_like(counts)
    completed_episodes = torch.zeros_like(counts)
    completed_length_steps = torch.zeros_like(counts)
    current_length_steps = torch.zeros(base.num_envs, device=base.device)
    termination_counts = {name: torch.zeros_like(counts) for name in base.termination_manager.active_terms}
    done_count = 0
    original_update = base.scene.update
    last_step = base._sim_step_counter

    def update(dt):
        nonlocal last_step
        original_update(dt)
        if base._sim_step_counter == last_step:
            return
        last_step = base._sim_step_counter
        command = base.command_manager.get_command('base_velocity')
        actual = torch.cat((robot.data.root_lin_vel_b[:, :2], robot.data.root_ang_vel_b[:, 2:3]), 1)
        forces = contacts.data.net_forces_w[:, forbidden].norm(dim=-1).amax(1)
        if not bool(torch.isfinite(actual).all() and torch.isfinite(forces).all()):
            raise RuntimeError('Nonfinite probe physics')
        error = (actual - command).square()
        relative = robot.data.root_pos_w[:, :2] - base.scene.env_origins[:, :2]
        outside_spawn = relative.abs().amax(1) > 1.5
        for family in range(5):
            selected = families == family
            sums[family] += error[selected].sum(0)
            counts[family] += selected.sum()
            contact_counts[family] += (forces[selected] > 1.).sum()
            tilt_counts[family] += (-robot.data.projected_gravity_b[selected, 2] < .5).sum()
            moving_counts[family] += (command[selected, :2].norm(dim=1) > .05).sum()
            terrain_exposure[family] += outside_spawn[selected].sum()

    runner.eval_mode()
    base.reset()
    observations = env.get_observations()
    base.scene.update = update
    try:
        with torch.inference_mode():
            for _ in range(steps):
                actions = runner.alg.policy.act_inference(observations)
                if not bool(torch.isfinite(actions).all()):
                    raise RuntimeError('Nonfinite deterministic probe action')
                observations, _, dones, _ = env.step(actions)
                ended = dones.bool().flatten()
                current_length_steps += 1
                done_count += int(ended.sum())
                for family in range(5):
                    selected = (families == family) & ended
                    completed_episodes[family] += selected.sum()
                    completed_length_steps[family] += current_length_steps[selected].sum()
                    # Native manager reset leaves this step's get_term masks intact.
                    for name, values in termination_counts.items():
                        values[family] += (base.termination_manager.get_term(name) & selected).sum()
                current_length_steps[ended] = 0
    finally:
        base.scene.update = original_update
    result = {}
    for family, name in enumerate(('flat', 'random', 'slope_up', 'slope_down', 'blocks')):
        denominator = max(float(counts[family]), 1.)
        result[name] = dict(physics_samples=int(counts[family]),
            pooled_rms_vx_vy_yaw=(sums[family] / denominator).sqrt().tolist(),
            forbidden_contact_step_fraction=float(contact_counts[family]) / denominator,
            tilted_over_60deg_step_fraction=float(tilt_counts[family]) / denominator,
            moving_command_step_fraction=float(moving_counts[family]) / denominator,
            root_outside_spawn_step_fraction=float(terrain_exposure[family]) / denominator,
            completed_episodes=int(completed_episodes[family]),
            completed_episode_total_seconds=float(completed_length_steps[family]) * base.step_dt,
            completed_episode_mean_seconds=(float(completed_length_steps[family] / completed_episodes[family]) * base.step_dt
                if completed_episodes[family] > 0 else None),
            termination_counts={name: int(values[family]) for name, values in termination_counts.items()})
    return dict(scope='Unpaired post-training rollout with training randomization and observation noise; deterministic action means; auto-reset; no route or policy acceptance',
                policy_steps=steps, duration_per_environment_s=steps * base.step_dt,
                resets=done_count, by_family=result, policy_quality_accepted=False)


def main():
    raise RuntimeError("Teacher247 rejected by user: actor ABI must remain57->16; training disabled")
    configure_process()
    from isaaclab.app import AppLauncher
    args = parse_args(AppLauncher)
    args.output.mkdir(parents=True)
    started = time.perf_counter()
    manifest = dict(schema=SCHEMA, status='starting', started_utc=utc_now(), seed=args.seed,
        num_envs=args.num_envs, requested_updates=args.updates, warmup=args.warmup,
        policy_quality_accepted=False, policy_quality_evaluated=False, simulation_only=True,
        terrain_profile='diagnostic', terrain_level=0, route_evaluation=False,
        anchor=str(ANCHOR.relative_to(ROOT)), anchor_sha256=sha256(ANCHOR),
        source_sha256={f'scripts/{name}': sha256(ROOT / 'scripts' / name) for name in SOURCES},
        vendor_manifest_sha256=sha256(ROOT / 'vendor/manifest.json'),
        effective_ppo=dict(rollout=24, initial_std=.3, std_trainable_after_warmup=True,
            initial_learning_rate=1e-3, warmup_schedule='fixed', schedule='adaptive', desired_kl=.01,
            clip_param=.2, entropy_coef=.01, epochs=5, minibatches=4,
            parent_action_drift_guard=False, actor_observations=247, critic_observations=247))
    save = lambda: write_json(args.output / 'manifest.json', manifest)
    save()
    app = env = runner = None
    exit_code = 1
    try:
        from b2w_rough_runtime import ANCHOR_SHA256, ROUGH_TASK
        if manifest['anchor_sha256'] != ANCHOR_SHA256:
            raise RuntimeError('Qualified Flat54 anchor hash mismatch')
        params = args.output / 'params'
        sources = params / 'source'
        sources.mkdir(parents=True)
        for name in SOURCES:
            shutil.copyfile(ROOT / 'scripts' / name, sources / name)
        shutil.copyfile(ROOT / 'vendor/manifest.json', params / 'vendor_manifest.json')
        args.kit_args = f'{args.kit_args} {project_kit_args()}'.strip()
        app = AppLauncher(args, fast_shutdown=True).app
        import gymnasium as gym
        import torch
        from isaaclab.utils.io import dump_yaml
        from isaaclab_tasks.utils.parse_cfg import load_cfg_from_registry
        from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
        from rsl_rl.runners import OnPolicyRunner
        from b2w_locomotion_teacher import make_teacher_env_cfg, lift_flat_actor, validate_teacher_environment
        from reference_transfer import load_reference_teacher
        torch.set_num_threads(4)
        torch.manual_seed(args.seed)
        cfg = make_teacher_env_cfg(num_envs=args.num_envs, device=args.device, seed=args.seed,
                                   headless=args.headless, curriculum=False, terrain_profile='diagnostic')
        cfg.log_dir = str(args.output)
        agent = load_cfg_from_registry(ROUGH_TASK, 'rsl_rl_cfg_entry_point')
        agent.seed, agent.device, agent.max_iterations = args.seed, args.device, args.updates
        agent.obs_groups = {'policy': ['policy'], 'critic': ['critic']}
        agent.policy.init_noise_std = .3
        agent.policy.actor_obs_normalization = False
        agent.policy.critic_obs_normalization = False
        agent.save_interval = 25
        agent.algorithm.learning_rate = 1e-3
        agent.algorithm.schedule = 'adaptive'
        agent.algorithm.clip_param = .2
        agent.algorithm.entropy_coef = .01
        agent.algorithm.desired_kl = .01
        if args.resume:
            agent.load_run, agent.load_checkpoint = str(args.resume.parent), args.resume.name
        dump_yaml(str(params / 'env.yaml'), cfg)
        dump_yaml(str(params / 'agent.yaml'), agent)
        env = gym.make(ROUGH_TASK, cfg=cfg)
        env = RslRlVecEnvWrapper(env, clip_actions=agent.clip_actions)
        observations = env.get_observations()
        manifest['runtime_validation'] = validate_teacher_environment(env)
        for name in ('policy', 'critic'):
            if observations[name].shape != (args.num_envs, 247) or not bool(torch.isfinite(observations[name]).all()):
                raise RuntimeError('Teacher observation shape/finiteness mismatch: ' + name)
        frozen_actor = frozen_std = None

        class MonitoredRunner(OnPolicyRunner):
            def log(self, locs, *positional, **keywords):
                losses = {name: float(value) for name, value in locs['loss_dict'].items()}
                if not all(math.isfinite(value) for value in losses.values()):
                    raise RuntimeError('Nonfinite PPO losses')
                for value in locs['obs'].values():
                    if not bool(torch.isfinite(value).all()):
                        raise RuntimeError('Nonfinite rollout observation')
                assert_finite_policy(self.alg.policy, torch)
                if locs['it'] < args.warmup:
                    if any(not torch.equal(value.detach().cpu(), frozen_actor[name])
                           for name, value in self.alg.policy.actor.state_dict().items()):
                        raise RuntimeError('Actor changed during critic-only warmup')
                    if not torch.equal(self.alg.policy.std.detach().cpu(), frozen_std):
                        raise RuntimeError('Exploration std changed during critic-only warmup')
                super().log(locs, *positional, **keywords)
                progress = dict(updated_utc=utc_now(), iteration=locs['it'],
                    updates_completed_this_run=locs['it'] - locs['start_iter'] + 1,
                    updates_requested_this_run=args.updates, transitions_this_run=self.tot_timesteps,
                    collection_seconds=locs['collection_time'], learning_seconds=locs['learn_time'],
                    losses=losses, learning_rate=float(self.alg.learning_rate),
                    std_min=float(self.alg.policy.std.min()), std_max=float(self.alg.policy.std.max()),
                    training_phase='critic_calibration' if locs['it'] < args.warmup else 'ppo',
                    policy_quality_accepted=False)
                manifest['progress'] = progress
                write_json(args.output / 'progress.json', progress)
                set_training_phase(self, locs['it'] + 1, args.warmup)
                save()

            def save(self, path, infos=None):
                assert_finite_policy(self.alg.policy, torch)
                info = dict(infos or {}, teacher_pilot=dict(schema=SCHEMA, seed=args.seed,
                    num_envs=args.num_envs, warmup=args.warmup, anchor_sha256=manifest['anchor_sha256'],
                    source_sha256=manifest['source_sha256']))
                super().save(path, info)

        runner = MonitoredRunner(env, agent.to_dict(), log_dir=str(args.output), device=args.device)
        policy = runner.alg.policy
        if args.resume:
            parent = json.loads((args.resume.parent / 'manifest.json').read_text(encoding='utf-8'))
            matching = [item for item in parent.get('checkpoints', []) if item['path'] == args.resume.name]
            if (parent.get('schema') != SCHEMA or parent.get('status') != 'completed'
                    or len(matching) != 1 or matching[0]['sha256'] != sha256(args.resume)
                    or any(parent[key] != manifest[key] for key in ('seed', 'num_envs', 'warmup', 'anchor_sha256', 'source_sha256'))):
                raise RuntimeError('Resume checkpoint must belong to this exact teacher recipe and seed')
            infos = runner.load(str(args.resume), load_optimizer=True, map_location=args.device)
            if not infos or infos.get('teacher_pilot', {}).get('schema') != SCHEMA:
                raise RuntimeError('Missing teacher checkpoint provenance')
            runner.current_learning_iteration += 1
            rates = {float(group['lr']) for group in runner.alg.optimizer.param_groups}
            if len(rates) != 1:
                raise RuntimeError('Resume optimizer has inconsistent learning rates')
            runner.alg.learning_rate = rates.pop()
            manifest['resume'] = dict(path=str(args.resume.relative_to(ROOT)), sha256=sha256(args.resume),
                optimizer_step=optimizer_step(runner.alg.optimizer), restored_learning_rate=runner.alg.learning_rate)
        else:
            source = load_reference_teacher(ANCHOR, 'cpu')
            manifest['actor_lift'] = lift_flat_actor(policy.actor, source.actor)
            with torch.no_grad():
                policy.std.fill_(.3)
        frozen_actor = {name: value.detach().cpu().clone() for name, value in policy.actor.state_dict().items()}
        frozen_critic = {name: value.detach().cpu().clone() for name, value in policy.critic.state_dict().items()}
        frozen_std = policy.std.detach().cpu().clone()
        start = int(runner.current_learning_iteration)
        manifest['starting_iteration'] = start
        manifest['starting_runner_iteration'] = start
        manifest['starting_optimizer_step'] = optimizer_step(runner.alg.optimizer)
        set_training_phase(runner, start, args.warmup)
        manifest['status'] = 'running'
        save()
        runner.learn(num_learning_iterations=args.updates, init_at_random_ep_len=True)
        end = int(runner.current_learning_iteration)
        if end != start + args.updates - 1:
            raise RuntimeError('Native runner iteration did not match requested budget')
        actor_changed = any(not torch.equal(value.detach().cpu(), frozen_actor[name]) for name, value in policy.actor.state_dict().items())
        critic_changed = any(not torch.equal(value.detach().cpu(), frozen_critic[name]) for name, value in policy.critic.state_dict().items())
        actor_updates = max(0, end - max(start, args.warmup) + 1)
        if actor_changed != (actor_updates > 0) or not critic_changed:
            raise RuntimeError('Actor/critic update verification failed')
        if optimizer_step(runner.alg.optimizer) <= manifest['starting_optimizer_step']:
            raise RuntimeError('Optimizer did not advance')
        manifest.update(ending_iteration=end, actor_updates_this_run=actor_updates,
            ending_runner_iteration=end,
            checkpoint=str((args.output / f'model_{end}.pt').relative_to(ROOT)),
            checkpoint_sha256=sha256(args.output / f'model_{end}.pt'),
            extra_input_weight_norm=float(policy.actor[0].weight[:, 57:].norm()),
            actor_changed=actor_changed, critic_changed=critic_changed,
            optimizer_max_step=optimizer_step(runner.alg.optimizer),
            final_learning_rate=float(runner.alg.learning_rate),
            final_std=policy.std.detach().cpu().tolist(),
            export_parity=export_parity(policy, env.get_observations(), args.output, torch),
            suffix_action_sensitivity=suffix_action_sensitivity(policy, env.get_observations(), torch))
        if args.probe_steps:
            manifest['post_training_probe'] = rollout_probe(env, runner, args.probe_steps, torch)
            write_json(args.output / 'post_training_probe.json', manifest['post_training_probe'])
        manifest['status'] = 'completed'
        exit_code = 0
    except BaseException as error:
        manifest.update(status='failed', error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        for name, resource in (('writer', getattr(runner, 'writer', None)), ('environment', env)):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as error:
                    manifest.setdefault('cleanup_errors', []).append(f'{name}: {error}')
                    manifest['status'] = 'failed'
                    exit_code = 1
        manifest.update(finished_utc=utc_now(), elapsed_seconds=time.perf_counter() - started,
            checkpoints=[dict(path=path.name, sha256=sha256(path), bytes=path.stat().st_size)
                         for path in sorted(args.output.glob('model_*.pt'))])
        save()
        if app is not None:
            app.app.post_quit(exit_code)
            app.close()
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
