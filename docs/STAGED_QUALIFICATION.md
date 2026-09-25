# Staged Flat: повторение на трёх seeds, 18 сентября 2026

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

> Исторический протокол завершённого опыта. Результаты и условия ниже сохранены;
> актуальные решения и очередь: [план](PROJECT_PLAN.md), [журнал](TRAINING_PROGRESS.md).

**Итог 18 сентября, 19:08:16 МСК:** staged seeds 49/50/51 завершили по
4000 updates (2500 upstream + 1500 mix) на 4096 средах. Все шесть training
сегментов, три экспорта и восемь evaluations завершены с exit 0; checkpoints,
optimizer/TensorBoard и CPU export parity проверены. [Итоговый снимок](results/2026-09-18-staged-qualification-final.json).
**Flat gate не пройден:** seed 49 прошёл оба профиля; seed 50 — ни одного;
seed 51 — только bounded_v1. Reference прошёл оба. Очередь завершена;
при проверке 18 сентября в 23:05 МСК Python-процессов проекта не обнаружено.
Последующие contact/height абляции также завершены; их итоги — в журнале.
Ноутбук технически квалифицирован, обучение ему не назначалось;
[сервер](SERVER_PERFORMANCE.md) к Isaac Lab не допущен.

Основание: [seed 48](results/2026-09-18-flat-schedule-final.json) прошёл оба
development профиля с 100/100 без отказов и всеми сценарными tracking gates.
Повторение проверило воспроизводимость расписания с нуля: успех development
seed 48 не перенёсся на все три новых seeds. Общая приёмка отклонена.

## Результаты завершённой серии

В каждой ячейке: эпизоды без падений/неколёсных контактов / эпизоды с tracking pass,
из 100. Приёмка tracking определяется pooled RMS каждого семейства сценариев;
число отдельных tracking pass само по себе не является gate.

| Политика | Nominal 20261201 | Bounded_v1 20261202 | Gate nominal / bounded |
|---|---:|---:|---|
| Reference | 100 / 99 | 100 / 100 | pass / pass |
| Seed 49 | 100 / 100 | 100 / 100 | pass / pass |
| Seed 50 | 88 / 82 | 93 / 86 | fail / fail |
| Seed 51 | 96 / 96 | 100 / 99 | fail / pass |

Seed 50: в nominal 11 первых контактов RL_calf при positive yaw и один FL_calf
при negative yaw; в bounded — семь RL_calf при positive yaw. Сценарный yaw RMS
при positive yaw **0,300 / 0,270 рад/с** (порог 0,25); vx RMS при negative yaw
**0,244 / 0,236 м/с** (порог 0,20). Seed 51: четыре первых контакта RL_calf
при positive yaw в nominal, все сценарные tracking gates пройдены на обоих
профилях. Все 23 первых отказа серии — body_contact, а не зарегистрированные
падения. Причина контактов по этим итоговым метрикам пока не установлена.

Финальные model_3999, exports и отчёты сверены по SHA256. CPU export parity:
295 входов на seed, max abs error 0. Physical digest совпадает между reference
и всеми seeds внутри каждого профиля и не меняется во время replay.
Ресурсы обучения: 4252 samples, telemetry errors 0, peak VRAM 10038 MiB,
минимальный запас 18,27% при guard 5%, максимум 65 °C.
Последняя сохранённая проверка кода в 15:18 МСК: 58 тестов проекта и 23 DNS-теста
без ошибок; vendor 1290 файлов / 6 источников проверен. Это отдельная
[проверка публикации](results/2026-09-18-publication-validation.json), а не новая
проверка кода после окончания обучения.

## Сохранённый кандидат seed49

Оба профиля: **100/100 без отказов**, 100/100 episode tracking passes и все
сценарные gates. Худший yaw scenario — positive: nominal 0,21230, bounded
0,20578 рад/с (<0,25). Худший linear component — lateral vy: 0,12554/0,13110 м/с
(<0,20). CPU parity: 295 входов, max abs error 0. Reference также прошёл оба
сценарных gate; cases и physical digests совпадают с seed49 в каждом профиле.

Проверка при актуализации 19 сентября: файлы checkpoint, policy export,
export-report и evaluation reports seed49/reference существуют, их SHA256
совпадают с [итоговым снимком](results/2026-09-18-staged-qualification-final.json).
Повторное обучение или новая evaluation при этой проверке не выполнялись.

- Checkpoint: `logs/rsl_rl/unitree_b2w_flat/2026-09-18_12-07-01-956158_flat_staged_seeds49_51_20260918_seed49_1/model_3999.pt`.
  SHA256: `7d434dce388d4e191d0666f3f6dc825e32aeea3501229c3b0e857233bb8ba12c`.
- Export: `logs/qualification/flat_staged_seeds49_51_20260918/seed49/export/policy-contract-export/policy.pt`.
  SHA256: `403e2ee602cc59260b46cd5a8735c773ccd0592c887ee66f74e023ed4a4d8aa2`.

Пути относительно корня проекта; файлы в logs исключены из Git. Исходные
артефакты сохраняем без дообучения, используем как контроль диагностики и
регрессии. Постоянное хранилище ещё предстоит выбрать. Статус — успешный локальный
Flat-кандидат, не подтверждённый по трём seeds релиз и не допуск к роботу.

## Дальнейший план

После этой серии выполнены контактные и height-абляции на development seeds
50/51; нового кандидата они не дали. [Сводка опытов](TRAINING_PROGRESS.md).
Прежний план очередного подбора reward weights пересмотрен: подготовлен
[reference transfer](REFERENCE_TRANSFER.md) с переносом совместимого actor,
новым critic и коротким PPO-бюджетом. Это отдельная проверка адаптации pretrained
политики; она не является повторением обучения 49/50/51 с нуля.

Seed49 и его артефакты сохраняются без дообучения как контроль. Cases 20261201/02
раскрыты и остаются development; их нельзя объявлять новыми hold-outs.
Условия независимой приёмки и перехода к Rough ведутся в
[PROJECT_PLAN](PROJECT_PLAN.md), статус запуска — в [TRAINING_PROGRESS](TRAINING_PROGRESS.md).

## Зафиксированный протокол завершённой серии

- Новые training seeds: **49, 50, 51**, каждый с нуля.
- 4096 сред, rollout 24, **4000 updates = 393 216 000 transitions на seed**.
  Полная серия: 1 179 648 000 transitions.
- Updates 0–2499: instrumented upstream commands, `pure_yaw_fraction=0`.
- После ровно 2500 updates: checkpoint model_2499 и один плановый restart.
  Сохраняются model, optimizer и adaptive learning rate; simulator/RNG
  инициализируются заново у каждого seed на одинаковой границе.
- Updates 2500–3999: `pure_yaw_fraction=0.25`. Yaw tracking weight **1,5**
  в обеих частях; остальные rewards, physics, PPO, observations/actions неизменны.
- Seeds 49/50 выполняются параллельно: сначала 2500, затем 1500 updates.
  После них seed 51 выполняет те же две части отдельно. Различие аппаратного
  расписания записывается; batch, sample budget и граница restart одинаковы.
- Минимум свободной VRAM **5%**, как ранее выбрал пользователь; монитор каждые
  5 s. Перед запуском требуется минимум 50% свободной памяти. Timeout сегмента
  4 h. NaN, ошибка процесса, hashes/артефактов останавливают очередь. Ошибки
  telemetry блокируют переход к следующему сегменту. Автоматических внеплановых
  training restart, продления бюджета и выбора промежуточного checkpoint нет.

Trainer и schedule уже прошли staged smoke 12+12 updates и полный development
run; исходные hashes проверяются перед повторением. Новые тесты проверяют
подстановку каждого seed, невозможность resume чужого seed и полный бюджет.
Повторный инфраструктурный smoke с теми же исходниками не включается.

## Новые hold-outs и критерии

Nominal evaluation seed **20261201**, bounded_v1 seed **20261202**; они не
использовались в прежних протоколах. До обучения сохраняются точные 100 cases
и спецификации физических профилей. Раскрытые 20261101/02 остаются development.

После обучения: checkpoints/optimizer/TensorBoard validation, CPU export parity,
затем reference и каждый из трёх seeds на обоих профилях (8 evaluations).
Оценки последовательные: 2 s settling + 20 s measurement, no auto-reset,
sticky failures с первого physics step. Physical readback/digest должен
совпадать между reference и всеми seeds соответствующего профиля.

Каждый seed обязан отдельно пройти оба профиля: **≥99/100 без падения или
неколёсного контакта**, в каждом семействе pooled RMS vx/vy ≤0,20 м/с,
yaw ≤0,25 рад/с. Публикуются p95/max, контакты и оба направления yaw.
Reference также должен пройти оба профиля. Среднее по трём seeds не заменяет
индивидуальный pass. При провале любого seed gate серии не закрывается.

После полного сравнения очередь останавливается. Pass этой серии относится
к заданным Flat-профилям; Rough, sim2sim и hardware требуют отдельных gates.

## Артефакты

- Coordinator: `scripts/run_staged_qualification.py`.
- Job: `logs/qualification_runs/flat_staged_seeds49_51_20260918/job.json`.
- Frozen protocol/source: соседние `protocol.json`, `protocol.md`, `source/`.
- Evaluation reports: `logs/qualification/flat_staged_seeds49_51_20260918/`.
- Запуск из корня проекта: `.venv/Scripts/python.exe -B -u scripts/run_staged_qualification.py`.
