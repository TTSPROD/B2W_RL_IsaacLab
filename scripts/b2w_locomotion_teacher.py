"""Simulation-only velocity teacher; a separate 247 -> 16 observation ABI.

The frozen Flat actor can initialize the first 57 inputs exactly. Clean body
velocity and terrain heights are appended, not inserted into the Flat ABI.
This teacher is not a blind-policy export or authorization for robot actuation.
Isaac imports are delayed until a running SimulationApp calls the factory.
"""
from __future__ import annotations

import copy
import math


TEACHER_LAYOUT = (
    ("base_ang_vel", 3), ("projected_gravity", 3), ("velocity_commands", 3),
    ("joint_pos", 16), ("joint_vel", 16), ("actions", 16),
    ("base_lin_vel", 3), ("height_scan", 187),
)
BLIND_DIM = 57
TEACHER_DIM = 247
ACTION_DIM = 16
MIXED_PROPORTIONS = {
    "flat": .30, "random_rough": .20, "slope_up": .10, "slope_down": .10,
    "pyramid_stairs": .15, "pyramid_stairs_inv": .15,
}


def observation_layout():
    """Return serializable ordered slices, including the 16 wheel-masked positions."""
    offset = 0
    result = []
    for name, width in TEACHER_LAYOUT:
        result.append({"name": name, "start": offset, "stop": offset + width})
        offset += width
    return result


def _teacher_observations(cfg):
    from isaaclab.managers import ObservationGroupCfg
    from isaaclab.utils import configclass

    original = cfg.observations.policy
    privileged = cfg.observations.critic

    # A new class is essential: restoring an inherited base_lin_vel attribute
    # would put it BEFORE the Flat terms and silently invalidate actor lifting.
    @configclass
    class TeacherPolicyCfg(ObservationGroupCfg):
        base_ang_vel = copy.deepcopy(original.base_ang_vel)
        projected_gravity = copy.deepcopy(original.projected_gravity)
        velocity_commands = copy.deepcopy(original.velocity_commands)
        joint_pos = copy.deepcopy(original.joint_pos)
        joint_vel = copy.deepcopy(original.joint_vel)
        actions = copy.deepcopy(original.actions)
        base_lin_vel = copy.deepcopy(privileged.base_lin_vel)
        height_scan = copy.deepcopy(privileged.height_scan)

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True
            self.base_lin_vel.scale = 2.0
            self.base_lin_vel.noise = None
            self.height_scan.noise = None

    @configclass
    class TeacherObservationsCfg:
        policy: TeacherPolicyCfg = TeacherPolicyCfg()
        critic: TeacherPolicyCfg = TeacherPolicyCfg()

        def __post_init__(self):
            self.critic.enable_corruption = False

    return TeacherObservationsCfg()


def build_teacher_terrain_cfg():
    """Mixed training terrain; broad native stairs are not a straight-march exam.

    Six ascending difficulty rows, twenty columns. The native height-field
    random rough generator samples the configured noise range at every row;
    unlike stairs/slopes, that native family does not scale with difficulty.
    """
    import isaaclab.terrains as terrain
    from b2w_rough_runtime import GEOMETRY_SEED
    from b2w_runtime import PROJECT_ROOT

    stairs = dict(step_height_range=(.05, .18), step_width=.35,
                  platform_width=3., border_width=1., holes=False)
    return terrain.TerrainGeneratorCfg(
        seed=GEOMETRY_SEED, curriculum=True, size=(12., 12.),
        num_rows=6, num_cols=20, border_width=10., horizontal_scale=.1,
        vertical_scale=.005, slope_threshold=.75, use_cache=False,
        cache_dir=str(PROJECT_ROOT / ".cache/teacher_terrains"),
        sub_terrains={
            "flat": terrain.MeshPlaneTerrainCfg(proportion=.30),
            "random_rough": terrain.HfRandomUniformTerrainCfg(
                proportion=.20, noise_range=(.01, .04), noise_step=.01,
                border_width=.25),
            "slope_up": terrain.HfPyramidSlopedTerrainCfg(
                proportion=.10, slope_range=(0., .25), platform_width=3., border_width=.25),
            "slope_down": terrain.HfInvertedPyramidSlopedTerrainCfg(
                proportion=.10, slope_range=(0., .25), platform_width=3., border_width=.25),
            "pyramid_stairs": terrain.MeshPyramidStairsTerrainCfg(proportion=.15, **stairs),
            "pyramid_stairs_inv": terrain.MeshInvertedPyramidStairsTerrainCfg(proportion=.15, **stairs),
        },
    )


def tile_boundary_timeout(env):
    """Truncate after the root crosses its tile; no corridor or route target.

    The boundary is at half tile size, not inside it. At every crossing the
    radial distance already exceeds the native terrain promotion threshold.
    """
    import torch

    size = env.scene.terrain.cfg.terrain_generator.size
    relative = env.scene["robot"].data.root_pos_w[:, :2] - env.scene.env_origins[:, :2]
    half_size = relative.new_tensor(size) * .5
    return torch.any(relative.abs() > half_size, dim=1)


def failure_aware_terrain_levels_vel(env, env_ids):
    """Native distance curriculum rule with a true-termination failure mask.

    Adapted from pinned Isaac Lab v2.3.2 locomotion/mdp/curriculums.py
    (BSD-3-Clause). A contact/tilt failure cannot promote even beyond half a
    tile. Time/tile truncations retain the native distance decision. This is
    a training curriculum signal, not the route acceptance criterion.
    """
    import torch

    terrain = env.scene.terrain
    ids = torch.as_tensor(env_ids, device=env.device, dtype=torch.long)
    # Initial reset has no trajectory and must not run a promotion/demotion.
    if ids.numel() == 0 or env.common_step_counter == 0:
        return terrain.terrain_levels.float().mean()
    distance = torch.linalg.vector_norm(
        env.scene["robot"].data.root_pos_w[ids, :2] - env.scene.env_origins[ids, :2], dim=1)
    failed = env.termination_manager.terminated[ids]
    command = env.command_manager.get_command("base_velocity")[ids, :2]
    move_up = (distance > terrain.cfg.terrain_generator.size[0] * .5) & ~failed
    short = distance < torch.linalg.vector_norm(command, dim=1) * env.max_episode_length_s * .5
    move_down = (short | failed) & ~move_up
    terrain.update_env_origins(ids, move_up, move_down)
    return terrain.terrain_levels.float().mean()


def make_teacher_env_cfg(*, num_envs, device, seed, headless=True,
                         curriculum=False, terrain_profile="diagnostic"):
    """Construct an isolated teacher config; diagnostic probes stay on level 0.

    ``mixed`` must be selected explicitly after the diagnostic pilot. Selecting
    ``curriculum=True`` enables the distance adapter only for the mixed terrain.
    Neither profile changes B2W action order/scales, actuators or reward weights.
    """
    if terrain_profile not in {"diagnostic", "mixed"}:
        raise ValueError("terrain_profile must be diagnostic or mixed")
    if curriculum and terrain_profile != "mixed":
        raise ValueError("Diagnostic pilot must remain fixed at terrain level 0")

    from isaaclab.envs import mdp
    from isaaclab.managers import CurriculumTermCfg, SceneEntityCfg, TerminationTermCfg
    from b2w_rough_runtime import make_rough_env_cfg

    cfg = make_rough_env_cfg(num_envs=num_envs, device=device, seed=seed, headless=headless)
    cfg.observations = _teacher_observations(cfg)
    # Retain every physics substep until the policy-step termination check.
    cfg.scene.contact_forces.history_length = max(cfg.scene.contact_forces.history_length, cfg.decimation)
    if terrain_profile == "mixed":
        cfg.scene.terrain.terrain_generator = build_teacher_terrain_cfg()
    cfg.scene.terrain.max_init_terrain_level = 0
    cfg.curriculum.terrain_levels = (
        CurriculumTermCfg(func=failure_aware_terrain_levels_vel) if curriculum else None)
    cfg.commands.base_velocity = mdp.UniformVelocityCommandCfg(
        asset_name="robot", resampling_time_range=(10., 10.),
        rel_standing_envs=.1, rel_heading_envs=1., heading_command=True,
        heading_control_stiffness=.5, debug_vis=False,
        ranges=mdp.UniformVelocityCommandCfg.Ranges(
            lin_vel_x=(-.6, .6), lin_vel_y=(-.2, .2), ang_vel_z=(-.6, .6),
            heading=(-math.pi, math.pi)),
    )
    reset = cfg.events.randomize_reset_base.params
    reset["pose_range"].update(z=(0., 0.), roll=(-.1, .1), pitch=(-.1, .1),
                               yaw=(-math.pi, math.pi))
    reset["velocity_range"] = {axis: (0., 0.) for axis in ("x", "y", "z", "roll", "pitch", "yaw")}
    cfg.events.randomize_apply_external_force_torque = None
    cfg.events.randomize_push_robot = None
    cfg.terminations.illegal_contact = TerminationTermCfg(
        func=mdp.illegal_contact, time_out=False,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names=["^(?!.*_foot$).*"]),
                "threshold": 1.0})
    cfg.terminations.bad_orientation = TerminationTermCfg(
        func=mdp.bad_orientation, time_out=False, params={"limit_angle": math.pi / 3})
    cfg.terminations.terrain_out_of_bounds = TerminationTermCfg(
        func=tile_boundary_timeout, time_out=True)
    return cfg


def _check_actor(actor, input_dim):
    import torch

    layers = ("Linear", "ELU", "Linear", "ELU", "Linear", "ELU", "Linear")
    if list(actor._modules.keys()) != [str(i) for i in range(7)]:
        raise ValueError("Expected sequential actor Linear/ELU [512,256,128] -> 16")
    for index, expected in enumerate(layers):
        layer = actor._modules[str(index)]
        actual = getattr(layer, "original_name", type(layer).__name__)
        if actual != expected or (expected == "ELU" and layer.alpha != 1.):
            raise ValueError(f"Unexpected actor activation/layer at {index}")
    widths = (input_dim, 512, 256, 128, ACTION_DIM)
    shapes = {}
    for index, (before, after) in enumerate(zip(widths[:-1], widths[1:])):
        shapes[f"{index * 2}.weight"] = (after, before)
        shapes[f"{index * 2}.bias"] = (after,)
    state = actor.state_dict()
    if set(state) != set(shapes):
        raise ValueError("Unexpected actor parameter names")
    for key, shape in shapes.items():
        value = state[key]
        if tuple(value.shape) != shape or value.dtype != torch.float32 or not torch.isfinite(value).all():
            raise ValueError(f"Invalid actor tensor: {key}")


def lift_flat_actor(target_actor, source_actor):
    """Copy 57-input Flat actor into 247-input teacher with zero new columns.

    Copies only actor weights; preserves caller's trainability flags. The new
    columns are ordinary trainable weights with nonzero gradients when unfrozen.
    Weight equality is exact; forward parity allows float32 GEMM rounding.
    """
    import torch
    from reference_transfer import reference_probes

    _check_actor(source_actor, BLIND_DIM)
    _check_actor(target_actor, TEACHER_DIM)
    source_state = source_actor.state_dict()
    target_state = target_actor.state_dict()
    with torch.no_grad():
        for name, target in target_state.items():
            if name == "0.weight":
                target.zero_()
                target[:, :BLIND_DIM].copy_(source_state[name])
            else:
                target.copy_(source_state[name])

    source_cpu = copy.deepcopy(source_actor).cpu().eval()
    target_cpu = copy.deepcopy(target_actor).cpu().eval()
    probes = reference_probes()
    generator = torch.Generator(device="cpu").manual_seed(24757)
    extras = torch.randn(len(probes), TEACHER_DIM - BLIND_DIM, generator=generator)
    with torch.no_grad():
        expected = source_cpu(probes)
        actual = target_cpu(torch.cat((probes, extras), dim=1))
        delta = float((actual - expected).abs().max())
        zero_columns = bool((target_cpu.state_dict()["0.weight"][:, BLIND_DIM:] == 0).all())
        exact_prefix = torch.equal(target_cpu.state_dict()["0.weight"][:, :BLIND_DIM],
                                   source_cpu.state_dict()["0.weight"])
    if not zero_columns or not exact_prefix or not torch.isfinite(actual).all() or delta > 1e-6:
        raise ValueError(f"Flat -> teacher actor lift parity failed: {delta}")
    return {"source_dim": BLIND_DIM, "target_dim": TEACHER_DIM, "actions": ACTION_DIM,
            "cpu_max_abs_error": delta, "tolerance": 1e-6, "parity_probe_count": len(probes),
            "first_layer_prefix_exact": exact_prefix, "new_columns_zero": zero_columns,
            "policy_quality_evaluated": False, "simulation_only": True}


def validate_teacher_environment(env, expected_level=0):
    """Check resolved manager terms, clean privileged suffix and B2W action ABI.

    Call after reset. Returns measured runtime fixtures for the launch manifest;
    this does not certify terrain quality or policy success.
    """
    import torch
    from smoke_b2w import _gpu_evidence

    base = env.unwrapped
    robot = base.scene["robot"]
    terrain = base.scene.terrain
    scanner = base.scene["height_scanner"]
    manager = base.observation_manager
    obs = manager.compute()
    names = [name for name, _ in TEACHER_LAYOUT]
    dims = [(width,) for _, width in TEACHER_LAYOUT]
    for group in ("policy", "critic"):
        if manager.active_terms[group] != names or manager.group_obs_term_dim[group] != dims:
            raise ValueError(f"Teacher {group} observation order/dimensions differ from declared ABI")
        if tuple(obs[group].shape) != (base.num_envs, TEACHER_DIM) or not torch.isfinite(obs[group]).all():
            raise ValueError(f"Invalid teacher {group} observations")
    expected_velocity = robot.data.root_lin_vel_b.clamp(-100., 100.) * 2.
    velocity_error = float((obs["policy"][:, 57:60] - expected_velocity).abs().max())
    suffix_error = float((obs["policy"][:, 57:] - obs["critic"][:, 57:]).abs().max())
    if velocity_error > 1e-6 or suffix_error > 1e-6:
        raise ValueError("Teacher privileged suffix is noisy, reordered or incorrectly scaled")
    if scanner.data.ray_hits_w.shape[1] != 187 or not torch.isfinite(scanner.data.ray_hits_w).all():
        raise ValueError("Teacher needs 187 finite terrain rays")
    if expected_level is not None and not (terrain.terrain_levels == expected_level).all():
        raise ValueError("Unexpected initial teacher terrain level")
    actions = base.action_manager
    if actions.active_terms != ["joint_pos", "joint_vel"] or actions.total_action_dim != ACTION_DIM:
        raise ValueError("Teacher B2W action ABI differs")
    actual_joint_names = []
    actual_scales = []
    for name in actions.active_terms:
        term = actions.get_term(name)
        actual_joint_names.extend(term._joint_names)
        scale = term._scale
        actual_scales.extend(scale[0].detach().cpu().tolist() if isinstance(scale, torch.Tensor)
                             else [float(scale)] * term.action_dim)
    if actual_joint_names != base.cfg.joint_names or actual_scales != [.125, .25, .25] * 4 + [5.] * 4:
        raise ValueError("Teacher changed B2W joint order/action scales")
    if base.cfg.scene.contact_forces.history_length < base.cfg.decimation:
        raise ValueError("Contact history must retain every policy interval physics substep")
    termination = base.termination_manager
    if set(termination.active_terms) != {"time_out", "terrain_out_of_bounds", "illegal_contact", "bad_orientation"}:
        raise ValueError("Unexpected teacher termination terms")
    contact = termination.get_term_cfg("illegal_contact")
    sensor_cfg = contact.params["sensor_cfg"]
    contact_names = base.scene["contact_forces"].body_names
    selected = [contact_names[index] for index in sensor_cfg.body_ids]
    nonwheel = [name for name in contact_names if not name.endswith("_foot")]
    if set(selected) != set(nonwheel) or contact.time_out or contact.params["threshold"] != 1.:
        raise ValueError("Non-wheel contact failure contract differs")
    if not termination.get_term_cfg("terrain_out_of_bounds").time_out:
        raise ValueError("Tile boundary must be a timeout for PPO bootstrapping")
    return {
        "actor": TEACHER_DIM, "critic": TEACHER_DIM, "actions": ACTION_DIM,
        "layout": observation_layout(), "height_rays": 187,
        "velocity_suffix_max_error": velocity_error, "clean_suffix_max_error": suffix_error,
        "action_joint_names": actual_joint_names, "action_scales": actual_scales,
        "contact_failure_bodies": selected, "contact_history_length": base.cfg.scene.contact_forces.history_length, "termination_terms": termination.active_terms,
        "terrain_levels": terrain.terrain_levels.tolist(), "terrain_types": terrain.terrain_types.tolist(),
        "terrain_families": list(terrain.cfg.terrain_generator.sub_terrains),
        "physics": _gpu_evidence(base, robot, torch),
        "simulation_only": True, "policy_quality_evaluated": False,
    }
