"""Offline paired height/yaw diagnosis with failure censoring and explicit reward provenance."""
import json
import re
from pathlib import Path
import numpy as np
import yaml
from b2w_runtime import PROJECT_ROOT as ROOT
from benchmark_b2w import sha256, utc_now, write_json
from yaw_trace_analysis import load_trace, mesh_vertices, bottom_point

JOB = ROOT/'logs/diagnostics/height_yaw_diagnostics_20260919/job.json'
PRIOR = ROOT/'logs/ablations/flat_height_dev50_51_20260919/job.json'
OUTPUT = ROOT/'docs/results/2026-09-19-height-yaw-diagnosis.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def stats(values):
    x = np.asarray(values)
    if x.size == 0:
        return None
    if not np.isfinite(x).all():
        raise ValueError('Nonfinite diagnostic values')
    q = np.quantile(x, [0, .05, .5, .95, 1])
    return dict(zip(('min', 'p05', 'median', 'p95', 'max'), map(float, q))) | {'mean':float(x.mean())}


def failure_times(report, env_ids):
    mapping = {f['env']:f['time_s'] for f in report['first_failures']}
    return np.array([mapping.get(i, np.inf) for i in env_ids])


def paired_mask(times, left_failures, right_failures, settling=2.):
    times = np.asarray(times)
    stop = np.minimum(left_failures, right_failures)
    return (times[:,None] > settling + 1e-7) & (times[:,None] < stop[None,:] - 1e-7)


def default_pose(config, names):
    rules = config['scene']['robot']['init_state']['joint_pos']
    pose = []
    for name in names:
        hits = [float(v) for expr,v in rules.items() if re.fullmatch(expr,name)]
        if len(hits) != 1:
            raise ValueError('Ambiguous default joint position: '+name)
        pose.append(hits[0])
    return np.array(pose)


def reward_terms(arr, config, meta):
    """Unweighted scalar terms at recorded states, not a training reward measurement."""
    rewards = config['rewards']
    upright = np.clip(-arr['projected_gravity'][...,2], 0, .7)/.7
    error = arr['actual']-arr['command']
    pose = rewards['joint_pos_penalty']['params']
    indices = [meta['policy_joint_names'].index(n) for n in pose['asset_cfg']['joint_names']]
    deviation = arr['joint_pos'][...,indices] - default_pose(config,meta['policy_joint_names'])[indices]
    moving = (np.linalg.norm(arr['command'],axis=-1)>float(pose['command_threshold'])) | (np.linalg.norm(arr['actual'][...,:2],axis=-1)>float(pose['velocity_threshold']))
    height_cfg = rewards.get('base_height_l2')
    target = float(height_cfg['params']['target_height']) if isinstance(height_cfg,dict) else .60
    return {
        'base_height_l2':(arr['root_pos'][...,2]-target)**2*upright,
        'joint_pos_penalty':np.linalg.norm(deviation,axis=-1)*np.where(moving,1.,float(pose['stand_still_scale']))*upright,
        'upward':(1-arr['projected_gravity'][...,2])**2,
        'track_lin_vel_xy_exp':np.exp(-np.sum(error[...,:2]**2,axis=-1)/float(rewards['track_lin_vel_xy_exp']['params']['std'])**2)*upright,
        'track_ang_vel_z_exp':np.exp(-error[...,2]**2/float(rewards['track_ang_vel_z_exp']['params']['std'])**2)*upright,
    }


def derived(arr, meta, geometry):
    gaps = {}
    for b,name in enumerate(meta['body_names']):
        if name.endswith('_calf'):
            gaps[name] = bottom_point(arr['body_pos'][:,:,b],arr['body_quat'][:,:,b],geometry[name])[0]
    return {'gaps':gaps, 'minimum_calf_gap':np.min(np.stack(list(gaps.values())),axis=0)}


def metrics(arr, meta, d, mask, config=None, policy_dt=.02):
    if not mask.any():
        return {'physics_samples':0, 'policy_samples':0}
    t = arr['time_s']
    boundary = (np.arange(len(t))%4==3)[:,None]
    policy_mask = mask & boundary
    err = arr['actual']-arr['command']
    clipped = np.abs(arr['computed_torque'][...,:12]-arr['applied_torque'][...,:12])>1e-3
    contact = np.linalg.norm(arr['contact_force'],axis=-1)
    out = {
        'physics_samples':int(mask.sum()), 'policy_samples':int(policy_mask.sum()),
        'height_m':stats(arr['root_pos'][...,2][mask]),
        'height_abs_error060_m':stats(np.abs(arr['root_pos'][...,2][mask]-.60)),
        'height_below055_fraction':float((arr['root_pos'][...,2][mask]<.55).mean()),
        'tilt_deg':stats(np.degrees(np.arccos(np.clip(-arr['projected_gravity'][...,2],-1,1)))[mask]),
        'minimum_calf_clearance_m':stats(d['minimum_calf_gap'][mask]),
        'calf_clearance_m':{n:stats(v[mask]) for n,v in d['gaps'].items()},
        'leg_clipping_fraction':float(clipped.any(-1)[mask].mean()),
        'max_leg_torque_clip_delta_nm':float(np.abs(arr['computed_torque'][...,:12]-arr['applied_torque'][...,:12])[mask].max()),
        'contact_force_max_n_by_body':dict(zip(meta['body_names'],contact[mask].max(0).tolist())),
        'joint_mean_rad':dict(zip(meta['policy_joint_names'][:12],arr['joint_pos'][...,:12][mask].mean(0).tolist())),
        'joint_velocity_rms_rad_s':dict(zip(meta['policy_joint_names'][:12],np.sqrt((arr['joint_vel'][...,:12][mask]**2).mean(0)).tolist())),
        'action_abs_max':float(np.abs(arr['action'][mask]).max()),
        'leg_target_abs_max_rad':float(np.abs(arr['joint_pos_target'][...,:12][mask]).max()),
    }
    if policy_mask.any():
        out['rms_vx_vy_yaw'] = np.sqrt((err[policy_mask]**2).mean(0)).tolist()
        out['signed_bias_vx_vy_yaw'] = err[policy_mask].mean(0).tolist()
        if config is not None:
            terms = reward_terms(arr,config,meta)
            out['offline_reward_terms'] = {}
            for name, raw in terms.items():
                term = config['rewards'].get(name)
                weight = float(term['weight']) if isinstance(term,dict) else 0.
                average = float(raw[policy_mask].mean())
                out['offline_reward_terms'][name] = {'unweighted_mean':average,'weight':weight,'weighted_per_second_mean':average*weight,'weighted_per_policy_step_mean':average*weight*policy_dt}
            # Trace covers four calves, not every non-wheel body. This is explicitly a proxy.
            calf_ids=[i for i,n in enumerate(meta['body_names']) if n.endswith('_calf')]
            forces=contact[:,:,calf_ids].reshape(-1,4,len(meta['env_ids']),len(calf_ids))
            contact_cfg=config['rewards']['undesired_contacts']
            count=(forces[:,1:].max(1)>float(contact_cfg['params']['threshold'])).sum(-1)
            pm=policy_mask[3::4]
            avg=float(count[pm].mean())
            weight=float(contact_cfg['weight'])
            out['calf_only_last3_contact_proxy']={'mean_body_count':avg,'weight':weight,'weighted_per_second_mean':avg*weight,'not_full_undesired_contact_term':True}
    return out


def training_windows(prior):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    out,configs={},{}
    for phase in ('train_seed50','train_seed51'):
        for run in prior[phase]['runs']:
            label=f"seed{run['seed']}_{run['arm']}"
            manifest_path=ROOT/run['training_manifest'];manifest=read(manifest_path)
            directory=manifest_path.parent;cfgpath=directory/'params/env.yaml'
            cfg=yaml.load(cfgpath.read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
            if manifest['effective_undesired_contact_weight']!=-3 or manifest['effective_yaw_tracking_weight']!=1.5:
                raise ValueError('Unexpected training reward config')
            height_term=cfg['rewards'].get('base_height_l2')
            actual_height_weight=float(height_term['weight']) if isinstance(height_term,dict) else 0.
            if actual_height_weight!=manifest['effective_base_height_weight']:
                raise ValueError('Manifest/config height mismatch')
            if isinstance(height_term,dict) and (float(height_term['params']['target_height'])!=.60 or height_term['params']['sensor_cfg']!='null'):
                raise ValueError('Unsupported height formula configuration')
            for term,key in (('undesired_contacts','effective_undesired_contact_weight'),('track_ang_vel_z_exp','effective_yaw_tracking_weight')):
                if float(cfg['rewards'][term]['weight'])!=manifest[key]:
                    raise ValueError('Manifest/config reward mismatch')
            if sha256(ROOT/run['final_checkpoint'])!=run['final_checkpoint_sha256']:
                raise ValueError('Training checkpoint changed')
            expected=-10 if run['arm']=='height10' else 0
            if manifest['effective_base_height_weight']!=expected:
                raise ValueError('Unexpected height term')
            configs[label]=(cfg,manifest['policy_dt'])
            ev=EventAccumulator(str(directory),size_guidance={'scalars':0});ev.Reload()
            tags=[x for x in ev.Tags()['scalars'] if x.startswith(('Episode_Reward/','Metrics/'))]
            windows={}
            for low,high in ((3700,3799),(3800,3899),(3900,3999),(3700,3999)):
                values={}
                for tag in tags:
                    rows=[x for x in ev.Scalars(tag) if low<=x.step<=high]
                    if len(rows)!=high-low+1 or not np.isfinite([x.value for x in rows]).all():
                        raise ValueError('Incomplete/nonfinite training window: '+label+'/'+tag)
                    values[tag]=float(np.mean([x.value for x in rows]))
                windows[f'{low}:{high}']=values
            out[label]={'manifest':str(manifest_path.relative_to(ROOT)),'manifest_sha256':sha256(manifest_path),'config_sha256':sha256(cfgpath),'events_sha256':{p.name:sha256(p) for p in directory.glob('events.out.tfevents.*')},'effective_height_weight':expected,'windows':windows}
    return out,configs


def main():
    if OUTPUT.exists():
        raise FileExistsError(OUTPUT)
    job,prior=read(JOB),read(PRIOR)
    if job['status']!='completed' or len(job['stages'])!=8 or len(job['reused'])!=4:
        raise RuntimeError('Complete verified replay matrix required')
    if sha256(PRIOR)!=job['source_job_sha256']:
        raise RuntimeError('Original experiment changed')
    training,configs=training_windows(prior)
    out={'created_utc':utc_now(),'job':str(JOB.relative_to(ROOT)),'job_sha256':sha256(JOB),
         'source_sha256':{p:sha256(ROOT/'scripts'/p) for p in ('analyze_height_yaw.py','yaw_trace_analysis.py')},
         'training_windows':training,'profiles':{},'fresh_replays':8,'reused_traces':4,
         'reward_formula_source_sha256':sha256(ROOT/'vendor/robot_lab/source/robot_lab/robot_lab/tasks/manager_based/locomotion/velocity/mdp/rewards.py'),
         'vendor_manifest_sha256':sha256(ROOT/'vendor/manifest.json'),
         'limitations':['Disclosed cases and selected development seeds; no independent acceptance.',
         'Paired measurement ends before the earlier first failure; shorter trajectories are censored, not treated as full successful episodes.',
         'Source DAE clearance is not exact cooked PhysX collider clearance; explicit leg clipping does not measure implicit wheel torque.',
         'Offline reconstructed rewards at policy boundaries use actual training config, but evaluate replay states, not training states. Only listed terms are reconstructed.',
         'Calf last-three-substep contact proxy excludes other non-wheel bodies and is not the full training contact reward.',
         'Reward/state correlations do not establish a unique causal explanation.']}
    plots=[]
    for profile,seed in (('nominal',20261201),('bounded_v1',20261202)):
        reports={};traces={};derived_values={};provenance={}
        labels=['reference','seed49','seed50_control','seed50_height10','seed51_control','seed51_height10']
        for label in labels:
            name=f'{label}_{profile}_{seed}';stage=(job['reused'] if label in ('reference','seed49') else job['stages'])[name]
            if not stage['original_results_exactly_reproduced'] or (label not in ('reference','seed49') and stage['external_exit_code']!=0):
                raise RuntimeError('Invalid replay')
            p=ROOT/stage['report']
            if sha256(p)!=stage['report_sha256']:
                raise RuntimeError('Report changed')
            r=read(p);arr,meta=load_trace(r)
            if not all(np.isfinite(v).all() for v in arr.values()):
                raise ValueError('Nonfinite trace')
            reports[label]=r;traces[label]=(arr,meta)
            provenance[label]={'report':str(p.relative_to(ROOT)),'report_sha256':sha256(p),'trace_sha256':r['yaw_trace']['sha256'],'policy_sha256':r['policy_sha256']}
        ref=reports['reference'];meta0=traces['reference'][1];times=traces['reference'][0]['time_s']
        meshes={n:mesh_vertices(n) for n in meta0['body_names'] if n.endswith('_calf')}
        geometry={n:vertices for n,(vertices,provenance_info) in meshes.items()}
        out['geometry']={n:info for n,(vertices,info) in meshes.items()}
        for label,r in reports.items():
            arr,meta=traces[label]
            if r['cases']!=ref['cases'] or r['physical_evidence']['properties_sha256']!=ref['physical_evidence']['properties_sha256']:
                raise ValueError('Case/physical mismatch')
            if meta['env_ids']!=meta0['env_ids'] or not np.array_equal(arr['time_s'],times):
                raise ValueError('Trace alignment mismatch')
            derived_values[label]=derived(arr,meta,geometry)
        pdata={'provenance':provenance,'pairs':{},'own_prefailure_windows':[]}
        for seed_id in (50,51):
            control=f'seed{seed_id}_control';variant=f'seed{seed_id}_height10'
            cf=failure_times(reports[control],meta0['env_ids']);vf=failure_times(reports[variant],meta0['env_ids'])
            mask=paired_mask(times,cf,vf)
            cset={f['env'] for f in reports[control]['first_failures']};vset={f['env'] for f in reports[variant]['first_failures']}
            pair={'failure_cases':{'common':sorted(cset&vset),'fixed_by_height':sorted(cset-vset),'new_with_height':sorted(vset-cset)},'matched':{},'per_case':[]}
            for scenario in ('all_yaw','yaw_positive','yaw_negative'):
                selection=np.ones(len(meta0['env_ids']),dtype=bool) if scenario=='all_yaw' else np.array([reports[control]['results'][i]['scenario']==scenario for i in meta0['env_ids']])
                smask=mask & selection[None,:]
                pair['matched'][scenario]={}
                for label in (control,variant,'seed49','reference'):
                    arr,meta=traces[label]
                    cfg,dt=configs.get(label,(None,.02))
                    pair['matched'][scenario][label]=metrics(arr,meta,derived_values[label],smask,cfg,dt)
            pair['settling']={}
            for label in (control,variant):
                arr,meta=traces[label];fail=failure_times(reports[label],meta['env_ids'])
                settle=(times[:,None]<=2.+1e-7)&(times[:,None]<fail[None,:]-1e-7)
                cfg,dt=configs[label];pair['settling'][label]=metrics(arr,meta,derived_values[label],settle,cfg,dt)
            for e,env_id in enumerate(meta0['env_ids']):
                cmask=np.zeros_like(mask);cmask[:,e]=mask[:,e]
                row={'env':env_id,'scenario':reports[control]['results'][env_id]['scenario'],'end_s':float(min(cf[e],vf[e],times[-1])),'policies':{}}
                for label in (control,variant):
                    arr,meta=traces[label]
                    row['policies'][label]=metrics(arr,meta,derived_values[label],cmask)
                pair['per_case'].append(row)
            for failed_label in (control,variant):
                for failure in reports[failed_label]['first_failures']:
                    if failure['env'] not in meta0['env_ids']:
                        raise ValueError('Failure outside recorded yaw cases')
                    e=meta0['env_ids'].index(failure['env']);end=failure['time_s'];start=max(0.,end-.5)
                    wmask=np.zeros_like(mask);wmask[:,e]=(times>=start)&(times<end-1e-7)
                    row={'failed_policy':failed_label,'failure':failure,'window_s':[start,end],'policies':{}}
                    for label in (control,variant,'seed49','reference'):
                        arr,meta=traces[label];cfg,dt=configs.get(label,(None,.02))
                        m=metrics(arr,meta,derived_values[label],wmask,cfg,dt)
                        m['comparator_already_failed']=bool(failure_times(reports[label],meta['env_ids'])[e]<end-1e-7)
                        row['policies'][label]=m
                    pdata['own_prefailure_windows'].append(row)
            pdata['pairs'][str(seed_id)]=pair
            plots.append((profile,seed_id,pair))
        out['profiles'][profile]=pdata
    out['findings']={}
    for profile,p in out['profiles'].items():
        for sid,pair in p['pairs'].items():
            rows=pair['matched']['all_yaw'];c=rows[f'seed{sid}_control'];v=rows[f'seed{sid}_height10']
            out['findings'][f'seed{sid}_{profile}']={'failure_cases':pair['failure_cases'],
                'matched_height_mean_control_variant_m':[c['height_m']['mean'],v['height_m']['mean']],
                'matched_min_calf_gap_mean_control_variant_m':[c['minimum_calf_clearance_m']['mean'],v['minimum_calf_clearance_m']['mean']],
                'matched_yaw_rms_control_variant':[c['rms_vx_vy_yaw'][2],v['rms_vx_vy_yaw'][2]],
                'matched_low_height_fraction_control_variant':[c['height_below055_fraction'],v['height_below055_fraction']],
                'leg_clipping_fraction_control_variant':[c['leg_clipping_fraction'],v['leg_clipping_fraction']]}
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(12,7),layout='constrained')
    xs=np.arange(len(plots));names=[f's{s}\n{p}' for p,s,_ in plots]
    specifications=[('height_m','mean','Height (m)'),('minimum_calf_clearance_m','mean','Minimum calf gap proxy (m)'),('rms_vx_vy_yaw',2,'Yaw RMS (rad/s)'),('height_below055_fraction',None,'Fraction height < 0.55 m')]
    for ax,(metric,key,title) in zip(axes.flat,specifications):
        for offset,arm,color in ((-.18,'control','#3478ba'),(.18,'height10','#d77932')):
            values=[]
            for p,s,pair in plots:
                x=pair['matched']['all_yaw'][f'seed{s}_{arm}'][metric]
                values.append(x if key is None else x[key])
            ax.bar(xs+offset,values,.36,label=arm,color=color)
        ax.set_xticks(xs,names);ax.set_title(title);ax.grid(axis='y',alpha=.2)
    axes[0,0].legend();fig.suptitle('Height ablation: matched yaw samples before the earlier first failure\nDiagnostic statistics, not acceptance scores')
    plot=ROOT/'docs/results/2026-09-19-height-yaw-matched.png'
    if plot.exists():raise FileExistsError(plot)
    fig.savefig(plot,dpi=150);plt.close(fig)
    out['plot']={'path':str(plot.relative_to(ROOT)),'sha256':sha256(plot)}
    write_json(OUTPUT,out)
    print(json.dumps(out['findings'],indent=2))


if __name__=='__main__':
    main()
