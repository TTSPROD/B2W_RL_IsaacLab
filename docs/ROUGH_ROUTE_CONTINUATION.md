# Rough route: запрошенное продолжение150→350

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

20.09.2026. После сообщения об остановке route59/60 на Flat regression
пользователь прямо поручил «продолжай». Разрешён один оставшийся этап200
updates/seed; прежний failed150 сохраняется. Это диагностическое продолжение,
не автоматическое продление и не успешное прохождение development protocol.

## Проверенный исходный результат

[Route queue](results/rough_route_correction_20260920.json) завершилась
20.09 в09:59:13 МСК:12 дочерних стадий exit0, оба seeds завершили150,
curriculum `[0,1,1,1,1]`. Все четыре Flat оценки дали100/100 safe и прошли
абсолютные tracking gates. Единственный относительный отказ: seed60,
bounded_v1, lateral yaw RMS0,03469682853251822 при лимите0,03414650888219207
рад/с; anchor0,024146508882192066. Остальные три Flat regression пройдены.
Rough150 не оценивался, поскольку Flat gate остановил очередь раньше.

Исключение относится только к этому известному quality failure. Перед
продолжением пересчитываются полные Flat rows и указанное превышение,
проверяются совпадение live/published job, source/protocol/parent hashes,
оба собственных checkpoint/optimizer и отсутствие незавершённых стадий.
Technical failure, иной parent, другой failed profile или дополнительные
абсолютные/относительные нарушения не покрываются этим запуском.

## Неизменённый recipe

Seeds59/60 продолжаются только от собственных route `model_149.pt`:
actor57→16, critic247, optimizer и curriculum восстанавливаются.
Новые critic или переинициализация actor не вводятся. Ровно200 updates/seed,
финальный `model_349.pt`,4096 env последовательно на квалифицированном desktop.
Новых transitions39 321 600; вместе с исходными150×2 получается68 812 800.

Сохраняются route command/reset/22с Rough и20с Flat, Flat tiles30%,
tilt terminal>60° дольше0,1с, LR1e−4 fixed, clip0,1, std0,1 fixed, entropy0,
rollout24, drift guards0,25 и false для initial random episode clock.
Stage2 открывает cap2; promotion остаётся только safe traversal.
Native reset после resume начинает новые эпизоды; физическое состояние и RNG
не продолжаются побитово. Исходники trainer/evaluator не меняются.

## Финальные проверки и ограничения

После обоих trainings выполняются4 Flat100 и48 Rough100 batches:
4families×3levels×2profiles×2seeds. Сохраняются исходные cases и все
Flat absolute/relative, Rough≥95% per kind/family/level/profile,
corridor/contact/tracking/route критерии. Level2 curriculum проверяется отдельно.

Финальный диагностический набор собирается даже при quality failure в
отдельном batch, но новых training updates после350 не назначается.
`final_checks_passed` описывает только финал. `development_protocol_passed`
и `policy_quality_accepted` остаются false даже при успешных финальных checks:
ранний failed150 не переписывается, новая qualification не запускалась.

Finite/drift/export/physics/source-hash failure немедленно прекращает
очередь. До child свободно≥50%VRAM; во время≥5%; training timeout3600с на seed,
evaluation1800с на batch. Повторный запуск в существующий output и
автоматический restart/замена seeds запрещены. Другие проекты, сервер,
Stairs и hardware не затрагиваются.

## Команды и provenance

`scripts/run_rough_route_continuation.py --verify_only` проверяет evidence без GPU training.
`scripts/run_rough_route_continuation.py --continue_after_failed_flat150` запускает очередь.
Требуются локальные исключённые из Git checkpoints/runtime; это не fresh-clone recipe.

Job: `logs/rough/rough_route_continue_20260920/job.json`.
Итог: `docs/results/rough_route_continue_20260920.json` после завершения.
Оба parents, protocol, источники и cases фиксируются хешами до первого child.
Во время исполнения frozen источники и этот протокол не изменяются.
Текущий статус и launch evidence — в [TRAINING_PROGRESS](TRAINING_PROGRESS.md).
