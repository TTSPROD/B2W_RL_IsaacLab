# Flat: проверка расписания команд, 18 сентября 2026

> Исторический протокол завершённого опыта. Результаты и условия ниже сохранены;
> актуальные решения и очередь: [план](PROJECT_PLAN.md), [журнал](TRAINING_PROGRESS.md).

**Итог 18 сентября, 12:49 МСК:** эксперимент seed 48 завершён. Staged прошёл
nominal и bounded_v1: по 100/100 без отказов и по 100/100 tracking; оба сценарных
gate пройдены. Constant: 99/100 и 92/100 без отказов; оба gate не пройдены.
Обе группы завершили 4000 updates, checkpoints/optimizer/TensorBoard и export
проверены. Последняя оценка прервалась вместе с координатором по неизвестной
причине; повторена на том же export, cases и physical profile с exit 0 и проверкой
digest. Обучение не перезапускалось. [Полный итог](results/2026-09-18-flat-schedule-final.json).
Выбранный staged позднее проверен на [seeds 49/50/51](STAGED_QUALIFICATION.md):
только seed 49 прошёл оба профиля, общий Flat gate не пройден. Обе очереди
завершены; дальнейшие решения — в [плане](PROJECT_PLAN.md).


## Поправка исполнения: параллельное обучение

18 сентября пользователь запросил ускорение параллельной работой. Работавший
constant trainer передаётся новому координатору без restart, staged запускается
рядом на той же GPU (2 × 4096). После окончания и проверки обоих первых сегментов
по 2500 updates обе группы продолжаются параллельно ещё по 1500 updates.
Исходные seed, commands/rewards, sample budget, restart boundary и evaluation cases
сохранены. Constant начинал один; отличие аппаратного расписания явно учтено.
Ни одного дополнительного simulator/RNG restart при передаче не предусматривается.
Порог свободной VRAM — 5%; монитор останавливает только принадлежащие ему trainer
при нарушении порога или технической ошибке. Проверки и evaluations идут после обучения.

Новый coordinator: `scripts/run_flat_schedule_parallel.py`.
Новый status: `logs/ablations/flat_schedule_parallel_seed48_20260918/job.json`.
Первоначальный последовательный протокол ниже сохранён как история решения;
его launch snapshot и исходный `protocol.json` не переписываются.


## Основание

[Диагностика](results/2026-09-18-flat-diagnosis.json) воспроизводится через
`scripts/diagnose_flat_qualification.py`. Все 53 первых отказа seeds45/46/47 —
касания задних голеней: RL_calf при positive yaw (45), RR_calf при negative yaw (8).
Raw actions не достигают clip100 (наблюдаемый максимум16,94), live observation
и action-target parity сохраняется. Это не исключает насыщение actuator torque.
Порог контакта одинаков —1N; train использует penalty weight−1, но
`illegal_contact=None`, а evaluator записывает sticky failure на каждом physics step.
Это различие целей, не обнаруженная ошибка evaluator. Reference прошёл оба профиля.

В окнах2200–2299 →2400–2499 training error_xy уменьшается:
seed45 0,639→0,550; seed46 1,067→0,912; seed47 0,813→0,640.
У seed46 штраф контактов остаётся существенно выше: −0,172 против ≈−0,0074.
Его nominal RMS vx особенно плох при движении назад (0,370м/с);
даже стойка имеет положительный bias vx около0,139м/с.
Эти training errors не являются RMS evaluator; разные команды/randomization/noise.
Кривые продолжают улучшаться, но не доказывают, что одного увеличения бюджета хватит.

Успешное прежнее продолжение начинало mix с уже обученной политики.
Гипотеза этого завершённого опыта: начальное освоение обычных команд до pure-yaw mix полезнее,
чем mix с нуля при одинаковом бюджете. Rewards, физика и evaluator сохраняются.

## Протокол, зафиксированный до запуска

| Параметр | Constant | Staged |
|---|---|---|
| Новый training seed |48|48|
| Среды / rollout |4096 /24|4096 /24|
| Updates0–2499 |mix0,25|instrumented upstream, mix0|
| Плановый restart |после2500 updates|после2500 updates|
| Updates2500–3999 |mix0,25|mix0,25|
| Yaw weight |1,5|1,5|
| Общий бюджет |4000 updates,393216000 transitions|тот же|

Mix0 использует уже проверенный адаптер: он не меняет команды или upstream RNG.
Обе группы стартуют с нуля и одного seed; после2500 updates сохраняются model,
optimizer и adaptive LR, simulator/RNG инициализируются заново у обеих групп.
Это парный development experiment, не репликация трёх training seeds.

Порядок: smoke обеих групп12+12 updates на16 средах; затем constant2500+1500,
затем staged2500+1500. Только один trainer одновременно; минимум свободной
VRAM5% сохраняет последний выбор пользователя. Перед очередью требуется≥50%
свободной VRAM. Контроль ресурсов каждые5s; timeout каждого training segment4h.
Ошибки процесса, NaN, hashes или проверки артефактов останавливают очередь.
Телеметрия проверяется после каждого сегмента; её ошибки блокируют следующий.
Незапланированный restart требует отдельного решения, автоматического resume нет.

Конечные model_3999 проходят checkpoint/optimizer/TensorBoard validation и
export parity, затем reference и обе группы получают по100 эпизодов на
nominal seed20261101 и bounded_v1 seed20261102. Cases и физические профили
записаны до обучения; одинаковость физических выборок проверяется digest/readback.
Старые20261001/02 раскрыты и используются только в диагностике.

На каждом профиле отдельно:≥99/100 без sticky failure; в каждом семействе
команд pooled RMS vx/vy≤0,20м/с и yaw≤0,25рад/с. Публикуются episode p95/max,
контакты и оба направления yaw. Reference должен пройти оба профиля.
Если проходит только одна группа — кандидат для будущей репликации;
если обе — сохранить более простую constant; если ни одна — новая гипотеза.
Промежуточный checkpoint не выбирается, budget автоматически не увеличивается.
После завершения очередь останавливается. Rough и новая трёхseed-серия не запускаются.

## Артефакты и запуск

- Coordinator: `scripts/run_flat_schedule_ablation.py`.
- Статус: `logs/ablations/flat_schedule_seed48_20260918/job.json`.
- Зафиксированный protocol/source snapshots: соседние `protocol.json`, `protocol.md`, `source/`.
- Оценки: `logs/qualification/flat_schedule_seed48_20260918/`.
- Запуск в project `.venv`: `python -B -u scripts/run_flat_schedule_ablation.py`.

По запросу пользователя установлен дополнительный Codex skill
[robium-ai/robium isaac-lab](https://github.com/robium-ai/robium/tree/863840ed40aaa218878ba4280816aa9b1f9541ed/skills/isaac-lab),
commit `863840ed40aaa218878ba4280816aa9b1f9541ed`.
Применены рекомендации по небольшому smoke, RSL-RL артефактам и изменению одного
фактора. Его результаты Go2/IsaacLab3.0 не переносятся на B2W/Lab2.3.2;
наш runtime и фиксированный бюджет сохраняются.
