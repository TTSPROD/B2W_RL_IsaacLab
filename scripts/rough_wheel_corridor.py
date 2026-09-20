"""Rough-only wheel corridor terminal and consistent curriculum failure telemetry."""
from __future__ import annotations
from rough_curriculum import SafeTraversalCurriculum

X_MIN, X_MAX, Y_LIMIT = -.6, 5.4, .9
WIDE_Y_LIMIT = 1.8
SIDE_NAMES = ('backward', 'forward', 'negative_y', 'positive_y')


def boundary_sides(wheel_relative, y_limit=Y_LIMIT):
    """Strict wheel-center boundaries; default matches the frozen evaluator."""
    import torch
    if y_limit not in (Y_LIMIT, WIDE_Y_LIMIT):
        raise ValueError("Only registered narrow/wide corridor limits are supported")
    if wheel_relative.ndim != 3 or wheel_relative.shape[1:] != (4, 3):
        raise ValueError('Expected four wheel centers per environment')
    return torch.stack(((wheel_relative[..., 0] < X_MIN).any(1),
                        (wheel_relative[..., 0] > X_MAX).any(1),
                        (wheel_relative[..., 1] < -y_limit).any(1),
                        (wheel_relative[..., 1] > y_limit).any(1)), 1)


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
    def __init__(self, env, cap=0, state=None, *, y_limit=Y_LIMIT):
        import torch
        if y_limit not in (Y_LIMIT, WIDE_Y_LIMIT):
            raise ValueError('Only registered narrow/wide corridor limits are supported')
        self.y_limit = y_limit
        base = env.unwrapped
        robot = base.scene['robot']
        self.wheels = [robot.body_names.index(f'{leg}_foot') for leg in ('FR', 'FL', 'RR', 'RL')]
        if state is not None and state.get('wheel_corridor_enabled') is not True:
            raise ValueError('Cannot reinterpret an old curriculum checkpoint as wheel-aware')
        if state is not None:
            saved_bounds = state.get('corridor_bounds', dict(x=[X_MIN, X_MAX], y=[-Y_LIMIT, Y_LIMIT]))
            if saved_bounds != dict(x=[X_MIN, X_MAX], y=[-y_limit, y_limit]):
                raise ValueError('Cannot change wheel corridor bounds on curriculum resume')
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
        self.corridor_sides |= boundary_sides(wheel, y_limit=self.y_limit) & rough[:, None]
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
            corridor_bounds=dict(x=[X_MIN, X_MAX], y=[-self.y_limit, self.y_limit]),
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



def validate_wide_corridor_fixture(env):
    """Native64 smoke: narrow lateral crossings survive; wide crossings terminate.

    Physics-rate samples precede the native manager reset. Injected root poses and
    progress counters belong only to this discarded smoke, never policy evaluation.
    """
    import torch
    base = env.unwrapped
    if base.num_envs != 64:
        raise ValueError('Injected wide corridor fixture is discard-only64')
    tracker = base._rough_traversal_tracker
    if not isinstance(tracker, WheelCorridorCurriculum) or tracker.y_limit != WIDE_Y_LIMIT:
        raise ValueError('Wide corridor fixture requires the matching wheel tracker')
    if 'rough_wheel_corridor' not in base.termination_manager.active_terms:
        raise ValueError('Wide corridor must retain its true terminal')
    robot = base.scene['robot']
    rough_id = int((tracker.family != 0).nonzero()[0, 0])
    flat_id = int((tracker.family == 0).nonzero()[0, 0])
    ids = torch.tensor([rough_id, flat_id], device=base.device)
    family = int(tracker.family[rough_id])
    actions = torch.zeros((64, 16), device=base.device)
    center = robot.data.root_state_w.new_tensor([[1., 0.], [1., 0.]])
    previous_update = base.scene.update
    samples = []

    def sample_physics(dt):
        before = tracker.ticks
        previous_update(dt)
        if tracker.ticks != before:
            samples.append((robot.data.body_link_pos_w[ids][:, tracker.wheels]
                            - base.scene.env_origins[ids, None, :]).clone())

    def move_root(xy, *, upright=False):
        state = robot.data.root_state_w[ids].clone()
        state[:, :2] = base.scene.env_origins[ids, :2] + xy
        state[:, 2] = base.scene.env_origins[ids, 2] + .8
        if upright:
            state[:, 3:7] = state.new_tensor([1., 0., 0., 0.])
        state[:, 7:] = 0.
        samples.clear()
        robot.write_root_state_to_sim(state, env_ids=ids)
        base.step(actions)
        if not samples:
            raise ValueError('Wide corridor fixture recorded no physics samples')
        return torch.stack(samples)

    def crossing_pose(side, limit):
        axis = 0 if side in ('forward', 'backward') else 1
        positive = side in ('forward', 'positive_y')
        offsets = robot.data.body_link_pos_w[ids][:, tracker.wheels] - robot.data.root_pos_w[ids, None, :]
        extreme = offsets[..., axis].amax(1) if positive else offsets[..., axis].amin(1)
        xy = center.clone()
        xy[:, axis] = limit - extreme
        if bool((xy.abs() > 5.3).any()):
            raise ValueError('Cannot realize wheel crossing inside original root bounds')
        return xy

    records, narrow_records = [], []
    base.scene.update = sample_physics
    try:
        with torch.inference_mode():
            for side, sign in (('negative_y', -1.), ('positive_y', 1.)):
                env.reset()
                move_root(center, upright=True)
                measured = move_root(crossing_pose(side, sign * 1.25))
                narrow = boundary_sides(measured.reshape(-1, 4, 3)).reshape(-1, 2, 4)
                wide = boundary_sides(measured.reshape(-1, 4, 3), y_limit=WIDE_Y_LIMIT)
                index = SIDE_NAMES.index(side)
                terminal = base.termination_manager.get_term('rough_wheel_corridor')
                if (not bool(narrow[:, :, index].any(0).all()) or bool(wide.any())
                        or bool(terminal[ids].any()) or bool(tracker.corridor_failed[ids].any())
                        or bool(base.reset_terminated[ids].any()) or bool(base.reset_time_outs[ids].any())):
                    raise ValueError('Narrow crossing did not survive the wide corridor: ' + side)
                narrow_records.append(dict(side=side, actual_narrow_crossing=True,
                    maximum_abs_wheel_y_m=float(measured[..., 1].abs().max()),
                    wide_crossing=False, rough_terminal=False, flat_terminal=False))
            for side, limit in (('forward', X_MAX + .08), ('backward', X_MIN - .08),
                                ('negative_y', -WIDE_Y_LIMIT - .08), ('positive_y', WIDE_Y_LIMIT + .08)):
                env.reset()
                move_root(center, upright=True)
                tracker.expected[rough_id] = 2.
                tracker.progress[rough_id] = 2.
                before_episodes = tracker.total_episodes[family]
                before_successes = tracker.total_successes[family]
                index = SIDE_NAMES.index(side)
                before_side = tracker.corridor_side_counts[index]
                measured = move_root(crossing_pose(side, limit))
                crossed = boundary_sides(measured.reshape(-1, 4, 3), y_limit=WIDE_Y_LIMIT).reshape(-1, 2, 4)
                terminal = base.termination_manager.get_term('rough_wheel_corridor')
                if (not bool(crossed[:, :, index].any(0).all()) or not bool(terminal[rough_id])
                        or bool(terminal[flat_id]) or not bool(base.reset_terminated[rough_id])
                        or bool(base.reset_time_outs[rough_id]) or bool(tracker.corridor_failed[rough_id])
                        or bool(tracker.failed[rough_id]) or bool(tracker.corridor_failed[flat_id])
                        or tracker.corridor_side_counts[index] <= before_side
                        or tracker.total_episodes[family] != before_episodes + 1
                        or tracker.total_successes[family] != before_successes):
                    raise ValueError('Wide native terminal/reset/curriculum/Flat mask fixture failed: ' + side)
                records.append(dict(side=side, actual_wheel_crossing=True,
                    rough_terminal=True, flat_terminal=False, timed_out=False,
                    sticky_cleared_on_reset=True, curriculum_failed_episode_recorded=True,
                    curriculum_success_increment=0, injected_expected_m=2., injected_progress_m=2.))
            env.reset()
    finally:
        base.scene.update = previous_update
    return dict(passed=True, injected_rough_id=rough_id, injected_flat_id=flat_id,
        bounds=dict(x=[X_MIN, X_MAX], y=[-WIDE_Y_LIMIT, WIDE_Y_LIMIT]),
        narrow_lateral_crossings=narrow_records, sides=records, cadence_hz=200, policy_reset_hz=50,
        scope='Native physics/reset smoke; injected counters and smoke weights are discarded')
