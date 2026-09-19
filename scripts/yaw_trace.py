"""Optional passive physics-substep traces for the fixed yaw cases (no control writes)."""
import hashlib
import json
from pathlib import Path


class YawTrace:
    def __init__(self, base, robot, sensor, policy_ids, total_steps, report_path, torch):
        self.torch = torch
        self.robot, self.sensor = robot, sensor
        self.ids = [i for i in range(base.num_envs) if i % 8 in (4, 5)]
        self.policy_ids = policy_ids
        self.names = [f'{leg}_{part}' for leg in ('FL', 'FR', 'RL', 'RR') for part in ('calf', 'foot')]
        self.body_ids = [robot.body_names.index(n) for n in self.names]
        self.sensor_ids = [sensor.body_names.index(n) for n in self.names]
        self.origins = base.scene.env_origins[self.ids].clone()
        self.total_steps = total_steps
        self.index = 0
        self.buffers = {}
        self.path = Path(report_path).with_suffix('.yaw.npz')
        if self.path.exists():
            raise FileExistsError(self.path)
        self.meta = {
            'env_ids': self.ids, 'body_names': self.names,
            'policy_joint_names': [robot.joint_names[i] for i in policy_ids],
            'sample_timing': 'State after physics integration; computed/applied torque used for the preceding integration.',
            'wheel_torque_caveat': 'Implicit actuator computed/applied torque are PD estimates, not measured solver joint torques.',
            'geometry_caveat': 'Body positions are link origins, not ground clearance; collision geometry must be transformed separately.',
            'joint_effort_limits': robot.data.joint_effort_limits[self.ids][:, policy_ids].cpu().tolist(),
            'actuator_types': {n:type(a).__name__ for n,a in robot.actuators.items()},
        }

    def capture(self, command, action, time_s):
        t = self.torch
        d = self.robot.data
        ids, joints, bodies = self.ids, self.policy_ids, self.body_ids
        fields = {
            'command': command[ids], 'action': action[ids],
            'actual': t.cat((d.root_lin_vel_b[ids, :2], d.root_ang_vel_b[ids, 2:3]), 1),
            'joint_pos': d.joint_pos[ids][:, joints],
            'joint_vel': d.joint_vel[ids][:, joints],
            'computed_torque': d.computed_torque[ids][:, joints],
            'applied_torque': d.applied_torque[ids][:, joints],
            'body_pos': d.body_link_pos_w[ids][:, bodies] - self.origins[:, None],
            'body_quat': d.body_link_quat_w[ids][:, bodies],
            'body_lin_vel': d.body_link_lin_vel_w[ids][:, bodies],
            'body_ang_vel': d.body_link_ang_vel_w[ids][:, bodies],
            'contact_force': self.sensor.data.net_forces_w[ids][:, self.sensor_ids],
            'root_pos': d.root_pos_w[ids] - self.origins,
            'projected_gravity': d.projected_gravity_b[ids],
            'joint_pos_target': d.joint_pos_target[ids][:, joints],
            'joint_vel_target': d.joint_vel_target[ids][:, joints],
        }
        for name, value in fields.items():
            if name not in self.buffers:
                self.buffers[name] = t.empty((self.total_steps, *value.shape), device=value.device, dtype=value.dtype)
            self.buffers[name][self.index].copy_(value)
        self.index += 1
        self.last_time = time_s

    def finish(self):
        import numpy as np
        if self.index != self.total_steps:
            raise RuntimeError('Incomplete trace')
        arrays = {k:v.cpu().numpy() for k,v in self.buffers.items()}
        arrays['time_s'] = np.arange(1,self.index+1) * (self.last_time / self.index)
        arrays['metadata_json'] = np.array(json.dumps(self.meta))
        np.savez_compressed(self.path, **arrays)
        return {'path':str(self.path), 'sha256':hashlib.sha256(self.path.read_bytes()).hexdigest(),
                'samples':self.index, **self.meta}
