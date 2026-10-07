"""Run a full-command-cycle reward/GAE/actor-gradient audit with zero PPO updates."""
from __future__ import annotations

import argparse
import copy
import faulthandler
import os
from pathlib import Path
import runpy
import shutil
import sys
import time

from gradient_audit_contract import SPEC_PATH, load_spec
from run_support import ROOT, managed_entrypoint, sha256, utc_now, write_json
from b2w_runtime import configure_process, project_kit_args


SOURCES = (
    "scripts/run_gradient_audit.py",
    "scripts/gradient_audit.py",
    "scripts/gradient_audit_contract.py",
    "scripts/b2w_schedule_pilot_cfg.py",
    "scripts/b2w_schedule_pilot_env.py",
    "scripts/b2w_reset_pilot_cfg.py",
    "scripts/b2w_reset_pilot_env.py",
    "scripts/b2w_curriculum_env.py",
    "scripts/stair_curriculum_monitor.py",
    "scripts/b2w_core_stage3_cfg.py",
    "scripts/b2w_core_stage3_sampling.py",
    "configs/24650_gradient_audit_20261005.json",
    "configs/24650_upright_schedule_ab_20261001.json",
    "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py",
)
COHORT_NAMES = ("retention", "flat", "rough", "stairs_up", "stairs_down")


class Aggregate:
    """GPU-resident sufficient statistics, synchronised only at finalisation."""

    def __init__(self, torch, device, reward_terms):
        self.torch = torch
        self.count = torch.zeros((), dtype=torch.float64, device=device)
        self.dones = torch.zeros_like(self.count)
        self.values = {name: [torch.zeros_like(self.count), torch.zeros_like(self.count),
                              torch.zeros_like(self.count)]
                       for name in ("environment_reward", "training_reward", "raw_gae", "advantage")}
        self.reward_terms = {name: [torch.zeros_like(self.count), torch.zeros_like(self.count)]
                             for name in reward_terms}

    def add(self, mask, environment_reward, training_reward, raw_advantage,
            advantage, dones, reward_terms, reward_names):
        count = mask.sum(dtype=self.torch.float64)
        self.count += count
        self.dones += dones[mask].double().sum()
        for name, values in (("environment_reward", environment_reward),
                             ("training_reward", training_reward),
                             ("raw_gae", raw_advantage), ("advantage", advantage)):
            selected = values[mask].double()
            self.values[name][0] += selected.sum()
            self.values[name][1] += selected.square().sum()
            self.values[name][2] += (selected > 0).double().sum()
        for index, name in enumerate(reward_names):
            selected = reward_terms[..., index][mask].double()
            self.reward_terms[name][0] += selected.sum()
            self.reward_terms[name][1] += selected.square().sum()

    @staticmethod
    def _finish(pair, count):
        if not count:
            return {"mean": None, "std": None}
        total, square = (float(value) for value in pair[:2])
        mean = total / count
        variance = max(0.0, square / count - mean * mean)
        result = {"mean": mean, "std": variance ** .5}
        if len(pair) == 3:
            result["positive_fraction"] = float(pair[2]) / count
        return result

    def finish(self):
        count = int(self.count)
        return {"count": count, "terminal_fraction": float(self.dones / self.count) if count else None,
                **{name: self._finish(pair, count) for name, pair in self.values.items()},
                "reward_terms": {name: self._finish(pair, count)
                                 for name, pair in self.reward_terms.items()}}


def _sample_group(torch, samples, name, mask, obs, actions, log_prob, advantage,
                  per_batch, maximum):
    current = sum(item["obs"].shape[0] for item in samples.setdefault(name, []))
    take = min(per_batch, maximum - current)
    if take <= 0:
        return
    indices = mask.flatten().nonzero(as_tuple=False).flatten()
    available = indices.shape[0]
    if not available:
        return
    if available > take:
        positions = torch.arange(take, device=indices.device) * available // take
        indices = indices[positions]
    samples[name].append({
        "obs": obs.reshape(-1, obs.shape[-1])[indices].detach().cpu(),
        "actions": actions.reshape(-1, actions.shape[-1])[indices].detach().cpu(),
        "log_prob": log_prob.reshape(-1)[indices].detach().cpu(),
        "advantage": advantage.reshape(-1)[indices].detach().cpu(),
    })


def _actor_gradient(torch, TensorDict, policy, algorithm, rows, chunk_size):
    rows = {key: torch.cat([item[key] for item in rows], dim=0) for key in rows[0]}
    count = rows["obs"].shape[0]
    named = [(name, parameter) for name, parameter in policy.named_parameters()
             if name.startswith("actor.") or name in {"std", "log_std"}]
    gradient = [torch.zeros_like(parameter, dtype=torch.float64, device="cpu") for _, parameter in named]
    surrogate_total = entropy_total = ratio_error = 0.0
    for start in range(0, count, chunk_size):
        stop = min(count, start + chunk_size)
        weight = (stop - start) / count
        obs = rows["obs"][start:stop].to(algorithm.device)
        actions = rows["actions"][start:stop].to(algorithm.device)
        old_log_prob = rows["log_prob"][start:stop].to(algorithm.device)
        advantage = rows["advantage"][start:stop].to(algorithm.device)
        batch = TensorDict({"policy": obs}, batch_size=[stop - start], device=algorithm.device)
        policy.act(batch)
        log_prob = policy.get_actions_log_prob(actions)
        ratio = torch.exp(log_prob - old_log_prob)
        surrogate = -advantage * ratio
        clipped = -advantage * torch.clamp(ratio, 1.0 - algorithm.clip_param,
                                           1.0 + algorithm.clip_param)
        surrogate_loss = torch.maximum(surrogate, clipped).mean()
        entropy = policy.entropy.mean()
        loss = surrogate_loss - algorithm.entropy_coef * entropy
        grads = torch.autograd.grad(loss, [parameter for _, parameter in named], allow_unused=True)
        for index, grad in enumerate(grads):
            if grad is not None:
                gradient[index] += grad.detach().double().cpu() * weight
        surrogate_total += float(surrogate_loss.detach()) * weight
        entropy_total += float(entropy.detach()) * weight
        ratio_error = max(ratio_error, float((ratio.detach() - 1.0).abs().max()))
    flat = torch.cat([value.flatten() for value in gradient])
    return flat, {"samples": count, "gradient_norm": float(flat.norm()),
                  "surrogate_loss": surrogate_total, "entropy": entropy_total,
                  "max_abs_ratio_minus_one": ratio_error,
                  "parameter_gradient_norms": {name: float(value.norm())
                                               for (name, _), value in zip(named, gradient)}}


def main():
    managed_entrypoint()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    spec = load_spec()
    job = Path(os.environ["B2W_JOB_DIR"]).resolve()
    output = job / "gradient_audit"
    output.mkdir(parents=True, exist_ok=False)
    faulthandler.enable()
    faulthandler.dump_traceback_later(90, repeat=True)
    hashes = {relative: sha256(ROOT / relative) for relative in SOURCES}
    for relative in SOURCES:
        destination = job / "sources" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    write_json(job / "experiment_manifest.json", {
        "created": utc_now(), "specification": spec,
        "specification_sha256": sha256(SPEC_PATH), "source_sha256": hashes,
        "ppo_updates": 0, "optimizer_steps": 0, "automatic_training_launch": False,
    })
    progress = {"status": "running", "phase": "bootstrap", "log_arms": [],
                "policy_steps": 0, "target_policy_steps": spec["rollout"]["policy_steps"],
                "ppo_updates": 0, "optimizer_steps": 0, "updated": utc_now()}

    def update_progress(phase, policy_steps=None):
        progress.update(phase=phase, updated=utc_now())
        if policy_steps is not None:
            progress["policy_steps"] = policy_steps
        write_json(job / "pilot_progress.json", progress)
        print("GRADIENT_AUDIT", phase, progress["policy_steps"], "/",
              progress["target_policy_steps"], flush=True)

    update_progress("bootstrap")
    os.environ.update(B2W_RESET_ARM="upright", B2W_SCHEDULE_ARM="fixed",
                      B2W_RESET_MODE="gradient_audit", B2W_RESET_OUTPUT=str(output),
                      B2W_RESET_RUN_NAME=job.name, HYDRA_FULL_ERROR="1")
    configure_process()
    import torch
    import tensordict
    import isaaclab.app
    from isaaclab.app import AppLauncher

    launched = []

    class LocalLauncher(AppLauncher):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            launched.append(self)
            from b2w_runtime import register_b2w_tasks
            register_b2w_tasks()
            import gymnasium as gym
            gym.register(id=spec["mdp"]["task"], entry_point="b2w_schedule_pilot_env:SchedulePilotEnv",
                         disable_env_checker=True,
                         kwargs={"env_cfg_entry_point": "b2w_schedule_pilot_cfg:env_config",
                                 "rsl_rl_cfg_entry_point": "b2w_schedule_pilot_cfg:agent_config"})

    isaaclab.app.AppLauncher = LocalLauncher
    train = ROOT / "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py"
    sys.path.insert(0, str(train.parent))
    sys.argv = [str(train), "--headless", "--task", spec["mdp"]["task"],
                "--num_envs", str(spec["rollout"]["num_envs"]),
                "--seed", str(spec["mdp"]["seed"]), "--device", "cuda:0",
                "--kit_args", project_kit_args()]
    env = None
    started = time.monotonic()
    try:
        runpy.run_path(str(train), run_name="b2w_gradient_audit_bootstrap")
        import gymnasium as gym
        from tensordict import TensorDict
        from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
        from rsl_rl.runners import OnPolicyRunner
        import rsl_rl.algorithms.ppo as ppo_module
        from b2w_schedule_pilot_cfg import env_config, agent_config
        from gradient_audit import PHASE_NAMES, cosine_matrix, raw_gae, semantic_phase_ids
        from stair_curriculum_contract import assert_exact_state

        cfg = env_config()
        cfg.scene.num_envs = spec["rollout"]["num_envs"]
        cfg.seed = spec["mdp"]["seed"]
        cfg.log_dir = str(output)
        agent = agent_config()
        env = RslRlVecEnvWrapper(gym.make(spec["mdp"]["task"], cfg=cfg),
                                 clip_actions=agent.clip_actions)
        runner = OnPolicyRunner(env, agent.to_dict(), log_dir=None, device=agent.device)
        runner.load(str(ROOT / spec["parent"]["checkpoint"]))
        saved = torch.load(ROOT / spec["parent"]["checkpoint"], map_location="cpu", weights_only=True)
        assert_exact_state(runner.alg.policy.state_dict(), saved["model_state_dict"], "model_before")
        assert_exact_state(runner.alg.optimizer.state_dict(), saved["optimizer_state_dict"], "Adam_before")
        if env.num_actions != 16 or env.get_observations()["policy"].shape != (env.num_envs, 57):
            raise ValueError("Actor ABI drift")
        if abs(env.unwrapped.step_dt - .02) > 1.e-9:
            raise ValueError("Policy rate drift")
        runtime_sources = (Path(sys.modules[OnPolicyRunner.__module__].__file__), Path(ppo_module.__file__))
        write_json(output / "runtime_sources.json", {
            "standard_runner": True, "custom_runner_hooks": False,
            "source_sha256": {str(path): sha256(path) for path in runtime_sources},
            "runtime": {"gpu": torch.cuda.get_device_name(), "torch": torch.__version__},
        })

        raw = env.unwrapped
        command = raw.command_manager.get_term("base_velocity")
        cohort_masks = {"retention": command.original_cohort}
        cohort_masks.update(command.target_masks)
        if tuple(cohort_masks) != COHORT_NAMES:
            raise ValueError("Unexpected cohort names")
        reward_names = tuple(raw.reward_manager.active_terms)
        aggregates = {}
        samples = {}
        rollout = spec["rollout"]
        sampling = spec["sampling"]
        steps_per_batch = rollout["steps_per_batch"]
        batches = rollout["policy_steps"] // steps_per_batch
        if rollout["randomize_initial_episode_length"]:
            raw.episode_length_buf = torch.randint_like(raw.episode_length_buf,
                                                        high=int(raw.max_episode_length))
        obs = env.get_observations().to(runner.device)
        runner.train_mode()
        update_progress("rollout", 0)
        for batch_index in range(batches):
            phase_rows = []
            environment_rewards = []
            reward_term_rows = []
            with torch.inference_mode():
                for _ in range(steps_per_batch):
                    phase_rows.append(semantic_phase_ids(command.command).clone())
                    actions = runner.alg.act(obs)
                    obs, reward, done, extras = env.step(actions.to(env.device))
                    obs, reward, done = obs.to(runner.device), reward.to(runner.device), done.to(runner.device)
                    environment_rewards.append(reward.clone())
                    reward_term_rows.append((raw.reward_manager._step_reward * raw.step_dt).clone())
                    runner.alg.process_env_step(obs, reward, done, extras)
                last_values = runner.alg.policy.evaluate(obs).detach()
                storage = runner.alg.storage
                unnormalised = raw_gae(storage.rewards, storage.dones, storage.values,
                                       last_values, runner.alg.gamma, runner.alg.lam)
                runner.alg.compute_returns(obs)
            phase = torch.stack(phase_rows)
            environment_reward = torch.stack(environment_rewards)
            reward_terms = torch.stack(reward_term_rows)
            training_reward = storage.rewards.squeeze(-1)
            raw_advantage = unnormalised.squeeze(-1)
            advantage = storage.advantages.squeeze(-1)
            dones = storage.dones.squeeze(-1)
            masks = {"total": torch.ones_like(phase, dtype=torch.bool)}
            masks.update({f"cohort/{name}": mask.unsqueeze(0).expand_as(phase)
                          for name, mask in cohort_masks.items()})
            masks.update({f"phase/{name}": phase == index for index, name in enumerate(PHASE_NAMES)})
            for cohort_name, cohort_mask in cohort_masks.items():
                expanded = cohort_mask.unsqueeze(0).expand_as(phase)
                masks.update({f"cohort_phase/{cohort_name}/{name}": expanded & (phase == index)
                              for index, name in enumerate(PHASE_NAMES)})
            for name, mask in masks.items():
                aggregate = aggregates.setdefault(name, Aggregate(torch, runner.device, reward_names))
                aggregate.add(mask, environment_reward, training_reward, raw_advantage,
                              advantage, dones, reward_terms, reward_names)
            sample_groups = {name: mask for name, mask in masks.items()
                             if name == "total" or name.startswith("cohort/") or name.startswith("phase/")}
            for name, mask in sample_groups.items():
                _sample_group(torch, samples, name, mask, storage.observations["policy"],
                              storage.actions, storage.actions_log_prob, storage.advantages,
                              sampling["samples_per_batch_per_group"], sampling["max_samples_per_group"])
            storage.clear()
            completed = (batch_index + 1) * steps_per_batch
            if completed % 240 == 0 or completed == rollout["policy_steps"]:
                update_progress("rollout", completed)

        update_progress("actor_gradients", rollout["policy_steps"])
        vectors = {}
        gradient_reports = {}
        for name, rows in samples.items():
            if not rows:
                continue
            vector, report = _actor_gradient(torch, TensorDict, runner.alg.policy, runner.alg,
                                             rows, sampling["gradient_chunk_size"])
            vectors[name] = vector
            gradient_reports[name] = report
        runner.alg.optimizer.zero_grad(set_to_none=True)
        assert_exact_state(runner.alg.policy.state_dict(), saved["model_state_dict"], "model_after")
        assert_exact_state(runner.alg.optimizer.state_dict(), saved["optimizer_state_dict"], "Adam_after")
        result = {
            "status": "completed", "created": utc_now(), "elapsed_seconds": time.monotonic() - started,
            "seed": spec["mdp"]["seed"], "num_envs": env.num_envs,
            "policy_steps": rollout["policy_steps"],
            "transitions": rollout["policy_steps"] * env.num_envs,
            "steps_per_batch": steps_per_batch, "ppo_updates": 0, "optimizer_steps": 0,
            "parent_model_exact_before": True, "parent_adam_exact_before": True,
            "parent_model_exact_after": True, "parent_adam_exact_after": True,
            "reward_term_names": reward_names,
            "groups": {name: aggregate.finish() for name, aggregate in aggregates.items()},
            "actor_gradients": gradient_reports,
            "actor_gradient_cosine": cosine_matrix(vectors),
            "coverage": raw.snapshot(),
            "interpretation_scope": "Actor PPO surrogate plus entropy only; no critic gradient and no update.",
            "automatic_training_launch": False,
        }
        write_json(output / "result.json", result)
        progress.update(status="completed", phase="completed", result="gradient_audit/result.json")
        update_progress("completed", rollout["policy_steps"])
    except BaseException as error:
        progress.update(status="failed", error=repr(error))
        update_progress("failed")
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        raise
    finally:
        faulthandler.cancel_dump_traceback_later()
        if env is not None:
            env.close()
        for launcher in launched:
            if launcher.app.is_running():
                launcher.app.close()


if __name__ == "__main__":
    main()
