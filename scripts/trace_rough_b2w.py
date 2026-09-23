"""Read-only wheel/heading instrumentation around the unchanged Rough replay harness."""
from __future__ import annotations
import math
import sys
sys.dont_write_bytecode = True
from benchmark_b2w import sha256
from b2w_runtime import PROJECT_ROOT as ROOT
import rough_metrics
from rough_wheel_corridor import boundary_sides, SIDE_NAMES

OriginalMetrics = rough_metrics.RoughMetrics


class TracedMetrics(OriginalMetrics):
    def __init__(self, base):
        super().__init__(base)
        self.trace_failed = self.t.zeros(base.num_envs, device=base.device, dtype=self.t.bool)
        self.first_crossing = [None] * base.num_envs
        self.prefailure_error = self.t.zeros((base.num_envs, 3), device=base.device)
        self.prefailure_samples = self.t.zeros(base.num_envs, device=base.device, dtype=self.t.long)
        self.trace_frames = []

    def physics(self, dt):
        contact, tilted = super().physics(dt)
        t, d = self.t, self.robot.data
        wheel = d.body_link_pos_w[:, self.wheels] - self.base.scene.env_origins[:, None, :]
        sides = boundary_sides(wheel)
        command = self.base.command_manager.get_command('base_velocity')
        actual = t.cat((d.root_lin_vel_b[:, :2], d.root_ang_vel_b[:, 2:3]), 1)
        q = d.root_quat_w
        yaw = t.atan2(2 * (q[:, 0]*q[:, 3] + q[:, 1]*q[:, 2]), 1 - 2*(q[:, 2]**2 + q[:, 3]**2))
        position = d.root_pos_w - self.base.scene.env_origins
        eligible = ~self.trace_failed & (self.ticks > 400)
        self.prefailure_error += (actual-command) * eligible[:, None]
        self.prefailure_samples += eligible
        newly = sides.any(1) & ~self.trace_failed
        for index in newly.nonzero().flatten().tolist():
            self.first_crossing[index] = dict(time_s=self.ticks*dt,
                sides=[name for k, name in enumerate(SIDE_NAMES) if bool(sides[index, k])],
                wheel_relative=wheel[index].tolist(), root_relative=position[index].tolist(),
                heading_rad=float(yaw[index]), actual_velocity=actual[index].tolist(),
                command=command[index].tolist(),
                prefailure_bias=(self.prefailure_error[index]/self.prefailure_samples[index].clamp_min(1)).tolist(),
                prefailure_samples=int(self.prefailure_samples[index]))
        self.trace_failed |= sides.any(1) | (contact > 1.) | tilted
        if self.ticks % 10 == 0:
            self.trace_frames.append(t.cat((position, yaw[:, None], actual, command,
                wheel[:, :, :2].flatten(1), self.trace_failed[:, None].float()), 1).clone())
        return contact, tilted

    def finish(self):
        result = super().finish()
        result['route_trace'] = dict(first_crossing=self.first_crossing,
            sample_dt=.05, fields=['root_x','root_y','root_z','heading','vx','vy','yaw_rate',
                'command_vx','command_vy','command_yaw',
                'FR_x','FR_y','FL_x','FL_y','RR_x','RR_y','RL_x','RL_y','failed'],
            frames=self.t.stack(self.trace_frames).cpu().tolist(),
            source_sha256={f'scripts/{n}':sha256(ROOT/'scripts'/n)
                for n in ('trace_rough_b2w.py','rough_wheel_corridor.py')},
            scope='Passive diagnostics, no command/action/physics/gate modification; first crossing at200Hz')
        return result


def main():
    rough_metrics.RoughMetrics = TracedMetrics
    from replay_rough_b2w import main as replay
    return replay()


if __name__ == '__main__':
    raise SystemExit(main())
