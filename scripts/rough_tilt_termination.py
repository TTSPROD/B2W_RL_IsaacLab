"""One-factor Rough correction: end sustained >60-degree tilt as a true terminal."""
from __future__ import annotations


def sustained_tilt(env):
    tracker = getattr(env, '_rough_traversal_tracker', None)
    if tracker is None:
        raise RuntimeError('Rough tilt termination requires physics-rate traversal telemetry')
    return tracker.tilt_failed.clone()


def configure_tilt_termination(cfg):
    from isaaclab.managers import TerminationTermCfg
    if getattr(cfg.terminations, 'rough_sustained_tilt', None) is not None:
        raise ValueError('Rough tilt termination already configured')
    cfg.terminations.rough_sustained_tilt = TerminationTermCfg(func=sustained_tilt, time_out=False)


def validate_tilt_fixture(env):
    """Exercise actual PhysX and native reset on one inverted robot; smoke runs only."""
    import torch
    base = env.unwrapped
    if base.num_envs != 64:
        raise ValueError('Injected tilt fixture is restricted to discarded 64-env smoke')
    robot = base.scene['robot']; tracker = base._rough_traversal_tracker
    ids = torch.tensor([0], device=base.device)
    with torch.inference_mode():
        state = robot.data.root_state_w[ids].clone()
        state[:, 2] = base.scene.env_origins[ids, 2] + .8
        state[:, 3:7] = state.new_tensor([0., 1., 0., 0.])
        state[:, 7:] = 0.
        robot.write_root_state_to_sim(state, env_ids=ids)
        tracker.tilt_time.zero_(); tracker.tilt_failed.zero_()
        triggered = None
        for step in range(15):
            base.step(torch.zeros((64, 16), device=base.device))
            if bool(base.termination_manager.get_term('rough_sustained_tilt')[0]):
                triggered = dict(policy_steps=step+1, elapsed_s=(step+1)*base.step_dt,
                                 terminated=bool(base.reset_terminated[0]),
                                 timed_out=bool(base.reset_time_outs[0]),
                                 timer_after_reset=float(tracker.tilt_time[0]),
                                 sticky_after_reset=bool(tracker.tilt_failed[0]))
                break
        if (triggered is None or not .1 < triggered['elapsed_s'] <= .16
                or not triggered['terminated'] or triggered['timed_out']
                or triggered['timer_after_reset'] != 0. or triggered['sticky_after_reset']):
            raise ValueError(f'Native tilt termination/reset fixture failed: {triggered}')
        env.reset()
    return dict(passed=True, injected_environment=0, tilt_degrees=180, **triggered)
