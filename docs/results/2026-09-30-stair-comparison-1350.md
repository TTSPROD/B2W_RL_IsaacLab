# A+1350 / B+1350: продолжение по указанию пользователя

Актуализировано 1 октября 2026. **Оценка завершена, B отклонён.**
Job `e6f8970e42a54854998f05dfefa718df` завершился 30.09 в 23:40 МСК, exit 0.
180 эпизодов выполнены в отдельных процессах с одинаковыми case/reset slots.

| Actor | Success | Unsafe | Подъём | Спуск | Max wheel saturation fraction |
|---|---:|---:|---:|---:|---:|
| Parent 24650 | 27/60 | 0 | 2/10 | 10/10 | 0.1275 |
| A +1350 | 23/60 | 0 | 0/10 | 8/10 | 0.1331 |
| B +1350 | 25/60 | 1 | 0/10 | 10/10 | 0.2720 |

У всех трёх Flat 10/20, Rough 5/20. B не проходит frozen gates: неполное
phase/level coverage, unsafe, регрессия подъёма, отсутствие требуемого ascent gain
против parent/A, yaw retention относительно A и рост wheel saturation.
Последняя метрика относится к симуляционной модели, не к измеренным лимитам B2W.
Кандидат core_24650 сохранён. Бюджет закрыт; A не продолжался, новых training seeds,
full screen и независимой validation нет.

Проверены raw/trace, captured source и export/input hashes; пересчитанное решение
совпало с записанным. Побайтные копии:
[сводка](evidence/stair_comparison_1350_20261001/summary.json),
[решение](evidence/stair_comparison_1350_20261001/decision.json),
[публикация и SHA-256](evidence/stair_comparison_1350_20261001/publication.json).
Raw остаются в `logs/dashboard/jobs/e6f8970e42a54854998f05dfefa718df/evaluation/`.

Следующий шаг — диагностика причин/фаз safety-reset и отсутствия promotions;
новая геометрия или constraints должны стать отдельной зафиксированной гипотезой.
Этот результат не доказывает невозможность обучения лестницам вообще.

**Обучение B завершено:** 30.09 в 23:12 МСК, 1350/1350 updates,
iteration 26000, 79.2 минуты. SHA checkpoint
`688ddce2ab463c41925c3cd98fb21a9925b19e246a764d9c76d5f9d7b1211ee1`,
SHA export `e7aee157f6fc2b51a2f0d6de6dd48dc292e085ae835b24fad339f523fd2d1197`.
Export parity прошёл с max abs error 0.0. A не продолжался.

Первый запуск evaluation упал до rollouts из-за `configs/...`, ошибочно
интерпретированного как `scripts/configs/...`. Исправлено разрешение путей
frozen sources и сохранение статуса уже завершённого training при ошибке
следующего этапа; 86 тестов прошли. Прежнее ошибочное progress сохранено
побайтно перед восстановлением статуса completed из captured snapshot.
[Evidence](evidence/stair_curriculum_20260930/training_completion.json).

**Завершённая оценка:** job `e6f8970e42a54854998f05dfefa718df`, только 180
эпизодов parent/A/B, без новых updates. Исходные training snapshots и exports
проверены отдельно от текущих исправленных implementation hashes.
В B curriculum не дал promotions; 1296 demotions, все target stairs на level 0.
Верхние уровни не покрыты. Это training observation, а не новый policy score.

## История запуска

Job `a2c89fd6c2a64c3cb8e005982e8249bd`, запущен 30.09.2026 в 21:48 МСК
независимым supervisor **при выключенном HTTP-дашборде**.
Preflight B пройден; PPO начался в 21:53 МСК. Проверены первые 12/1350
updates при выключенном HTTP-сервере, после чего монитор включён отдельно.
Актуальный progress хранится в `logs/dashboard/jobs/<id>/pilot_progress.json`.
Дашборд только показывает файлы, логи и метрики; выполнение от него не зависит.

## Изменение бюджета

После прерывания исходного A/B пользователь явно указал: **A не продолжать,
B обучить 1350 updates**. Предложенное восстановление A+150 и разбиение B
1350+150 отменены до запуска. Recovery-конфиг не использовался ни одним job.

- A: существующий `model_26000.pt`, ровно +1350 updates от 24650;
  SHA-256 `6dd8cf28c785591b13c3b4ef3d1d8fd459a7a1ea7ad86d58ae4c5eeeeb452551`.
- B: исходный 24650 с точным восстановлением actor/critic/std/Adam,
  **1350 непрерывных updates**, 4096 сред, seed 9903, LR cap 1e-5.
- ABI 57→16/50 Hz, rewards, safety, геометрия, команды и PPO сохранены.
- После обучения: export parity, новый parent probe, A+1350 и B+1350 —
  **180 эпизодов** в отдельных процессах с одинаковыми case/reset slots.
- +500 не участвует в этом отборе. Финальный допустимый checkpoint — +1350.
  Сохранённый диагностический +500 B может присутствовать в logs.

[Поправка](../../configs/24650_stair_comparison_1350_20260930.json), SHA-256
`df92541d64ec1666b9ef2c52674d910e1bbee5c56b021df91826d2937571ffef`.
Исходный [план 1500](2026-09-30-stair-curriculum-plan.md), его configs и raw
не переписываются. В новом manifest отдельно указаны изменения launcher/supervisor.

Coverage A извлечён из `B2W_PROGRESS` на iteration 26000, а не из позднего
снимка 1449 updates. Последние 99 updates прерванной попытки не входят в веса
или coverage сравнения. Изменение бюджета выбрано после прерывания A и до
оценки новых checkpoints; результат требует подтверждения независимыми seeds.

Остальные критерии исходного плана сохранены: покрытие всех фаз и верхнего
уровня, unsafe=0, отсутствие регрессий ячеек, выигрыш ≥2 ascent episodes
против parent/A, сохранение малых lateral/yaw и ограничение роста saturation.
Автоматической promotion или аппаратного допуска нет; кандидат core_24650.

## Проверка независимого выполнения

85 тестов прошли с exit 0: job `8b32a565d31d4f4d883f8303837684d0`.
Проверены запрет POST в дашборде, запуск при ошибке открытия монитора,
режим без монитора, process tree cancellation и frozen budget/coverage.
Тестовый job и этот workflow запущены через CLI, когда HTTP-сервер был выключен.
Факт PPO updates без сервера сохранён в [evidence](evidence/stair_curriculum_20260930/independent_supervisor.json).
Монитор можно включить отдельно; job не ждёт его готовности и не обращается к API.

```powershell
& .\scripts\run_local.ps1 scripts/manage_runs.py status
& .\scripts\start_dashboard.ps1
```

Остановка активного процесса выполняется отдельной командой supervisor
(указанные в отчёте jobs уже завершены):

```powershell
& .\scripts\run_local.ps1 scripts/manage_runs.py stop <active-job-id>
```

Новый запуск создаёт собственные snapshots/checkpoints/evidence; старые файлы
прерванного эксперимента остаются неизменными.
