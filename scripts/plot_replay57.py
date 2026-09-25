"""Static scientific figure for the four-state replay, not an acceptance chart."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from replay57_protocol import ROOT,BASE,DT,SEEDS

s = json.loads((ROOT/'docs/results/evidence/replay57_19999_20260925/summary.json').read_text())
conditions = [('mujoco_cooked_shapes','MuJoCo cooked','#2878b5'),
              ('mujoco_source_shapes','MuJoCo source','#df8f2d'),
              ('isaac_contactmesh','Isaac','#24865d')]
fig,axes = plt.subplots(2,2,figsize=(12.5,8),layout='constrained')
for col,i in enumerate((0,2)):
    ax = axes[0,col]
    for name,label,color in conditions:
        a = np.load(BASE/f'{name}.npz')
        # Non-overlapping .2 s means, solely for readable plots.
        v = a['root_velocity_b'][:,i,0].reshape(25,10).mean(axis=1)
        ax.plot(np.arange(25)*.2+.1,v,label=label,color=color,lw=2)
    ax.axhline(.3,color='#555555',ls='--',lw=1,label='Command 0.30 m/s')
    ax.set(title=f'Replayed stall state {SEEDS[i]}',xlabel='Replay time (s)',ylabel='Body forward velocity (m/s)')
    ax.grid(alpha=.2)
axes[0,0].legend(fontsize=9)
for j,(name,label,color) in enumerate(conditions):
    rows = [r for r in s['rows'] if r['condition']==name]
    x = np.arange(4)+(j-1)*.24
    axes[1,0].bar(x,[r['mean_body_velocity'][0] for r in rows],width=.22,label=label,color=color)
    axes[1,1].bar(x,[r['total_reward_rate_mean'] for r in rows],width=.22,color=color)
axes[1,0].axhline(.3,color='#555555',ls='--',lw=1)
for ax in axes[1]:
    ax.set_xticks(range(4),['7201\nstall','7202\ncontrol','7203\nstall','7204\ncontrol'])
    ax.grid(axis='y',alpha=.2)
axes[1,0].set(title='Mean command response over all 5 s',ylabel='Body forward velocity (m/s)')
axes[1,1].set(title='Saved reward: moving controls score higher',ylabel='Sum of weighted reward rates (1/s)',ylim=(0,18))
fig.suptitle('B2W upstream19999 | four full states, three contact models | diagnostic only',fontsize=14)
path = ROOT/'docs/results/figures/replay57_19999_20260925.png'
if path.exists():
    raise FileExistsError(path)
fig.savefig(path,dpi=170)
print(path)
