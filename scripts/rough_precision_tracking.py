"""One registered reward-width experiment; upstream functions remain immutable."""
from types import SimpleNamespace

SOURCE_STD = .5
PRECISION_STD = .25
TERMS = {'track_lin_vel_xy_exp': 3., 'track_ang_vel_z_exp': 1.5}


def _check_term(term, name, std):
    if (term is None or term.weight != TERMS[name] or term.params.get('std') != std
            or getattr(term.func, '__name__', None) != name
            or term.params.get('command_name') != 'base_velocity'):
        raise ValueError('Unexpected tracking term: ' + name)


def configure_precision_tracking(cfg):
    # Validate both before mutating either: a partially changed recipe is invalid.
    for name in TERMS:
        _check_term(getattr(cfg.rewards, name, None), name, SOURCE_STD)
    for name in TERMS:
        getattr(cfg.rewards, name).params['std'] = PRECISION_STD
    return dict(source_std=SOURCE_STD, tracking_std=PRECISION_STD, weights=dict(TERMS),
                scope='All Flat and Rough training tiles; evaluation is unchanged',
                actor_observations=57, hypothesis='Higher sensitivity to small velocity errors')


def precision_tracking_fixture(env):
    """Check native reward functions on live and synthetic CUDA tensors without state writes."""
    import torch
    raw = env.unwrapped
    errors = torch.tensor([0., .05, .25, -.25, 1.], device=raw.device)
    data = SimpleNamespace(root_lin_vel_b=torch.zeros((5, 3), device=raw.device),
                           root_ang_vel_b=torch.zeros((5, 3), device=raw.device),
                           projected_gravity_b=torch.tensor([[0., 0., -1.]] * 5, device=raw.device))
    data.root_lin_vel_b[:, 0] = errors
    data.root_lin_vel_b[:, 1] = errors * .5
    data.root_ang_vel_b[:, 2] = errors
    # Include partial and zero upright factors, preserving the upstream semantics.
    data.projected_gravity_b[-2:, 2] = torch.tensor([-.35, .2], device=raw.device)
    synthetic = SimpleNamespace(scene={'robot': SimpleNamespace(data=data)},
        command_manager=SimpleNamespace(get_command=lambda name: torch.zeros((5, 3), device=raw.device)))
    results = {}
    for name in TERMS:
        term = raw.reward_manager.get_term_cfg(name)
        _check_term(term, name, PRECISION_STD)
        largest = 0.
        for tested in (synthetic, raw):
            robot = tested.scene['robot'].data
            command = tested.command_manager.get_command('base_velocity')
            if name == 'track_lin_vel_xy_exp':
                square_error = ((command[:, :2] - robot.root_lin_vel_b[:, :2]) ** 2).sum(dim=1)
            else:
                square_error = (command[:, 2] - robot.root_ang_vel_b[:, 2]) ** 2
            expected = torch.exp(-square_error / PRECISION_STD**2)
            expected *= torch.clamp(-robot.projected_gravity_b[:, 2], 0., .7) / .7
            actual = term.func(tested, **term.params)
            if actual.device.type != 'cuda' or not torch.isfinite(actual).all():
                raise ValueError('Native reward must return finite CUDA values')
            deviation = float((actual - expected).abs().max())
            if deviation > 1e-6:
                raise ValueError('Native precision reward formula mismatch: ' + name)
            largest = max(largest, deviation)
        results[name] = dict(std=term.params['std'], weight=term.weight, max_abs_error=largest)
    return dict(passed=True, native_terms=results, synthetic_cases=5,
                live_cases=raw.num_envs, simulator_state_modified=False)
