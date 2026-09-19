"""Visible Isaac Sim Flat policy playback controlled by the connected Xbox gamepad."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback
sys.dont_write_bytecode = True
from b2w_runtime import PROJECT_ROOT as ROOT, FLAT_TASK, configure_process, make_flat_env_cfg, project_kit_args
from b2w_gamepad import XInputController, CommandMapper
from check_stand_b2w import _nominal_cfg

QUALIFICATION = ROOT / 'docs/results/2026-09-19-reference-qualification-resume-final.json'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def qualified_policy(seed):
    job = read(QUALIFICATION)
    if job['status'] != 'completed' or not job['decision']['flat_transfer_gate_passed']:
        raise ValueError('Three-seed Flat qualification did not pass')
    stage = job['exports'][f'seed{seed}']
    report = (ROOT / stage['report']).resolve()
    if not report.is_relative_to(ROOT) or digest(report) != stage['report_sha256']:
        raise ValueError('Export report hash mismatch')
    export = read(report)['training_export']
    policy = (ROOT / export['export']).resolve()
    checkpoint = (ROOT / export['checkpoint']).resolve()
    if (not policy.is_relative_to(ROOT) or not checkpoint.is_relative_to(ROOT)
            or export['status'] != 'passed' or digest(policy) != export['export_sha256']
            or digest(checkpoint) != export['checkpoint_sha256']):
        raise ValueError('Qualified policy provenance mismatch')
    return policy, export

def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(path)

def check_finite_tensor(value, name, torch, device):
    if str(value.device) != str(torch.device(device)):
        raise RuntimeError(f'Unexpected viewer tensor device: {name}: {value.device}')
    if not bool(torch.isfinite(value).all()):
        raise RuntimeError(f'Nonfinite viewer tensor: {name}')


def configure_storm_visuals(stage):
    """Author display-only USD materials before PhysX tensor views are created."""
    from pxr import UsdShade, Sdf, UsdGeom, UsdPhysics
    materials = {}
    for name, color in {'body': (.55,.6,.66), 'wheel': (.045,.05,.055), 'floor': (.24,.26,.29)}.items():
        path = f'/World/ViewerMaterials/{name}'
        material = UsdShade.Material.Define(stage, path)
        shader = UsdShade.Shader.Define(stage, path+'/Shader')
        shader.CreateIdAttr('UsdPreviewSurface')
        shader.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(color)
        shader.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(.8)
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), 'surface')
        materials[name] = material
    for prim in list(stage.Traverse()):
        if prim.IsA(UsdGeom.Mesh) or prim.HasAPI(UsdPhysics.RigidBodyAPI):
            path = str(prim.GetPath())
            name = ('wheel' if ('wheel' in path.lower() or '_foot' in path.lower()) else 'body') if '/Robot/' in path else 'floor'
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(materials[name], UsdShade.Tokens.strongerThanDescendants)
    # Display-only floor and one-meter grid: no collision/physics API.
    floor = UsdGeom.Mesh.Define(stage, '/World/ViewerFloor')
    floor.CreatePointsAttr([(-100.,-100.,-.005),(100.,-100.,-.005),(100.,100.,-.005),(-100.,100.,-.005)])
    floor.CreateFaceVertexCountsAttr([4]); floor.CreateFaceVertexIndicesAttr([0,1,2,3])
    floor.CreateSubdivisionSchemeAttr('none')
    UsdShade.MaterialBindingAPI.Apply(floor.GetPrim()).Bind(materials['floor'])
    grid = UsdGeom.BasisCurves.Define(stage, '/World/ViewerGrid')
    grid.CreateTypeAttr('linear')
    points=[]
    for n in range(-100,101):
        points.extend([(-100.,float(n),.002),(100.,float(n),.002),(float(n),-100.,.002),(float(n),100.,.002)])
    grid.CreatePointsAttr(points); grid.CreateCurveVertexCountsAttr([2]*(len(points)//2))
    grid.CreateWidthsAttr([.012]); grid.SetWidthsInterpolation('constant')
    grid.CreateDisplayColorAttr([(.36,.4,.44)])


def main():
    configure_process()
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    # Load the project h5py DLLs before Kit adds its renderer DLL search paths.
    # GUI extension discovery imports recorder_manager; otherwise Windows can
    # resolve an incompatible already-loaded native dependency (0xc0000139).
    import h5py  # noqa: F401
    from isaaclab.app import AppLauncher
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy-seed', type=int, choices=(54, 55, 56), default=54)
    parser.add_argument('--max-forward', type=float, default=1.)
    parser.add_argument('--max-lateral', type=float, default=1.)
    parser.add_argument('--max-yaw', type=float, default=1.)
    parser.add_argument('--renderer', dest='viewer_renderer', choices=('storm', 'rtx'), default='storm')
    parser.add_argument('--graphics-api', choices=('vulkan', 'd3d12'), default=None)
    parser.add_argument('--gamepad-index', type=int, choices=range(4), default=0)
    AppLauncher.add_app_launcher_args(parser)
    parser.set_defaults(headless=False, device='cpu', rendering_mode='performance')
    args = parser.parse_args()
    if args.headless:
        parser.error('This viewer requires a visible GUI')
    args.graphics_api = args.graphics_api or ('vulkan' if args.viewer_renderer == 'storm' else 'd3d12')
    if args.viewer_renderer == 'storm' and (args.graphics_api != 'vulkan' or args.device != 'cpu'):
        parser.error('Storm viewer requires Vulkan and CPU physics for USD pose updates')
    policy_path, export = qualified_policy(args.policy_seed)
    controller, mapper = XInputController(args.gamepad_index), CommandMapper(args.max_forward, args.max_lateral, args.max_yaw)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'logs/teleop' / stamp
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'starting', 'started_utc': stamp, 'policy_seed': args.policy_seed,
              'task': FLAT_TASK, 'policy': str(policy_path.relative_to(ROOT)),
              'policy_sha256': digest(policy_path), 'checkpoint_sha256': export['checkpoint_sha256'],
              'controller': 'Windows XInput Xbox', 'gamepad_index': args.gamepad_index,
              'graphics_api': args.graphics_api, 'simulation_device': args.device, 'simulation_only': True, 'num_envs': 1, 'physics_dt': .005, 'policy_dt': .02,
              'command_limits_vx_vy_yaw': [args.max_forward, args.max_lateral, args.max_yaw], 'renderer_requested': args.viewer_renderer, 'rendering_mode': args.rendering_mode, 'dead_zone': .15,
              'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in
                  (Path(__file__), ROOT/'scripts/b2w_gamepad.py', ROOT/'scripts/b2w_runtime.py', ROOT/'scripts/check_stand_b2w.py', ROOT/'apps/b2w.gamepad.storm.kit')},
              'ui_automation_note': 'Computer Use helper unavailable (Windows1058); viewport captured through native Kit API'}
    save(out/'status.json', report)
    print('SESSION', out, flush=True)
    app = env = None
    try:
        args.kit_args = f'{args.kit_args} {project_kit_args()} --/app/vulkan={str(args.graphics_api == "vulkan").lower()}'.strip()
        if args.viewer_renderer == 'storm':
            if not args.experience:
                args.experience = str(ROOT/'apps/b2w.gamepad.storm.kit')
            args.kit_args += f' --ext-folder {(ROOT/".runtime/IsaacLab/apps").as_posix()} --ext-folder {(ROOT/".runtime/IsaacLab/source").as_posix()}'
            sim_package = ROOT/'.venv/Lib/site-packages/isaacsim'
            for folder in ('exts', 'extscache', 'extsPhysics', 'extsDeprecated', 'kit/exts', 'kit/extscore'):
                args.kit_args += f' --ext-folder {(sim_package/folder).as_posix()}'
            args.kit_args += f' --/app/extensions/registryCache={(ROOT/".cache/kit/extensions").as_posix()} --/exts/omni.kit.registry.nucleus/cachePath={(ROOT/".cache/kit/registry").as_posix()}'
            args.kit_args += ' --/exts/omni.kit.registry.nucleus/cacheCreateLinks=false --/exts/omni.kit.registry.nucleus/tryBothHttpAndHttps=false'
            args.kit_args += ' --/renderer/enabled=pxr --/renderer/active=pxr --/pxr/rendermode=HdStormRendererPlugin --/physics/updateToUsd=true --/physics/updateVelocitiesToUsd=true'
        app = AppLauncher(args, fast_shutdown=True).app
        import gymnasium as gym
        import torch
        import carb
        import omni.ui as ui
        from isaaclab.sim import DomeLightCfg, DistantLightCfg
        from omni.kit.viewport.utility import get_active_viewport, capture_viewport_to_file
        torch.set_num_threads(1)
        settings = carb.settings.get_settings()
        report['original_main_rate_limit'] = {'enabled': settings.get('/app/runLoops/main/rateLimitEnabled'), 'frequency': settings.get('/app/runLoops/main/rateLimitFrequency')}
        settings.set_bool('/app/runLoops/main/rateLimitEnabled', False)
        carb.settings.get_settings().set_bool('/persistent/app/omniverse/gamepadCameraControl', False)
        cfg = make_flat_env_cfg(num_envs=1, device=args.device, seed=args.policy_seed, headless=False)
        _nominal_cfg(cfg)
        if args.viewer_renderer == 'storm':
            cfg.sim.use_fabric = False
            cfg.sim.render.antialiasing_mode = None
        # Visual-only overrides avoid unrelated remote HDR/MDL downloads.
        cfg.scene.terrain.visual_material = None
        cfg.scene.sky_light.spawn = (DistantLightCfg(intensity=3., color=(1., 1., 1.)) if args.viewer_renderer == 'storm'
                                     else DomeLightCfg(intensity=1800., color=(.85, .9, 1.)))
        cfg.viewer.origin_type = 'world'
        cfg.viewer.eye = (3., -3., 2.)
        cfg.viewer.lookat = (0., 0., .6)
        cfg.viewer.resolution = (1280, 800)
        cfg.episode_length_s = 86400.
        if args.viewer_renderer == 'storm':
            from pxr import UsdGeom, UsdPhysics
            import omni.usd
            original_spawn = cfg.scene.robot.spawn.func
            def spawn_with_preview(prim_path, spawn_cfg, *spawn_args, **spawn_kwargs):
                prim = original_spawn(prim_path, spawn_cfg, *spawn_args, **spawn_kwargs)
                configure_storm_visuals(omni.usd.get_context().get_stage())
                return prim
            cfg.scene.robot.spawn.func = spawn_with_preview
        env = gym.make(FLAT_TASK, cfg=cfg)
        base = env.unwrapped
        stage = base.sim.stage
        viewport = get_active_viewport()
        if viewport is None:
            raise RuntimeError('The viewer requires an active viewport')
        if viewport is not None:
            viewport.fill_frame = False
            viewport.resolution = (1280, 720)
            if args.viewer_renderer == 'storm':
                viewport.set_hd_engine('pxr', 'HdStormRendererPlugin')
        report['viewport_engine'] = viewport.hydra_engine
        report['viewport_delegate'] = viewport.render_mode
        if args.viewer_renderer == 'storm' and (viewport.hydra_engine != 'pxr' or viewport.render_mode != 'HdStormRendererPlugin'):
            raise RuntimeError('Storm viewport delegate did not activate')
        report['renderer_active'] = settings.get('/renderer/active')
        report['renderer_enabled'] = settings.get('/renderer/enabled')
        report['pxr_delegate'] = settings.get('/pxr/rendermode')
        report['usd_pose_updates'] = settings.get('/physics/updateToUsd')
        report['fabric_enabled'] = settings.get('/physics/fabricEnabled')
        if args.viewer_renderer == 'storm' and report['renderer_enabled'] != 'pxr':
            raise RuntimeError(f'Unexpected enabled renderers: {report["renderer_enabled"]}')
        env.reset(seed=args.policy_seed)
        robot = base.scene['robot']
        usd_body_prims = {}
        max_visual_position_error = 0.
        if args.viewer_renderer == 'storm':
            usd_body_prims = {prim.GetName(): prim for prim in stage.Traverse()
                              if '/Robot/' in str(prim.GetPath()) and prim.HasAPI(UsdPhysics.RigidBodyAPI)}
            if set(robot.body_names) != set(usd_body_prims):
                raise RuntimeError('Incomplete USD body pose verification map')
        policy = torch.jit.load(str(policy_path), map_location=args.device).eval()
        ids, names = robot.find_joints(cfg.joint_names, preserve_order=True)
        if names != cfg.joint_names or base.action_manager.total_action_dim != 16:
            raise RuntimeError('Action/joint contract mismatch')
        if base.observation_manager.active_terms['policy'] != ['base_ang_vel','projected_gravity','velocity_commands','joint_pos','joint_vel','actions']:
            raise RuntimeError('Observation term contract mismatch')
        dt, decimation = cfg.sim.dt, cfg.decimation
        if dt != .005 or decimation != 4:
            raise RuntimeError('Qualified policy requires200Hz physics/50Hz control')
        command = base.command_manager.get_command('base_velocity')
        flags = {'reset': False, 'follow': True}
        def request_reset(): flags['reset'] = True
        def toggle_camera(): flags['follow'] = not flags['follow']
        window = ui.Window('B2W Flat - Xbox Controller', width=390, height=300)
        with window.frame:
            with ui.VStack(spacing=5):
                ui.Label(f'Qualified Flat policy: seed{args.policy_seed} / model349', height=24)
                ui.Label('HOLD LB + left stick: move / strafe', height=22)
                ui.Label('HOLD LB + right stick: turn', height=22)
                ui.Label('Release LB: stop. B: brake (release LB to rearm)', height=22)
                ui.Label('A: reset robot     X: toggle follow camera', height=22)
                state_label = ui.Label('Starting...', height=24)
                velocity_label = ui.Label('', height=24)
                ui.Button('Reset robot (A)', clicked_fn=request_reset, height=26)
                ui.Button('Toggle follow camera (X)', clicked_fn=toggle_camera, height=26)
        previous_action = torch.zeros((1,16),device=base.device)
        def reset_robot():
            nonlocal previous_action
            root = robot.data.default_root_state.clone()
            root[:,:3] += base.scene.env_origins
            root[:,7:] = 0.
            robot.write_root_state_to_sim(root)
            robot.write_joint_state_to_sim(robot.data.default_joint_pos.clone(), torch.zeros_like(robot.data.default_joint_vel))
            base.scene.reset()
            base.action_manager.reset()
            previous_action.zero_()
            command.zero_()
            base.action_manager.process_action(previous_action)
            base.scene.write_data_to_sim()
            base.scene.update(dt=0.)
            base.sim.forward()
            mapper.command = (0.,0.,0.)
        reset_robot()
        timing_sums = dict(policy=0., physics=0., rendering=0., other=0.)
        timing_frames, timing_window_start, last_performance = 0, time.perf_counter(), {}
        frame, resets, max_obs_error, max_target_error = 0, 0, 0., 0.
        motion_frames, packet_changes, previous_packet = 0, 0, None
        fallen = False
        settle_frames = 100
        started, last_log = time.perf_counter(), 0.
        capture_requested = False
        viewport_capture = None
        report['status'] = 'running'
        save(out/'status.json', report)
        with torch.inference_mode():
            while app.is_running():
                loop_start = time.perf_counter()
                pad = controller.read()
                velocity, reset, camera = mapper.advance(pad, dt * decimation)
                if pad.connected and pad.packet != previous_packet:
                    packet_changes += 1; previous_packet = pad.packet
                if camera: toggle_camera()
                if reset or flags['reset']:
                    reset_robot(); flags['reset'] = False; fallen = False; resets += 1
                    settle_frames = 100
                if not base.sim.is_playing():
                    mapper.command = (0.,0.,0.)
                    base.sim.render()
                    time.sleep(.01)
                    continue
                if fallen or settle_frames > 0:
                    velocity = (0.,0.,0.); mapper.command = velocity
                    settle_frames = max(0, settle_frames - 1)
                policy_started = time.perf_counter()
                command[:] = torch.tensor(velocity, device=base.device)
                obs = base.observation_manager.compute()['policy']
                position = robot.data.joint_pos[:,ids] - robot.data.default_joint_pos[:,ids]
                position[:,12:] = 0.
                terms = [robot.data.root_ang_vel_b,robot.data.projected_gravity_b,command,
                         position,robot.data.joint_vel[:,ids],previous_action]
                independent = torch.cat([term.clamp(-100,100)*scale for term,scale in zip(terms,(.25,1.,1.,1.,.05,1.))],dim=1)
                error = float((obs-independent).abs().max());max_obs_error=max(max_obs_error,error)
                if tuple(obs.shape)!=(1,57) or error>1e-5: raise RuntimeError('Live observation parity failed')
                action=policy(obs); check_finite_tensor(action,'policy_action',torch,base.device)
                if tuple(action.shape)!=(1,16) or bool((action.abs()>100).any()):raise RuntimeError('Action shape/saturation mismatch')
                base.action_manager.process_action(action)
                expected_pos=(action[:,:12]*torch.tensor([.125,.25,.25]*4,device=base.device)+robot.data.default_joint_pos[:,ids[:12]]).clamp(-100,100)
                expected_vel=(action[:,12:]*5.).clamp(-100,100)
                target_error=max(float((base.action_manager.get_term('joint_pos').processed_actions-expected_pos).abs().max()),
                                 float((base.action_manager.get_term('joint_vel').processed_actions-expected_vel).abs().max()))
                max_target_error=max(max_target_error,target_error)
                if target_error>1e-5:raise RuntimeError('Live action target parity failed')
                previous_action=action.clone()
                policy_seconds = time.perf_counter() - policy_started
                physics_seconds, rendering_seconds = 0., 0.
                for substep in range(decimation):
                    physics_started = time.perf_counter()
                    base._sim_step_counter+=1
                    base.action_manager.apply_action();base.scene.write_data_to_sim()
                    base.sim.step(render=False)
                    base.scene.update(dt=dt)
                    physics_seconds += time.perf_counter() - physics_started
                    if base._sim_step_counter % cfg.sim.render_interval == 0:
                        render_started = time.perf_counter()
                        base.sim.render()
                        rendering_seconds += time.perf_counter() - render_started
                check_finite_tensor(torch.cat((robot.data.root_state_w,robot.data.joint_pos,robot.data.joint_vel),1),'state',torch,base.device)
                root_position=robot.data.root_pos_w[0].tolist()
                fallen |= float(robot.data.projected_gravity_b[0,2])>-.4 or root_position[2]<.25
                if flags['follow'] and frame%5==0:
                    x,y,z=root_position
                    base.sim.set_camera_view((x+3.,y-3.,z+1.8),(x,y,z))
                timing_sums['policy'] += policy_seconds
                timing_sums['physics'] += physics_seconds
                timing_sums['rendering'] += rendering_seconds
                timing_sums['other'] += time.perf_counter() - loop_start - policy_seconds - physics_seconds - rendering_seconds
                timing_frames += 1
                if timing_frames >= 100:
                    elapsed = time.perf_counter() - timing_window_start
                    last_performance = {'policy_fps': timing_frames / elapsed, 'realtime_factor': timing_frames * .02 / elapsed,
                                        'mean_ms': {k: 1000 * v / timing_frames for k, v in timing_sums.items()}}
                    timing_sums = dict(policy=0., physics=0., rendering=0., other=0.)
                    timing_frames, timing_window_start = 0, time.perf_counter()
                frame+=1;motion_frames+=int(any(abs(v)>1e-4 for v in velocity))
                status='DISCONNECTED - zero command' if not pad.connected else ('FALL - press A to reset' if fallen else ('DRIVING' if any(velocity) else 'READY - hold LB to move'))
                state_label.text=status + (f"  | {last_performance['policy_fps']:.0f} FPS / {last_performance['realtime_factor']:.2f}x" if last_performance else '')
                velocity_label.text=f'vx {velocity[0]:+.2f}  vy {velocity[1]:+.2f} m/s   yaw {velocity[2]:+.2f} rad/s'
                if (frame>=150 and not capture_requested) or frame%500==0:
                    viewport=get_active_viewport()
                    if viewport is not None:
                        viewport_capture = capture_viewport_to_file(viewport,str(out/'viewport.png'))
                        capture_requested=True
                if loop_start-last_log>=1.:
                    if usd_body_prims:
                        xforms = UsdGeom.XformCache()
                        positions = robot.data.body_pos_w[0].tolist()
                        visual_error = max(max(abs(float(a)-float(b)) for a,b in zip(
                            xforms.GetLocalToWorldTransform(usd_body_prims[name]).ExtractTranslation(), pos))
                            for name,pos in zip(robot.body_names,positions))
                        max_visual_position_error=max(max_visual_position_error,visual_error)
                        if visual_error>.001: raise RuntimeError(f'USD/physics body position mismatch: {visual_error}')
                    report.update(status='running',updated_utc=datetime.now(timezone.utc).isoformat(),
                         policy_frames=frame,sim_seconds=frame*dt*decimation,wall_seconds=loop_start-started,
                         gamepad_connected=pad.connected,gamepad_packet=pad.packet,packet_changes=packet_changes,
                         buttons=pad.buttons,sticks=[pad.lx,pad.ly,pad.rx,pad.ry],command=list(velocity),
                         root_position=root_position,actual_velocity=robot.data.root_lin_vel_b[0].tolist(),
                         actual_yaw_rate=float(robot.data.root_ang_vel_b[0,2]),
                         resets=resets,motion_command_frames=motion_frames,fallen=fallen,
                         live_observation_max_error=max_obs_error,live_action_target_max_error=max_target_error,
                         visual_body_position_max_error_m=max_visual_position_error,
                         performance=last_performance,
                         viewport_resolution=list(viewport.resolution) if viewport else None,
                         viewport_fps=viewport.fps if viewport else None,
                         viewport_capture=str((out/'viewport.png').relative_to(ROOT)),gui_status=status)
                    save(out/'status.json',report);last_log=loop_start
                time.sleep(max(0.,dt*decimation-(time.perf_counter()-loop_start)))
        report['status']='closed'
    except BaseException as exc:
        report.update(status='failed',error=str(exc),traceback=traceback.format_exc())
        raise
    finally:
        report['finished_utc']=datetime.now(timezone.utc).isoformat()
        save(out/'status.json',report)
        if env is not None:env.close()
        if app is not None:app.close()

if __name__=='__main__':
    main()
