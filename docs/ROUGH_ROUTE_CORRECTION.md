# Rough: согласованное распределение учебных маршрутов

20.09.2026. Новый ограниченный development опыт после проверки финалов350.
Основание: [аудит](results/2026-09-20-rough-latest-audit.json) и
[первичные исследования](ROUGH_RESEARCH_2026-09-20.md).
Предыдущие неудачи150/350 и их артефакты сохраняются.

## Причина изменения

В прежнем обучении команды vx/vy до±1 м/с, случайные heading/reset yaw и
длинные эпизоды не согласованы с площадкой12×12 м. Даже точное выполнение
vx=1 м/с за10 с может нарушить curriculum boundary±5,4 м. Это доказанный
контрпример постановки, но доля таких отказов в прошлой очереди не измерена.
В evaluation важны накопленные displacement/heading errors: допустимый
velocity RMS сам по себе не гарантирует удержание wheel corridor.

Меняется один связанный компонент — распределение учебных эпизодов на Rough.
Команды, reset и длительность согласуются вместе; эффект каждого из них
отдельно этот опыт не идентифицирует. Никакого position/heading feedback
или скрытой навигации в policy/evaluator не добавляется.

## Recipe и reference

- Свежие training seeds59/60. Общий actor — квалифицированный Flat seed54,
  прямой потомок исходной reference; у каждого новый critic247 и optimizer.
  Checkpoints57/58 после failed350 не продолжаются. Это повторяемость
  fine-tuning общей линии, не независимое обучение с нуля.
- Исходная `vendor/rl_sar/policy/b2w/robot_lab/policy.pt` и Flat anchor54
  отдельно оцениваются на прежних random level0 cases nominal/bounded_v1.
  [Результат](results/rough_reference_baseline_20260920.json). Эта ограниченная
  проверка не доказывает превосходство одной политики на всех terrains.
  Имитационная потеря к reference на Rough не добавляется: её собственный
  успех сначала измеряется. Reference используется через actor transfer,
  frozen drift comparator и сохранение Flat replay.
- Один процесс4096 env на RTX4070Ti; seeds последовательно. Для каждого
  50 critic-only updates, затем100+200 PPO. Максимум68 812 800 transitions;
  технические2+2×64 и comparator evaluations считаются отдельно.
- Стандартный PPO: LR1e−4 fixed, clip0,1, std0,1 fixed, entropy0, rollout24.
  Rewards, physics, terrain mix/geometry, actor57→16 и critic247 сохраняются.
  Tilt terminal>60° дольше0,1 с и оба drift limits0,25 сохраняются.

## Распределение эпизодов

Flat tiles30% сохраняют исходный reset,20 с time limit,10 с resampling,
широкие velocity/heading commands и pure-yaw mix0,25.
Rough tiles70% получают22 с:2 с settling и20 с командного эпизода.
60% traverse vx∈[0,20;0,24] м/с;20% approach vx0,30 в течение12 с,
затем stand;20% такой же approach, затем yaw±[0,20;0,30] рад/с.
vy0; до фазы turn yaw0. Выбор ветви и параметров производится на reset,
не меняется посреди эпизода. Это распределение, а не копия evaluation cases:
новый seeded RNG и training terrain geometry сохранены отдельно.

Rough root reset: x0, y±0,10 м, z offset0, yaw±0,025 рад,
roll/pitch±0,1 рад как раньше, root velocities0. Остальные randomization
events сохраняются. Начальная рандомизация episode clock отключается для
всего vector runner: иначе robot на spawn сразу получает позднюю фазу команды.
Это меняет начальную фазу Flat episodes, но не их штатный20 с рецепт.
Partial episodes/RNG не восстанавливаются побитово; stage resume восстанавливает
свой actor/critic/optimizer и curriculum, затем выполняет native reset.

Safe curriculum остаётся прежним: только safe directed traversal, минимум100
moving episodes, promotion≥80%, demotion≤60%, caps0/1/2 по stages.
Смена command distribution при resume запрещена; новая серия начинается
со stage0. Новые qualification seeds и Stairs этим запуском не назначаются.

## Проверки и остановки

Перед основной очередью: CPU tests, vendor hashes, завершённый reference
comparator; native64-env reset/command/timeout/partial-reset fixture, tilt
fixture и GPU PPO/resume2+2 с проверкой optimizer и export parity.
Все smoke веса discard. Начало training подтверждается progress/checkpoint,
один только supervisor PID не считается успешно обученной политикой.

После50/150/350 — обязательные Flat nominal/bounded_v1 по100 cases:
safe≥99/100, каждый scenario RMS≤0,20/0,20/0,25 и прежний relative gate
к anchor54. После150 — все4 Rough families×2 profiles level0 с прежним
development threshold90% отдельно по traverse/stand/turn. После350 —
levels0/1/2 с≥95% в каждом kind/family/profile и curriculum level2.
Никакие cases, corridor, contact, route, tracking или regression limits
не ослабляются. Раскрытые cases — development/regression, не новый hold-out.

Quality failure прекращает следующие updates. Finite/drift/export/runtime,
VRAM и source/protocol hash failure прекращают очередь немедленно.
До дочернего процесса≥50% VRAM свободно; во время≥5%; train timeout3600 с,
evaluation batch1800 с. Нет автоматических продлений, смены seeds или
поиска удачного промежуточного checkpoint. Только полный финал350 обоих
seeds может открыть отдельную qualification задачу.

## Запуск и артефакты

`scripts/run_rough_route_preflight.py --attempt 1` — discard preflight.
`scripts/run_rough_route_correction.py --preflight docs/results/rough_route_preflight_20260920_1.json`
— основная очередь; требует локальных anchor/checkpoints/runtime, не fresh clone.

Job: `logs/rough/rough_route_correction_20260920/job.json`.
Training: `logs/rsl_rl/unitree_b2w_rough/*_rough_route_correction_20260920_s*_stage*`.
Frozen sources/protocol/cases и SHA256 фиксируются до запуска.
Датированная launch-запись и текущий статус находятся в
[TRAINING_PROGRESS](TRAINING_PROGRESS.md); этот frozen protocol во время
очереди не изменяется. GPU jobs других проектов не используются.
Git хранит код и отчёты; новые checkpoints остаются в исключённых `logs/`.
