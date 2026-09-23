"""Nominal Isaac replay of the pinned reference (diagnostic, not release acceptance)."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import sys
import traceback

sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT, FLAT_TASK, configure_process, make_flat_env_cfg, project_kit_args
from check_stand_b2w import _nominal_cfg
from smoke_b2w_desktop import _check_tensors, _gpu_evidence, _write_report

from flat_evaluation import SCENARIOS, make_cases, summarize
from physical_evaluation import PROFILES, configure_physical_evaluation, physical_evidence


def main():
    configure_process()
    from isaaclab.app import AppLauncher
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--num_envs', type=int, default=16)
    parser.add_argument('--suite', choices=('diagnostic', 'flat100'), default='diagnostic')
    parser.add_argument('--yaw_trace', action='store_true', help='Passive yaw physics trace; writes a separate diagnostic NPZ')
    parser.add_argument('--reward_diagnostics', action='store_true', help='Record weighted reward components; diagnostic only')
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--physical_profile', choices=PROFILES, default='nominal')
    parser.add_argument('--duration_s', type=float, default=20.)
    parser.add_argument('--settle_s', type=float, default=2.)
    parser.add_argument('--policy', type=Path, default=PROJECT_ROOT / 'vendor/rl_sar/policy/b2w/robot_lab/policy.pt')
    parser.add_argument('--report', type=Path, default=PROJECT_ROOT / 'logs/qualification/reference_replay.json')
    AppLauncher.add_app_launcher_args(parser)
    parser.set_defaults(headless=True, device='cuda:0')
    args = parser.parse_args()
    report_path = args.report.resolve()
    policy_path = args.policy.resolve()
    if args.yaw_trace and (report_path.exists() or report_path.with_suffix('.yaw.npz').exists()):
        parser.error('Trace outputs must be new; refusing overwrite')
    if not report_path.is_relative_to((PROJECT_ROOT / 'logs/qualification').resolve()):
        parser.error('--report must be inside project logs/qualification')
    if not policy_path.is_relative_to(PROJECT_ROOT.resolve()) or not policy_path.is_file():
        parser.error('--policy must be an existing file inside this project')
    if args.suite == 'flat100' and (args.num_envs < 100 or args.duration_s != 20. or args.settle_s != 2.):
        parser.error('flat100 requires at least 100 environments, 20 seconds and 2 seconds settling')
    if args.num_envs < 8 or (args.suite == 'diagnostic' and args.num_envs % 8) or not args.headless or args.enable_cameras or not args.device.startswith('cuda'):
        parser.error('Requires a positive multiple of 8 environments, headless CUDA, no cameras')
    if not all(math.isfinite(x) for x in (args.duration_s, args.settle_s)) or args.duration_s <= 0 or args.settle_s < 0:
        parser.error('Invalid duration')
    report = {
        'schema_version': 1, 'status': 'starting', 'scope': 'heldout_commands_and_initial_pose' if args.suite == 'flat100' else 'nominal_policy_replay_diagnostic',
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'policy_path': str(policy_path.relative_to(PROJECT_ROOT)),
        'policy_sha256': hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        'source_sha256': {name: hashlib.sha256((PROJECT_ROOT / name).read_bytes()).hexdigest()
                          for name in ('scripts/replay_reference_b2w.py', 'scripts/check_stand_b2w.py', 'scripts/b2w_runtime.py', 'scripts/flat_evaluation.py', 'scripts/physical_evaluation.py')},
        'new_policy_trained_by_this_script': False, 'release_acceptance_test': False,
        'suite': args.suite, 'evaluation_seed': args.seed, 'num_envs': args.num_envs, 'duration_s': args.duration_s, 'settle_s': args.settle_s,
        'reset_count_during_replay': 0,
        'failure_accounting': 'Sticky failure flags checked every physics step from t=0; no reset or recovery counted as success',
        'policy_active_during_settling': True, 'external_exit_code_required': 0,
        'thresholds': {'stand_tilt_deg': 15., 'moving_tilt_deg': 45., 'root_height_m': [.4, .8],
                       'non_wheel_contact_n': 1., 'tracking_rms_xy_m_s': .2, 'tracking_rms_yaw_rad_s': .25},
    }
    cases = make_cases(args.num_envs, args.seed, heldout=args.suite == 'flat100')
    report['cases'] = cases
    report['case_distribution'] = {'forward_backward_m_s': [.2, .5], 'lateral_abs_m_s': [.15, .3], 'yaw_abs_rad_s': [.2, .5], 'initial_yaw_rad': [-math.pi, math.pi], 'leg_offset_rad': [-.025, .025]} if args.suite == 'flat100' else 'fixed nominal diagnostic'
    app = env = None
    exit_code = 1
    _write_report(report_path, report)
    try:
        args.kit_args = f'{args.kit_args} {project_kit_args()}'.strip()
        app = AppLauncher(args, fast_shutdown=True).app
        import gymnasium as gym
        import torch
        torch.set_num_threads(4)
        cfg = make_flat_env_cfg(num_envs=args.num_envs, device=args.device, seed=args.seed, headless=True)
        report['disabled_events'] = _nominal_cfg(cfg)
        report['physical_profile'] = configure_physical_evaluation(cfg, args.physical_profile)
        cfg.scene.env_spacing = 25.
        cfg.episode_length_s = args.duration_s + args.settle_s + 1.
        dt, decimation = cfg.sim.dt, cfg.decimation
        policy_dt = dt * decimation
        settle_steps, measure_steps = round(args.settle_s / policy_dt), round(args.duration_s / policy_dt)
        if not math.isclose(settle_steps * policy_dt, args.settle_s) or not math.isclose(measure_steps * policy_dt, args.duration_s):
            raise ValueError('Durations must be multiples of policy period')
        env = gym.make(FLAT_TASK, cfg=cfg)
        base = env.unwrapped
        env.reset(seed=args.seed)
        robot, sensor = base.scene['robot'], base.scene['contact_forces']
        root = robot.data.default_root_state.clone()
        root[:, :3] += base.scene.env_origins
        root[:, 7:] = 0.
        if args.suite == 'flat100':
            yaw = torch.tensor([case['initial_yaw_rad'] for case in cases], device=base.device)
            root[:, 3:7] = 0.
            root[:, 3] = torch.cos(yaw / 2)
            root[:, 6] = torch.sin(yaw / 2)
        robot.write_root_state_to_sim(root)
        joint_position = robot.data.default_joint_pos.clone()
        leg_ids, _ = robot.find_joints(cfg.leg_joint_names, preserve_order=True)
        joint_position[:, leg_ids] += torch.tensor([case['leg_position_offset_rad'] for case in cases], device=base.device)
        robot.write_joint_state_to_sim(joint_position, torch.zeros_like(robot.data.default_joint_vel))
        base.scene.reset()
        base.scene.write_data_to_sim()
        base.scene.update(dt=0.)
        report['physical_evidence'] = physical_evidence(base)
        policy_ids, policy_names = robot.find_joints(cfg.joint_names, preserve_order=True)
        if policy_names != cfg.joint_names:
            raise RuntimeError('Policy joint order mismatch')
        expected_terms = ['base_ang_vel', 'projected_gravity', 'velocity_commands', 'joint_pos', 'joint_vel', 'actions']
        if base.observation_manager.active_terms['policy'] != expected_terms:
            raise RuntimeError('Unexpected policy observation terms')
        body_ids = [i for i, name in enumerate(sensor.body_names) if not name.endswith('_foot')]
        if cfg.base_link_name not in sensor.body_names or len(sensor.body_names) - len(body_ids) != 4:
            raise RuntimeError('Unexpected wheel/body contact sensor names')
        report.update(gpu_pipeline=_gpu_evidence(base, robot, torch), physics_dt=dt, policy_dt=policy_dt,
                      policy_joint_names=policy_names, policy_to_asset_indices=policy_ids,
                      contact_bodies_checked=[sensor.body_names[i] for i in body_ids])
        recorder = None
        if args.yaw_trace:
            from yaw_trace import YawTrace
            recorder = YawTrace(base, robot, sensor, policy_ids, (settle_steps + measure_steps) * decimation, report_path, torch)
            report['source_sha256']['scripts/yaw_trace.py'] = hashlib.sha256((PROJECT_ROOT / 'scripts/yaw_trace.py').read_bytes()).hexdigest()
        policy = torch.jit.load(str(policy_path), map_location=args.device).eval()
        n = args.num_envs
        device = base.device
        scenario_ids = torch.arange(n, device=device) % len(SCENARIOS)
        scheduled = torch.tensor([case['command'] for case in cases], device=device)
        command = base.command_manager.get_command('base_velocity')
        previous_action = torch.zeros((n, 16), device=device)
        failed = torch.zeros(n, dtype=torch.bool, device=device)
        failure_events = []
        reward_sum = torch.zeros((n, len(base.reward_manager.active_terms)), device=device)
        error_sum = torch.zeros((n, 3), device=device)
        actual_sum = torch.zeros_like(error_sum)
        command_sum = torch.zeros_like(error_sum)
        valid_sum = torch.zeros_like(error_sum)
        valid_count = torch.zeros(n, device=device)
        stop_sum = torch.zeros_like(error_sum)
        stop_count = torch.zeros(n, device=device)
        max_tilt, max_contact, max_action = (torch.zeros(n, device=device) for _ in range(3))
        min_height = torch.full((n,), float('inf'), device=device)
        obs_max_error = 0.
        action_target_max_error = 0.
        reference_obs_max_error = 0.
        saturation_observation_steps = 0
        action_saturation_steps = 0
        base.action_manager.process_action(previous_action)
        report['status'] = 'running'
        _write_report(report_path, report)
        with torch.inference_mode():
            for step in range(settle_steps + measure_steps):
                if not app.is_running():
                    raise RuntimeError('SimulationApp stopped early')
                measured_time = (step - settle_steps) * policy_dt
                command[:] = 0. if step < settle_steps else scheduled
                if measured_time >= args.duration_s / 2:
                    command[scenario_ids >= 6] = 0.
                obs = base.observation_manager.compute()['policy']
                position = robot.data.joint_pos[:, policy_ids] - robot.data.default_joint_pos[:, policy_ids]
                position[:, 12:] = 0.
                terms = [robot.data.root_ang_vel_b, robot.data.projected_gravity_b, command,
                         position, robot.data.joint_vel[:, policy_ids], previous_action]
                scales = [.25, 1., 1., 1., .05, 1.]
                independent = torch.cat([term.clamp(-100, 100) * scale for term, scale in zip(terms, scales)], dim=1)
                reference_obs = torch.cat([term * scale for term, scale in zip(terms, scales)], dim=1).clamp(-100, 100)
                error = float((obs - independent).abs().max())
                obs_max_error = max(obs_max_error, error)
                reference_error = float((obs - reference_obs).abs().max())
                reference_obs_max_error = max(reference_obs_max_error, reference_error)
                saturation_observation_steps += int(reference_error > 1e-5)
                if tuple(obs.shape) != (n, 57) or error > 1e-5:
                    raise RuntimeError(f'Live observation contract mismatch: {obs.shape}, error={error}')
                _check_tensors(obs, 'actor_input', torch)
                action = policy(obs)
                _check_tensors(action, 'policy_action', torch)
                if tuple(action.shape) != (n, 16):
                    raise RuntimeError('Unexpected policy output shape')
                action_saturation_steps += int(bool((action.abs() > 100).any()))
                max_action = torch.maximum(max_action, action.abs().amax(1))
                base.action_manager.process_action(action)
                leg_scales = torch.tensor([.125, .25, .25] * 4, device=device)
                expected_pos = (action[:, :12] * leg_scales + robot.data.default_joint_pos[:, policy_ids[:12]]).clamp(-100, 100)
                expected_vel = (action[:, 12:] * 5.).clamp(-100, 100)
                target_error = max(float((base.action_manager.get_term('joint_pos').processed_actions - expected_pos).abs().max()),
                                   float((base.action_manager.get_term('joint_vel').processed_actions - expected_vel).abs().max()))
                action_target_max_error = max(action_target_max_error, target_error)
                if target_error > 1e-5:
                    raise RuntimeError(f'Live action target contract mismatch: {target_error}')
                previous_action = action.clone()
                for substep in range(decimation):
                    base._sim_step_counter += 1
                    base.action_manager.apply_action()
                    base.scene.write_data_to_sim()
                    base.sim.step(render=False)
                    base.scene.update(dt=dt)
                    _check_tensors(torch.cat((robot.data.root_state_w, robot.data.joint_pos, robot.data.joint_vel,
                                              robot.data.applied_torque, sensor.data.net_forces_w.flatten(1)), 1), 'state', torch)
                    tilt = torch.rad2deg(torch.acos((-robot.data.projected_gravity_b[:, 2]).clamp(-1, 1)))
                    height = robot.data.root_pos_w[:, 2] - base.scene.env_origins[:, 2]
                    contact = torch.linalg.vector_norm(sensor.data.net_forces_w[:, body_ids], dim=-1).amax(1)
                    max_tilt = torch.maximum(max_tilt, tilt)
                    max_contact = torch.maximum(max_contact, contact)
                    min_height = torch.minimum(min_height, height)
                    tilt_limit = torch.where(scenario_ids == 0, 15., 45.)
                    failures = {'tilt': tilt > tilt_limit, 'height': (height < .4) | (height > .8), 'body_contact': contact > 1.}
                    new_failure = torch.stack(list(failures.values())).any(0) & ~failed
                    for idx in new_failure.nonzero().flatten().tolist():
                        failure_events.append({'env': idx, 'scenario': SCENARIOS[idx % 8][0],
                            'time_s': step * policy_dt + (substep + 1) * dt,
                            'reasons': [reason for reason, flags in failures.items() if bool(flags[idx])],
                            'tilt_deg': float(tilt[idx]), 'height_m': float(height[idx]), 'contact_n': float(contact[idx]),
                            'contact_bodies': {sensor.body_names[b]: float(torch.linalg.vector_norm(sensor.data.net_forces_w[idx, b]))
                                               for b in body_ids if float(torch.linalg.vector_norm(sensor.data.net_forces_w[idx, b])) > 1.},
                            'command_vx_vy_yaw': command[idx].tolist(),
                            'actual_vx_vy_yaw': torch.cat((robot.data.root_lin_vel_b[idx, :2], robot.data.root_ang_vel_b[idx, 2:3])).tolist(),
                            'joint_positions_policy_order': robot.data.joint_pos[idx, policy_ids].tolist(),
                            'applied_torques_policy_order': robot.data.applied_torque[idx, policy_ids].tolist()})
                    failed |= new_failure
                    if recorder is not None:
                        recorder.capture(command, action, step * policy_dt + (substep + 1) * dt)
                if args.reward_diagnostics:
                    base.reward_manager.compute(dt=policy_dt)
                    if step >= settle_steps:
                        reward_sum += base.reward_manager._step_reward
                if step >= settle_steps:
                    actual = torch.cat((robot.data.root_lin_vel_b[:, :2], robot.data.root_ang_vel_b[:, 2:3]), 1)
                    actual_sum += actual
                    command_sum += command
                    squared = (actual - command).square()
                    error_sum += squared
                    valid_sum += squared * (~failed)[:, None]
                    valid_count += ~failed
                    if measured_time >= args.duration_s * .75:
                        stopped = scenario_ids >= 6
                        stop_sum += squared * stopped[:, None]
                        stop_count += stopped
                if (step + 1) % 100 == 0:
                    report.update(policy_steps_completed=step + 1, failed_environments=int(failed.sum()),
                                  first_failures=failure_events, live_observation_max_error=obs_max_error)
                    _write_report(report_path, report)
                    print(f'[REPLAY] {step + 1}/{settle_steps + measure_steps}; failures={int(failed.sum())}', flush=True)
        if recorder is not None:
            report['yaw_trace'] = recorder.finish()
        after = physical_evidence(base)
        if after['properties_sha256'] != report['physical_evidence']['properties_sha256']:
            raise RuntimeError('Physical properties changed during replay')
        report['physical_evidence']['persistent_through_replay'] = True
        report['physical_evidence']['end_properties_sha256'] = after['properties_sha256']
        rms = (error_sum / measure_steps).sqrt()
        results = []
        for i in range(n):
            tracking = bool((rms[i, :2] <= .2).all() and rms[i, 2] <= .25)
            results.append({'env': i, 'scenario': SCENARIOS[i % 8][0], 'no_fall_or_body_contact': not bool(failed[i]),
                'tracking_threshold_met': tracking, 'rms_vx_vy_yaw': rms[i].tolist(),
                'mean_actual_vx_vy_yaw': (actual_sum[i] / measure_steps).tolist(),
                'mean_command_vx_vy_yaw': (command_sum[i] / measure_steps).tolist(),
                'signed_tracking_bias_vx_vy_yaw': ((actual_sum[i] - command_sum[i]) / measure_steps).tolist(),
                'valid_tracking_samples': int(valid_count[i]),
                'rms_before_failure': (valid_sum[i] / valid_count[i]).sqrt().tolist() if valid_count[i] else None,
                'stop_last_quarter_rms': (stop_sum[i] / stop_count[i]).sqrt().tolist() if stop_count[i] else None,
                'max_tilt_deg': float(max_tilt[i]), 'minimum_height_m': float(min_height[i]),
                'maximum_non_wheel_contact_n': float(max_contact[i]), 'max_abs_raw_action': float(max_action[i])})
        report.update(status='completed', results=results, first_failures=failure_events,
                      policy_steps_completed=settle_steps + measure_steps,
                      physics_steps_completed=(settle_steps + measure_steps) * decimation,
                      all_environments_no_fall=not bool(failed.any()),
                      live_observation_max_error=obs_max_error, live_action_target_max_error=action_target_max_error,
                      isaac_vs_reference_observation_max_error=reference_obs_max_error,
                      observation_saturation_mismatch_steps=saturation_observation_steps,
                      raw_action_saturation_steps=action_saturation_steps,
                      training_randomization_evaluated=False,
                      bounded_physical_randomization_evaluated=args.physical_profile == 'bounded_v1',
                      interpretation='Completed diagnostic with individual outcomes; 100 episodes/3 seeds, randomization and sim2sim remain untested')
        if args.reward_diagnostics:
            report['weighted_reward_rate_by_scenario'] = {
                scenario[0]: dict(zip(base.reward_manager.active_terms,
                                     (reward_sum[scenario_ids == index].mean(0) / measure_steps).tolist()))
                for index, scenario in enumerate(SCENARIOS)}
            report['reward_diagnostics_note'] = 'Weighted terms per second, sampled after each policy step, measurement window including failed episodes; nominal replay without reset.'
        report['summary'] = summarize(results)
        if args.suite == 'flat100':
            report['scope'] = 'heldout_commands_initial_pose_and_' + args.physical_profile
            report['interpretation'] = 'One policy, 100 or more command/initial-pose episodes; physical coverage is exactly the recorded profile. Three training seeds, wider randomization and sim2sim are separate gates.'
            report['summary']['confidence_note'] = 'Wilson interval is descriptive for this fixed case suite and recorded physical profile; it does not measure training-seed variability.'
        exit_code = 0
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        print(report['traceback'], file=sys.stderr, flush=True)
    finally:
        if env is not None:
            try:
                env.close()
            except BaseException as exc:
                report.update(status='cleanup_failed', cleanup_error=str(exc))
                exit_code = 1
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        _write_report(report_path, report)
        print(f"[REPLAY] {report['status']}: {report_path}", flush=True)
        if app is not None:
            app.app.post_quit(exit_code)
            app.close()
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
