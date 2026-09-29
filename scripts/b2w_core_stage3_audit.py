"""Fail closed unless stage 3 differs from selected 24650 only as declared."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

from b2w_core_stage3_cfg import PLAN
from b2w_training_audit import differences


def audit_core_stage3(env_cfg, agent_cfg, parent_folder, run_path):
    from isaaclab.utils.io import dump_yaml

    run_path = Path(run_path)
    env_path = run_path / "core_stage3_environment.yaml"
    dump_yaml(str(env_path), env_cfg)
    saved = yaml.load((parent_folder / "env.yaml").read_text(), Loader=yaml.BaseLoader)
    current = yaml.load(env_path.read_text(), Loader=yaml.BaseLoader)

    protected = []
    for section in ("observations", "actions", "events", "rewards", "curriculum", "sim", "decimation"):
        protected.extend(differences(saved[section], current[section], section))
    for section in ("actuators", "init_state", "spawn"):
        protected.extend(differences(saved["scene"]["robot"][section], current["scene"]["robot"][section],
                                     "robot." + section))
    # Hydra's explicit smoke override propagates the requested environment count
    # into the terrain importer.  It is not a semantic terrain change; the
    # launcher separately restricts that override to the one-update audit smoke.
    saved_terrain = copy.deepcopy(saved["scene"]["terrain"])
    current_terrain = copy.deepcopy(current["scene"]["terrain"])
    saved_terrain.pop("num_envs", None)
    current_terrain.pop("num_envs", None)
    protected.extend(differences(saved_terrain, current_terrain, "scene.terrain"))

    command_changes = differences(saved["commands"]["base_velocity"], current["commands"]["base_velocity"],
                                  "commands.base_velocity")
    termination_changes = differences(saved["terminations"], current["terminations"], "terminations")
    expected_class = (len(command_changes) == 1
                      and command_changes[0]["path"] == "commands.base_velocity.class_type"
                      and command_changes[0]["saved"] == "b2w_core_stage1_cfg:CoreStage1VelocityCommand"
                      and command_changes[0]["current"] == "b2w_core_stage3_cfg:CoreStage3VelocityCommand")
    expected_timeout = (len(termination_changes) == 1
                        and termination_changes[0]["path"] == "terminations.time_out.func"
                        and termination_changes[0]["saved"] == "b2w_core_stage1_cfg:core_stage1_timeout"
                        and termination_changes[0]["current"] == "b2w_core_stage3_cfg:core_stage3_timeout")
    episode_changes = differences(saved["episode_length_s"], current["episode_length_s"], "episode_length_s")

    generator = env_cfg.scene.terrain.terrain_generator
    proportions = {name: terrain.proportion for name, terrain in generator.sub_terrains.items()}
    geometry_ok = (
        generator.num_rows == 10 and generator.num_cols == 40
        and proportions == PLAN["terrain_proportions"]
        and tuple(generator.sub_terrains["target_rough"].noise_range)
            == tuple(PLAN["target_geometry"]["rough_noise_m"])
        and tuple(generator.sub_terrains["target_stairs_up"].step_height_range)
            == tuple(PLAN["target_geometry"]["stair_height_m"])
        and generator.sub_terrains["target_stairs_up"].platform_width
            == PLAN["target_geometry"]["stair_platform_m"]
    )

    saved_agent = yaml.safe_load((parent_folder / "agent.yaml").read_text())
    current_agent = copy.deepcopy(dict(agent_cfg))
    if (saved_agent["obs_groups"] == {}
            and current_agent.get("obs_groups") == {"policy": ["policy"], "critic": ["critic"]}):
        current_agent["obs_groups"] = {}
    for section, expected in (("policy", "ActorCritic"), ("algorithm", "PPO")):
        if (saved_agent[section].get("class_name") == expected
                and "class_name" not in current_agent[section]):
            current_agent[section]["class_name"] = expected
    agent_protected = []
    for key in ("num_steps_per_env", "empirical_normalization", "obs_groups", "clip_actions", "class_name", "policy"):
        agent_protected.extend(differences(saved_agent[key], current_agent[key], "agent." + key))
    saved_algorithm = dict(saved_agent["algorithm"])
    current_algorithm = dict(current_agent["algorithm"])
    saved_algorithm.pop("learning_rate")
    current_algorithm.pop("learning_rate")
    agent_protected.extend(differences(saved_algorithm, current_algorithm, "agent.algorithm"))
    learning_rate_ok = (saved_agent["algorithm"]["learning_rate"] == 1e-5
                        and current_agent["algorithm"]["learning_rate"] == PLAN["lr_cap"])

    unexpected = protected + agent_protected
    passed = (not unexpected and expected_class and expected_timeout and not episode_changes
              and geometry_ok and learning_rate_ok)
    report = {
        "status": "passed" if passed else "failed",
        "protected_differences": protected,
        "agent_protected_differences": agent_protected,
        "command_changes": command_changes,
        "termination_changes": termination_changes,
        "episode_changes": episode_changes,
        "terrain_proportions": proportions,
        "geometry_ok": geometry_ok,
        "learning_rate": {"parent": saved_agent["algorithm"]["learning_rate"],
                          "current": current_agent["algorithm"]["learning_rate"], "ok": learning_rate_ok},
        "scope": "24650 Flat/Rough bank-weight correction plus lower LR; rewards/PPO/physics/robot/ABI/events unchanged",
    }
    (run_path / "core_stage3_config_audit.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("CORE_STAGE3_CONFIG_AUDIT=" + json.dumps(report), flush=True)
    if not passed:
        raise RuntimeError("Core stage-3 config audit failed before any PPO update")
