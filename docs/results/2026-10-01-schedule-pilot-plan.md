# D1.1: native adaptive/fixed schedule A/B

01.10.2026 пользователь разрешил продолжить локальное обучение по следующему
плану. [Исходная спецификация](../../configs/24650_upright_schedule_ab_20261001.json)
сохранена побайтно: design SHA-256
`5dc6fa17a5f51eb6b895fc90bd8bd7d7f65fea377e2259d90279508c4ede87b6`.
Её исторический `launch_enabled=false` описывает готовность на момент создания;
разрешённое исполнение фиксируется отдельно в experiment_manifest нового job.
План — [TRAINING_STRATEGY](../TRAINING_STRATEGY.md),
основание — [результат reset-only пилота](2026-10-01-reset-pilot-result.md).

## Постановка

Обе ветки восстанавливают actor/critic/std/Adam ровно из core_24650,
seed 9911, 4096 envs × 24 policy steps/update, по 300 updates.
Final iteration 24949; 29 491 200 transitions и 144 с/env на плечо.
Rewards, geometry, command banks/weights, terminations, actuators, physics,
ABI 57→16 и previous-action semantics одинаковы. Обе ветки используют
upright reset roll/pitch ±0.10 рад и fixed target levels без promotions.
Единственный learning diff: `algorithm.schedule=adaptive/fixed`.
Начальный/восстановленный Adam LR 1e-5; entropy/std и остальные PPO поля parent.

Pipeline — неизменённый pinned Robot Lab train.py и штатные OnPolicyRunner/PPO,
native resume, init_at_random_ep_len=True. Custom runner/LR cap/hooks нет.
[Task config](../../scripts/b2w_schedule_pilot_cfg.py) наследует выполненную
upright постановку; новый startup audit сравнивает весь actual MDP с captured
upright YAML, нормализуя только seed/log dir/число сред и имя command class.
Оригинальный audit дополнительно сверяет robot/ABI/rewards/events с parent.

## Порядок и проверки

[Supervisor workflow](../../scripts/run_schedule_pilot.py) запускает fresh
preflight A/B: 128 envs × 3600 steps, 0 PPO updates. Восстановление model/Adam
точное, initial tilt/nonfinite/hard-joint invalid=0, stale contact resets=0,
safety имеет приоритет над timeout; доступны noninitial и >=12 с zero phases
в каждом target cohort. Runtime/source hashes обеих веток совпадают.
Failed preflight закрывает workflow без PPO; старые preflight/A/B не кешируются.

После положительного preflight последовательно идут A 300, B 300,
export parity и 180 episodes parent/A/B в fresh processes, одинаковые slots,
reset seeds 73001–73005. Policy IDs: 24650, scheduleadaptive_24949,
schedulefixed_24949. Parent probe выполняется заново; текущие evaluator thresholds
и 60-episode protocol сохранены. Final checkpoint выбран заранее;
intermediate checkpoints только diagnostic.

[Независимая проверка завершения](../../scripts/schedule_completion.py)
требует child exit 0, все 300 standard iterations, полный timesteps count,
finite checkpoint 24949 и Adam +6000 steps/параметр. Для fixed дополнительно
все 300 logged LR и final optimizer LR равны 1e-5, atol 1e-10.
Так completion не зависит от Python-кода после Kit fast shutdown.
Actual executed hashes в job/sources отделены от design и поздних implementation hashes.

Retention/gain gates взяты из frozen specification: каждая cell не хуже parent
и A, frozen observed parent floors, unsafe=0, малые lateral/yaw не хуже parent/A
более чем на 0.02, saturation extras к parent ≤0.02 wheels/0.01 legs.
Schedule hypothesis поддерживается только при retention и +2 успешных descent
episodes либо +0.05 mean progress ratio descent stop/restart относительно A.
Native schedule без gain не объявляется доказанной причиной прежнего отказа.
Automatic promotion, budget extension и qualification отсутствуют.

## Выполнение

Перед запуском 102 tests прошли с exit 0, supervisor job
`0888121b794d4a388ef5df9e852be126`. Проверены разрешённый agent diff,
rejection invalid reset/missing zero, сохранение LR при реальном native PPO
update на синтетических данных, rejection неправильного fixed LR в completion
и невозможность заменить retention успехом отдельной gain-метрики.
Синтетический unit test не является тренировкой B2W или evaluation policy.

Job `fca74ce8c7284885bb8fdd2aa5d84610` поставлен 01.10 в 12:54:35 МСК
через независимый supervisor без открытия HTTP-монитора.
Raw, captured sources, checkpoints и exports хранятся в собственных job/run.
Candidate core_24650 сохранён. На момент запуска результата обучения/отбора нет.


Первая попытка `fca74ce8c7284885bb8fdd2aa5d84610` отменена через supervisor
в 12:58 МСК до PPO: при интеграции новым arm names не соответствовали ключи
унаследованного curriculum monitor. Сохранены original source snapshots/raw.
Новый contract явно определяет оба arm keys с `adaptive=False` для terrain;
это не связано с native PPO schedule. Добавлен тест arm mapping и вывод
исключения до Kit close. MDP/PPO и frozen design не менялись.
Повторные 102 tests прошли, job `94fc3ff42eb2414ab249356ef877a37f`, exit 0.
Исправленный job `2eaf04619ca64678a110e6cc9fa96ff9` запущен в 12:59:29 МСК,
выполняет новые preflights с начала; ни одного PPO update из первой попытки нет.


Fresh preflights исправленного job завершены с exit 0: оба по 3600 steps,
0 PPO updates, exact model/Adam restore, initial invalid=0, stale contact=0,
terminal overrides timeout, доступность noninitial/long-zero и MDP audits
подтверждены. Native agent diff только schedule; runtime одинаковый.
[Preflight publication и raw hashes](evidence/schedule_pilot_20261001/preflight.json).
На 13:07 МСК adaptive выполнил 29/300 standard PPO updates; fixed и
180 probes идут затем. Actual training agent audit passed. Before-run project
verifier: 250 local links, 2 retained checkpoints, исходные 480 episodes;
vendor verifier: 1463 файла / 6 sources. Исторические 51 reset-pilot inputs
проверены неизменными. Итог нового обучения и отбора пока отсутствует.

## Итог

Исправленный job завершён 01.10 в 14:03:29 МСК, exit 0. Обе ветки выполнили
по 300 updates; export parity и 180 probes завершены. Parent/adaptive/fixed:
27/24/22 successes, unsafe 0/0/0. Fixed не прошёл retention и frozen parent
floors; schedule hypothesis не поддержана. Promotion, qualification и budget
extension отсутствуют. Подробный пересчёт и diagnostics —
[отдельный отчёт](2026-10-01-schedule-pilot-result.md).

Последующая проверка промежуточных fixed checkpoints опубликована отдельно:
[+1/+51/+101/+151](2026-10-05-schedule-checkpoint-diagnosis.md). Ни один не
прошёл parent retention; это не меняет frozen design или итог D1.1.
