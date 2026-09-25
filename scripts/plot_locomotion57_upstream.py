"""Plot measured Flat responses; no smoothing or successful-episode selection."""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from locomotion57_protocol import ROOT, POLICIES, cases_for


def main():
    source = ROOT/'logs/locomotion57_upstream_20260925/development/isaac_flat.npz'
    with np.load(source) as archive:
        trace = archive['trace']
    cases = cases_for('flat')
    count = len(cases)*16
    selected = [('vx_+1.00', 0, 'Продольная команда 1.0 м/с', 'vx, м/с'),
                ('precision_vy_+0.10', 1, 'Боковая команда 0.1 м/с', 'vy, м/с'),
                ('precision_wz_+0.10', 2, 'Угловая команда 0.1 рад/с', 'ωz, рад/с'),
                ('turning', 2, 'Поворот при vx=0.5 м/с', 'ωz, рад/с')]
    figure, axes = plt.subplots(2, 2, figsize=(12.8, 7.5), sharex=True, constrained_layout=True)
    colors = ('#1565c0', '#d17b00', '#16845b')
    for ax, (name, axis, title, ylabel) in zip(axes.flat, selected):
        index = next(i for i, case in enumerate(cases) if case.name == name)
        case = cases[index]
        t = (np.arange(case.steps)+1)*.02
        command = case.schedule()[0][:, axis]
        ax.plot(t, command, color='#222222', linestyle='--', linewidth=1.4, label='Внешняя команда')
        for j, (policy, color) in enumerate(zip(POLICIES, colors)):
            signals = trace[:case.steps, j*count+index*16:j*count+(index+1)*16, axis]
            low, median, high = np.nanquantile(signals, [.1, .5, .9], axis=1)
            ax.fill_between(t, low, high, color=color, alpha=.13, linewidth=0)
            ax.plot(t, median, color=color, linewidth=1.1, label=str(policy))
        ax.set_title(title, fontsize=11)
        ax.set_ylabel(ylabel)
        ax.set_xlabel('Время, с')
        ax.grid(alpha=.18)
        ax.spines[['top', 'right']].set_visible(False)
    axes.flat[0].legend(ncol=2, fontsize=9)
    figure.suptitle('Isaac · upstream B2W · медиана и 10–90% по 16 reset seeds', fontsize=14)
    output = ROOT/'docs/results/figures/upstream_locomotion57_flat_20260925.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=160)
    plt.close(figure)
    print(output)


if __name__ == '__main__':
    main()
