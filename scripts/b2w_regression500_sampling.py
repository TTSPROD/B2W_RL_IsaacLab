"""Time-only tensor schedules for the measured regressions of checkpoint 23999."""
import torch


class RehearsalBank:
    def __init__(self, cases, device):
        width = max(len(case['segments']) for case in cases)
        self.commands = torch.zeros(len(cases), width, 3, device=device)
        self.durations = torch.zeros(len(cases), width, device=device)
        self.modes = torch.zeros(len(cases), width, dtype=torch.long, device=device)
        self.lengths = torch.tensor([len(case['segments']) for case in cases], device=device)
        self.weights = torch.tensor([case['weight'] for case in cases], device=device)
        # One-time construction; environment sampling below has no per-env loop.
        for index, case in enumerate(cases):
            for phase, segment in enumerate(case['segments']):
                self.commands[index, phase] = torch.tensor(segment['command'], device=device)
                self.durations[index, phase] = segment['seconds']
                self.modes[index, phase] = segment['mode']

    def sample(self, case_ids, phases, fresh):
        next_phase = phases + 1
        restart = fresh | (next_phase >= self.lengths[case_ids])
        draw = torch.multinomial(self.weights, len(case_ids), replacement=True)
        case_ids = torch.where(restart, draw, case_ids)
        next_phase = torch.where(restart, 0, next_phase)
        return (self.commands[case_ids, next_phase], self.modes[case_ids, next_phase],
                self.durations[case_ids, next_phase], case_ids, next_phase)

