"""Clean task adaptation on pinned Robot Lab; imported after SimulationApp."""
import os
import torch
import yaml
from isaaclab.envs.mdp.commands import UniformVelocityCommand
from isaaclab.managers import TerminationTermCfg
from isaaclab.terrains import MeshPlaneTerrainCfg
from robot_lab.tasks.manager_based.locomotion.velocity.config.wheeled.unitree_b2w.rough_env_cfg import UnitreeB2WRoughEnvCfg
from robot_lab.tasks.manager_based.locomotion.velocity.config.wheeled.unitree_b2w.agents.rsl_rl_ppo_cfg import UnitreeB2WRoughPPORunnerCfg
from local_b2w_assets import configure_b2w_env
from native_continuation_sampling import programs, yaw_reward
from run_support import ROOT, read_json

PLAN = read_json(ROOT/'configs/24650_native_continuation_20261012.json')
ARM = os.environ['B2W_NATIVE_ARM']
TASK = 'B2W-Native-Standard-Continuation-v0'


class ProgramCommand(UniformVelocityCommand):
    def __init__(self, cfg, env):
        super().__init__(cfg, env)
        self.table, self.durations = programs(self.device)
        self.mode = torch.zeros(self.num_envs, device=self.device, dtype=torch.long)
        self.phase = torch.zeros_like(self.mode)
        self.sign = torch.ones(self.num_envs, device=self.device)
        self.stair_move = torch.zeros(self.num_envs, device=self.device, dtype=torch.bool)
        self.counts = torch.zeros(5, device=self.device, dtype=torch.long)
        self.exposure = torch.zeros(5, device=self.device, dtype=torch.long)
        self.signed_exposure = torch.zeros(3, 2, device=self.device, dtype=torch.long)
        terrain = env.scene.terrain
        # Stratified generation assigns family types by cumulative proportions.
        self.stairs = terrain.terrain_types < 6
        self.probabilities = torch.tensor(PLAN['arms'][ARM], device=self.device)
        self.step = 0

    def _resample_command(self, env_ids):
        ids = torch.arange(self.num_envs, device=self.device)[env_ids] if isinstance(env_ids, slice) else env_ids
        fresh = self.command_counter[ids] == 0
        direct = ids[~self.stairs[ids]]
        if len(direct):
            old_mode = self.mode[direct]
            next_phase = self.phase[direct] + 1
            next_phase = next_phase.clamp_max(7)
            restart = (self.command_counter[direct] == 0) | (self.durations[old_mode, next_phase] == 0) | (self.phase[direct] == 7)
            draws = torch.multinomial(self.probabilities, len(direct), replacement=True)
            signs = (2*torch.randint(2, (len(direct),), device=self.device)-1).float()
            self.mode[direct] = torch.where(restart, draws, old_mode)
            self.sign[direct] = torch.where(restart, signs, self.sign[direct])
            self.phase[direct] = torch.where(restart, 0, next_phase)
            self.counts += torch.bincount(draws[restart], minlength=5)
            m, p = self.mode[direct], self.phase[direct]
            self.vel_command_b[direct] = self.table[m, p]*self.sign[direct, None]
            self.time_left[direct] = self.durations[m, p]
        stairs = ids[self.stairs[ids]]
        if len(stairs):
            move = (self.command_counter[stairs] == 0) | ~self.stair_move[stairs]
            self.stair_move[stairs] = move
            # Uphill/downhill terrain are rehearsed with forward body commands.
            self.vel_command_b[stairs] = 0
            self.vel_command_b[stairs, 0] = move.float()*.5
            self.time_left[stairs] = torch.where(move, 12., 14.)
            self.mode[stairs] = torch.where(move, 1, 0)
        self.is_standing_env[ids] = self.vel_command_b[ids].abs().sum(dim=1) == 0
        self.is_heading_env[ids] = False

    def _update_metrics(self):
        super()._update_metrics()
        self.exposure += torch.bincount(self.mode, minlength=5)
        for axis in range(3):
            c = self.vel_command_b[:, axis]
            self.signed_exposure[axis] += torch.stack(((c > 0).sum(), (c < 0).sum()))
        self.step += 1


def retained_yaw(env, std, command_name, focused_std=.25):
    robot = env.scene['robot']
    return yaw_reward(env.command_manager.get_command(command_name)[:, 2],
                      robot.data.root_ang_vel_b[:, 2], robot.data.projected_gravity_b[:, 2], std, focused_std)


def unsafe(env):
    return env.safety_flags.any(dim=1) if hasattr(env, 'safety_flags') else torch.zeros(env.num_envs, device=env.device, dtype=torch.bool)


def timeout(env):
    return (env.episode_length_buf >= env.max_episode_length) & ~unsafe(env)


def bounds(env, asset_cfg, distance_buffer):
    from isaaclab_tasks.manager_based.locomotion.velocity.mdp.terminations import terrain_out_of_bounds
    return terrain_out_of_bounds(env, asset_cfg, distance_buffer) & ~unsafe(env)


def env_config():
    cfg = configure_b2w_env(UnitreeB2WRoughEnvCfg())
    cfg.episode_length_s = PLAN['common_mdp']['episode_length_s']
    cfg.scene.contact_forces.update_period = cfg.sim.dt
    cmd = cfg.commands.base_velocity
    cmd.class_type = ProgramCommand
    cmd.heading_command = False
    cmd.rel_heading_envs = 0.
    cmd.rel_standing_envs = 0.
    cmd.ranges.heading = None
    cmd.resampling_time_range = (10., 10.)
    cfg.events.randomize_reset_base.params['pose_range']['roll'] = (-.1, .1)
    cfg.events.randomize_reset_base.params['pose_range']['pitch'] = (-.1, .1)
    cfg.rewards.track_ang_vel_z_exp.func = retained_yaw
    cfg.rewards.track_ang_vel_z_exp.params['focused_std'] = .25
    terrain = cfg.scene.terrain.terrain_generator
    for sub in terrain.sub_terrains.values():
        sub.proportion *= .75
    terrain.sub_terrains['flat_rehearsal'] = MeshPlaneTerrainCfg(proportion=.25)
    terrain.curriculum = True
    cfg.scene.terrain.max_init_terrain_level = 9
    cfg.curriculum = {}
    cfg.terminations.safety = TerminationTermCfg(func=unsafe, time_out=False)
    cfg.terminations.time_out.func = timeout
    cfg.terminations.terrain_out_of_bounds.func = bounds
    return cfg


def agent_config():
    cfg = UnitreeB2WRoughPPORunnerCfg()
    saved = yaml.safe_load((ROOT/'policies/local/core_24650/agent.yaml').read_text())
    for key, value in saved.items():
        if key in ('policy', 'algorithm'):
            for field, setting in value.items():
                setattr(getattr(cfg, key), field, setting)
        else:
            setattr(cfg, key, value)
    cfg.obs_groups = {'policy': ['policy'], 'critic': ['critic']}
    training = PLAN['training']
    cfg.seed = training['seed']
    cfg.max_iterations = training['updates_per_arm']
    cfg.save_interval = training['save_interval']
    cfg.experiment_name = f'b2w_native_standard_{ARM}_{cfg.seed}'
    cfg.run_name = os.environ['B2W_JOB_DIR'].rsplit('/', 1)[-1]
    cfg.resume = True
    cfg.load_run = '_parent'
    cfg.load_checkpoint = 'model_24650.pt'
    cfg.algorithm.schedule = training['schedule']
    cfg.algorithm.learning_rate = training['learning_rate']
    return cfg
