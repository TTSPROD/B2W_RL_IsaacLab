# Native standard continuation от 24650

Пользователь разрешил дообучение 12.10 и уточнил бюджет GPU: до 4000 сред.
Текущий bounded A/B — local RTX4070 Ti; server jobs и hardware не выполняются.

[Frozen recipe](../../configs/24650_native_continuation_20261012.json):
по 150 PPO updates, 4000 envs, seed 9930, final iteration 24799.
Оба плеча начинают с неизменённого checkpoint 24650 и его Adam state.
Pinned Robot Lab train.py, установленный OnPolicyRunner/PPO исполняются без
изменения bytes или наследования прежних runner hooks.

Изменение между плечами — только вероятности полных direct command programs
на non-stair terrain: control 20% на zero/vx/vy/yaw/mixed;
focus 10/10/35/35/10%. Первый знак осевых и mixed программ выбирается независимо
на каждом цикле. Полные величины/длительности соответствуют v2; stair sampling
одинаковый. Гипотеза: дополнительная экспозиция малых осевых команд улучшит
tracking без потери нуля, longitudinal, mixed и лестничных навыков.

Общая для A/B новая task configuration строится напрямую от pinned B2W Rough,
без импорта исторических task chains. Сохранены actor ABI 57→16, critic247,
scales/order, raw previous actions, исходные rewards/actuators и parent
moderate-yaw reward kernel. Общие настройки объявлены явно: direct body-frame
commands без heading, upstream terrain families75% + flat25%, upright roll/pitch
reset±0.1rad, 70s horizon, fixed terrain levels, fixed LR1e-5, true safety terminal
каждый physics step. Это новая runtime/task-линия, а не exact replay истории.
Физические расхождения Isaac/MuJoCo дообучением ещё не устранены.

До PPO — 128env ×3600steps на каждом плече: exact actor/critic/Adam restore,
нет optimizer updates, finite state/actions, command coverage, initial tilt-valid,
safety precedence над timeouts. Snapshot resolved config/PhysX и все hashes
сохраняются. Training safety counts не являются acceptance метриками.

После обучения — только final checkpoints, без выбора промежуточных сохранений.
Parent/control/focus проверяются в отдельных fresh processes, полный v2 case order,
по160 episodes, всего480. Одинаковые case/reset slots и GPU/runtime.
Порог scoring не изменяется. Focus gate: unsafe0, paired losses0 против обоих,
не менее2 wins против parent и1 против control, без ухудшения success cells и
max wheel saturation. Прохождение означает finalist, без automatic promotion.
При отрицательном результате parent сохраняется; бюджет не продлевается.

Исходная попытка: job `5ab68628f8664d5d8b0b91c3cfaa64b5`,
raw `logs/dashboard/jobs/5ab68628f8664d5d8b0b91c3cfaa64b5/native_continuation/`.
Этот документ фиксирует план, не подтверждает completion или качество новых весов.
