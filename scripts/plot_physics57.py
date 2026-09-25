"""Standalone figures for measured physics probes and the diagnostic subset."""
from pathlib import Path
import json
import numpy as np
from b2w_runtime import configure_process
configure_process()
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from physics57_protocol import ROOT,BASE,DT

summary=json.loads((ROOT/'docs/results/evidence/physics57_20260925/summary.json').read_text())
fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
colors={'Isaac':'#2357a5','vendor':'#b74949','damping_only':'#d28a1a','mechanics_implicit':'#228b73'}
for name,file,label in (
    ('Isaac','isaac_airborne_0.002.npz','Isaac reference'),
    ('vendor','mujoco_airborne_vendor_0.002.npz','MuJoCo vendor'),
    ('damping_only','mujoco_airborne_damping_only_0.002.npz','Passive damping removed'),
    ('mechanics_implicit','mujoco_airborne_mechanics_implicit_0.002.npz','Mechanics + implicit wheels')):
    a=np.load(BASE/file)
    axes[0].plot((np.arange(len(a['dq']))+1)*DT,a['dq'][:,4,12:].mean(axis=1),
                 label=label,color=colors[name],linewidth=1.8,linestyle='--' if name=='Isaac' else '-')
axes[0].plot([0,.5,.5,2.5,2.5,4],[0,0,10,10,0,0],color='#555',linestyle=':',label='Velocity target')
axes[0].set(xlabel='Time (s)',ylabel='Wheel velocity (rad/s)',title='No ground contact: four-wheel mean')
axes[0].legend(fontsize=8,loc='upper right')
variants=('vendor','damping_only','mechanics_implicit')
labels=('Vendor','Damping only','Mechanics + implicit')
x=np.arange(2)
for j,v in enumerate(variants):
    rows=[next(r for r in summary['micro_totals'] if r['variant']==v and r['policy']==p) for p in (10000,19999)]
    vals=[r['outcomes'].get('success',0) for r in rows]
    bars=axes[1].bar(x+(j-1)*.25,vals,width=.23,label=labels[j],color=colors[v])
    axes[1].bar_label(bars,labels=[f'{n}/20' for n in vals],fontsize=9,padding=3)
axes[1].set(xticks=x,xticklabels=['Upstream 10000','Upstream 19999'],ylim=(0,22),
            ylabel='Successful episodes (all applicable gates)',title='Paired diagnostic subset: 4 reset seeds')
axes[1].legend(fontsize=8,loc='upper right')
for ax in axes:
    ax.grid(axis='y',alpha=.2)
    ax.set_axisbelow(True)
    ax.spines[['top','right']].set_visible(False)
fig.suptitle('B2W: actuator mismatch is measurable; policy acceptance remains open',fontsize=13)
path=ROOT/'docs/results/figures/physics57_diagnostics_20260925.png'
fig.savefig(path,dpi=170)
print(path)
