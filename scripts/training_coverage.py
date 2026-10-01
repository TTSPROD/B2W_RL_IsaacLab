"""Tensor diagnostics only: no command/physics/reward changes or RNG draws."""
import torch


class TrainingCoverage:
    def __init__(self, masks, banks, device, dt):
        self.masks, self.dt = masks, dt
        count = len(next(iter(masks.values())))
        self.returns = torch.zeros(count, device=device, dtype=torch.float64)
        self.lengths = torch.zeros(count, device=device, dtype=torch.long)
        self.groups = {name: torch.zeros(5, device=device, dtype=torch.float64) for name in masks}
        self.banks = banks
        self.phases = {name: torch.zeros((len(bank.commands),bank.commands.shape[1]),
                                        device=device,dtype=torch.long) for name,bank in banks.items()}
        self.full_counts = torch.zeros(count, device=device, dtype=torch.long)

    def observe(self, reward, case_ids, phase_ids):
        self.returns += reward.detach().to(torch.float64)
        self.lengths += 1
        for name, mask in self.masks.items():
            self.groups[name][0] += mask.sum()
            if name in self.phases:
                valid = mask & (phase_ids >= 0)
                width = self.phases[name].shape[1]
                flat = case_ids[valid]*width + phase_ids[valid]
                self.phases[name] += torch.bincount(flat, minlength=self.phases[name].numel()).reshape_as(self.phases[name])

    def reset(self, ids):
        if ids is None:
            ids = torch.arange(len(self.lengths),device=self.lengths.device)
        active = torch.zeros_like(self.lengths,dtype=torch.bool)
        active[ids] = True
        active &= self.lengths > 0
        for name, mask in self.masks.items():
            selected = active & mask
            horizon = round((20 if name == 'retention' else 70)/self.dt)
            full = selected & (self.lengths >= horizon)
            self.groups[name][1] += selected.sum()
            self.groups[name][2] += self.returns[selected].sum()
            self.groups[name][3] += self.lengths[selected].sum()
            self.groups[name][4] += full.sum()
            self.full_counts[full] += 1
        self.returns[ids] = 0
        self.lengths[ids] = 0

    def snapshot(self):
        result = {}
        for name, mask in self.masks.items():
            steps, episodes, total_return, lengths, full = self.groups[name].cpu().tolist()
            result[name] = {'envs':int(mask.sum().item()),'transitions':int(steps),
                'completed_episodes':int(episodes),'full_horizon_episodes':int(full),
                'min_full_episodes_per_env':int(self.full_counts[mask].min().item()),
                'mean_completed_return':total_return/episodes if episodes else None,
                'mean_completed_length_s':lengths*self.dt/episodes if episodes else None}
            if name in self.phases:
                result[name]['case_phase_steps'] = self.phases[name].cpu().tolist()
        return result


def install_coverage(env):
    command = env.command_manager.get_term('base_velocity')
    masks = {'retention':command.original_cohort, **command.target_masks}
    diagnostics = TrainingCoverage(masks,command.rehearsal_banks,env.device,env.step_dt)
    manager = env.reward_manager
    original_compute, original_reset = manager.compute, manager.reset
    def compute(dt):
        reward = original_compute(dt)
        diagnostics.observe(reward,command.rehearsal_case,command.rehearsal_phase)
        return reward
    def reset(env_ids=None):
        diagnostics.reset(env_ids)
        return original_reset(env_ids)
    manager.compute, manager.reset = compute, reset
    return diagnostics
