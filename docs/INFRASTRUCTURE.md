# Инфраструктура B2W

Текущая цель — низкоуровневая locomotion57→16 по внешним командам скорости.
Runtime qualification отделена от приемки policy: development `locomotion57_v1`
выполнен локально на RTX4080 Laptop в Isaac и CPU MuJoCo для трех серверных checkpoints.
Новые серверные jobs не запускались; полной policy qualification пока нет. Его критерии и очередность работ задает
[PROJECT_PLAN.md](PROJECT_PLAN.md).

Актуально на **25 сентября 2026**.

## Вычислительные линии

| Линия | Подтверждённый scope | Текущее использование |
|---|---|---|
| RTX 4080 Laptop, Windows 11, 12 GB | Isaac headless до 4096 env, evaluation, MuJoCo batch/viewer | Новый evaluator внешних команд, actuator/physics parity и парный baseline |
| RTX 4070 Ti desktop, 12 GB | Отдельная Flat-линия со своим runtime/evidence | Не смешивать checkpoints и seeds с ноутбуком |
| 4×Hopper server, Ubuntu 22.04 | Завершённые upstream20000 и inverse57 headless runs | Историческая линия; новый job только по явному разрешению |

Headless B2W qualification не подтверждает GUI, RTX rendering, камеры или произвольные Isaac Sim workloads.

## Runtime

- Baseline: robot_lab/Isaac Lab 2.3.2, Isaac Sim 5.1, Python 3.11, RSL-RL 3.1.2.
- Ноутбук: проектное `.venv` + `.runtime/IsaacLab`; бинарные Sim packages из `D:\isaacsim51`.
- Полный локальный Python запускается через `scripts/run_local.ps1`; системный Python не содержит Torch/Isaac dependencies.
- Vendor snapshots неизменны и проверяются `python scripts/vendor_materials.py verify`.

```powershell
python scripts/vendor_materials.py verify
& .\scripts\run_local.ps1 -m unittest discover -s tests -q
```

После contact57b diagnosis проверено:1290 vendor-файлов,287 tests — OK.
Последний этап:36 policy-free probes и20 новых19999 episodes выполнены локально;
[отчет и ограничения](results/2026-09-25-contact57b-19999.md).
По последующему указанию пользователя upstream10000 больше не запускается.

## Пути и границы

- Локальный проект: `C:\Users\ra.suragin\Documents\ChatGPT\B2W_RL_IsaacLab`.
- Основной серверный каталог: `/home/user/projects/B2W_RL_IsaacLab`.
- Transfer cache: `/home/user/.cache/B2W_RL_IsaacLab-sync`.
- Исторически разрешённая завершённая линия: `/home/user/B2W_RL_IsaacLab_Server`.

Не открывать старые B2W-проекты, не менять глобальные drivers/packages и не вытеснять чужие workloads. Logs, caches и environments не добавлять в Git. Экспериментальные policies допускаются только с manifest/SHA и явным статусом `not accepted`.

## Синхронизация

Обычный путь — Git fast-forward с чистым tracked state. `scripts/sync_server.ps1` не удаляет файлы и не делает force/reset. Для машин с неисправным DNS используется [github-dns-bypass](../skills/github-dns-bypass/SKILL.md); TLS verification сохраняется. На desktop, где GitHub доступен штатно, bypass не нужен.

## Решение по compute

Сейчас compute выделяется на evaluator/parity/evaluation, а не на длинное обучение.
Исторический ноутбучный probe `4096×25` подтвердил throughput и память, но не качество.
Предлагаемый новый train следует после P1–P3 из [PROJECT_PLAN.md](PROJECT_PLAN.md)
с заранее зафиксированным budget/gate; новый серверный job требует отдельного решения.
