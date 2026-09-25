# Сохранённые политики B2W

- [Канонический реестр всех линий, SHA и решений](../docs/POLICY_REGISTRY.md). На 25 сентября принятой Rough/Stairs политики нет; inverse57 update3000 — только working parent, а ручной MuJoCo run cycle57 model3000 содержал unsafe episode.
- [75 экспериментальных checkpoints ноутбука и сервера](experimental/README.md): **не приняты**, включая snapshots остановленных runs; SHA и ABI в manifest.
- [Настольный Flat seed54](desktop/flat54/README.md): checkpoint и TorchScript из ранее опубликованного handoff. Квалификация относится только к Flat по настольному протоколу; не принятая Rough/Stairs политика.
- [Внешний reference rl_sar](../vendor/rl_sar/policy/b2w/robot_lab/policy.pt): исходный опубликованный файл, не результат обучения этого проекта.

Три параллельные линии имеют разные истории seeds и gates. [Общая сводка](../docs/TRAINING_STATUS.md). Git snapshot `experimental/` зафиксирован 23 сентября и намеренно не переписывается задним числом: завершённые позже inverse57, cycle57 и payload57 перечислены в реестре, но не опубликованы в этом каталоге. Наличие весов не разрешает управление реальным роботом.
