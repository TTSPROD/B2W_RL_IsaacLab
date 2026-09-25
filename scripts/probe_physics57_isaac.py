"""Compiled Isaac readback and controlled airborne/contact target traces."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import numpy as np
from b2w_runtime import configure_process
configure_process()
from physics57_protocol import ROOT, BASE, CONFIG, AIRBORNE, CONTACT, DT, case_boxes, targets, command, save_json, sha256

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--suite', choices=('airborne', 'contact'), required=True)
parser.add_argument('--dt', type=float, required=True)
args = parser.parse_args()
tag = f'isaac_{args.suite}_{args.dt:g}'
output = BASE/f'{tag}.json'
if output.exists():
    raise FileExistsError(output)
from isaaclab.app import AppLauncher
sys.argv = [sys.argv[0], '--portable-root', str(ROOT/'.cache/kit'), '--ext-folder', str(ROOT/'.runtime/extensions')]
app = AppLauncher({'headless': True}).app
import gymnasium as gym
import torch
import trimesh
from pxr import Usd, UsdPhysics
from isaaclab.terrains import TerrainGeneratorCfg
from isaaclab.terrains.sub_terrain_cfg import SubTerrainBaseCfg
from isaaclab.utils import configclass
from isaaclab_tasks.utils import parse_env_cfg
from b2w_runtime import register_b2w_tasks
from local_b2w_assets import configure_b2w_env
from check_policy_contract import load_contract
from locomotion57_protocol import export_path

cases = AIRBORNE if args.suite == 'airborne' else CONTACT
duration = 4. if args.suite == 'airborne' else 10.

def terrain_function(difficulty, cfg):
    meshes = []
    for i, case in enumerate(cases):
        for box in case_boxes(case):
            transform = trimesh.transformations.rotation_matrix(box['pitch'], [0,1,0])
            transform[:3,3] = np.asarray(box['pos'])+[40, 40+4*i, 0]
            meshes.append(trimesh.creation.box(box['size'], transform))
    return meshes, np.array([40.,40.,0.])

@configclass
class ProbeTerrainCfg(SubTerrainBaseCfg):
    function = terrain_function

env = None
try:
    register_b2w_tasks()
    torch.set_num_threads(4)
    task = 'RobotLab-Isaac-Velocity-Rough-Unitree-B2W-v0'
    cfg = parse_env_cfg(task, device='cuda:0', num_envs=len(cases), use_fabric=True)
    cfg.seed = 20260925
    cfg.sim.dt = args.dt
    cfg.decimation = round(DT/args.dt)
    assert abs(cfg.decimation*args.dt-DT) < 1e-10
    cfg.sim.gravity = (0.,0.,-9.81)
    cfg.scene.robot.spawn.rigid_props.disable_gravity = args.suite == 'airborne'
    cfg.scene.terrain.terrain_generator = TerrainGeneratorCfg(seed=20260925, size=(80.,80.),
        border_width=0, num_rows=1, num_cols=1, curriculum=False, use_cache=False,
        sub_terrains={'probes': ProbeTerrainCfg()})
    cfg.scene.terrain.max_init_terrain_level = 0
    cfg.scene.height_scanner = cfg.scene.height_scanner_base = None
    cfg.scene.contact_forces.update_period = args.dt
    cfg.observations.critic.height_scan = None
    cfg.observations.policy.enable_corruption = False
    cfg.events = cfg.curriculum = cfg.terminations = cfg.rewards = {}
    cfg.commands.base_velocity.heading_command = False
    cfg.commands.base_velocity.rel_heading_envs = cfg.commands.base_velocity.rel_standing_envs = 0.
    cfg.commands.base_velocity.resampling_time_range = (1e9,1e9)
    for key in ('lin_vel_x','lin_vel_y','ang_vel_z'):
        setattr(cfg.commands.base_velocity.ranges, key, (0.,0.))
    configure_b2w_env(cfg)
    env = gym.make(task,cfg=cfg).unwrapped
    env.reset()
    robot, scene = env.scene['robot'], env.scene
    contact = scene['contact_forces']
    ids, names = robot.find_joints(load_contract()['joint_names'], preserve_order=True)
    contract = load_contract()
    default = torch.tensor(contract['default_dof_pos'],device=env.device)
    scales = torch.tensor(contract['action_scale'],device=env.device)
    view = robot.root_physx_view
    def array(value):
        return value.detach().cpu().numpy()
    compiled = {'body_names':robot.body_names, 'joint_names':names,
        'mass_kg':array(view.get_masses()[0]).tolist(),
        'com_pose_b_wxyz':array(robot.data.body_com_pose_b[0]).tolist(),
        'inertia_body_frame_kg_m2':array(view.get_inertias()[0]).reshape(-1,3,3).transpose(0,2,1).tolist(),
        'armature':array(view.get_dof_armatures()[0,ids]).tolist(),
        'solver_stiffness':array(view.get_dof_stiffnesses()[0,ids]).tolist(),
        'solver_damping':array(view.get_dof_dampings()[0,ids]).tolist(),
        'joint_friction':array(view.get_dof_friction_properties()[0,ids]).tolist(),
        'solver_max_effort':array(view.get_dof_max_forces()[0,ids]).tolist(),
        'solver_max_velocity':array(view.get_dof_max_velocities()[0,ids]).tolist(),
        'joint_ranges':array(robot.data.joint_pos_limits[0,ids]).tolist(),
        'material_properties':array(view.get_material_properties()[0]).tolist(),
        'actuators':{name:{'class':type(a).__name__, 'joint_names':a.joint_names,
            'stiffness':array(a.stiffness[0]).tolist(), 'damping':array(a.damping[0]).tolist(),
            'effort_limit':array(a.effort_limit[0]).tolist()} for name,a in robot.actuators.items()}}
    prim = env.sim.stage.GetPrimAtPath('/World/envs/env_0/Robot')
    compiled['collision_prims'] = []
    for node in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()):
        if node.HasAPI(UsdPhysics.CollisionAPI):
            attrs = {str(a.GetName()):str(a.Get()) for a in node.GetAttributes()
                     if a.GetName().startswith(('physics:','physxCollision:','xformOp:')) or
                     a.GetName() in ('size','radius','height','extent','axis')}
            compiled['collision_prims'].append({'path':str(node.GetPath()),'type':node.GetTypeName(),'attributes':attrs})
    roots = robot.data.default_root_state.clone()
    roots[:,:3] += scene.env_origins
    roots[:,1] += torch.arange(len(cases),device=env.device)*4
    roots[:,2] = scene.env_origins[:,2]+(3. if args.suite == 'airborne' else .65)
    positions = robot.data.default_joint_pos.clone()
    velocities = torch.zeros_like(positions)
    kinematics=[]
    for pose_id in range(3):
        q = positions.clone()
        if pose_id:
            offset = .08*np.sin(np.arange(12)*.7+pose_id)
            q[:,ids[:12]] += torch.as_tensor(offset,device=env.device,dtype=q.dtype)
        robot.write_root_state_to_sim(roots)
        robot.write_joint_state_to_sim(q,velocities)
        env.sim.forward()
        scene.update(args.dt)
        body_pose = array(robot.data.body_link_pose_w[0]).copy()
        body_pose[:,:3] -= array(roots[0,:3])
        kinematics.append({'joint_pos':array(q[0,ids]).tolist(),'body_pose_root_wxyz':body_pose.tolist()})
    robot.write_root_state_to_sim(roots)
    robot.write_joint_state_to_sim(positions,velocities)
    scene.reset()
    env.sim.forward()
    scene.update(args.dt)
    initial_root = array(roots).copy()
    initial_root[:,:3] -= array(scene.env_origins)
    initial_root[:,1] -= np.arange(len(cases))*4
    protected = contact.find_bodies(['base_link','.*_hip'])[0]
    model = torch.jit.load(str(export_path(10000)),map_location=env.device).eval() if args.suite=='contact' else None
    previous = torch.zeros((len(cases),16),device=env.device)
    records = {key:[] for key in ('q','dq','tau','root','targets','base_hip_force')}
    with torch.inference_mode():
        for step in range(round(duration/DT)):
            t = step*DT
            if model is None:
                physical = torch.as_tensor(np.stack([targets(c,t) for c in cases]),device=env.device,dtype=torch.float32)
                action = (physical-default)/scales
            else:
                commands = torch.as_tensor(np.stack([command(c,t) for c in cases]),device=env.device,dtype=torch.float32)
                q = robot.data.joint_pos[:,ids]-default
                q[:,12:] = 0
                obs = torch.cat((robot.data.root_ang_vel_b.clamp(-100,100)*.25,
                    robot.data.projected_gravity_b,commands,q.clamp(-100,100),
                    robot.data.joint_vel[:,ids].clamp(-100,100)*.05,previous.clamp(-100,100)),dim=1)
                action = model(obs)
                physical = (action*scales+default).clamp(-100,100)
            previous.copy_(action)
            env.action_manager.process_action(action)
            forces = torch.zeros(len(cases),device=env.device)
            for _ in range(cfg.decimation):
                env.action_manager.apply_action()
                scene.write_data_to_sim()
                env.sim.step(render=False)
                scene.update(args.dt)
                forces = torch.maximum(forces,contact.data.net_forces_w[:,protected].norm(dim=-1).max(dim=1).values)
            root_state = array(robot.data.root_state_w).copy()
            root_state[:,:3] -= array(scene.env_origins)
            root_state[:,1] -= np.arange(len(cases))*4
            for key,value in (('q',robot.data.joint_pos[:,ids]),('dq',robot.data.joint_vel[:,ids]),
                ('tau',robot.data.applied_torque[:,ids]),('root',root_state),
                ('targets',physical),('base_hip_force',forces)):
                records[key].append(array(value).copy() if isinstance(value,torch.Tensor) else value.copy())
    traces = {key:np.asarray(value) for key,value in records.items()}
    assert all(np.isfinite(value).all() for value in traces.values())
    BASE.mkdir(parents=True,exist_ok=True)
    trace_path = BASE/f'{tag}.npz'
    np.savez_compressed(trace_path,**traces)
    save_json(output,{'engine':'Isaac','suite':args.suite,'dt_s':args.dt,'cases':cases,
        'compiled':compiled,'kinematics':kinematics,'initial_root':initial_root.tolist(),
        'initial_joint_pos':array(positions[:,ids]).tolist(),
        'gravity':(0.,0.,0.) if args.suite == 'airborne' else cfg.sim.gravity,
        'policy_export_sha256':sha256(export_path(10000)) if model is not None else None,
        'config_sha256':sha256(CONFIG),'source_sha256':sha256(__file__),
        'protocol_source_sha256':sha256(ROOT/'scripts/physics57_protocol.py'),
        'trace_file':str(trace_path.relative_to(ROOT)), 'trace_sha256':sha256(trace_path)})
    print('DONE',output,flush=True)
except BaseException:
    import traceback
    traceback.print_exc()
    sys.stderr.flush()
    raise
finally:
    if env is not None:
        env.close()
    app.close()
