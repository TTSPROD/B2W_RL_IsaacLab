# Перезапуск локальной стратегии обучения B2W stairs

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](../PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

**Архив предложения:** позже пользователь отклонил расширение входов. ABI57→16 сохраняется; stair-v4 не реализована и не запущена. Действующая линия и результаты: [TRAINING_STATUS](../TRAINING_STATUS.md).

Дата: 23 сентября 2026. В анализ входят только локальные эксперименты на RTX 4080 Laptop. Серверная линия исключена.

## Диагноз

Локальный цикл экспериментов исчерпал полезность малых поправок к прежней постановке. Control57 достигает `1106/1536` полных циклов и `169` unsafe на открытой suite, но ни один из проверенных вариантов — command profile, stop pulse, landing starts, roll-in, ascent mix, `base_lin_vel`, wheel-head-only, teacher anchor или внешний wheel clamp — не улучшил оба training seed без деградации safety/rough.

Последний screen `brake-min=0.15 + ramp10` снизил stop failures с `82` до `43` относительно парного slow-brake контроля, но сохранил `32/33` unsafe против `30/32` у исходных control57. Это сильный признак, что торможение можно улучшать локально, но целевая задача остаётся частично ненаблюдаемой и конфликтной.

Текущий actor видит velocity command, но не видит расстояние до цели, положение относительно конца марша или фазу задания. При этом trainer/evaluator вычисляет passage, brake, hold и restart из privileged `root_pos_w` вне политики. Один и тот же нулевой velocity command означает разные состояния: стоять перед стартом, удерживаться после прохода или восстанавливаться после ошибки. Запрет на любое расширение 57-D ABI теперь мешает проверить основную причинную гипотезу.

Короткая 60-D абляция с `base_lin_vel` не опровергает goal-conditioned подход: она добавила скорость, но оставила скрытыми цель и фазу и дала всего 50 PPO updates. Продолжать 25–50-update fine-tune прежней velocity-only задачи не следует.

## Что делают близкие работы

- [Chamorro et al.](https://arxiv.org/abs/2402.06143) для blind stair climbing заменяют velocity-only постановку на position-based цель, используют asymmetric actor–critic и явный stair-mode bit.
- [DreamWaQ](https://arxiv.org/abs/2301.10602) использует temporal proprioceptive history, privileged critic и совместно обучаемую оценку скорости/контекста; в статье `H=5`, 4096 сред и curriculum/domain randomization.
- [RMA](https://arxiv.org/abs/2107.04034) разделяет privileged base policy и adaptation module, оценивающий скрытые внешние факторы по истории.
- [Parkour in the Wild](https://arxiv.org/abs/2505.11164) сначала обучает terrain-specific experts, затем distillation + RL fine-tuning; авторы отдельно отмечают collapse единой политики при обучении всех сложных terrain с нуля и пользу сохранения разнообразия старых terrain.
- Открытая [B2W stairs задача в unitree_rl_mjlab](https://github.com/sabernagato/unitree_rl_mjlab) также выделена как отдельный specialist task, а не как несколько десятков обновлений универсальной rough policy.

Эти результаты не переносятся на B2W автоматически, но согласованно указывают на смену task formulation, memory/estimation и specialist-first обучение вместо дальнейшего reward tweaking.

## Новая основная линия: Stair v4

### 1. Разделить policy roles

- `rough57` сохраняется неизменным как regression baseline для flat/rough и fallback; это больше не обязательный ABI stair policy.
- Новая `stair-v4` — отдельный specialist с версионируемым ABI. Сначала одна conditioned policy для up/down; если один direction систематически подавляет другой, обучать два experts и только после успеха решать вопрос distillation/FSM switching.
- Никакие новые веса не считать release policy до export parity и sim2sim.

### 2. Сделать задачу наблюдаемой

Минимальный stair-v4 actor получает прежнюю проприоцепцию плюс:

- relative target в body/yaw frame (`dx, dy, dz`);
- явный task mode (`rough`, `stair-up`, `stair-down`, `hold/restart`) как one-hot либо эквивалентный стабильный контракт;
- либо измеренную/оценённую `base_lin_vel`, либо короткую историю наблюдений и действий. Предпочтительный deployable student — history encoder; ground-truth velocity допустима только для teacher/diagnostic до проверки estimator.

Critic получает privileged terrain heights, true base velocity, contacts, friction/payload и phase state. Actor не получает недоступные на роботе значения. Перед обучением фиксируются ABI, нормировка, latency и источник relative target.

### 3. Сначала доказать feasibility teacher

Первый эксперимент — один oracle/teacher seed с position-based task, точной симуляционной relative target и asymmetric critic. Это диагностический верхний предел, не deployable policy.

- 4096 сред, evaluation каждые 25 updates;
- начальный лимит 300 updates; продление до 1000 только при росте held-out success;
- early stop после пяти evaluations без улучшения worst-row cycle success;
- checkpoint выбирается по вектору `full cycle → unsafe → passage → hold`, не по train reward.

Если teacher не проходит хотя бы 85% полного цикла на новом development наборе без роста unsafe, сначала исправлять task/reward/terrain, а не обучать student.

### 4. Curriculum по фазам и измеренному успеху

1. Flat point-to-point: reach → brake → hold → reverse target; randomized start distance and velocity.
2. Fixed 14/32 stairs отдельно up/down, со сбросами на approach, mid-flight, landing и restart.
3. Диапазон 5–20 cm rise, 25–42 cm run, разное число ступеней, landing length, heading error и стартовая скорость.
4. Mixed replay flat/rough/stairs; доля каждого семейства регулируется по его success, а не вручную одним процентом.
5. После устойчивого baseline — friction, mass/COM, payload, actuator strength/gain, observation noise и delay.

Reward строится вокруг potential progress к relative target, terminal success и удержания позиции/скорости. Base/hip contact, tilt и limits становятся явными termination/cost. Passage, hold и restart логируются отдельно. Внешний wheel clamp не входит в train/deploy policy.

### 5. Student и объединение навыков

После успешного teacher:

- student получает deployable proprioceptive history и task/target inputs;
- distillation выполняется по DAgger-style rollout states, затем PPO fine-tuning на полном распределении;
- rough57 используется как teacher/replay anchor на flat/rough, но stair states обучаются у stair expert;
- объединять skills в одну policy только после того, как каждый expert отдельно проходит свои ворота.

### 6. Новая оценка

- Старые stair seeds и геометрии считать development, поскольку по ним уже многократно принимались решения.
- До v4 training зафиксировать новый validation набор; закрытые 4101–4104 оставить одноразовым финальным тестом.
- Сначала один feasibility seed; после прохождения 85% — три независимых training seeds с одинаковым budget и config.
- Release gate остаётся ≥95% полных безопасных циклов в каждой строке, без ухудшения flat/rough более допуска; публиковать Wilson interval, worst-row, failure taxonomy и seed spread.

## Остановленные направления

До новых данных не запускать: дополнительные brake-distance/min-speed sweeps, wheel clamp/ramp, stop pulses, изменение только reward weight, up/down fractions, landing-start fractions, просмотр новых checkpoint той же 57-D траектории и 25–50-update fine-tune прежней velocity-only задачи.

Следующий кодовый шаг — реализовать отдельный `stair-v4` environment/config вне `vendor/` и unit tests контракта target/mode/history. До этого новое обучение не запускать.
