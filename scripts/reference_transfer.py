"""Strict actor-only transfer from the pinned B2W TorchScript reference.

This module does not modify PPO, its optimizer, observations, rewards or physics.
The caller owns the training schedule and must not reinitialize an adapted actor
on resume. Reference parity proves import correctness, not policy acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path

import torch
from torch import nn


ACTOR_SHAPES = {
    "0.weight": (512, 57), "0.bias": (512,),
    "2.weight": (256, 512), "2.bias": (256,),
    "4.weight": (128, 256), "4.bias": (128,),
    "6.weight": (16, 128), "6.bias": (16,),
}
LAYERS = ("Linear", "ELU", "Linear", "ELU", "Linear", "ELU", "Linear")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _module_name(module):
    return getattr(module, "original_name", type(module).__name__)


def _check_actor(actor):
    _require(list(actor._modules.keys()) == [str(i) for i in range(7)], "Unexpected actor module layout")
    for index, expected in enumerate(LAYERS):
        module = actor._modules[str(index)]
        _require(_module_name(module) == expected, f"Actor layer {index} must be {expected}")
        if expected == "ELU":
            _require(float(module.alpha) == 1.0, "Actor ELU alpha must equal 1")
    state = actor.state_dict()
    _require(set(state) == set(ACTOR_SHAPES), "Unexpected actor state keys")
    for key, shape in ACTOR_SHAPES.items():
        value = state[key]
        _require(tuple(value.shape) == shape, f"Unexpected actor shape: {key}")
        _require(value.dtype == torch.float32, f"Actor tensor must be float32: {key}")
        _require(bool(torch.isfinite(value).all()), f"Non-finite actor tensor: {key}")


def _check_policy(policy):
    _require(not getattr(policy, "state_dependent_std", False), "State-dependent std is unsupported")
    _require(getattr(policy, "noise_std_type", "scalar") == "scalar", "Scalar std parameter required")
    _require(isinstance(policy.actor_obs_normalizer, nn.Identity), "Policy normalizer must be Identity")
    _require(not getattr(policy, "actor_obs_normalization", False), "Actor observation normalization must be disabled")
    _require(policy.obs_groups.get("policy") == ["policy"], "Actor observation group must be policy only")
    _require(isinstance(getattr(policy, "std", None), nn.Parameter), "Policy std parameter is missing")
    _require(tuple(policy.std.shape) == (16,), "Expected 16 scalar action standard deviations")
    _require(bool(torch.isfinite(policy.std).all()), "Non-finite action standard deviations")
    _check_actor(policy.actor)


def _actor_observations(policy, observations):
    inputs = policy.get_actor_obs(observations)
    _require(inputs.ndim == 2 and inputs.shape[1] == 57 and inputs.shape[0] > 0,
             "Actor observations must have nonempty shape [N,57]")
    _require(inputs.dtype == torch.float32, "Actor observations must be float32")
    _require(bool(torch.isfinite(inputs).all()), "Non-finite actor observations")
    return inputs


def reference_probes():
    """295 deterministic synthetic ABI probes; not physical evaluation cases."""
    neutral = torch.zeros(1, 57)
    neutral[:, 5] = -1.
    basis = torch.eye(57) * .25
    generator = torch.Generator(device="cpu").manual_seed(73052)
    random = torch.randn(180, 57, generator=generator).clamp(-5., 5.)
    return torch.cat((neutral, neutral + basis, neutral - basis, random))


def load_reference_teacher(path, device="cpu"):
    """Load and validate the immutable actor without touching a training policy."""
    path = Path(path).resolve()
    _require(path.is_file(), f"Reference policy is missing: {path}")
    teacher = torch.jit.load(str(path), map_location=device).eval()
    _require(hasattr(teacher, "normalizer") and _module_name(teacher.normalizer) == "Identity",
             "Reference normalizer must be Identity")
    _require(not list(teacher.normalizer.state_dict()), "Reference Identity has unexpected state")
    _check_actor(teacher.actor)
    _require(set(teacher.state_dict()) == {"actor." + key for key in ACTOR_SHAPES},
             "Unexpected reference state keys")
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)
    with torch.no_grad():
        probes = reference_probes().to(device)
        output = teacher(probes)
        _require(tuple(output.shape) == (295, 16) and bool(torch.isfinite(output).all()),
                 "Reference output must be finite [295,16]")
        _require(torch.equal(teacher.normalizer(probes), probes), "Reference normalizer changes inputs")
        _require(torch.allclose(output, teacher.actor(probes), atol=1e-5, rtol=1e-5),
                 "Reference forward differs from actor-only forward")
    return teacher


def set_actor_trainable(policy, trainable: bool, fixed_std: float = .1):
    """Toggle actor burn-in; validate fixed exploration and leave critic alone."""
    _require(math.isfinite(fixed_std) and fixed_std > 0., "fixed_std must be finite and positive")
    _check_policy(policy)
    _require(torch.equal(policy.std.detach(), torch.full_like(policy.std, fixed_std)),
             "Action std differs from the registered fixed exploration level")
    for parameter in policy.actor.parameters():
        parameter.requires_grad_(bool(trainable))
        if not trainable:
            parameter.grad = None
    policy.std.requires_grad_(False)
    policy.std.grad = None


@torch.no_grad()
def measure_reference_drift(policy, teacher, observations):
    """Compare deterministic means on identical actual policy inputs.

    Gaussian KL uses the current scalar std for both distributions. Target RMS
    scales raw mean differences; it does not measure resulting robot motion.
    """
    inputs = _actor_observations(policy, observations)
    expected = teacher(inputs)
    actual = policy.act_inference(observations)
    _require(tuple(actual.shape) == (inputs.shape[0], 16), "Unexpected actor output shape")
    _require(tuple(expected.shape) == tuple(actual.shape), "Unexpected reference output shape")
    _require(bool(torch.isfinite(actual).all() and torch.isfinite(expected).all()), "Non-finite action means")
    _require(bool(torch.isfinite(policy.std).all() and (policy.std > 0).all()), "Invalid fixed action std")
    delta = actual - expected
    scales = delta.new_tensor([.125, .25, .25] * 4 + [5.] * 4)
    target_delta = delta * scales
    return {
        "sample_count": int(inputs.shape[0]),
        "raw_action_rms": float(delta.square().mean().sqrt()),
        "raw_action_max_abs": float(delta.abs().max()),
        "mean_gaussian_kl": float((.5 * (delta / policy.std).square().sum(-1)).mean()),
        "leg_target_rms_rad": float(target_delta[:, :12].square().mean().sqrt()),
        "wheel_target_rms_rad_s": float(target_delta[:, 12:].square().mean().sqrt()),
        "scope": "Same observations, deterministic means; target deltas before physical target clipping",
    }


def initialize_reference(policy, path, observations, fixed_std: float = .1):
    """Copy only actor parameters, freeze actor/std and return teacher, metadata.

    Requires a fresh optimizer supplied by the caller. Critic weights and flags
    are preserved. Do not call after loading an adaptation checkpoint on resume.
    """
    _check_policy(policy)
    inputs = _actor_observations(policy, observations)
    _require(math.isfinite(fixed_std) and fixed_std > 0., "fixed_std must be finite and positive")
    device = next(policy.actor.parameters()).device
    _require(inputs.device == device, "Actor and observations must be on the same device")
    teacher = load_reference_teacher(path, device)
    policy.actor.load_state_dict(teacher.actor.state_dict(), strict=True)
    with torch.no_grad():
        policy.std.fill_(fixed_std)
    set_actor_trainable(policy, False, fixed_std)
    # CPU parity validates the copied network independently of GPU math settings.
    cpu_actor = copy.deepcopy(policy.actor).cpu().eval()
    cpu_teacher = load_reference_teacher(path, "cpu")
    probes = reference_probes()
    with torch.no_grad():
        expected = cpu_teacher(probes)
        cpu_output = cpu_actor(probes)
        cpu_error = float((cpu_output - expected).abs().max())
        _require(torch.allclose(cpu_output, expected, atol=1e-5, rtol=1e-5), "CPU reference import parity failed")
        # Use full precision for cross-device verification, then restore training.
        saved_tf32 = torch.backends.cuda.matmul.allow_tf32
        try:
            torch.backends.cuda.matmul.allow_tf32 = False
            device_output = policy.actor(probes.to(device)).cpu()
        finally:
            torch.backends.cuda.matmul.allow_tf32 = saved_tf32
        device_error = float((device_output - expected).abs().max())
        _require(torch.allclose(device_output, expected, atol=1e-4, rtol=1e-4),
                 "Cross-device reference import parity failed")
        drift = measure_reference_drift(policy, teacher, observations)
        _require(drift["raw_action_max_abs"] <= 1e-4, "Live reference import parity failed")
    metadata = {
        "reference_path": str(Path(path).resolve()),
        "reference_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "actor_observations": 57, "actions": 16,
        "hidden_dims": [512, 256, 128], "activation": "elu",
        "normalizer": "Identity", "copied_state_keys": ["actor." + key for key in ACTOR_SHAPES],
        "critic_initialization": "unchanged fresh critic; caller controls burn-in",
        "optimizer_initialization": "caller must provide fresh optimizer",
        "fixed_std": fixed_std, "actor_initially_frozen": True,
        "parity_probe_count": 295, "cpu_max_abs_error": cpu_error,
        "device": str(device), "cross_device_max_abs_error": device_error,
        "cross_device_tf32": False, "live_import_drift": drift,
        "policy_quality_evaluated": False,
    }
    return teacher, metadata

def apply_flat_upright_reset(env_cfg):
    """Change only roll/pitch reset orientation for the explicit Flat curriculum."""
    params = env_cfg.events.randomize_reset_base.params
    pose = params["pose_range"]
    before = copy.deepcopy(pose)
    for key in ("roll", "pitch"):
        _require(tuple(pose[key]) == (-3.14, 3.14), "Expected pinned recovery reset range")
    pose["roll"] = (-.1, .1)
    pose["pitch"] = (-.1, .1)
    return {"before_pose_range": before, "after_pose_range": copy.deepcopy(pose),
            "changed_fields": ["events.randomize_reset_base.params.pose_range.roll",
                               "events.randomize_reset_base.params.pose_range.pitch"],
            "scope": "Flat upright-start curriculum; no recovery capability qualification"}
