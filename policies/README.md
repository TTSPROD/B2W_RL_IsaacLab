# Сохранённые политики B2W

Политики предназначаются для низкоуровневого исполнения внешних body-frame команд
`(vx, vy, omega_z)`, ABI57→16. Критерии: [PROJECT_PLAN.md](../docs/PROJECT_PLAN.md).
Development `locomotion57_v1` выполнен для upstream10000/15000/19999; все три не приняты. [Отчет](../docs/results/2026-09-25-upstream-locomotion57.md). Статусы и cycle/corridor
scores в вложенных snapshot README/manifest относятся к исходным протоколам.
Архивные handoff/snapshot файлы сохраняются без переписывания; отсутствие новой
оценки не повышает статус весов. ABI60 не совместима с действующим контрактом.

- [Канонический реестр всех линий, SHA и решений](../docs/POLICY_REGISTRY.md). На 25 сентября новой low-level qualification нет; inverse57 update3000 и cycle57 model3000 — непринятые кандидаты для baseline по внешним командам.
- [75 экспериментальных checkpoints ноутбука и сервера](experimental/README.md): **не приняты**, включая snapshots остановленных runs; SHA и ABI в manifest.
- [Настольный Flat seed54](desktop/flat54/README.md): checkpoint и TorchScript из ранее опубликованного handoff. Квалификация относится только к Flat по настольному протоколу; не принятая Rough/Stairs политика.
- [Внешний reference rl_sar](../vendor/rl_sar/policy/b2w/robot_lab/policy.pt): исходный опубликованный файл, не результат обучения этого проекта.

Три параллельные линии имеют разные истории seeds и gates. [Общая сводка](../docs/TRAINING_STATUS.md). Git snapshot `experimental/` зафиксирован 23 сентября и намеренно не переписывается задним числом: завершённые позже inverse57, cycle57 и payload57 перечислены в реестре, но не опубликованы в этом каталоге. Наличие весов не разрешает управление реальным роботом.
