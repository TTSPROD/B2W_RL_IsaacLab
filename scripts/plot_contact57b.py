"""Visualize measured force sensitivity and 19999 slow-ascent failure traces."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from contact57b_model import BASE
from physics57_protocol import ROOT

fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
for r,color in ((1.,'#b34839'),(0.,'#da9679')):
    a=np.load(BASE/f'impact_isaac_r{r:g}_0.002.npz')
    t=(np.arange(len(a['root']))+1)*.002
    axes[0,0].plot(t,a['force_z'][:,0]/1000,label=f'Isaac restitution {r:g}',color=color)
    axes[0,1].plot(t,a['root'][:,0,2],label=f'Isaac restitution {r:g}',color=color)
a=np.load(BASE/'impact_mujoco_cooked_shapes_d1_0.002.npz')
t=(np.arange(len(a['root']))+1)*.002
axes[0,0].plot(t,a['force_z'][:,0]/1000,label='MuJoCo cooked, default solref',color='#007f8b')
axes[0,1].plot(t,a['root'][:,0,2],label='MuJoCo cooked, default solref',color='#007f8b')
axes[0,0].set(xlim=(.18,.55),xlabel='Time (s)',ylabel='Total vertical contact force (kN)',title='Policy-free drop: contact peaks remain different')
axes[0,1].set(xlabel='Time (s)',ylabel='Root height (m)',title='Whole-robot motion; active PD held constant')
axes[0,1].legend(fontsize=8)
trace=np.load(BASE/'micro_up_14x32_19999_cooked_shapes.npz')
motion=trace['forward_0.30']
detail=trace['forward_0.30__detail']
t=(np.arange(len(motion))+1)*.02
colors=['#b34839','#4665a2','#cf8b0e','#007f8b']
for i in range(4):
    axes[1,0].plot(t,motion[:,i,3],label=f'seed {7201+i}',color=colors[i])
    vx=np.convolve(motion[:,i,0],np.ones(50)/50,mode='valid')
    axes[1,1].plot(t[49:],vx,label=f'seed {7201+i}',color=colors[i])
axes[1,0].axhline(3.92,color='grey',linestyle=':',label='stair far edge (diagnostic)')
axes[1,0].set(xlabel='Time (s)',ylabel='Root x (m)',title='19999 at 0.3 m/s: two persistent stalls')
axes[1,0].legend(fontsize=8,loc='upper left')
axes[1,1].plot([0,2,2,32,32,45],[0,0,.3,.3,0,0],'k--',linewidth=1,label='external vx command')
axes[1,1].set(xlabel='Time (s)',ylabel='Body vx, 1 s trailing mean (m/s)',title='Tracking and stopping are separate failures')
axes[1,1].legend(fontsize=8,loc='upper right')
for ax in axes.flat:
    ax.grid(alpha=.2)
fig.suptitle('B2W contact57b — isolated cooking and upstream19999 diagnosis',fontsize=14)
out=ROOT/'docs/results/figures/contact57b_diagnostics_20260925.png'
fig.savefig(out,dpi=160)
print(out)
