"""Small environment safety adapter; standard runner and PPO are untouched."""
import os
from pathlib import Path
import torch
from isaaclab.envs import ManagerBasedRLEnv
from native_continuation_sampling import safety
from run_support import ROOT, write_json


class NativeContinuationEnv(ManagerBasedRLEnv):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from check_policy_contract import load_contract
        self.contract = load_contract()
        self.robot = self.scene['robot']
        self.contact = self.scene['contact_forces']
        self.joint_ids, names = self.robot.find_joints(self.contract['joint_names'], preserve_order=True)
        assert names == self.contract['joint_names']
        self.protected = self.contact.find_bodies(['base_link', '.*_hip'])[0]
        assert len(self.protected) == 5 and abs(self.physics_dt-.005) < 1e-9 and abs(self.step_dt-.02) < 1e-9
        shapes = self.observation_manager.group_obs_dim
        assert shapes['policy'] == (57,) and shapes['critic'] == (247,) and self.action_manager.total_action_dim == 16, shapes
        self.safety_flags = torch.zeros(self.num_envs, 4, device=self.device, dtype=torch.bool)
        self.reason_counts = torch.zeros(4, device=self.device, dtype=torch.long)
        self.initial_invalid = torch.zeros((), device=self.device, dtype=torch.long)
        self.initial_states = 0
        self.stepping = False
        update = self.scene.update

        def observed_update(dt):
            update(dt)
            if self.stepping:
                data = self.robot.data
                force = self.contact.data.net_forces_w[:, self.protected].norm(dim=-1).amax(dim=1)
                flags = safety(data.joint_pos[:, self.joint_ids], data.joint_vel[:, self.joint_ids],
                               data.applied_torque[:, self.joint_ids], data.projected_gravity_b, force,
                               data.root_state_w, self.action_manager.action,
                               data.joint_pos_limits[:, self.joint_ids[:12]])
                self.safety_flags |= flags
                if flags[:, 0].any():
                    raise FloatingPointError('Non-finite physics/action; abort continuation')

        self.scene.update = observed_update
        self.output = Path(os.environ['B2W_JOB_DIR'])/'native_continuation'/os.environ['B2W_NATIVE_ARM']/os.environ['B2W_NATIVE_MODE']
        self.output.mkdir(parents=True, exist_ok=True)
        from isaaclab.utils.io import dump_yaml
        from isaac_physics_snapshot import resolved_snapshot
        dump_yaml(str(self.output/'resolved_env.yaml'), self.cfg)
        write_json(self.output/'resolved_physx.json', resolved_snapshot(self.robot, self.joint_ids, self.cfg))
        write_json(self.output/'abi.json', {'actor': 57, 'critic': 247, 'actions': 16, 'policy_dt_s': self.step_dt,
                   'joint_names': names, 'previous_action': 'raw, no runner clipping', 'hardware_enabled': False})

    def step(self, action):
        if not torch.isfinite(action).all():
            raise FloatingPointError('Non-finite policy action')
        self.safety_flags.zero_()
        self.stepping = True
        try:
            result = super().step(action)
            assert not (self.reset_terminated & self.reset_time_outs).any()
            return result
        finally:
            self.stepping = False

    def _reset_idx(self, ids):
        if hasattr(self, 'safety_flags'):
            self.reason_counts += self.safety_flags[ids].sum(dim=0)
        super()._reset_idx(ids)
        if hasattr(self, 'robot'):
            self.initial_invalid += (self.robot.data.projected_gravity_b[ids, 2] > -.5).sum()
            self.initial_states += len(ids)

    def snapshot(self):
        cmd = self.command_manager.get_term('base_velocity')
        return {'reason_counts': self.reason_counts.cpu().tolist(), 'initial_tilt_invalid': int(self.initial_invalid),
                'initial_states': self.initial_states, 'command_cycles': cmd.counts.cpu().tolist(),
                'command_steps': cmd.exposure.cpu().tolist(), 'signed_steps': cmd.signed_exposure.cpu().tolist(),
                'physics_dt_s': self.physics_dt, 'standard_runner': True, 'custom_runner_hooks': False}

    def close(self):
        if hasattr(self, 'output') and not self._is_closed:
            write_json(self.output/'training_safety.json', self.snapshot())
        super().close()
