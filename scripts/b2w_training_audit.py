"""Compare the installed upstream task with the saved 19999 training configuration."""
import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def differences(left, right, path=""):
    if isinstance(left, dict) and isinstance(right, dict):
        out = []
        for key in sorted(left.keys() | right.keys()):
            out.extend(differences(left.get(key), right.get(key), f"{path}.{key}".strip(".")))
        return out
    return [] if left == right else [{"path": path, "saved": left, "current": right}]


def audit_upstream(env_cfg, agent_cfg):
    from isaaclab.utils.io import dump_yaml
    from isaaclab.terrains import HfTerrainBaseCfg

    # The saved env.yaml is dumped AFTER TerrainGenerator has propagated these
    # parent settings into each sub-config. Mirror that deterministic resolution.
    generator = env_cfg.scene.terrain.terrain_generator
    for sub in generator.sub_terrains.values():
        sub.size = generator.size
        if isinstance(sub, HfTerrainBaseCfg):
            sub.horizontal_scale = generator.horizontal_scale
            sub.vertical_scale = generator.vertical_scale
            sub.slope_threshold = generator.slope_threshold

    destination = ROOT / ".cache/training-audit"
    destination.mkdir(parents=True, exist_ok=True)
    dump_yaml(str(destination / "upstream_env.yaml"), env_cfg)
    dump_yaml(str(destination / "upstream_agent.yaml"), agent_cfg)
    parent = ROOT / "policies/server/upstream_19999"
    saved = yaml.load((parent / "env.yaml").read_text(), Loader=yaml.BaseLoader)
    current = yaml.load((destination / "upstream_env.yaml").read_text(), Loader=yaml.BaseLoader)
    changes = []
    sections = ["observations", "actions", "events", "rewards", "terminations", "curriculum"]
    for section in sections:
        changes.extend(differences(saved[section], current[section], section))
    for section in ("actuators", "init_state"):
        changes.extend(differences(saved["scene"]["robot"][section], current["scene"]["robot"][section], f"robot.{section}"))
    for section in ("rigid_props", "articulation_props", "fix_base", "merge_fixed_joints"):
        changes.extend(differences(saved["scene"]["robot"]["spawn"].get(section), current["scene"]["robot"]["spawn"].get(section), f"spawn.{section}"))
    for key in ("dt", "physx", "gravity", "physics_material"):
        changes.extend(differences(saved["sim"][key], current["sim"][key], f"sim.{key}"))
    for key in ("decimation", "episode_length_s"):
        changes.extend(differences(saved[key], current[key], key))
    changes.extend(differences(saved["scene"]["terrain"]["terrain_generator"], current["scene"]["terrain"]["terrain_generator"], "terrain_generator"))
    saved_cmd, current_cmd = (cfg["commands"]["base_velocity"] for cfg in (saved, current))
    for key in ("class_type", "ranges", "heading_command", "heading_control_stiffness", "rel_heading_envs", "rel_standing_envs", "resampling_time_range"):
        changes.extend(differences(saved_cmd[key], current_cmd[key], f"commands.{key}"))
    saved_agent = yaml.load((parent / "agent.yaml").read_text(), Loader=yaml.BaseLoader)
    current_agent = yaml.load((destination / "upstream_agent.yaml").read_text(), Loader=yaml.BaseLoader)
    for key in ("policy", "algorithm", "num_steps_per_env", "clip_actions"):
        changes.extend(differences(saved_agent[key], current_agent[key], f"agent.{key}"))
    files = [parent / "env.yaml", parent / "agent.yaml", ROOT / "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py"]
    report = {"status": "passed" if not changes else "mismatch", "differences": changes,
              "scope": "unchanged upstream configuration, before declared continuation adaptations",
              "sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (destination / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print("UPSTREAM_CONFIG_AUDIT=" + json.dumps(report), flush=True)
    if changes:
        raise RuntimeError("Saved 19999 configuration differs from current upstream; see .cache/training-audit/audit.json")
    return report
