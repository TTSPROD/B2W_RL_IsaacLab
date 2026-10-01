"""Read-only aligned samples before the two retained LR-pilot safety events."""
import json
import numpy as np
from run_support import ROOT,read_json,sha256


def analyze():
    base=ROOT/'logs/dashboard/jobs/72ef5d9d71f04597a9a07585a1cafcc9/evaluation'
    rows=[];inputs={}
    for event,command_time,joint in [('lrlow_24750',7.4,11),('lrlow_24950',4.2,5)]:
        for policy in ['24650','lrcontrol_24950',event]:
            path=base/policy/'stairs_up_18.json';data=read_json(path)
            for p in (path,path.with_suffix('.npz')):inputs[p.relative_to(ROOT).as_posix()]=sha256(p)
            index=next(i for i,r in enumerate(data['records']) if r['case']=='traverse_0.7' and r['seed']==73005)
            with np.load(path.with_suffix('.npz')) as arrays:
                t=round(command_time*10);values=arrays['joints_10hz'][t,index]
                raw=float(arrays['raw_actions_10hz'][t,index,joint])
                forces=arrays['wheels_xyz_upforce_50hz'][t*5,index,:,3].tolist()
                rows.append({'event_policy':event,'policy':policy,'seed':73005,'command_start_s':command_time,
                    'sample_end_s':command_time+.02,'joint':data['compiled_model']['joint_names'][joint],
                    'q_rad':float(values[joint]),'dq_rad_s':float(values[16+joint]),
                    'tau_nm':float(values[32+joint]),'target_rad':-1.5+.25*raw,
                    'hard_range_rad':data['compiled_model']['hard_joint_ranges'][joint],
                    'wheel_upforce_n':forces,'command':arrays['commands'][index,t*5].tolist(),
                    'unsafe':data['records'][index]['safety']['unsafe_flags']})
    return {'schema':'b2w_aligned_stair_safety_v1','samples':rows,'input_sha256':inputs,
            'script_sha256':sha256(__file__),
            'scope':'Aligned 10 Hz samples; no reconstruction of unrecorded 200 Hz trajectory; descriptive, not causal.'}


if __name__=='__main__':print(json.dumps(analyze(),indent=2))
