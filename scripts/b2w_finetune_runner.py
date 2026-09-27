"""Local resume/LR safeguards around upstream RSL-RL; no vendor edits."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import time

import torch
import rsl_rl.runners
from rsl_rl.runners import OnPolicyRunner

from b2w_finetune_sampling import learning_rate_after_resume


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def install_runner(parent, parent_sha, root, *, expected_iteration=19999, lr_cap=5e-5, max_updates=2000,
                   extra_sources=(), reward_note="original rewards"):
    class ContinuationRunner(OnPolicyRunner):
        def __init__(self, *args, **kwargs):
            torch.set_num_threads(4)
            super().__init__(*args, **kwargs)
            self.run_path = Path(self.log_dir)
            self.run_path.mkdir(parents=True, exist_ok=True)
            self.started = time.time()
            self.lr_cap = lr_cap
            self.completed_updates = 0
            self.parent_loaded = False
            self.progress = {"status": "initializing", "completed_updates": 0}
            base = self.env.unwrapped
            obs = self.env.get_observations()
            expected = ["base_ang_vel", "projected_gravity", "velocity_commands", "joint_pos", "joint_vel", "actions"]
            if list(base.observation_manager.active_terms["policy"]) != expected:
                raise RuntimeError("Actor observation order changed")
            if obs["policy"].shape != (self.env.num_envs, 57) or obs["critic"].shape != (self.env.num_envs, 247):
                raise RuntimeError("Actor/critic ABI mismatch")
            if self.env.num_actions != 16 or abs(base.step_dt - 0.02) > 1e-10:
                raise RuntimeError("Action/50 Hz ABI mismatch")
            if not 1 <= self.env.num_envs <= 4096 or not 1 <= self.cfg["max_iterations"] <= max_updates:
                raise RuntimeError("Requested run exceeds the authorized local budget")
            if self.is_distributed:
                raise RuntimeError("Local single-GPU continuation only")
            self.alg.optimizer.register_step_pre_hook(self._before_optimizer_step)

        def _before_optimizer_step(self, optimizer, args, kwargs):
            # Upstream adapts LR per minibatch. Cap BOTH fields before every step.
            self.alg.learning_rate = min(self.alg.learning_rate, self.lr_cap)
            for group in optimizer.param_groups:
                group["lr"] = self.alg.learning_rate
            finite = torch.stack([p.grad.isfinite().all() for p in self.alg.policy.parameters() if p.grad is not None]).all()
            if not finite.item():
                raise FloatingPointError("Non-finite PPO gradients; update aborted")

        def load(self, path, load_optimizer=True):
            if Path(path).resolve() != parent.resolve() or not load_optimizer:
                raise RuntimeError("Must restore pinned parent including Adam state")
            result = super().load(path, load_optimizer=True)
            saved = torch.load(parent, map_location="cpu", weights_only=True)
            for name, actual in self.alg.policy.state_dict().items():
                if not torch.equal(actual.cpu(), saved["model_state_dict"][name]):
                    raise RuntimeError(f"Parent restoration mismatch: {name}")
            saved_lr = saved["optimizer_state_dict"]["param_groups"][0]["lr"]
            restored_lr = self.alg.optimizer.param_groups[0]["lr"]
            if restored_lr != saved_lr or not self.alg.optimizer.state:
                raise RuntimeError("Adam state/LR not restored")
            self.alg.learning_rate = learning_rate_after_resume(saved_lr, self.lr_cap)
            for group in self.alg.optimizer.param_groups:
                group["lr"] = self.alg.learning_rate
            if saved["iter"] != expected_iteration:
                raise RuntimeError("Wrong parent iteration")
            # RSL-RL saves the index of the last completed update, not the next.
            self.current_learning_iteration = saved["iter"] + 1
            self.start_iteration = self.current_learning_iteration
            self.parent_loaded = True
            source_paths = [root / "scripts" / name for name in (
                "train_b2w_19999.py", "b2w_finetune_cfg.py", "b2w_finetune_runner.py",
                "b2w_finetune_sampling.py", "b2w_runtime.py", "local_b2w_assets.py")]
            source_paths += [root / "vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py",
                             Path(importlib.import_module("rsl_rl.algorithms.ppo").__file__),
                             Path(importlib.import_module("rsl_rl.runners.on_policy_runner").__file__)]
            source_paths += [root / "scripts" / name for name in extra_sources]
            source_paths += [
                Path(importlib.import_module("isaaclab.terrains.config.rough").__file__),
                Path(importlib.import_module(
                    "robot_lab.tasks.manager_based.locomotion.velocity.config.wheeled.unitree_b2w.rough_env_cfg").__file__),
            ]
            captured = self.run_path / "sources"
            captured.mkdir(exist_ok=True)
            hashes = {}
            for source in source_paths:
                hashes[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
                shutil.copyfile(source, captured / source.name)
            self.manifest = {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "parent": str(parent), "parent_sha256": parent_sha,
                "parent_iteration": expected_iteration, "first_update_index": self.start_iteration,
                "additional_updates": self.cfg["max_iterations"], "num_envs": self.env.num_envs,
                "rollout_steps": self.num_steps_per_env, "seed": self.cfg["seed"],
                "gpu": torch.cuda.get_device_name(), "torch": torch.__version__,
                "rsl_rl": importlib.metadata.version("rsl-rl-lib"),
                "saved_adam_lr": saved_lr, "restored_adam_lr": restored_lr,
                "initial_finetune_lr": self.alg.learning_rate, "lr_cap": self.lr_cap,
                "parent_state_exact": True, "actor_observations": 57, "critic_observations": 247,
                "actions": 16, "policy_hz": 50,
                "command_probabilities_general_cohort": dict(zip(
                    self.env.unwrapped.command_manager.get_term("base_velocity").mode_names,
                    self.env.unwrapped.command_manager.get_term("base_velocity").probabilities)),
                "stair_stop_cohort_envs": int(self.env.unwrapped.command_manager.get_term("base_velocity").stop_cohort.sum()),
                "terrain_proportions": {
                    name: sub.proportion for name, sub in
                    self.env.unwrapped.cfg.scene.terrain.terrain_generator.sub_terrains.items()
                },
                "retention_measures": ["all upstream terrain families and difficulty rows",
                    "25 percent flat terrain rehearsal", "translation, mixed and zero commands retained",
                    "original mass, actuators, observation noise and domain randomization",
                    "Adam/critic/actor/std restoration, smaller PPO clipping and capped adaptive LR"],
                "reward_configuration": reward_note,
                "qualification": "not evaluated; training diagnostics do not establish skill retention",
                "sources_sha256": hashes,
            }
            write_json(self.run_path / "continuation_manifest.json", self.manifest)
            command = self.env.unwrapped.command_manager.get_term("base_velocity")
            if hasattr(command, "original_cohort"):
                self.manifest["original_vendor_cohort_envs"] = int(command.original_cohort.sum())
                self.manifest["direct_command_cohort_envs"] = int((~command.original_cohort).sum())
                self.manifest["command_distribution_note"] = (
                    "50% of environments per cohort, not 50% of resampling events; "
                    "original: vendor sampler/heading, 10s resampling, 2% stand, 20s episodes; "
                    "direct: focused sampling, 60s episodes, stair move/stop subcohort")
                self.manifest["retention_measures"].append(
                    "half of environments preserve original command distribution, 20s horizon and terrain curriculum")
                audit_path = root / ".cache/training-audit/audit.json"
                self.manifest["upstream_config_audit"] = json.loads(audit_path.read_text())
                shutil.copyfile(audit_path, self.run_path / "upstream_config_audit.json")
                write_json(self.run_path / "continuation_manifest.json", self.manifest)
            # Upstream save() expects its logging writer, initialized by learn().
            # Save the verified zero-update state before entering learn directly.
            torch.save({"model_state_dict": self.alg.policy.state_dict(),
                        "optimizer_state_dict": self.alg.optimizer.state_dict(), "iter": expected_iteration,
                        "infos": {"updates": 0, "parent_sha256": parent_sha}},
                       self.run_path / f"model_{expected_iteration}.pt")
            print("RESUME_VERIFIED=" + json.dumps(self.manifest), flush=True)
            return result

        def learn(self, num_learning_iterations, init_at_random_ep_len=False):
            if not self.parent_loaded or num_learning_iterations != self.cfg["max_iterations"]:
                raise RuntimeError("Resume/budget verification failed")
            try:
                # Long zero windows must not be cut by randomized initial timeouts.
                super().learn(num_learning_iterations, init_at_random_ep_len=False)
                self.progress["status"] = "completed"
                write_json(self.run_path / "progress.json", self.progress)
            except BaseException as error:
                self.progress.update(status="failed", error=repr(error))
                write_json(self.run_path / "progress.json", self.progress)
                raise

        def log(self, locs, *args, **kwargs):
            losses = {key: float(value) for key, value in locs["loss_dict"].items()}
            if not all(math.isfinite(v) for v in losses.values()):
                raise FloatingPointError(f"Non-finite losses: {losses}")
            if not torch.stack([p.isfinite().all() for p in self.alg.policy.parameters()]).all().item():
                raise FloatingPointError("Non-finite policy weights")
            super().log(locs, *args, **kwargs)
            self.completed_updates = locs["it"] - self.start_iteration + 1
            command = self.env.unwrapped.command_manager.get_term("base_velocity")
            self.progress = {
                "status": "running", "updated_utc": datetime.now(timezone.utc).isoformat(),
                "iteration": locs["it"], "completed_updates": self.completed_updates,
                "target_updates": self.cfg["max_iterations"], "num_envs": self.env.num_envs,
                "elapsed_seconds": time.time() - self.started,
                "iteration_seconds": locs["collection_time"] + locs["learn_time"],
                "learning_rate": self.alg.learning_rate, "losses": losses,
                "commands_sampled": dict(zip(command.mode_names, command.resample_counts.cpu().tolist())),
                "training_zero_windows": int(command.zero_windows.item()),
                "training_zero_passes": int(command.zero_passes.item()),
                "training_stair_tile_zero_windows": int(command.stair_zero_windows.item()),
                "training_stair_tile_zero_passes": int(command.stair_zero_passes.item()),
                "scheduled_stair_stop_starts": int(command.stair_stop_starts.item()),
            }
            write_json(self.run_path / "progress.json", self.progress)
            for key in ("training_zero_windows", "training_zero_passes", "training_stair_tile_zero_windows",
                        "training_stair_tile_zero_passes", "scheduled_stair_stop_starts"):
                self.writer.add_scalar(f"Focus/{key}", self.progress[key], locs["it"])
            if self.completed_updates % 10 == 0 or self.completed_updates == 1:
                print("B2W_PROGRESS=" + json.dumps(self.progress), flush=True)

        def save(self, path, infos=None):
            super().save(path, infos={"parent_sha256": parent_sha, "additional_updates": self.completed_updates,
                                    "effective_learning_rate": self.alg.learning_rate})
            if self.completed_updates == self.cfg["max_iterations"]:
                from isaaclab_rl.rsl_rl import export_policy_as_jit
                export_policy_as_jit(self.alg.policy, self.alg.policy.actor_obs_normalizer,
                                     str(self.run_path / "export"))
                write_json(self.run_path / "export/manifest.json", {
                    "parent_sha256": parent_sha, "checkpoint": str(path),
                    "checkpoint_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                    "export_sha256": hashlib.sha256((self.run_path / "export/policy.pt").read_bytes()).hexdigest(),
                    "additional_updates": self.completed_updates, "quality_evaluated": False})

    rsl_rl.runners.OnPolicyRunner = ContinuationRunner
