# Монитор текущего запуска B2W

При запуске нового обучения, тестов или оценки через `scripts/manage_runs.py`
или managed training/evaluation entrypoint дашборд автоматически запускается
и открывается в браузере. Уже работающий HTTP-сервер используется повторно.

[Локальный монитор](http://127.0.0.1:8765/#jobs) показывает **один текущий job**:
статус supervisor, фазу, прогресс обучения или оценки, exit code, результаты
и журнал этого процесса. Обновление — каждые 3 секунды. Новый job автоматически
заменяет предыдущий на экране; история запусков, старые обучения и сохранённые
сравнения в интерфейсе не отображаются. После завершения остаётся итоговый статус
этого job до следующего запуска. Если jobs ещё нет, показано ожидание.

Текущий job — активный (`queued`, `running`, `stopping`) или требующий восстановления
с живым worker; при отсутствии такого job — последний созданный.
Данные берутся из `/api/current`, без подстановки evidence старого job или registry.

## Открыть вручную

```powershell
& .\scripts\start_dashboard.ps1
```

Прежние ссылки `#overview`, `#selection` и остальные также открывают единый экран.

## Независимое выполнение

```powershell
& .\scripts\run_local.ps1 scripts/manage_runs.py start evaluate --policy 24650
& .\scripts\run_local.ps1 scripts/manage_runs.py start tests --no-monitor
& .\scripts\run_local.ps1 scripts/manage_runs.py status
& .\scripts\run_local.ps1 scripts/manage_runs.py stop <job-id>
```

`start` создаёт новый job. Один локальный job занимает слот; файловая блокировка
сериализует разные CLI. `--no-monitor` отключает автоматическое открытие.
Клиент сначала создаёт job, затем отдельно запускает монитор без ожидания;
сбой монитора не отменяет выполнение. Диагностика открытия — `logs/dashboard/monitor.log`.
`dashboard/submit.py` сохранён как совместимый CLI без обращений к HTTP API.

Supervisor в `scripts/job_manager.py` / `scripts/job_worker.py` управляет процессами.
Дашборд только читает файлы: HTTP POST запрещён (405), кнопок запуска и остановки нет.
Закрытие браузера или HTTP-сервера не останавливает job. В Windows supervisor
владеет Job Object; при его аварийном выходе завершается его дочернее дерево.
Монитор в это дерево не входит. Потеря heartbeat показывается как `interrupted`,
без предположения об успешном завершении.

Состояния и evidence остаются в `logs/dashboard/jobs/<id>/`: request, state,
progress, stdout/stderr, snapshots. Старые runs сохраняются на диске и доступны
через CLI; live logs не входят в Git. Изменение монитора не меняет hashes evidence
реально выполненных запусков. Оценка policy сама по себе не даёт допуска к hardware.

[План проекта](../docs/PROJECT_PLAN.md) · [Протокол](../docs/CORE_LOCOMOTION_EVALUATION.md)
