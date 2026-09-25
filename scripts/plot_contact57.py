"""Static scientific summary of the contact geometry diagnosis."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from physics57_protocol import ROOT

data = json.loads((ROOT/'docs/results/evidence/contact57_20260925/summary.json').read_text())
fig,axes = plt.subplots(1,3,figsize=(14,4.4),layout='constrained')
colors = {'mechanics_control':'#6b7280','source_shapes':'#007f8b'}
labels = {'mechanics_control':'Mechanical control','source_shapes':'Training collision geometry'}
for ax,metric,scale,label in ((axes[0],'leg_q_max_abs_delta_rad',1,'Max leg angle error (rad)'),
                            (axes[1],'root_position_delta_m',1000,'Max root position error (mm)')):
    for variant in colors:
        values = [max(r[metric] for r in data['contact_rows'] if r['variant']==variant and r['dt_s']==dt)*scale for dt in (.005,.002,.001)]
        ax.plot([5,2,1],values,'o-',label=labels[variant],color=colors[variant],linewidth=2)
    ax.set(xlabel='MuJoCo physics step (ms)',ylabel=label,xticks=[1,2,5])
    ax.grid(alpha=.2)
axes[0].set_title('100 ms shared-state probes\n16 states per physics step')
axes[1].set_title('Root error does not improve uniformly\nIsaac reference: 5 / 2 / 2 ms')
x = np.arange(2)
for i,variant in enumerate(colors):
    counts = [next(r['outcomes'].get('success',0) for r in data['micro_totals'] if r['variant']==variant and r['policy']==p) for p in (10000,19999)]
    bars = axes[2].bar(x+(i-.5)*.34,counts,.34,color=colors[variant],label=labels[variant])
    axes[2].bar_label(bars,labels=[f'{n}/20' for n in counts],padding=3)
axes[2].set(xticks=x,xticklabels=['upstream10000','upstream19999'],ylim=(0,21.5),ylabel='Successful diagnostic episodes',title='Paired policy screen\n0 unsafe; neither policy accepted')
axes[2].grid(axis='y',alpha=.2)
axes[0].legend(fontsize=8,loc='center left')
fig.suptitle('B2W contact57 — source geometry correction, 25 September 2026',fontsize=14)
output = ROOT/'docs/results/figures/contact57_diagnostics_20260925.png'
fig.savefig(output,dpi=160)
print(output)
