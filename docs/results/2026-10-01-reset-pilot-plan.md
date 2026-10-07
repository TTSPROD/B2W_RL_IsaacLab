# Reset-only A/B через стандартный Robot Lab train.py

1 октября 2026. Пользователь разрешил продолжить локальное обучение после
обновления плана. Parent — 24650; ABI 57→16, policy/physics 50/200 Hz.
Новых server jobs и hardware действий в этом опыте нет.

## Frozen постановка

[Конфиг](../../configs/24650_reset_ab_20261001.json), SHA-256
`0b01ba76c5bbd492740117a0655f596580deeca3ed9202042ea4d363ecb19d5c`.
Гипотеза — initial orientation reset допускает состояния вне tilt terminal,
что сокращает доступное время исполнения команд.
[Offline основание](2026-10-01-training-plan-review.md).

- A/control: прежние roll/pitch ±3.14 рад. B/upright: ±0.10 рад.
- Остальные reset ranges/events, assets/dynamics, geometry, rewards, command
  banks, cohorts и общий physics-tick safety adapter одинаковы.
- Target levels фиксированы, adaptive promotions нет в обоих плечах.
- Неизменённый vendor Robot Lab train.py и стандартные OnPolicyRunner/PPO;
  прежние ContinuationRunner, optimizer hooks и custom LR cap не используются.
- Parent agent config: начальный LR 1e-5 и штатный adaptive schedule,
  4096 envs, 24 steps/update; seed 9910, 300 updates/плечо.
- Стандартный resume загружает model/std/critic/Adam; `init_at_random_ep_len=True`
  и сохранённый iteration index — поведение штатного pipeline.
- 300 фактических updates начинаются с index 24650 и заканчиваются index 24949.
  Номер файла не трактуется как число дополнительных updates.

Это общая новая execution recipe относительно исторического A/B; одинаковый
seed не делает её траектории идентичными старым runs. Новый manifest сохраняет
source snapshots и hashes, включая стандартный train.py.

## Preflight до PPO

Отдельные fresh processes A/B, 128 envs × 3600 policy steps (72 с),
deterministic parent и 0 PPO updates. Проверяются model/Adam exact restore,
observations/actions/50 Hz, отсутствие bootstrap safety как timeout.
Instrumentation записывает initial gravity/q/root state, первые события по
cohort/phase и возрасту, limiting joint/contact magnitude/command/level.
Initial contact buffer читается без вызова lazy sensor recomputation;
physics safety получает свежие samples после каждого physics tick.

Frozen gates: в B нет initial-invalid tilt/nonfinite/hard q и stale contact
buffer; initial tilt mismatch воспроизводится в A; rate первых tilt events
до 2 с снижается минимум на 50%; каждая target cohort достигает ненулевых фаз
и хотя бы одной полной длинной zero phase. Все failures сохраняются.
Если gates не пройдены, workflow завершает диагностику без PPO.

## Обучение и оценка

После успешного preflight supervisor последовательно выполняет 300 updates A,
300 updates B, export parity и 180 probe episodes parent/A/B.
Policy IDs: 24650, resetcontrol_24949, resetupright_24949.
Каждый actor оценивается в отдельном процессе с одинаковыми slots и пятью
известными seeds. Изменений evaluator thresholds нет.

Retention B: unsafe=0; ни одна probe ячейка не теряет successes к parent/A;
малые lateral/yaw response не хуже более чем на 0.02; рост max saturation
fraction к parent ≤0.02 wheels/0.01 legs. Итоговое поведение остановки остаётся
частью v2 scoring. Отбирается только final checkpoint; бюджет не продлевается.
Preflight, training coverage и policy score публикуются раздельно.
Автоматической promotion/qualification нет; candidate core_24650 сохранён.

Запуск: `scripts/run_reset_pilot.py` через независимый supervisor.
Training: `scripts/train_reset_pilot.py` — внешний runtime/task bootstrap
стандартного train.py; dashboard только показывает progress и logs.
Raw, checkpoints, exports и captured sources сохраняются в собственном job/run.

## Выполнение

Job `00cdfe392007469888265badecf3bfdf` запущен 01.10.2026 в 10:38 МСК
через supervisor без открытия HTTP-монитора. Перед ним 92 теста завершены
с exit 0, job `e37ab27aeaf04ec09bc9d1436d637f0d`; проверены retained policy
hashes, 214 local links и 1463 pinned vendor-файла. Этот job отменён через
supervisor после зависания upright rollout на 720 steps; PPO в нём не выполнялся.
Полный control preflight и частичный upright raw сохранены. Причина зависания
не установлена; успешным весь job не считается.

Диагностический upright replay `2fdee06e32d244bdb321b6b8887142b5` завершён
с exit 0, 3600 steps и 0 PPO updates. Периодические stack dumps добавлены
как диагностика; строки faulthandler `Timeout` сами по себе не означают остановку.
Исправлена подпись progress: rollout windows без PPO теперь дают
`completed_updates=0`. MDP и PPO при этом не менялись.

Полный control: initial tilt-invalid 1673/2019; upright: 0/354.
Rate первых tilt events до 2 с: 0.180881 → 0 events/(env·s).
Оба restore audits точные, stale contact buffers отсутствуют; в B доступны
длинные zero phases во всех target cohorts. Frozen preflight gates пройдены.
[Публикация с raw hashes](evidence/reset_pilot_20261001/preflight.json).

**Training workflow:** `e7169d2cf7bc4fc0a7d504b62a14c3f7`, 01.10 в 10:58 МСК.
Полные preflight results скопированы побайтно; config/plan/source/runtime
проверены. В cache receipt отдельно объявлены изменения logging/stack
diagnostics и orchestrator; логика MDP/PPO не менялась.
Control выполняет PPO, на 11:02 МСК достигнуты 60/300 rollout/update windows,
config audit passed; стандартные runner/PPO source hashes сохранены.
После A автоматически идут B, export parity и 180 episodes. Final result
пока отсутствует, candidate core_24650 не изменён. После старта отдельно
сверены реальные `params/agent.yaml`: policy/algorithm совпадают с parent,
OnPolicyRunner, 24 rollout steps, clip_actions=None. На следующей проверке
достигнуты 100/300 windows; обучение продолжается независимо от чата.


### Восстановление workflow 01.10 в 11:27 МСК

Control A завершил все 300 updates за 1200.92 с; final checkpoint 24949,
29 491 200 transitions, Adam +6000 steps на каждом параметре (300 × 5 × 4).
Checkpoint SHA-256: `1fbd345221b2d975ee23c50ae31d2a39ce3e977cad40049850cb3167b0a40a65`.
Исходный workflow завершился с exit 1 в 11:18 МСК: Kit fast shutdown
завершил Python до post-runpy записи `completed`; supervisor ошибочно
потребовал этот статус. B и evaluation в исходном job не выполнялись.

Проверка завершения перенесена в независимый controller: child exit 0,
все 300 runner iterations и 29 491 200 transitions в stdout, точный agent,
config audit, final iteration/finite checkpoint и Adam delta. Статуса
rollout progress недостаточно для подтверждения training. Стандартные
train.py/runner/PPO, MDP, seed и бюджет сохранены. Проверка завершения
и неполного Adam/log проверена тестом; всего 97 тестов, exit 0, job
`bc6aa3bef03043b299336d87eb1b132b`.

[Проверка и hashes](evidence/reset_pilot_20261001/control_completion_recovery.json)
разделяет historical raw и implementation hashes. Исходные raw не переписаны.
Новый job `37198e6459844450a190984e03beef16` хранит byte copies/receipt
проверенного A, не повторяет его updates и начал B от исходного 24650.
После B остаются export parity и 180 probe episodes; acceptance пока отсутствует.


## Итог 01.10 в 12:03 МСК

Восстановленный workflow завершён с exit 0: B 300 updates, обе модели
export parity max error 0, 180 probe episodes. Parent/A/B success 27/21/18,
unsafe 0/0/0; B не прошёл retention. Budget и seed 9910 закрыты;
кандидат core_24650 сохранён. [Результат и проверка](2026-10-01-reset-pilot-result.md)
разделяет устранение initial-invalid и качество actor. Следующий опыт
задан текущим TRAINING_STRATEGY, исходные recipe и gates выше сохранены.
