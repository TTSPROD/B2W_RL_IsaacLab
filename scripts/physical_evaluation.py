"""Bounded, persistent physical variations for local Flat policy evaluation.

Importing this module does not initialize Kit. Configure a fresh evaluation
configuration AFTER _nominal_cfg and BEFORE gym.make; call physical_evidence
after the evaluator's explicit scene reset, and again after replay if desired.
These engineering ranges are not measured hardware tolerances.
"""
from __future__ import annotations

import hashlib
from typing import Any

PROFILES = ("nominal", "bounded_v1")
_EVENT_NAMES = ("physical_eval_material", "physical_eval_mass", "physical_eval_gains")
STATIC_FRICTION = (0.6, 1.0)
DYNAMIC_FRICTION = (0.5, 0.8)
SCALE_RANGE = (0.9, 1.1)


def profile_spec(profile: str) -> dict[str, Any]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown physical evaluation profile: {profile}")
    if profile == "nominal":
        return {"profile": profile, "randomized": False, "event_mode": None}
    return {
        "profile": profile, "randomized": True, "event_mode": "startup",
        "scope": "engineering robustness screen, not measured hardware tolerances",
        "material": {
            "asset": "robot", "bodies": "all", "num_buckets": 64,
            "static_friction_uniform": list(STATIC_FRICTION),
            "dynamic_friction_uniform_before_consistency_clamp": list(DYNAMIC_FRICTION),
            "dynamic_friction_transform": "min(sampled_dynamic, sampled_static)",
            "restitution": 0.0,
            "sampling": "64 material buckets sampled once, assigned per collision shape",
        },
        "mass": {
            "bodies": "all", "scale_uniform": list(SCALE_RANGE),
            "recompute_inertia": True, "sampling": "independent per environment and body",
        },
        "actuator_gains": {
            "joints": "all", "kp_scale_uniform": list(SCALE_RANGE),
            "kd_scale_uniform": list(SCALE_RANGE),
            "sampling": "independent per environment, joint and gain; zero gains stay zero",
        },
        "excluded": ["COM", "latency", "pushes", "observation_noise"],
    }


def configure_physical_evaluation(cfg, profile: str) -> dict[str, Any]:
    """Add only startup events; nominal is a strict no-op on cfg."""
    specification = profile_spec(profile)
    if profile == "nominal":
        return specification
    # A caller must disable training events first, otherwise ranges would compose
    # with upstream randomization or reset-time changes.
    active = [
        name for name, term in vars(cfg.events).items()
        if term is not None and hasattr(term, "mode")
    ]
    if active:
        raise ValueError(f"Call _nominal_cfg before physical evaluation; active events: {active}")
    from isaaclab.envs import mdp
    from isaaclab.managers import EventTermCfg, SceneEntityCfg

    cfg.events.physical_eval_material = EventTermCfg(
        func=mdp.randomize_rigid_body_material, mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "static_friction_range": STATIC_FRICTION,
            "dynamic_friction_range": DYNAMIC_FRICTION,
            "restitution_range": (0.0, 0.0),
            "num_buckets": 64, "make_consistent": True,
        },
    )
    cfg.events.physical_eval_mass = EventTermCfg(
        func=mdp.randomize_rigid_body_mass, mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "mass_distribution_params": SCALE_RANGE,
            "operation": "scale", "distribution": "uniform",
            "recompute_inertia": True,
        },
    )
    cfg.events.physical_eval_gains = EventTermCfg(
        func=mdp.randomize_actuator_gains, mode="startup",
        params={
            "asset_cfg": SceneEntityCfg("robot"),
            "stiffness_distribution_params": SCALE_RANGE,
            "damping_distribution_params": SCALE_RANGE,
            "operation": "scale", "distribution": "uniform",
        },
    )
    return specification


def physical_evidence(base) -> dict[str, Any]:
    """Read applied PhysX/actuator properties and fail closed on missing variation.

    Returns compact summaries, per-environment extrema, and complete samples for
    the first eight environments. The digest covers ALL measured environments,
    including inertia, so two calls can verify persistence through pose resets.
    Explicit PD gains must be read from actuator tensors, not PhysX drive gains.
    """
    import torch

    configured = [getattr(base.cfg.events, name, None) for name in _EVENT_NAMES]
    if any(term is not None for term in configured) and not all(term is not None for term in configured):
        raise RuntimeError("Incomplete bounded physical evaluation event set")
    profile = "bounded_v1" if all(term is not None for term in configured) else "nominal"
    robot = base.scene["robot"]

    def cpu(value, label):
        result = value.detach().to(device="cpu", dtype=torch.float64).contiguous()
        if result.numel() == 0 or not bool(torch.isfinite(result).all()):
            raise RuntimeError(f"Missing/non-finite physical property: {label}")
        return result

    materials = cpu(robot.root_physx_view.get_material_properties(), "materials")
    masses = cpu(robot.root_physx_view.get_masses(), "masses")
    defaults = cpu(robot.data.default_mass, "default masses")
    inertias = cpu(robot.root_physx_view.get_inertias(), "inertias")
    default_inertias = cpu(robot.data.default_inertia, "default inertias")
    if bool((defaults <= 0).any()) or bool((masses <= 0).any()):
        raise RuntimeError("Body masses must be positive")
    mass_ratios = masses / defaults
    default_kp = cpu(robot.data.default_joint_stiffness, "default Kp")
    default_kd = cpu(robot.data.default_joint_damping, "default Kd")
    kp = torch.full_like(default_kp, float("nan"))
    kd = torch.full_like(default_kd, float("nan"))
    covered = torch.zeros(default_kp.shape[1], dtype=torch.bool)
    for actuator in robot.actuators.values():
        indices = actuator.joint_indices
        if isinstance(indices, torch.Tensor):
            indices = indices.cpu()
        if bool(covered[indices].any()):
            raise RuntimeError("Overlapping actuator joint coverage")
        kp[:, indices] = cpu(actuator.stiffness, "actual actuator Kp")
        kd[:, indices] = cpu(actuator.damping, "actual actuator Kd")
        covered[indices] = True
    if not bool(covered.all()):
        raise RuntimeError("Missing actuator joint coverage")
    kp, kd = cpu(kp, "assembled Kp"), cpu(kd, "assembled Kd")
    if materials.ndim != 3 or materials.shape[0] != masses.shape[0] or materials.shape[2] != 3:
        raise RuntimeError(f"Unexpected PhysX material shape: {tuple(materials.shape)}")

    def check_range(values, limits, label):
        if bool(((values < limits[0] - 1e-6) | (values > limits[1] + 1e-6)).any()):
            raise RuntimeError(f"Applied {label} outside configured range {limits}")

    def gain_ratios(actual, default, label):
        if bool((default < 0).any()):
            raise RuntimeError(f"Negative default {label}")
        positive = default > 0
        if not bool(positive.any()):
            raise RuntimeError(f"No positive default {label} for variation evidence")
        if not bool((actual[~positive] == 0).all()):
            raise RuntimeError(f"Zero default {label} changed")
        # Null marks a zero default gain in serialized ratios.
        ratio = torch.ones_like(actual)
        ratio[positive] = actual[positive] / default[positive]
        return ratio, positive

    kp_ratios, kp_positive = gain_ratios(kp, default_kp, "Kp")
    kd_ratios, kd_positive = gain_ratios(kd, default_kd, "Kd")
    if profile == "bounded_v1":
        check_range(materials[:, :, 0], STATIC_FRICTION, "static friction")
        check_range(materials[:, :, 1], DYNAMIC_FRICTION, "dynamic friction")
        if bool((materials[:, :, 1] > materials[:, :, 0] + 1e-6).any()):
            raise RuntimeError("Dynamic friction exceeds static friction")
        if not bool((materials[:, :, 2].abs() <= 1e-6).all()):
            raise RuntimeError("Unexpected restitution")
        for values, label in (
            (mass_ratios, "mass scale"),
            (kp_ratios[kp_positive], "Kp scale"),
            (kd_ratios[kd_positive], "Kd scale"),
        ):
            check_range(values, SCALE_RANGE, label)
            if not bool(((values - 1.0).abs() > 1e-6).any()):
                raise RuntimeError(f"Configured {label} variation was not applied")
        if float(materials[:, :, 0].max() - materials[:, :, 0].min()) <= 1e-6:
            raise RuntimeError("Configured material variation was not applied")
        if not torch.allclose(inertias, default_inertias * mass_ratios[..., None], rtol=1e-5, atol=1e-7):
            raise RuntimeError("Inertia does not match applied mass scaling")

    def stats(values):
        return {"min": float(values.min()), "max": float(values.max()), "mean": float(values.mean())}

    digest = hashlib.sha256()
    for label, values in (("materials", materials), ("masses", masses), ("inertia", inertias), ("kp", kp), ("kd", kd)):
        digest.update(f"{label}:{tuple(values.shape)}:float64".encode("ascii"))
        digest.update(values.numpy().tobytes())
    n = masses.shape[0]
    per_environment = []
    for i in range(n):
        per_environment.append({
            "env": i, "total_mass_kg": float(masses[i].sum()),
            "total_mass_ratio": float(masses[i].sum() / defaults[i].sum()),
            "body_mass_scale": stats(mass_ratios[i]),
            "static_friction": stats(materials[i, :, 0]),
            "dynamic_friction": stats(materials[i, :, 1]),
            "kp_scale_nonzero": stats(kp_ratios[i][kp_positive[i]]),
            "kd_scale_nonzero": stats(kd_ratios[i][kd_positive[i]]),
        })
    samples = []
    for i in range(min(n, 8)):
        samples.append({
            "env": i, "materials_static_dynamic_restitution": materials[i].tolist(),
            "body_mass_kg": masses[i].tolist(), "body_mass_scale": mass_ratios[i].tolist(),
            "body_inertia_kg_m2_flat9": inertias[i].tolist(),
            "joint_kp": kp[i].tolist(), "joint_kd": kd[i].tolist(),
            "joint_kp_scale": [float(r) if bool(p) else None for r, p in zip(kp_ratios[i], kp_positive[i])],
            "joint_kd_scale": [float(r) if bool(p) else None for r, p in zip(kd_ratios[i], kd_positive[i])],
        })
    return {
        "profile": profile, "applied_properties_verified": True,
        "variation_applied_verified": profile == "bounded_v1",
        "properties_sha256": digest.hexdigest(), "num_envs": n,
        "environment_seed": getattr(base.cfg, "seed", None),
        "rng_contract": "cfg.seed seeds torch before scene/event construction; command cases use separate Python Random; policy loads after startup",
        "default_properties_env0": {
            "body_mass_kg": defaults[0].tolist(),
            "body_inertia_kg_m2_flat9": default_inertias[0].tolist(),
            "joint_kp": default_kp[0].tolist(), "joint_kd": default_kd[0].tolist(),
        },
        "readback": "PhysX materials/masses/inertias; actuator model Kp/Kd",
        "body_names": list(robot.body_names), "joint_names": list(robot.joint_names),
        "material_columns": ["static_friction", "dynamic_friction", "restitution"],
        "mass_scale": stats(mass_ratios),
        "kp_scale_nonzero": stats(kp_ratios[kp_positive]),
        "kd_scale_nonzero": stats(kd_ratios[kd_positive]),
        "static_friction": stats(materials[:, :, 0]),
        "dynamic_friction": stats(materials[:, :, 1]),
        "per_environment": per_environment, "first_environment_samples": samples,
        "zero_default_kp_count": int((~kp_positive).sum()),
        "zero_default_kd_count": int((~kd_positive).sum()),
    }
