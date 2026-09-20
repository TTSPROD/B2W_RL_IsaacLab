"""Frozen 100-case Rough route evaluation; direct physics stepping without auto-reset."""
from __future__ import annotations
import argparse,json,math,sys,time,traceback
from pathlib import Path
sys.dont_write_bytecode=True
from b2w_runtime import PROJECT_ROOT as ROOT,configure_process,project_kit_args
from b2w_rough_runtime import ROUGH_TASK,make_rough_env_cfg,validate_environment
from rough_evaluation import FAMILIES,CASE_SEEDS,GEOMETRY_SEED,make_cases,digest,summarize
from benchmark_b2w import sha256,write_json,utc_now


def main():
    configure_process()
    from isaaclab.app import AppLauncher
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--policy',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--family',choices=FAMILIES,required=True);p.add_argument('--level',type=int,choices=range(3),required=True)
    p.add_argument('--physical_profile',choices=CASE_SEEDS,default='nominal')
    p.add_argument('--fixture',action='store_true',help='12-case,1s harness fixture; never acceptance')
    AppLauncher.add_app_launcher_args(p);p.set_defaults(headless=True,device='cuda:0')
    args=p.parse_args();args.policy=(ROOT/args.policy).resolve();args.report=(ROOT/args.report).resolve()
    if not args.policy.is_relative_to(ROOT) or not args.policy.is_file():raise ValueError('Policy must be inside project')
    if not args.report.is_relative_to(ROOT/'logs') or args.report.exists():raise ValueError('New project logs report required')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    cases=make_cases(args.family,args.level,args.physical_profile)
    if args.fixture:cases=[cases[i] for i in [0,1,2,3,60,61,62,63,80,81,82,83]]
    n=len(cases);report=dict(status='starting',started_utc=utc_now(),policy=str(args.policy.relative_to(ROOT)),
        policy_sha256=sha256(args.policy),family=args.family,level=args.level,physical_profile=args.physical_profile,
        cases=cases,cases_sha256=digest(cases),geometry_seed=GEOMETRY_SEED,fixture=args.fixture,
        policy_quality_evaluated=not args.fixture,auto_reset=False,
        source_sha256={f'scripts/{name}':sha256(ROOT/'scripts'/name) for name in ('replay_rough_b2w.py','rough_evaluation.py','rough_metrics.py','b2w_rough_runtime.py','b2w_rough_terrain.py','physical_evaluation.py')})
    save=lambda:write_json(args.report,report);save();app=env=None;exitcode=1
    try:
        args.kit_args=f'{args.kit_args} {project_kit_args()}'.strip();app=AppLauncher(args,fast_shutdown=True).app
        import gymnasium as gym
        import torch
        from check_stand_b2w import _nominal_cfg
        from physical_evaluation import configure_physical_evaluation,physical_evidence
        from rough_metrics import RoughMetrics
        torch.set_num_threads(4)
        cfg=make_rough_env_cfg(num_envs=n,device=args.device,seed=CASE_SEEDS[args.physical_profile],headless=True)
        gen=cfg.scene.terrain.terrain_generator;gen.seed=GEOMETRY_SEED;gen.num_cols=1
        tile=gen.sub_terrains[args.family];tile.proportion=1.;tile.geometry_seed=GEOMETRY_SEED
        gen.sub_terrains={args.family:tile}
        report['disabled_events']=_nominal_cfg(cfg)
        report['physical_spec']=configure_physical_evaluation(cfg,args.physical_profile)
        env=gym.make(ROUGH_TASK,cfg=cfg);base=env.unwrapped;env.reset(seed=CASE_SEEDS[args.physical_profile])
        robot=base.scene['robot'];terrain=base.scene.terrain
        terrain.terrain_levels[:]=args.level
        terrain.env_origins[:]=terrain.terrain_origins[args.level,terrain.terrain_types]
        base.scene.env_origins[:]=terrain.env_origins
        root=robot.data.default_root_state.clone();root[:,:3]+=base.scene.env_origins;root[:,7:]=0.
        root[:,1]+=torch.tensor([c['start_y'] for c in cases],device=base.device)
        yaw=torch.tensor([c['initial_yaw'] for c in cases],device=base.device)
        root[:,3:7]=0.;root[:,3]=torch.cos(yaw/2);root[:,6]=torch.sin(yaw/2)
        robot.write_root_state_to_sim(root)
        ids,names=robot.find_joints(cfg.joint_names,preserve_order=True)
        pos=robot.data.default_joint_pos.clone();pos[:,ids[:12]]+=torch.tensor([c['leg_offset'] for c in cases],device=base.device)
        robot.write_joint_state_to_sim(pos,torch.zeros_like(robot.data.default_joint_vel))
        base.scene.reset();base.scene.write_data_to_sim();base.scene.update(dt=0.)
        report['runtime']=validate_environment(env,expected_level=args.level)
        report['physical_evidence']=physical_evidence(base)
        metrics=RoughMetrics(base);report['collision_geometry']=metrics.geometry;save()
        actor=torch.jit.load(str(args.policy),map_location=base.device).eval()
        command=base.command_manager.get_command('base_velocity');previous=torch.zeros((n,16),device=base.device)
        base.action_manager.process_action(previous)
        dt=cfg.sim.dt;policy_dt=dt*cfg.decimation
        total_steps=50 if args.fixture else 1100;settle=0 if args.fixture else 100
        failures=[None]*n;errors=[];bias=[];route_max=torch.zeros(n,device=base.device)
        rollback=torch.zeros(n,device=base.device);last_x=root[:,0].clone();max_tilt=torch.zeros_like(route_max)
        stall_time=torch.zeros_like(route_max);stall_origin=root[:,0].clone();stall_max=torch.zeros_like(route_max)
        action_clip=torch.zeros_like(route_max);obs_clip=torch.zeros_like(route_max)
        max_obs_error=max_target_error=0.;scales=torch.tensor([.125,.25,.25]*4,device=base.device)
        traverse=torch.tensor([c['kind']=='traverse' for c in cases],device=base.device)
        vx=torch.tensor([c['vx'] for c in cases],device=base.device)
        turn=torch.tensor([c['yaw'] for c in cases],device=base.device)
        with torch.inference_mode():
            for step in range(total_steps):
                if not app.is_running():raise RuntimeError('App stopped early')
                measured=(step-settle)*policy_dt
                command.zero_()
                if step>=settle:
                    command[:,0]=torch.where(traverse | (measured<12.),vx,0.)
                    if measured>=12.:command[:,2]=turn
                obs=base.observation_manager.compute()['policy']
                joint=robot.data.joint_pos[:,ids]-robot.data.default_joint_pos[:,ids];joint[:,12:]=0
                terms=[robot.data.root_ang_vel_b,robot.data.projected_gravity_b,command,joint,robot.data.joint_vel[:,ids],previous]
                independent=torch.cat([v.clamp(-100,100)*s for v,s in zip(terms,(.25,1.,1.,1.,.05,1.))],1)
                max_obs_error=max(max_obs_error,float((obs-independent).abs().max()))
                if max_obs_error>1e-5 or not torch.isfinite(obs).all():raise ValueError('Rough actor ABI failed')
                obs_clip+=torch.cat(terms,1).abs().gt(100).any(1)
                action=actor(obs)
                if not torch.isfinite(action).all():raise ValueError('Nonfinite policy action')
                action_clip+=action.abs().gt(100).any(1)
                base.action_manager.process_action(action)
                expected_pos=(action[:,:12]*scales+robot.data.default_joint_pos[:,ids[:12]]).clamp(-100,100)
                expected_vel=(action[:,12:]*5).clamp(-100,100)
                error=max(float((expected_pos-base.action_manager.get_term('joint_pos').processed_actions).abs().max()),
                          float((expected_vel-base.action_manager.get_term('joint_vel').processed_actions).abs().max()))
                max_target_error=max(max_target_error,error)
                if error>1e-5:raise ValueError('Action target parity after clipping failed')
                previous=action.clone()
                for substep in range(cfg.decimation):
                    base._sim_step_counter+=1;base.action_manager.apply_action();base.scene.write_data_to_sim()
                    base.sim.step(render=False);base.scene.update(dt=dt)
                    contact,tilted=metrics.physics(dt)
                    relative=robot.data.root_pos_w-base.scene.env_origins
                    route_max=torch.maximum(route_max,relative[:,0])
                    rollback+=(last_x-robot.data.root_pos_w[:,0]).clamp_min(0);last_x=robot.data.root_pos_w[:,0].clone()
                    angle=torch.acos((-robot.data.projected_gravity_b[:,2]).clamp(-1,1))*180/math.pi
                    max_tilt=torch.maximum(max_tilt,angle)
                    wheel=robot.data.body_link_pos_w[:,metrics.wheels]-base.scene.env_origins[:,None,:]
                    outside=(wheel[:,:,1].abs()>.9).any(1)|(wheel[:,:,0]<-.6).any(1)|(wheel[:,:,0]>5.4).any(1)
                    causes={'body_contact':contact>1.,'tilt':tilted,'corridor':outside}
                    anyfail=torch.stack(list(causes.values())).any(0)
                    for index in anyfail.nonzero().flatten().tolist():
                        if failures[index] is None:
                            forces=metrics.sensor.data.net_forces_w[index].norm(dim=-1)
                            failures[index]=dict(time_s=step*policy_dt+(substep+1)*dt,
                                reasons=[key for key,value in causes.items() if bool(value[index])],
                                contact_bodies={metrics.sensor.body_names[i]:float(forces[i]) for i in metrics.forbidden if forces[i]>1.},
                                root_relative=relative[index].tolist(),tilt_deg=float(angle[index]))
                metrics.sample_geometry()
                if step>=settle:
                    actual=torch.cat((robot.data.root_lin_vel_b[:,:2],robot.data.root_ang_vel_b[:,2:3]),1)
                    errors.append((actual-command).square());bias.append(actual-command)
                    forward=command[:,0]>.05
                    advanced=robot.data.root_pos_w[:,0]-stall_origin>=.05
                    stall_time=torch.where(forward&~advanced,stall_time+policy_dt,0.)
                    stall_origin=torch.where(advanced|~forward,robot.data.root_pos_w[:,0],stall_origin)
                    stall_max=torch.maximum(stall_max,stall_time)
                if step%100==99:
                    report.update(policy_steps_completed=step+1,failed_cases=sum(f is not None for f in failures));save()
                    print(f'[ROUGH] {step+1}/{total_steps}, failures={report["failed_cases"]}',flush=True)
        after=physical_evidence(base)
        if after['properties_sha256']!=report['physical_evidence']['properties_sha256']:raise ValueError('Bounded physics did not persist')
        report['physical_evidence']['persistent_through_replay']=True
        err=torch.stack(errors);signed=torch.stack(bias);rows=[]
        for i,case in enumerate(cases):
            goal=float(route_max[i])>=3.
            if not goal and failures[i] is None:failures[i]=dict(time_s=22.,reasons=['route_incomplete'])
            rows.append(dict(index=case['index'],success=failures[i] is None,first_failure=failures[i],
                squared_error_sum=err[:,i].sum(0).tolist(),measurement_steps=len(err),rms=err[:,i].mean(0).sqrt().tolist(),
                error_p95=torch.quantile(signed[:,i].abs(),.95,dim=0).tolist(),error_max=signed[:,i].abs().amax(0).tolist(),
                signed_bias=signed[:,i].mean(0).tolist(),route_progress_m=float(route_max[i]),rollback_m=float(rollback[i]),
                max_stall_seconds=float(stall_max[i]),max_tilt_deg=float(max_tilt[i]),
                action_clipping_steps=int(action_clip[i]),observation_clipping_steps=int(obs_clip[i])))
        report.update(status='completed',results=rows,summary=None if args.fixture else summarize(cases,rows),
                      metrics=metrics.finish(),live_observation_max_error=max_obs_error,action_target_max_error=max_target_error,
                      physics_steps_completed=total_steps*cfg.decimation,fixture_passed=args.fixture)
        exitcode=0
    except BaseException as exc:
        report.update(status='failed',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        if env is not None:
            try:env.close()
            except BaseException as exc:report.update(status='failed',cleanup_error=str(exc));exitcode=1
        report['finished_utc']=utc_now();save()
        if app is not None:app.app.post_quit(exitcode);app.close()
    return exitcode


if __name__=='__main__':raise SystemExit(main())
