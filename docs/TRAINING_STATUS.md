# Текущий статус B2W

Дата актуализации: 1 октября 2026.

## Кандидат и результат

**core_24650** выбран по v2 сравнительному screen с upstream_19999 и rl_sar.
У всех actors сохранён ABI 57→16, deterministic inference, 50 Hz.
Кандидат пока не прошёл все nominal cells; аппаратного допуска нет.

| Policy | Успех | Unsafe | Полностью пройденные ячейки |
|---|---:|---:|---:|
| core_24650 | 107/160 | 0 | 20/32 |
| upstream_19999 | 87/160 | 2 | 15/32 |
| rl_sar | 66/160 | 5 | 7/32 |

[Отчёт, отдельные проверки и raw hashes](results/2026-09-30-locomotion-v2-selection.md).
480 эпизодов завершены; независимая validation не запускалась из-за failures screen.

- Checkpoint: `policies/local/core_24650/model_24650.pt`.
- Checkpoint SHA-256: `458f08260f310e0d29d30d7aef3235df5d9c1c8b31d9e0f9637b1dc7f7466123`.
- Export SHA-256: `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36`.
- Методика: [v2 locomotion](CORE_LOCOMOTION_EVALUATION.md).
- Исторический v1 stage-2: 194/300, 0 unsafe; stage-3: 181/300, 0 unsafe.
  Эти результаты не сравниваются напрямую с v2 из-за изменения программ и scoring.

## Открытые задачи

**B завершён:** 1350/1350 updates, iteration 26000, 30.09 23:12 МСК.
Сравнение завершено 30.09 в 23:40 МСК, job `e6f8970e42a54854998f05dfefa718df`,
exit 0: 180 эпизодов parent/A+1350/B+1350, без новых updates.
Parent — 27/60, unsafe 0; A — 23/60, unsafe 0; B — 25/60, unsafe 1.
На подъёме parent 2/10, A и B 0/10. B не прошёл frozen gates:
coverage, safety, ascent, yaw retention относительно A и wheel saturation.
Кандидат core_24650 сохранён; full screen/validation и новые seeds не запускались.
[Итог и проверяемые hashes](results/2026-09-30-stair-comparison-1350.md).

**Training job:** `a2c89fd6c2a64c3cb8e005982e8249bd`, 30.09 21:48 МСК.
По прямому указанию пользователя A не продолжался; B обучен от 24650
до +1350. Training завершён; исходный workflow имеет exit 1 из-за ошибки
пути при старте evaluation. Исправленная оценка выполнена отдельным job выше.
Дашборд переведён в режим чтения. 85 тестов прошли при выключенном HTTP-сервере;
новый workflow также запущен без него. [Карточка](results/2026-09-30-stair-comparison-1350.md).


**Предыдущий stair curriculum A/B прерван:** job `98144fd30b284ac1acc9c90c9f376bbb`,
последнее heartbeat 30.09 в 21:35:53 МСК. A достиг 1449/1500 updates;
последний целый checkpoint — 26000 (+1350), B не начался. Dashboard работает,
на момент проверки его supervisor/обучение отсутствовали, причина завершения неизвестна.
Parent probe завершён: 27/60, unsafe 0; новых qualification результатов нет.
[Проверка и сохранённые hashes](results/evidence/stair_curriculum_20260930/interruption_98144.json).

Завершён [A/B пилот от 24650](results/2026-09-30-tracking-posture-pilot.md):
dashboard job `d3c316481f4b4954b65656b82dc00e67`, seed 9901, 100 updates на плечо,
420 probe episodes. Все три reward-варианта отклонены; parent остаётся кандидатом.
Небольшое улучшение малых команд воспроизводится и в control continuation;
на подъёме есть регрессии и hard joint violations у части checkpoints.
Full screen/validation и второй training seed не запускались.

[Диагностика control](results/2026-09-30-stair-continuation-diagnosis.md): ещё 310 эпизодов.
При прежнем порядке батча исходы и массивы совпадают точно; обратный порядок
меняет 7/140 success. Отдельные процессы с одинаковыми слотами дают на подъёме
parent 2/10, control +25 1/10, control +100 2/10, все без unsafe; успешные cases
различаются. Предыдущие unsafe остаются в evidence.

[LR-пилот 1e-5/1e-6 завершён и отклонён](results/2026-09-30-lr-pilot-result.md):
job `72ef5d9d71f04597a9a07585a1cafcc9`, exit 0, 18:37 МСК.
Выполнены 2 × 300 updates на 4096 средах и 420 probe episodes в одинаковых слотах.
Parent 27/60 unsafe 0; control +300 25/60 unsafe 0; low LR +300 25/60 unsafe 1.
Tracking gain недостаточен; low LR +100/+300 нарушают hard joint limit на подъёме.
Полных target episodes 5311/5324 и 5312/5324: строгий минимум два в каждой среде
не достигнут. Даже без этого ограничения поведенческие критерии не пройдены.
Full screen/validation не запускались; кандидат 24650 сохранён.
Проверены raw/source/export hashes и точное совпадение пересчитанного решения.

После обзора первичных источников был принят [план](TRAINING_STRATEGY.md):
согласовать safety semantics обучения/оценки, затем matched A/B адаптивного
curriculum лестниц (до 1500 updates на плечо). Проверено в коде: target cohorts
не участвуют в текущем adaptive terrain curriculum; privileged critic уже есть.
После положительного результата — повтор на двух seeds и отдельная проверка
разнообразия команд. Adapter и самостоятельный dashboard workflow реализованы;
обе ветки прошли preflight: по 3600 steps / 72 с на 128 средах, 0 PPO updates,
точное восстановление Adam, проверка конфигов и приоритета safety над timeout.
[Карточка запуска, frozen config и диагностика](results/2026-09-30-stair-curriculum-plan.md).

Теперь этот опыт закрыт на +1350. Следующий шаг — разбор причин/фаз частых
safety-reset и отсутствия promotions (B: 0 promotions, 1296 demotions,
все target stairs на level 0). Изменение geometry или constraints требует
отдельной зафиксированной гипотезы; A/B автоматически не продлевать.

- Проверить причины steady tracking failures на Flat/Rough по каждой оси,
  знаку и скорости; low-command response остаётся отдельной диагностикой.
- Разобрать подъём, остановку/restart на высоких ступенях отдельно от спуска.
  Сатурация модели колёс не равна измеренному thermal/current limit B2W.
- Закрыть независимую nominal validation только после успешного screen.
- Выполнить MuJoCo/DDS qualification, аппаратный mapping и actuator/latency
  identification по [SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md).

Предыдущие sampling и kernel эксперименты не подтвердили автоматическую
promotion. Их результаты не доказывают невозможность дальнейшего улучшения
24650 и не дают основания заранее назначать full retrain.
[Закрытие ветки](results/2026-09-30-experiment-closure.md).

## Проверка инфраструктуры

1 октября 2026 перед публикацией: **89 unit/integration tests**, exit 0,
supervisor job `e22338170c3d4a1895168deedc48c20e`. Проверены 204 локальные ссылки,
2 retained checkpoints, исходный v2 screen на 480 эпизодов и 1463 vendor-файла
из 6 pinned sources. Для нового сравнения отдельно проверены 180 эпизодов,
raw/trace/captured source/export hashes и совпадение пересчитанного решения.
Первый проверочный job `d33fad44b20d4f2c8d690588c3c53e93` потерял heartbeat без
итогового exit code; он не считается успешным. Повтор выше завершён с ожиданием
итога supervisor. История технических неудачных запусков сохранена.

Перед LR-пилотом: **72 unit/integration tests**, exit 0, dashboard job
`0b6775dfcbf74abfb64ff6753f2add99`. Preflight job
`2d1ca414a9124d289db958456ba9f242` завершён с exit 0 после обоих audits.

После диагностики лестниц: **65 unit/integration tests**, exit 0, dashboard job
`3829efeea392458f8af91262b21734bb`; project verifier проверил retained policies,
исходный 480-episode screen и 150 local links. Новые 310 эпизодов отдельно
проверены по frozen plans, actor SHA и raw/source hashes при публикации сводки.

Независимый supervisor выполняет train/test/compare, сохраняет status,
return code, progress и logs. Старые hardcoded selected-run/iteration фильтры
удалены. Проектные PowerShell evaluation wrappers сведены к общему supervisor.

Финальная проверка после A/B: 61 unit/integration tests, exit 0 (dashboard job
`154319580991448891076a9cac346fbe`); vendor verifier — 1463 файла / 6 источников;
project verifier — 2 retained checkpoints, 480 исходных эпизодов и 142 local links.
Дополнительно валидированы 420 paired probe episodes, hashes raw/sources и 6 новых
checkpoint exports (ошибка parity на fixtures 0). Тот posture A/B workflow завершён;
актуальные итоги последующих LR/stair workflows указаны выше и доступны в dashboard.
Кнопкой UI остановлен отдельный test job `07f65d7bf5d8485183f8c3aade65d1ed`:
статус cancelled. Тест supervisor также проверяет завершение дочернего дерева.
Перезапуск HTTP-сервера не прерывает detached worker; состояние восстанавливается
из сохранённых файлов. Технические неудачные запуски остаются в истории.

В рамках проверки launcher выполнен **один** локальный PPO update на 128 средах
от 19999 (30.09.2026, run `2026-09-30_15-36-00`). Он проверяет восстановление
parent/optimizer, запись checkpoint и dashboard status. Этот checkpoint не
выбран кандидатом и не включён в registry; обучение осталось в logs.
Новых серверных jobs и hardware actuation не было.
