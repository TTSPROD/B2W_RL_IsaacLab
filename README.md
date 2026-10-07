# B2W RL · Isaac Lab

Низкоуровневая policy Unitree B2W: 57 observations → 16 actions
(12 leg position targets + 4 wheel velocity targets), 50 Hz.
Внешние команды (vx, vy, ωz) приходят в body frame. Ноль требует остановки
и устойчивости; маршрут и абсолютный heading принадлежат внешнему уровню.

## Мониторинг и выполнение

```powershell
& .\scripts\start_dashboard.ps1
```

[Открыть монитор](http://127.0.0.1:8765/#jobs): статус, progress, логи
и результаты одного текущего запуска. Он автоматически открывается при новом
managed запуске обучения, тестов или оценки и переключается на новый job.
После завершения сохраняет итоговый статус до следующего запуска.
Дашборд только читает файлы; обучение, тесты и сравнение
выполняет независимый supervisor без HTTP-сервера и браузера.

```powershell
& .\scripts\run_local.ps1 scripts/manage_runs.py start tests --no-monitor
& .\scripts\run_local.ps1 scripts/manage_runs.py status
& .\scripts\run_local.ps1 scripts/manage_runs.py stop <job-id>
```

B завершило 1350 updates; A сохранён на +1350 без продолжения. Сравнение
`e6f8970e42a54854998f05dfefa718df` завершено: 180 эпизодов, exit 0.
Parent — 27/60, A — 23/60, B — 25/60; unsafe соответственно 0/0/1.
B не прошёл критерии продвижения. Кандидат остаётся core_24650.
[Инструкция](dashboard/README.md) · [Карточка](docs/results/2026-09-30-stair-comparison-1350.md).

## Текущий кандидат

**core_24650** остаётся development candidate. В сравнительном v2 screen
30.09.2026 на RTX4080 Laptop проверены 19999, 24650 и pinned rl_sar:
лучший результат у 24650, но весь объявленный диапазон ещё не принят.
24650: 107/160, 0 unsafe; 19999: 87/160, 2 unsafe; rl_sar: 66/160, 5 unsafe.
Simulation/hardware qualification отсутствует.
[Полный результат сравнения](docs/results/2026-09-30-locomotion-v2-selection.md).

Последующий [A/B пилот от 24650](docs/results/2026-09-30-tracking-posture-pilot.md)
завершён: 2 × 100 updates, 420 probe episodes. Изменение pose penalty не прошло
критерии продвижения; кандидат сохранён.

[Диагностика control](docs/results/2026-09-30-stair-continuation-diagnosis.md)
добавила 310 эпизодов и выявила влияние порядка actor в батче. Для следующего
пилота предусмотрено сравнение в одинаковых case/reset slots.
[LR-пилот 1e-5/1e-6 завершён](docs/results/2026-09-30-lr-pilot-result.md):
2 × 300 updates, 420 эпизодов. Критерии улучшения не пройдены;
на +300 control и low LR дают 25/60, у low LR один unsafe. Кандидат — 24650.

[План обучения](docs/TRAINING_STRATEGY.md): прежний curriculum закрыт на +1350.
[Reset-only pilot завершён](docs/results/2026-10-01-reset-pilot-result.md):
по 300 updates A/B и 180 probe episodes, job `37198e6459844450a190984e03beef16`,
exit 0. Parent/A/B 27/21/18 successes из 60, unsafe 0/0/0. Upright reset
устранил initial tilt-invalid, но B потерял stair tempo и малые команды;
кандидат 24650 сохранён. Следующая проверка — native adaptive против fixed
LR 1e-5 на одинаковом upright reset. [D1.1 workflow](docs/results/2026-10-01-schedule-pilot-plan.md)
реализован и запущен через supervisor 01.10 в 12:59 МСК: fresh preflight,
по 300 updates, seed 9911, 180 episodes. Бюджет закрытого reset пилота
не продлевается; нового результата пока нет.
Основой pipeline служит стандартный pinned Robot Lab train.py/OnPolicyRunner/PPO;
изменения ограничиваются подтверждёнными failures, без старых runner hooks.
[Исходная карточка](docs/results/2026-10-01-reset-pilot-plan.md) сохраняет
постановку, preflight и историю восстановления workflow.

V2 отделяет software contract, короткий отбор (160 эпизодов на policy),
независимую validation выбранного actor и sim2real. Отдельно публикуются tracking,
переходы, непрерывный ноль, stair traversal, safety и нагрузка приводов.
[Протокол и первичные источники](docs/CORE_LOCOMOTION_EVALUATION.md).

- [Актуальный статус](docs/TRAINING_STATUS.md) и [реестр policies](docs/POLICY_REGISTRY.md)
- [План проекта](docs/PROJECT_PLAN.md) и [SDK2 sim2real](docs/SDK2_DEPLOYMENT.md)
- [Инфраструктура](docs/INFRASTRUCTURE.md) и [индекс документации](docs/README.md)
- [Закрытие последнего эксперимента](docs/results/2026-09-30-experiment-closure.md)

Сохранены checkpoint/export packages 24650 и upstream19999.
rl_sar из той же Robot Lab линии по сообщению владельца участвует в сравнении;
его bytes остаются в vendor. Экспериментальная Git-ветка relkernel удалена,
raw evidence и восстановимый bundle сохранены. Новых серверных обучений нет.

## Проверка проекта

```powershell
python scripts/vendor_materials.py verify
& .\scripts\run_local.ps1 -m unittest discover -s tests -q
& .\scripts\run_local.ps1 scripts/verify_project.py
```

Стандартная команда unit tests выше возвращает supervisor job ID;
итоговый exit code и журнал доступны через CLI и монитор. Реальное управление B2W требует
отдельного явного допуска и прохождения этапов из SDK2 deployment plan.
