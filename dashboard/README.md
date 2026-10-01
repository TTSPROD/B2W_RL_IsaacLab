# Монитор B2W

Дашборд **только показывает** состояние, логи, TensorBoard, checkpoints и результаты.
Запуск, остановка, продолжение и жизненный цикл процессов принадлежат независимому
supervisor в `scripts/job_manager.py` / `scripts/job_worker.py`.
Наличие HTTP-сервера, открытого браузера или чата не требуется для обучения.
HTTP POST запрещён (405); в интерфейсе нет кнопок запуска и остановки.

## Открыть монитор

```powershell
& .\scripts\start_dashboard.ps1
```

[Локальный монитор](http://127.0.0.1:8765/#jobs) читает сохранённые состояния.
«Монитор запусков» показывает phase, updates, coverage, logs и exit code.
«Оценка policy» по умолчанию показывает текущее сравнение Parent / A +1350 /
B +1350: завершённые эпизоды, success, unsafe и прогресс каждого actor/terrain.
Страница обновляется каждые 10 секунд, результаты появляются после сохранения
целого прогона. Пока покрытие policies различается, общий success несопоставим.
Переключатель источника сохраняет доступ к сравнению 19999 / 24650 / rl_sar
из registry. Диагностическая оценка не подменяет принятого кандидата.

Сервер использует TensorBoard из существующего `B2W_ISAAC_SIM_ENV`
(по умолчанию `D:\isaacsim51`), в том числе при запуске из чистого `.venv`.
При отсутствии зависимости графиков управление supervisor остаётся доступным,
а монитор показывает предупреждение и метаданные запуска.

## Независимое выполнение

```powershell
& .\scripts\run_local.ps1 scripts/manage_runs.py start tests --no-monitor
& .\scripts\run_local.ps1 scripts/manage_runs.py start evaluate --policy 24650 --no-monitor
& .\scripts\run_local.ps1 scripts/manage_runs.py status
& .\scripts\run_local.ps1 scripts/manage_runs.py stop <job-id>
```

`start` действительно запускает работу. `--no-monitor` отключает попытку
открыть дашборд. Без него клиент сначала создаёт job, затем отдельно пробует
открыть монитор; ошибка монитора не отменяет и не задерживает выполнение job.
Managed training/evaluation entrypoints используют тот же независимый клиент.
`dashboard/submit.py` оставлен как совместимый CLI, без обращений к HTTP API.

Один локальный job занимает слот; файловая блокировка сериализует разные CLI.
В Windows supervisor владеет Job Object: при его аварийном выходе завершается
его дочернее дерево. HTTP-сервер в это дерево не входит. Закрытие сервера не
останавливает supervisor; авария самого supervisor требует восстановления.
После утраты heartbeat job показывается interrupted, а не успешно завершённым.
Остановка через CLI сохраняет уже записанные файлы; незаписанные updates теряются.

Состояния хранятся в историческом `logs/dashboard/jobs/<id>/`: request, state,
progress, stdout/stderr, snapshots и evidence. Название каталога не означает
зависимость от дашборда. Запись JSON атомарная; live logs не входят в Git.
Старые отменённые/прерванные runs не удаляются и не объявляются завершёнными.

Последняя оценка: [B на 1350 updates, A сохранён](../docs/results/2026-09-30-stair-comparison-1350.md).
Завершены 180 эпизодов: parent/A/B — 27/23/25 successes, unsafe 0/0/1.
B отклонён; кандидат core_24650 сохранён. Страница «Оценка policy» показывает
окончательный результат и решение; сохранённое сравнение из registry доступно отдельно.

Историческая команда воспроизведения workflow (заново обучает B):

```powershell
& .\scripts\run_local.ps1 scripts/manage_runs.py start stair_comparison_1350 --no-monitor
```

Эта команда создаёт новый job, а не подключается к текущему. Для уже работающего
эксперимента достаточно `status` или монитора. Не запускать второй экземпляр.

[План проекта](../docs/PROJECT_PLAN.md) · [Протокол](../docs/CORE_LOCOMOTION_EVALUATION.md)
