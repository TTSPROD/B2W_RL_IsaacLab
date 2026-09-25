# Аудит пути B2W от обучения до реального робота

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](../PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

Дата: 24 сентября 2026. Область аудита: текущая линия `57 observations → 16 actions`,
PPO/RSL-RL, локальные и серверные checkpoints, stair/payload experiments, evaluation и
подготовка SDK2. Никакое управление реальным роботом этим документом не разрешается.

> Update 25 сентября: после этого аудита batch MuJoCo adapter дополнен
> интерактивным XInput viewer с выбираемыми policy/map. Runtime и startup smoke
> исполняются, но первая ручная stair-сессия содержала unsafe episode. Поэтому
> тезис ниже уточняется: **MuJoCo runtime теперь исполняем, release-quality
> multi-seed gate исполнен, но провален; SDK2 runtime по-прежнему не открыт**.
> Flat80/80 и descent60/60 прошли без unsafe, ascent23/60 дал37 unsafe. См.
> [viewer](2026-09-25-mujoco-gamepad-viewer.md) и
> [multi-seed gate](2026-09-25-cycle57-mujoco-multiseed.md).

## Решение

Текущий выбор **PPO + blind actor57 + privileged critic** сохраняется. Переход на SAC/TD3
сейчас неэффективен: он разрывает совместимость с reference/RSL-RL, требует нового
training/runtime пути и не устраняет обнаруженную ошибку постановки полного цикла. Главный
лимит сейчас — не алгоритм, а objective/evaluation gap и незакрытый sim-to-real contract.

Новых длинных запусков до завершения P0–P2 ниже не выполнять. Сначала нужно:

1. оценить уже сохранённую траекторию cycle57, а не только финальный checkpoint;
2. сделать actuator/safety metrics обязательной частью stair gate;
3. зафиксировать один причинный A/B против reward loophole;
4. параллельно открыть read-only deployment lane: SDK2 recorded-state replay, timing и
   измерение параметров реального робота без публикации motor commands.

## Что сделано хорошо

- Actor ABI, порядок суставов, masking wheel positions и 50 Hz сохранены как `57→16`.
- `vendor/` неизменен; политики идентифицируются run/ABI/SHA, а не одним seed.
- Train/eval используют общий stop boundary v3; unsafe имеет приоритет над success.
- Development и validation разделены, закрытые stair seeds не используются для tuning.
- Результаты публикуются по строкам/направлениям, а training reward не выдаётся за quality.
- Payload имеет явную массу, COM и инерцию; checkpoints, которые ухудшили completion,
  отклонены вместо оправдания ростом reward.
- Upstream, inverse57 и локальные линии сравниваются с указанием места обучения и оценки.

Эта дисциплина уже предотвращает две типичные ошибки: cherry-picking финального update и
принятие политики по одному красивому видео.

## Критические разрывы

### 1. Reward оптимизирует proxy, а gate проверяет полный цикл

`stair_goal=250` выдаётся только после restart, а variant B/C добавляет dense stop-speed
reward. В C-long stop failures местами снизились, но `passage` и `completion` ухудшались,
а `incomplete` рос. Это подтверждённый loophole: политика может выгоднее не завершать
маршрут, чем рисковать терминальным исходом.

Следующий treatment должен использовать **одноразовые монотонные milestones**:
safe passage → успешный hold → restart, при доминирующем bonus полного цикла. Dense
stop-speed не должен быть самостоятельным основанием для продолжения. Если используется
potential shaping, потенциал задаётся на расширенном состоянии `(phase, state)`, обнуляется
на границах фаз и не создаёт бесплатного бонуса при смене цели.

### 2. Stair gate пока не является actuator-safety gate

Evaluator учитывает contact/tilt, passage, stop и restart, но не делает обязательными:

- долю времени у joint position/velocity/effort limits;
- peak/RMS torque и mechanical power отдельно для 12 leg и 4 wheel actuators;
- action rate/jerk и raw-action tails;
- rolling consistency/wheel slip;
- contact impulse и пиковую нагрузку;
- energy per metre и energy per completed cycle.

В сохранённом upstream reward leg torque/power penalized с малыми коэффициентами, тогда как
wheel torque/power penalties отключены. Для тяжёлого B2W нельзя сначала произвольно поднять
penalty: сперва измерить распределения parent/candidates, задать hardware-derived limits и
только затем менять один term.

### 3. Domain randomization шире имеющихся измерений и неполна по нужным осям

Текущий upstream использует friction, mass/COM, gains `0.5–2.0`, reset force/torque и pushes.
Эти диапазоны инженерные, не измеренный envelope робота. Одновременно отсутствует явная
randomization sensor/action latency, loop jitter, stale samples, wheel radius, motor strength/
torque-speed/battery state и IMU bias. Широкая DR не заменяет нужную DR и может расходовать
capacity на физически невозможные комбинации.

DR вводится лестницей: nominal → измеренные mass/COM/inertia/friction/wheel radius →
actuator strength/gains → observation bias/noise → latency/jitter/dropout → pushes. Новое
семейство допускается только после nominal gate и отдельной robustness-кривой.

### 4. Fine-tune не сохраняет PPO неизменным

Upstream agent содержит `clip_param=0.2`, `entropy_coef=0.01`, trainable exploration std и
initial std `1.0`. Stair wrapper задаёт `clip_param=0.1`, `entropy_coef=0.0`, восстанавливает
примерно `0.1` из parent и замораживает std. Fixed LR также меняется между runs. Это может
быть разумным conservative fine-tune, но это отдельный фактор; такие эксперименты нельзя
описывать как изменение только curriculum/reward.

До следующего pilot manifest должен сохранять **effective loaded values** после всех hooks:
clip, entropy, std/trainability, LR каждого optimizer group, GAE, epochs/minibatches и
normalization. Для причинного A/B эти значения обязаны совпадать. Алгоритмический sweep не
нужен; выбирается один явно названный `conservative_finetune_v1` recipe.

### 5. Evaluation статистически хороша для development, но ещё не release evidence

128 параллельных эпизодов одной геометрии — это variations initial state/physics, а не 128
разных лестниц. Point threshold `≥95%` полезен как development gate, но не доказывает 95%
надёжность на реальном распределении. Для release нужны несколько held-out геометрий,
независимые environment seeds, Wilson intervals и failure taxonomy. Recipe подтверждается
минимум на трёх training seeds; validation не выбирает другой checkpoint после провала.

### 6. Deployment work начинается слишком поздно

На дату аудита MuJoCo adapter и SDK2 runtime ещё не являлись исполняемым gate;
25 сентября базовый batch/interactive MuJoCo runtime появился, но release gate
остался открытым, как отмечено в update выше. Если ждать принятой stair policy,
поздно обнаружатся motor order/sign, firmware mode, estimator convention, timing
и watchdog ошибки. Read-only replay, export parity, p99 inference и fault
injection не требуют разрешения на actuation и должны идти параллельно с policy work.

## Скорректированный критический путь

### P0 — использовать уже оплаченные samples, без обучения

1. На неизменном open screen выполнить coarse scan cycle57 checkpoints через каждые
   100 updates, включая parent и final. Использовать 64 env/направление.
2. Три недоминируемых checkpoint проверить на 128 env по всем development stair rows.
3. Считать candidate недоминируемым только если одновременно не хуже parent по passage,
   unsafe и worst-row full-cycle. Final `model_3998.pt` не имеет приоритета над промежуточным.
4. На том же screen собрать per-term reward returns и phase outcome:
   before-flight / on-flight / landing / stop-speed / stop-drift / no-restart.
5. Если ни один checkpoint не доминирует parent, ветку cycle57 закрыть без validation.

### P1 — единый deployability evaluator

Расширить один evaluator, не создавать несовместимые отчёты. Для каждого episode outcome
должен быть взаимоисключающим и сумма равна `N`:

`success | unsafe | stop_failure | timeout | incomplete_before_flight |
incomplete_on_flight | incomplete_on_landing | no_restart`.

К каждому исходу добавить actuator/saturation/slip/energy metrics выше. Зафиксировать JSON
schema, hashes suite/code/model/robot asset, physics dt/decimation/solver и applied DR
readback. Unit tests покрывают границы фаз 99/100/101, autoreset и unsafe precedence.

### P2 — один причинный A/B, не новый sweep

Гипотеза: **phase-balanced one-shot milestones устраняют avoidance loophole лучше, чем
dense stop-speed reward** при прежнем actor57.

- Control: замороженный `conservative_finetune_v1` и текущая cycle task без нового shaping.
- Treatment: одноразовые safe-passage/hold/restart milestones; одинаковый full-cycle bonus.
- Actor ABI/actions, parent SHA, payload physics, terrain mix, DR, PPO, env count, seeds и
  sample budget совпадают. Privileged critic может получить phase/applied-DR, но тогда это
  единственное дополнительное изменение и critic/optimizer инициализируются заново.
- 50-update pilot на двух development training seeds, checkpoints каждые 25 updates.
- Продление до 100/200 updates — только если treatment улучшает worst-row full-cycle минимум
  на 5 п.п., не снижает passage, не повышает unsafe/limit violations и не ухудшает flat/rough.
- Пять screens без улучшения ≥2/128 или два последовательных ухудшения safety закрывают run.
- Никаких одновременно добавленных observation noise, terrain-proportion и LR изменений.

### P3 — curriculum и измеренная DR

После nominal успеха расширять только один axis за ступень. Для command envelope включить
stand, forward/backward, lateral/yaw, brake/hold/restart и command-rate variation. Stair
curriculum меняет rise/run/steps/approach/landing; flat и rough replay сохраняют исходный
command distribution. Payload/no-payload являются отдельными strata, а не усредняются.

Blind57 feasibility stop: если замороженный treatment не достигает development gate на
трёх seeds при предельном бюджете 300 updates/seed, вычисления останавливаются. Тогда
release scope сужается до flat/rough либо пользователь отдельно решает вопрос наблюдаемости;
ABI самовольно не расширяется.

### P4 — заморозка recipe и validation

1. Три training seeds, одинаковый sample budget и selection rule.
2. Selection только по development: safety filter → worst-row cycle → passage → energy.
3. Одна закрытая validation без выбора замены после просмотра результатов.
4. На каждой stair строке: point success ≥95%, ноль limit/non-finite/watchdog violations;
   публиковать Wilson95 lower bound, а не скрывать его за pooled total.
5. Flat regression: fall/contact не хуже 2 п.п., tracking не хуже 10%; rough/inverse gates
   остаются построчными. Payload и nominal проходят отдельно.

### P5 — sim-to-sim и read-only deployment lane

Этот этап начинается параллельно с P0:

- export + CPU/live parity на fixtures и recorded Isaac states;
- C++ SDK2 adapter без публикации commands, motor permutation/sign/unit tests;
- 50 Hz policy / выбранный low-level loop, p50/p95/p99 latency и deadline-miss injection;
- stale/NaN/out-of-range/CRC faults переводят FSM в проверенное безопасное состояние;
- один и тот же exported artifact в Isaac и MuJoCo на flat/rough/stairs;
- model/actuator mismatch report: mass/COM/inertia, wheel radius, limits, torque-speed,
  friction/contact и estimator frames.

Перед DR получить с реального робота без locomotion: firmware/mode, motor order/sign,
read-only state logs, loop jitter, IMU convention, nominal pose, configured limits и массу/
payload. Неизвестные значения не заменять reward coefficients.

### P6 — staged hardware acceptance

`offline fixtures → recorded-state replay → MuJoCo → suspended/sign check → stand/stop →
low-speed flat → bounded flat → rough → stairs`.

Каждый переход требует E-stop, страховку, оператора, заранее заданные abort thresholds и
rollback artifact. Первый hardware objective — корректный stop/watchdog, не максимальная
скорость и не промышленная лестница. Thermal/current evidence собирается на коротких runs с
cooldown; simulator power proxy не считается доказательством температуры приводов.

## Что больше не делать

- Не продолжать checkpoint из-за роста mean reward или уменьшения одного `stop_failed`.
- Не запускать 500–1000 updates до cheap checkpoint screens.
- Не менять одновременно reward, noise, terrain mix, LR и payload.
- Не выбирать final iteration по умолчанию и не открывать validation для tuning.
- Не расширять blind actor ABI без отдельного решения пользователя.
- Не считать wide unmeasured DR, Isaac-only success или SDK2 dry-run допуском к роботу.
