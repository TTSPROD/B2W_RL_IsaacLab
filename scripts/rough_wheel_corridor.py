"""Rough-only wheel corridor terminal and consistent curriculum failure telemetry."""
from __future__ import annotations
from rough_curriculum import SafeTraversalCurriculum

X_MIN, X_MAX, Y_LIMIT = -.6, 5.4, .9
SIDE_NAMES = ('backward', 'forward', 'negative_y', 'positive_y')


def boundary_sides(wheel_relative):
    """Strict inequalities match the frozen evaluator; tensor shape [env, wheel, xyz]."""
    import torch
    if wheel_relative.ndim != 3 or wheel_relative.shape[1:] != (4, 3):
        raise ValueError('Expected four wheel centers per environment')
    return torch.stack(((wheel_relative[..., 0] < X_MIN).any(1),
                        (wheel_relative[..., 0] > X_MAX).any(1),
                        (wheel_relative[..., 1] < -Y_LIMIT).any(1),
                        (wheel_relative[..., 1] > Y_LIMIT).any(1)), 1)


def wheel_corridor_terminal(env):
    tracker = getattr(env, '_rough_traversal_tracker', None)
    if not isinstance(tracker, WheelCorridorCurriculum):
        raise RuntimeError('Wheel corridor requires its physics-rate curriculum tracker')
    return tracker.corridor_failed.clone()


def configure_wheel_corridor(cfg):
    from isaaclab.managers import TerminationTermCfg
    if getattr(cfg.terminations, 'rough_wheel_corridor', None) is not None:
        raise ValueError('Wheel corridor already configured')
    cfg.terminations.rough_wheel_corridor = TerminationTermCfg(func=wheel_corridor_terminal, time_out=False)


class WheelCorridorCurriculum(SafeTraversalCurriculum):
    def __init__(self, env, cap=0, state=None):
        import torch
        base = env.unwrapped
        robot = base.scene['robot']
        self.wheels = [robot.body_names.index(f'{leg}_foot') for leg in ('FR', 'FL', 'RR', 'RL')]
        if state is not None and state.get('wheel_corridor_enabled') is not True:
            raise ValueError('Cannot reinterpret an old curriculum checkpoint as wheel-aware')
        self.corridor_failed = torch.zeros(base.num_envs, dtype=torch.bool, device=base.device)
        self.corridor_sides = torch.zeros((base.num_envs, 4), dtype=torch.bool, device=base.device)
        self.corridor_episodes = [0] * 5
        self.corridor_side_counts = [0] * 4
        super().__init__(env, cap=cap, state=state)

    def update(self, dt):
        before = self.ticks
        super().update(dt)
        if self.ticks == before:
            return
        wheel = self.robot.data.body_link_pos_w[:, self.wheels] - self.env.scene.env_origins[:, None, :]
        finite = self.t.isfinite(wheel).all(dim=(1, 2))
        self.nonfinite |= ~finite
        rough = self.family != 0
        self.corridor_sides |= boundary_sides(wheel) & rough[:, None]
        self.corridor_failed |= (~finite | self.corridor_sides.any(1)) & rough
        self.failed |= self.corridor_failed

    def reset(self, ids):
        for family in range(1, 5):
            self.corridor_episodes[family] += int(((self.family[ids] == family) & self.corridor_failed[ids]).sum())
        for side in range(4):
            self.corridor_side_counts[side] += int(self.corridor_sides[ids, side].sum())
        # Parent consumes self.failed before clearing it, preventing false promotion.
        super().reset(ids)
        self.corridor_failed[ids] = False
        self.corridor_sides[ids] = False

    def snapshot(self):
        result = super().snapshot()
        result.update(wheel_corridor_enabled=True,
            corridor_bounds=dict(x=[X_MIN, X_MAX], y=[-Y_LIMIT, Y_LIMIT]),
            corridor_failed_episodes_since_restart=list(self.corridor_episodes),
            corridor_sides_since_restart=dict(zip(SIDE_NAMES, self.corridor_side_counts)),
            scope='Safe traversal plus Rough-only sticky wheel corridor; true terminal; Flat unchanged')
        return result


def validate_corridor_fixture(env):
    """Use native PhysX, manager terminal and reset on actual wheel positions, smoke only."""
    import torch
    base = env.unwrapped
    if base.num_envs != 64:
        raise ValueError('Injected corridor fixture is discard-only64')
    tracker = base._rough_traversal_tracker
    robot = base.scene['robot']
    rough_id = int((tracker.family != 0).nonzero()[0, 0])
    flat_id = int((tracker.family == 0).nonzero()[0, 0])
    records = []
    with torch.inference_mode():
        for label, offset in (('forward', (5.6, 0.)), ('backward', (-.8, 0.)),
                              ('negative_y', (0., -1.1)), ('positive_y', (0., 1.1))):
            env.reset()
            ids = torch.tensor([rough_id, flat_id], device=base.device)
            state = robot.data.root_state_w[ids].clone()
            state[:, :2] = base.scene.env_origins[ids, :2] + state.new_tensor(offset)
            state[:, 2] = base.scene.env_origins[ids, 2] + .8
            state[:, 3:7] = state.new_tensor([1., 0., 0., 0.])
            state[:, 7:] = 0.
            robot.write_root_state_to_sim(state, env_ids=ids)
            base.step(torch.zeros((64, 16), device=base.device))
            term = base.termination_manager.get_term('rough_wheel_corridor')
            if (not bool(term[rough_id]) or bool(term[flat_id]) or not bool(base.reset_terminated[rough_id])
                    or bool(base.reset_time_outs[rough_id]) or bool(tracker.corridor_failed[rough_id])
                    or tracker.corridor_side_counts[SIDE_NAMES.index(label)] < 1):
                raise ValueError('Native corridor terminal/reset/Flat mask fixture failed: ' + label)
            records.append(dict(side=label, rough_terminal=True, flat_terminal=False,
                                timed_out=False, sticky_cleared_on_reset=True))
        env.reset()
    return dict(passed=True, injected_rough_id=rough_id, injected_flat_id=flat_id,
                sides=records, cadence_hz=200, policy_reset_hz=50)
