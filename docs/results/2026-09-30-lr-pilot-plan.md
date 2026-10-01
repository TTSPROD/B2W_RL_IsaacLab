# LR-пилот от 24650: план до обучения

Дата: 30.09.2026. Основание —
[диагностика control continuation](2026-09-30-stair-continuation-diagnosis.md).
Гипотеза: меньший LR cap помогает сохранить навыки parent при continuation.
Диагностика не установила LR как причину прежних failures.

## Зафиксированный эксперимент

[Конфигурация](../../configs/24650_lr_ab_20260930.json), SHA-256
`1a510dd230ee9d011d4c04b7a7b3390b2de320b0e89a64c145da5812d62ff1ff`.

| Параметр | Control | Low LR |
|---|---|---|
| Parent | core_24650 | Тот же checkpoint |
| LR cap | 1e-5 | 1e-6 |
| Training seed | 9901 | 9901 |
| Среды | 4096 | 4096 |
| Updates | 300 | 300 |
| Rollout | 24 × 0,02 с | Тот же |
| Опыт | 29 491 200 transitions | 29 491 200 transitions |
| Симулированное время / среду | 144 с | 144 с |
| Checkpoints для probe | +25 / +100 / +300 | +25 / +100 / +300 |

Reward terms/weights, первоначальные банки 24650, геометрия, cohorts, noise,
randomization, actuators, 57→16 ABI, 50 Hz и остальные PPO настройки сохраняются.
Actor/critic/std и все tensors состояния Adam проверяются после восстановления.
LR ограничивается перед каждым optimizer step, включая adaptive LR upstream.
Новые identities: `lrcontrol_24675/24750/24950`, `lrlow_24675/24750/24950`;
они не смешиваются с прежними `control_*` exports.

## Один самостоятельный dashboard workflow

1. Проверить frozen inputs/sources; выполнить нулевой audit обоих плеч на 128 средах.
2. Измерить parent: restricted probe, 60 эпизодов. Flat μ=1 и Rough 0,10 м —
   stand/longitudinal/lateral/yaw; Stairs up/down 0,18 м — traverse 0,7 и stop/restart 0,5.
3. Обучить control 300 updates, затем low LR 300 updates. Повторить config/Adam
   audit перед первым update каждого плеча уже на 4096 средах.
4. Выполнить export parity шести checkpoints и тот же probe для каждого.
   Один actor на fresh process, одинаковые case/reset slots и число сред.
   Всего с parent: 420 эпизодов, 28 terrain processes. Проверки +25/+100
   выполняются после обучения обоих плеч и не являются online early stopping.
5. Рассчитать решение. Только прошедший правила финалист получает полный v2
   screen: ещё 160 эпизодов, восемь процессов. Independent validation,
   второй training seed и автоматическая promotion не запускаются.

Чат и браузер не управляют процессом. Worker сохраняет status/return code,
владеет деревом дочерних процессов, позволяет остановить весь workflow.
При ошибке дальнейшие стадии не исполняются; сохранённые данные остаются.

## Покрытие обучения и решение

Диагностика не меняет commands/rewards/RNG/physics. Для retention, flat, rough,
stairs_up/down отдельно записываются transitions, completed episodes,
mean completed return/length, минимум полных episodes на среду. Для target banks
сохраняются counts исполненных шагов каждой фазы каждого case.

Target horizon — 70 с. Для решения нужны минимум два полных target episodes
на **каждую** среду в каждом плече. 144 с — бюджет, а не обещание покрытия
при ранних termination. Незавершённые returns не считаются completed returns.
Training diagnostics не заменяют deterministic policy evaluation.

Retained behavior и улучшение рассматриваются отдельно. Публикуются дефицит
успехов относительно parent по ячейкам и сравнение с matched control.
Равенство parent само по себе не продвигает новый actor.

Финалистом может стать только low-LR checkpoint +300 при всех условиях:

- Полные, проверенные 420 probe episodes; coverage gate обоих плеч выполнен.
- Нет unsafe у кандидата.
- В каждой terrain/case ячейке success count не меньше parent и matched control.
- Средний response ratio на ±0,3 lateral и yaw выше parent минимум на 0,05
  и matched control минимум на 0,02 — одновременно для обеих осей.
- Максимальная доля torque saturation не превышает parent более чем на 0,02
  для колёс и 0,01 для ног. Это метрика модели, не hardware thermal limit.

Все gates locomotion v2 сохранены. Checkpoints +25/+100 — только диагностика.
Один training seed и пять reset seeds дают предварительный результат.

## Запуск и артефакты

```powershell
& .\scripts\run_local.ps1 scripts/run_lr_pilot.py --preflight-only
& .\scripts\run_local.ps1 scripts/run_lr_pilot.py
```

Команды выполняются по очереди через [дашборд](../../dashboard/README.md).
Первая делает audits без обучения; вторая запускает весь workflow.
Submission не является подтверждением завершения обучения.

В `logs/dashboard/jobs/<id>/` сохраняются `experiment_manifest.json`, sources,
`pilot_progress.json`, журналы audits/плеч, `evaluation/<actor>/` с plans/raw,
общая `evaluation/analysis/summary.json`, `pilot_decision.json` и `result.json`.
Последний появляется только после успешного завершения workflow. Completed с
selected=null означает завершённый эксперимент без продвижения; failed — ошибку.
Изменение protected sources/frozen inputs блокирует следующую стадию.
Исторические raw/checkpoints/exports не перезаписываются. Hardware approval нет.

72 unit/integration tests прошли до запуска. Отдельный preflight job
`2d1ca414a9124d289db958456ba9f242` завершён: оба аудита, 0 updates, exit 0.
Основной job: `72ef5d9d71f04597a9a07585a1cafcc9`; актуальная стадия в dashboard.
Этот документ — план и provenance запуска, не отчёт о качестве полученных весов.
