"""Four 19999 failure/control states, 5 s fresh-contact Isaac replay and ledger."""
import os
import sys
import time
import traceback
from pathlib import Path
from b2w_runtime import configure_process
configure_process()
if os.environ.get('B2W_PAYLOAD_URDF'):
    raise RuntimeError('Nominal replay refuses a payload override')
ROOT = Path(__file__).resolve().parents[1]
if (ROOT/'logs/replay57_19999_20260925/isaac_nominal.npz').exists():
    raise FileExistsError('isaac_nominal')
from isaaclab.app import AppLauncher
sys.argv = [sys.argv[0],'--portable-root',str(ROOT/'.cache/kit'),'--ext-folder',str(ROOT/'.runtime/extensions')]
app = AppLauncher({'headless':True}).app

import gymnasium as gym
import numpy as np
import torch
import trimesh
from isaaclab.terrains import TerrainGeneratorCfg
from isaaclab.terrains.sub_terrain_cfg import SubTerrainBaseCfg
from isaaclab.sensors import ContactSensorCfg
from isaaclab.utils import configclass
from isaaclab_tasks.utils import parse_env_cfg
from b2w_runtime import register_b2w_tasks
from local_b2w_assets import configure_b2w_env
from check_policy_contract import load_contract
from locomotion57_protocol import terrain_boxes, export_path, Telemetry
from replay57_protocol import BASE, DT, PHYSICS_DT, STEPS, BODY_NAMES, write_result, saved_config, reward_terms
from replay57_rewards import live_reward_config, offline_ledger

definition = terrain_boxes('up_14x32')
def terrain_function(difficulty,cfg):
    meshes = []
    for box in definition['boxes']:
        transform = trimesh.transformations.rotation_matrix(box['pitch'],[0,1,0])
        transform[:3,3] = np.asarray(box['pos'])+[40,40,0]
        meshes.append(trimesh.creation.box(box['size'],transform))
    return meshes,np.array([40.,40.,0.])


@configclass
class ReplayTerrainCfg(SubTerrainBaseCfg):
    function = terrain_function


def point_contacts(sensor, com, velocity):
    f,p,normal,_,count,start = [x.cpu().numpy() for x in sensor.contact_physx_view.get_contact_data(dt=PHYSICS_DT)]
    result = np.zeros((4,3))
    max_count = 0
    for i in range(4):
        for j in range(count.shape[1]):
            k,n = int(start[i,j]),int(count[i,j])
            max_count = max(max_count,n)
            sl = slice(k,k+n)
            force = np.abs(f[sl,0])
            active = force >= 5.
            if not active.any():
                continue
            v = velocity[i,:3]+np.cross(velocity[i,3:],p[sl]-com[i])
            tangent = v-(v*normal[sl]).sum(axis=1,keepdims=True)*normal[sl]
            result[i] += [force[active].sum(),(force[active]*(tangent[active]**2).sum(axis=1)).sum(),active.sum()]
    return result,max_count


env = None
try:
    register_b2w_tasks()
    torch.set_num_threads(4)
    task = 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0'
    cfg = parse_env_cfg(task,device='cuda:0',num_envs=4,use_fabric=True)
    cfg.seed = 7200
    cfg.sim.dt,cfg.decimation = PHYSICS_DT,10
    cfg.scene.terrain.terrain_generator = TerrainGeneratorCfg(seed=20260925,size=(80.,80.),
        border_width=0,num_rows=1,num_cols=1,curriculum=False,use_cache=False,
        sub_terrains={'course':ReplayTerrainCfg()})
    cfg.scene.terrain.max_init_terrain_level = 0
    cfg.scene.height_scanner = cfg.scene.height_scanner_base = None
    cfg.observations.critic.height_scan = None
    cfg.observations.policy.enable_corruption = False
    cfg.events,cfg.curriculum,cfg.terminations = {},{},{}
    cfg.rewards = live_reward_config()
    cfg.scene.contact_forces.update_period = PHYSICS_DT
    cfg.scene.contact_forces.history_length = 3
    for leg in ('FR','FL','RR','RL'):
        setattr(cfg.scene,f'replay_{leg}',ContactSensorCfg(
            prim_path=f'{{ENV_REGEX_NS}}/Robot/{leg}_foot',update_period=PHYSICS_DT,
            filter_prim_paths_expr=['/World/ground/terrain'],max_contact_data_count_per_prim=64))
    cfg.commands.base_velocity.heading_command = False
    cfg.commands.base_velocity.rel_heading_envs = cfg.commands.base_velocity.rel_standing_envs = 0.
    cfg.commands.base_velocity.resampling_time_range = (1e9,1e9)
    cfg.commands.base_velocity.ranges.lin_vel_x = (.3,.3)
    cfg.commands.base_velocity.ranges.lin_vel_y = cfg.commands.base_velocity.ranges.ang_vel_z = (0,0)
    configure_b2w_env(cfg)
    env = gym.make(task,cfg=cfg).unwrapped
    env.reset()
    scene,device = env.scene,env.device
    robot,contact = scene['robot'],scene['contact_forces']
    contract = load_contract()
    ids,names = robot.find_joints(contract['joint_names'],preserve_order=True)
    assert names == contract['joint_names'] and abs(env.step_dt-DT)<1e-10
    body_ids = robot.find_bodies(BODY_NAMES,preserve_order=True)[0]
    contact_ids = contact.find_bodies(BODY_NAMES,preserve_order=True)[0]
    wheels = robot.find_bodies([f'{leg}_foot' for leg in ('FR','FL','RR','RL')],preserve_order=True)[0]
    protected = contact.find_bodies(['base_link','.*_hip'])[0]
    src = np.load(BASE/'capture.npz')
    roots = torch.tensor(np.concatenate([src['root_pose'],src['root_com_velocity_w']],axis=1),device=device,dtype=torch.float32)
    roots[:,:3] += scene.env_origins
    pos,vel = robot.data.default_joint_pos.clone(),robot.data.default_joint_vel.clone()
    pos[:,ids] = torch.tensor(src['q'],device=device,dtype=torch.float32)
    vel[:,ids] = torch.tensor(src['dq'],device=device,dtype=torch.float32)
    robot.write_root_state_to_sim(roots)
    robot.write_joint_state_to_sim(pos,vel)
    scene.update(PHYSICS_DT)
    previous = torch.tensor(src['previous_action'],device=device,dtype=torch.float32)
    env.action_manager.process_action(previous)
    commands = torch.tensor([.3,0,0],device=device).expand(4,-1)
    env.command_manager.get_term('base_velocity').vel_command_b.copy_(commands)
    default = torch.tensor(contract['default_dof_pos'],device=device)
    scale = torch.tensor(contract['action_scale'],device=device)
    actor = torch.jit.load(str(export_path(19999)),map_location=device).eval()
    soft_limits = robot.data.soft_joint_pos_limits[0,ids].cpu().numpy()
    telemetry = Telemetry(4,contract['torque_limits'],robot.data.joint_pos_limits[0,ids[:12]].cpu().numpy(),PHYSICS_DT)
    arrays = {k:[] for k in ['trace','root_pose','root_velocity_b','gravity','q','dq','ddq','tau','action',
        'previous_action','targets','contact_history','physics_tau','physics_requested_tau','physics_contact','physics_wheel_positions','reward_rates']}
    initial = {'pose_max_abs_error':float((robot.data.root_state_w[:,:7]-roots[:,:7]).abs().max()),
        'root_com_velocity_max_abs_error':float((robot.data.root_com_vel_w-roots[:,7:]).abs().max()),
        'joint_pos_max_abs_error':float((robot.data.joint_pos-pos).abs().max()),
        'joint_vel_max_abs_error':float((robot.data.joint_vel-vel).abs().max())}
    print('INITIAL',initial,flush=True)
    max_contacts = 0
    started = time.monotonic()
    with torch.inference_mode():
        for step in range(STEPS):
            q = robot.data.joint_pos[:,ids]-default
            q[:,12:] = 0
            obs = torch.cat([robot.data.root_ang_vel_b.clamp(-100,100)*.25,robot.data.projected_gravity_b,
                commands,q.clamp(-100,100),robot.data.joint_vel[:,ids].clamp(-100,100)*.05,previous.clamp(-100,100)],dim=1)
            action = actor(obs)
            assert action.shape == (4,16) and torch.isfinite(action).all()
            arrays['action'].append(action.cpu().numpy().copy())
            arrays['previous_action'].append(previous.cpu().numpy().copy())
            arrays['targets'].append((action*scale+default).clamp(-100,100).cpu().numpy())
            env.action_manager.process_action(action)
            previous.copy_(action)
            for sub in range(10):
                env.action_manager.apply_action()
                scene.write_data_to_sim()
                env.sim.step(render=False)
                scene.update(PHYSICS_DT)
                # Read on every physics step, preserving training's acceleration/history cadence.
                q,dq,tau,ddq = [v[:,ids].cpu().numpy().copy() for v in
                    (robot.data.joint_pos,robot.data.joint_vel,robot.data.applied_torque,robot.data.joint_acc)]
                force = contact.data.net_forces_w[:,protected].norm(dim=-1).max(dim=1).values.cpu().numpy()
                telemetry.update(q,dq,tau,robot.data.projected_gravity_b[:,2].cpu().numpy(),force,
                    np.isfinite(q).all(axis=1)&np.isfinite(dq).all(axis=1),np.ones(4,bool),step*DT+(sub+1)*PHYSICS_DT)
                arrays['physics_tau'].append(tau)
                arrays['physics_requested_tau'].append(robot.data.computed_torque[:,ids].cpu().numpy().copy())
                com = robot.data.body_com_pos_w[:,wheels].cpu().numpy()
                velocity = robot.data.body_com_vel_w[:,wheels].cpu().numpy()
                measured = []
                for w,leg in enumerate(('FR','FL','RR','RL')):
                    slip,count = point_contacts(scene[f'replay_{leg}'],com[:,w],velocity[:,w])
                    max_contacts = max(max_contacts,count)
                    measured.append(slip)
                arrays['physics_contact'].append(np.stack(measured,axis=1))
                arrays['physics_wheel_positions'].append((robot.data.body_link_pos_w[:,wheels]-scene.env_origins[:,None]).cpu().numpy())
            root_pose = robot.data.root_link_pose_w.clone()
            root_pose[:,:3] -= scene.env_origins
            root_velocity = torch.cat([robot.data.root_lin_vel_b,robot.data.root_ang_vel_b],dim=1).cpu().numpy()
            arrays['trace'].append(np.concatenate([root_velocity[:,:2],root_velocity[:,5:6],root_pose[:,:3].cpu().numpy()],axis=1))
            for k,v in [('root_pose',root_pose.cpu().numpy()),('root_velocity_b',root_velocity),
                ('gravity',robot.data.projected_gravity_b.cpu().numpy()),('q',q),('dq',dq),('tau',tau),('ddq',ddq),
                ('contact_history',contact.data.net_forces_w_history[:,:,contact_ids].cpu().numpy())]:
                arrays[k].append(v.copy())
            env.reward_manager.compute(DT)
            arrays['reward_rates'].append(env.reward_manager._step_reward.cpu().numpy().copy())
            if step%50==0:
                print('REPLAY',step,'elapsed',time.monotonic()-started,flush=True)
    arrays = {k:np.asarray(v) for k,v in arrays.items()}
    arrays['soft_joint_limits'] = soft_limits
    names = env.reward_manager.active_terms
    proxy = offline_ledger(arrays,soft_limits)
    errors = {name:float(np.max(np.abs(proxy[name]-arrays['reward_rates'][:,:,i]))) for i,name in enumerate(names)}
    write_result('isaac_nominal',arrays,{'engine':'Isaac','initial_state_errors':initial,
        'safety':[telemetry.result(i) for i in range(4)],'reward_names':names,'reward_proxy_max_errors':errors,
        'body_names':BODY_NAMES,'maximum_contacts_per_wheel_pair':max_contacts,
        'contact_filter':'/World/ground/terrain','contact_capacity_per_wheel':64,
        'wall_seconds':time.monotonic()-started,
        'torque_semantics':'Isaac computed/applied PD; implicit wheel applied torque is an estimate, not solver impulse',
        'physics_materials':{'ground':str(cfg.scene.terrain.physics_material),'robot':str(cfg.sim.physics_material)}})
    if max(errors.values()) > 2e-5:
        raise RuntimeError(f'Reward proxy mismatch: {errors}')
    if max_contacts >= 64 or arrays['physics_contact'][...,0].sum() <= 0:
        raise RuntimeError('Invalid contact instrumentation')
    for variant in ('mujoco_cooked_shapes','mujoco_source_shapes','warm_check'):
        data = np.load(BASE/f'{variant}.npz')
        ledger = offline_ledger(data,soft_limits)
        write_result(f'{variant}_ledger',{'reward_rates':np.stack([ledger[n] for n in names],axis=-1)},
            {'engine':'offline actual upstream reward functions','input':variant,'reward_names':names,
             'physics_semantics':'MuJoCo actuator torques and normal-only contact history; not identical solver physics'})
except Exception:
    traceback.print_exc()
    raise
finally:
    if env is not None:
        env.close()
    app.close()
