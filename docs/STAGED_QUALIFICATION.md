# Staged Flat: повторение на трёх seeds, 18 сентября 2026

**Снимок 18 сентября, 15:12:52 МСК:** seeds 49/50 завершили первые 2500 updates
с exit 0 и проверкой артефактов. Выполняется вторая часть: **2596/4000** и
**2597/4000** соответственно; seed 51 ещё не запущен, evaluations — 0/8.
Исходники активной очереди совпадают с frozen SHA256. [Датированный снимок](results/2026-09-18-staged-qualification-status.json).
Ноутбук прошёл техническую [квалификацию](LAPTOP_WORKER.md), но обучение ему
не назначено. По последнему уточнению пользователя очередь остаётся на ПК:
49/50 параллельно до 4000, затем 51 отдельно. [Сервер проверен](SERVER_PERFORMANCE.md),
к Isaac Lab не допущен. Качество seeds 49/50/51 пока не оценено.

Основание: [seed 48](results/2026-09-18-flat-schedule-final.json) прошёл оба
development профиля с 100/100 без отказов и всеми сценарными tracking gates.
Пользователь разрешил продолжить обучение. Следующий этап проверяет
воспроизводимость расписания, а не продолжает веса удачного seed.

## Зафиксированный протокол

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
