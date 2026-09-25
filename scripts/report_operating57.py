"""Generate the measured response figure and dated operating-range report."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from locomotion57_protocol import ROOT, sha256
from operating57_protocol import CONFIG, SEEDS, cases_for


def main():
    base = ROOT / "docs/results/evidence/operating57_19999_20260925"
    evidence = ROOT / "docs/results/evidence/operating57_19999_20260925"
    data = json.loads((base / "isaac_flat.json").read_text())
    summary = json.loads((evidence / "summary.json").read_text())
    rows = {row["case"]: row for row in summary["fresh"]["rows"]}
    cases = cases_for()
    with np.load(base / "isaac_flat.npz") as archive:
        trace = archive["trace"]
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    for axis, (name, title, unit) in enumerate(zip(
            ("vx", "vy", "wz"), ("Продольная скорость", "Боковая скорость", "Поворот"),
            ("м/с", "м/с", "рад/с"))):
        ax = axes[0, axis]
        ax.plot([-1.1, 1.1], [-1.1, 1.1], "--", color="#555", linewidth=1, label="Идеальный отклик")
        for case in cases:
            if not case.name.startswith(name + "_"):
                continue
            row = rows[case.name]
            command = case.segments[1].command[axis]
            records = [r for r in data["records"] if r["case"] == case.name]
            velocities = [s["mean_velocity"][axis] for r in records for s in r["segments"]
                          if s.get("complete") and s.get("segment") == 1]
            low, median, high = np.quantile(velocities, [.1, .5, .9])
            color = "#197a56" if row["success"] == SEEDS else "#c93636" if row["unsafe"] else "#c27b16"
            ax.errorbar(command, median, yerr=[[median-low], [high-median]], fmt="o",
                        color=color, capsize=3, markersize=6)
            ax.annotate(f"{row['success']}/{SEEDS}", (command, median),
                        xytext=(0, 9), textcoords="offset points", fontsize=8, ha="center")
        ax.set(title=title, xlabel=f"Команда, {unit}", ylabel=f"Средний отклик, {unit}",
               xlim=(-1.14, 1.14), ylim=(-1.2, 1.2))
        ax.grid(alpha=.2)
    selected = [("vx_+0.70", 0), ("vy_+0.50", 1), ("wz_-0.70", 1)]
    for ax, (name, axis) in zip(axes[1], selected):
        index = next(i for i, c in enumerate(cases) if c.name == name)
        case = cases[index]
        times = (np.arange(case.steps) + 1) * .02
        signals = trace[:case.steps, index*SEEDS:(index+1)*SEEDS, axis]
        low, median, high = np.nanquantile(signals, [.1, .5, .9], axis=1)
        ax.plot(times, case.schedule()[0][:, axis], "--", color="#333", linewidth=1, label="Команда")
        ax.fill_between(times, low, high, color="#2768af", alpha=.2, label="10–90% reset seeds")
        ax.plot(times, median, color="#2768af", linewidth=1.2, label="Медиана")
        ax.axvline(4, color="#999", linewidth=.6, linestyle=":")
        ax.axvline(34, color="#999", linewidth=.6, linestyle=":")
        label = name if not name.startswith("wz") else "Побочная vy при ωz=−0.7 рад/с"
        ax.set(title=f"{label}: pass {rows[name]['success']}/{SEEDS}", xlabel="Время, с",
               ylabel="рад/с" if axis == 2 else "м/с")
        ax.grid(alpha=.2)
    axes[1, 0].legend(fontsize=8, loc="lower center")
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("B2W 19999 · Isaac Flat · 32 новых reset seeds на сценарий\n"
                 "Числа у точек: полный pass (tracking + переход + остановка + safety)", fontsize=13)
    figure_path = ROOT / "docs/results/figures/operating57_19999_20260925.png"
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=160)
    plt.close(fig)

    lines = [
        "# Operating57: проверка19999 в диапазонах вендорского обучения", "",
        "Дата:25 сентября2026. Запрос пользователя — проверить исходную модель с учетом",
        "реального распределения команд стандартного vendor train.py; точность малых команд не является приоритетом.", "",
        "**Выполнено1152 новых эпизода Isaac Flat:36 сценариев ×32 reset seeds8201–8232.**",
        "716/1152 выполнили все применимые gates;3 unsafe по compiled hard joint ranges.",
        "Проверялся frozen actor; обучение и аппаратные испытания не выполнялись.", "",
        "## Что проверено", "",
        f"Parent19999 SHA-256: `{summary['checkpoint_sha256']}`.",
        "Тот же проверенный TorchScript export, ABI57→16,50Hz, deterministic actor.",
        "Заморожены ±0.3/0.5/0.7/1.0 по каждой оси; четыре диагонали (±0.5,±0.5,0),",
        "четыре сочетания (±0.5,0,±0.5), ноль и три последовательности .3→.7→−.5",
        "с изменением команды каждые10s. Каждая последовательность заканчивается непрерывным нулем12s.",
        "Обычный сценарий:2s initialization +30s постоянная команда +12s ноль.",
        "Критерии этого screen: Flat RMSE≤(.2,.2,.25),",
        "mean response≥80%, moving1s windows после2s settling, zero≤.1m/s и .1rad/s непрерывно10s.",
        "Safety проверяется на каждом physics step200Hz, без startup grace и autoreset.",
        "Observation parity и command readback: max abs0.0. Время simulation loop101.875s.", "",
        "Saved training config: vx/vy±1m/s, yaw±1rad/s, linear vector norm≤.2 обнуляется,",
        "resampling10s, standing probability2%, heading controller0.5, rel_heading_envs1.0.",
        "Command curriculum выключен. Диапазоны совпадают с vendor defaults.",
        "Этот screen проверяет поддерживаемые диапазоны, а не воспроизводит весь training distribution:",
        "навигационной heading-коррекции нет, команды подаются напрямую; nominal physics и upright reset,",
        "без training DR/observation noise;30s constant segments длиннее training resampling10s.", "",
        "## Все новые строки", "",
        "Полный pass включает старт/переход, установившийся tracking, остановку и safety.",
        "Колонка steady отдельно показывает установившийся tracking в завершенных эпизодах;",
        "она не заменяет полный pass. Средние скорости — медианы по полным ненулевым segments;",
        "unsafe/incomplete всегда остаются в denominator полного pass.", "",
        "| Сценарий | Full pass/32 | Steady/32 | Zero/32 | Unsafe | Медиана фактической скорости (vx,vy,wz) |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for case in cases:
        row = rows[case.name]
        mean = row["measured_velocity_complete_segments_median"]
        values = "—" if mean is None else ", ".join(f"{v:.3f}" for v in mean)
        steady = row["steady_tracking_pass_complete_episodes"]
        lines.append(f"|{case.name}|{row['success']}|{steady if steady is not None else '—'}|"
                     f"{row['complete_zero_segments_pass']}|{row['unsafe']}|{values}|")
    lines += [
        "", "Для transitions медиана объединяет разные ненулевые segments; для анализа отдельных",
        "переходов использовать raw JSON/NPZ. Точки32/32 являются development observations,",
        "не статистическим доказательством99% надежности и не непрерывным рабочим envelope.", "",
        "![Measured response](figures/operating57_19999_20260925.png)", "",
        "## Выводы по рабочим скоростям", "",
        "- Все шесть продольных точек ±0.3/0.5/0.7 и longitudinal transitions прошли32/32.",
        "- Боковые ±0.5/0.7 прошли32/32. При ±0.3 отклик есть (~0.225–0.232),",
        "  но он составляет75–77% вместо необходимых80%, поэтому0/32.",
        "- При vx±1.0 фактическая скорость ~±0.805–0.809; полный pass0/32 главным образом из-за moving-window error.",
        "- Повороты ±0.7/1.0 дают большой установившийся отклик, но переходы/непрерывный ноль остаются проблемой.",
        "  Для wz−0.7 steady32/32 при full0/32: это не отсутствие способности поворачивать.",
        "  Причина всех32 transition flags в этой строке — незаданная боковая скорость: moving1s RMSE(vy)",
        "  превышает0.20m/s; медиана максимума0.244m/s. По ωz moving-window нарушений здесь0/32.",
        "  Нарушения встречаются и поздно в30s сегменте, поэтому это не только задержка начала поворота.",
        "- Все диагонали имеют steady32/32; full31–32/32. Движение с поворотом: steady32/32, full27–30/32,",
        "  преимущественно отказы остановки. Результаты отдельных осей не означают pass любых сочетаний.", "",
        "## Три unsafe эпизода", "",
        "Во всех случаях задний правый hip (`RR_hip_joint`) пересек compiled hard range с tolerance0.001rad:", "",
        "| Команда | Reset seed | Время от начала,s | Выход за hard range,rad |", "|---|---:|---:|---:|",
    ]
    for item in summary["fresh"]["unsafe_episodes"]:
        safety = item["safety"]
        lines.append(f"|{item['case']}|{item['seed']}|{safety['unsafe_time_s']:.3f}|"
                     f"{-min(safety['hard_joint_margin_min_rad']):.6f}|")
    lines += [
        "", "Это небольшие превышения границ симуляционной модели; падения и base/hip-contact failures не зарегистрированы.",
        "Они остаются unsafe по заранее зафиксированному протоколу. Аппаратные пределы не измерены.",
        "Wheel speed peak38.55rad/s, maximum per-episode wheel saturation fraction7.18%,",
        "longest saturation0.20s. Это telemetry, не отдельное допускающее решение для реальных приводов.", "",
        "## Решение и evidence", "",
        "19999 полезно исследовать в продольных точках0.3/0.5/0.7 и боковых0.5/0.7; полный заявленный диапазон",
        "и combinations пока не проходят. Следующая приоритетная проблема — побочные линейные движения при",
        "повороте и остановка после него",
        "на рабочих командах. Этот screen не выполняет обучения и не даёт допуска к роботу.", "",
        "- [Протокол и hashes исходного запуска](../../configs/locomotion57_19999_operating_screen_20260925.json).",
        "- [Численная сводка, все строки и происхождение](evidence/operating57_19999_20260925/summary.json).",
        "- [Все 1152 эпизода последней проверки](evidence/operating57_19999_20260925/episodes.csv).",
        "- [Manifest и hashes](evidence/operating57_19999_20260925/manifest.json).",
        "- Raw data: [результаты JSON](evidence/operating57_19999_20260925/isaac_flat.json), [трассы NPZ](evidence/operating57_19999_20260925/isaac_flat.npz).",
    ]
    report = ROOT / "docs/results/2026-09-25-operating57-19999.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    paths = [*(ROOT / "scripts" / name for name in json.loads(CONFIG.read_text())["source_sha256"]), CONFIG, report, figure_path, evidence / "summary.json", evidence / "episodes.csv",
             base / "isaac_flat.json", base / "isaac_flat.npz",
             ROOT / "scripts/summarize_operating57.py", Path(__file__), ROOT / "tests/test_operating57.py"]
    manifest = {"files": {path.relative_to(ROOT).as_posix(): sha256(path) for path in paths},
                "new_episodes": 1152,
                "training_updates": 0, "new_server_jobs": 0, "qualification": False}
    (evidence / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(report)
    print(figure_path)


if __name__ == "__main__":
    main()
