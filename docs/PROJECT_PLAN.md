# План проекта B2W

**20.09, следующий опыт:** [wheel corridor63/64](ROUGH_WHEEL_CORRIDOR.md).
Согласовать Rough training constraint с прежним evaluator: пересечение границы
колесом — true terminal и curriculum failure. Precision std0,25 и Flat replay
сохраняются. Actor отqualified54, свежие critic247/optimizer,50+100+200updates
single4096; максимум68812800transitions. Native64 train/resume,175CPUtests,
1290vendor hashes пройдены; основная очередь подготовлена.
Фактический запуск — в [TRAINING_PROGRESS](TRAINING_PROGRESS.md).

Precision61/62 завершились15:56:59МСК на150: Flat400/400 safe и все4absolute/
relative gates pass; Rough1124/1600 success,0/16 suites,476corridor failures.
[Итог](results/rough_precision_training_20260920.json),
[проверка26artifacts](results/2026-09-20-precision150-corridor-audit.json).
Новая [диагностика](results/rough_corridor_trace_20260920.json) сохранила исходные
200rows random0nominal;61:18negative-y/4forward,62:7negative-y/16forward.
Это ограниченный поднабор; прежний root proxy заменён точными wheel crossings.

## Следующие этапы

1. Проверить новую constraint на64env: все4границы, Rough-only, native reset,
   отсутствие timeout bootstrap, train/resume2+2. Выполнено, веса discard.
2. Запустить63/64 по50critic-only, затем Flat checks. После100PPO до150 —
   все4Flat+16Rough level0,≥90% каждого kind/family/profile. Любой fail
   закрывает следующие updates обоих seeds после полного диагностического блока.
3. При pass150 — ещё200PPO,4Flat+48Rough levels0/1/2,≥95% каждого kind,
   всеFlat gates и curriculum level2. Acceptance автоматически не выдаётся.
4. При fail проверять corridor terminal counts, episode length и route completion:
   снижение выходов за счёт остановки движения не является успехом.
   При недостаточной наблюдаемости — отдельный history/velocity estimator либо
   navigation controller с новым контрактом и повторной Flat/export квалификацией.
5. Только общий development pass открывает новые qualification seeds/cases,
   затем Stairs. Live robot actuation этим планом не разрешается.

Reference уже является предком54 и comparator дляdrift. Flat BC пока не нужен:
precision150 сохранил все Flat gates. Новый опыт начинается от54, чтобы не
менять terminal/value function внутри чужого failed150 checkpoint.
Сравнение63/64 с61/62 историческое, не paired causal control.
[Полный протокол](ROUGH_WHEEL_CORRIDOR.md), [исследования](ROUGH_RESEARCH_2026-09-20.md).
Исторические57–60failed350 и61/62failed150, gates и vendor сохраняются.

## История смены Flat подхода — до19.09

Последние четыре серии меняли веса/форму contact и height, но ни одна не дала
кандидата на обоих выбранных seeds. Contact −3 снизил число отказов 23→14;
height L2 и lower-L1 вернули его к23, contact −6 — к20.
У −6 seed50 улучшился, seed51 ухудшился до85/98 безопасных эпизодов из100.
Это не объясняется недостаточным throughput: 2×4096 уже квалифицированы.
[Проверенные результаты](TRAINING_PROGRESS.md), [исследование методов](REWARD_RESEARCH.md).

Слабое место — pure yaw и контакты задних голеней. Диагностика видит малый зазор
и просадку; насыщение leg torque в измеренных окнах не объясняет большинство
отказов. Есть несовпадение задач: upstream reset roll/pitch ±3,14 и отсутствие
contact termination учат также recovery, тогда как Flat evaluator фиксирует
контакт >1 N как sticky failure. Это гипотеза о распределении, а не доказанный
bug. Нельзя одновременно менять reset, termination и rewards и приписывать
эффект одному весу.

Reference и seed49 уже показали безопасный Flat на проверенных cases.
Поэтому приоритет — перенос полезного навыка с явным происхождением.
Обучение с нуля остаётся исследовательской веткой и больше не является
обязательным условием получения прикладной политики.

## Исходный reference transfer и продолжение

Описанный ниже цикл50+100+200 дошёл до150 и прошёл все4 evaluations100/100.
Последний stage остановлен. Превышение drift seed53 существовало до его первого
PPO-update; upright resume smoke на обоих seeds прошёл при прежнем лимите.
Продолжение [REFERENCE_RESUME](REFERENCE_RESUME.md) завершено успешно на350.
Пройденный qualification протокол — [REFERENCE_QUALIFICATION](REFERENCE_QUALIFICATION.md).
Исторический recipe ниже сохраняет происхождение parent checkpoints.

1. Проверить reference actor 57→16, Identity normalizer и точную загрузку.
   Сохранить seed49 и исходную reference неизменными. CPU smoke, GPU
   train/resume smoke, экспорт и reference regression обязательны.
2. Два новых seeds52/53: один общий pretrained actor, разные свежие critics/RNG.
   **50 critic-only updates**, затем **100 + 200 PPO updates** на каждом.
   Native RSL-RL PPO; std0,1 фиксирован, LR1e−4 постоянный, clip0,1, entropy0.
   Rewards, reset, actions и runtime сохраняются; pure-yaw mix0,25.
3. После cumulative50/150/350 — одинаковые nominal/bounded development
   evaluations. Любой непроход seed/profile останавливает очередь.
   Reference проходит оба профиля до основного обучения; seed49 — дополнительный
   замороженный comparator. Лимит actor drift контролируется каждый update.
4. Только финал350 может стать development-кандидатом. Промежуточные checkpoints
   служат остановке, а не поиску удачного результата. Без продления и sweep.

Максимум **68 812 800 transitions** основной очереди, против589 824 000 в одной
прошлой серии4×1500: в8,57 раза меньше. Это снижение бюджета, не обещание
ускорения сходимости. Проверки и startup оплачиваются отдельно.
[Полный протокол, cases, stops и запуск](REFERENCE_TRANSFER.md).

## Как принимаем результат

Development pass означает работоспособный путь дообучения и сохранение Flat
навыка, а не улучшение reference. Сравнивать отдельно safety, worst-scenario
tracking и предконтактные данные; рост суммарной training reward не доказательство.

Успешный recipe50 critic +100 recovery PPO +200 upright PPO заморожен и
проверен на новых seeds54/55/56 и evaluation seeds2026091961/2026091962.
Все три финала350 отдельно прошли nominal и bounded_v1. Квалификация закрыта.
Остановка координатора после150 у54/55 исправлена без повторения updates:
собственный load_run проверяется по checkpoint/hash/seed, параметры не изменены.
[Дополнение к протоколу](REFERENCE_QUALIFICATION_RESUME.md).

Все три квалифицированных финала сохранены как Flat anchors. Rough runtime,
terrain и evaluator проверены; текущая поправка описана в
[ROUGH_PRECISION_TRACKING](ROUGH_PRECISION_TRACKING.md). Route59/60 завершены без
quality pass и сохранены как история. Старые evaluation cases теперь
раскрыты: годятся для regression, но не должны выдаваться за новую независимую
приёмку после подбора параметров. Автопродление Flat ради reward не требуется.

## Архитектура и границы

Isaac Lab v2.3.2 + immutable robot_lab v2.3.2, Isaac Sim5.1.0,
Python3.11 и RSL-RL3.1.2; версии и commits зафиксированы в requirements/vendor.
Blind actor, privileged critic. 57 observations →16 actions:
12 joint position targets и4 wheel velocity targets, 50 Hz.
[Контракт](POLICY_CONTRACT.md), [модели](ROBOT_MODEL_COMPARISON.md).

Reference импортируется только как actor; у него нет исходного training
critic/optimizer. Их нельзя выдумать или взять от другой политики.
Рекуррентный SRU/другой observation ABI не взаимозаменяем с этим экспортом.
History/velocity estimator и constrained RL — отдельные возможные этапы,
а не часть текущего короткого опыта.

Desktop Windows/RTX4070Ti: Flat headless и2×4096 квалифицированы.
Ноутбук квалифицирован отдельно; текущая очередь ему не назначается.
Сервер не прошёл Isaac gate, несмотря на Hopper/CUDA.
[Инфраструктура](INFRASTRUCTURE.md), [решение по вычислениям](COMPUTE_DECISION.md).
Предыдущие проекты и их jobs не используются; vendor не изменяется.

## Этапы и выходные критерии

| Этап | Требуемое свидетельство | Статус |
|---|---|---|
| Runtime Flat | GPU smoke, PPO/resume, длительная telemetry, throughput | Desktop пройден |
| Policy contract | Объективная export/live parity, order/scales/history | Nominal пройден; saturation/hardware открыты |
| Flat transfer |3 одинаково проведённых fine-tuning seeds, каждый2 профиля | Пройден19.09:54/55/56, все6 оценок100/100 и tracking pass |
| Rough | Smoke/throughput;2development seeds50+100+200; затем3qualification seeds; Flat regression | 61/62failed150; corridor63/64 preflight пройден, очередь подготовлена; acceptance открыт |
| Stairs | Отдельный straight-march evaluator; up/down0,05–0,18 м; 2 development +3 qualification seeds; Rough/Flat regression | После Rough qualification, не запускался |
| Sim2sim | MuJoCo с согласованной моделью и ABI, измеренный разрыв | Не выполнен |
| SDK/hardware | Offline replay→fault tests→стенд→ограниченные испытания | Управление не разрешено |

## Метрики

Flat: по100 эпизодов на seed/profile, ≥99/100 без sticky failure.
В **каждом** семействе pooled RMS vx/vy ≤0,20 м/с, yaw ≤0,25 рад/с.
Публиковать p95/max, signed bias, причины первого отказа и Wilson95, включая
разброс training seeds. Mean и лучший seed не заменяют отдельные passes.
Nominal/bounded — только зафиксированное покрытие; оно не доказывает полную
робастность к любым pushes, noise или реальной динамике.

Evaluator:2 s active settling +20 s измерения, без auto-reset;
контакты учитываются сt=0 на каждом physics step. Tilt stand≤15°, moving≤45°,
height0,4–0,8 m, non-wheel contact≤1 N. Пороги не ослабляются ради pass.
Для Rough/parkour политика допустимых контактов задаётся отдельно: опора на
колено встречается в опубликованных системах и не равна допустимому Flat-контакту.

Rough/Stairs: ≥95% на каждом family/level/profile каждого seed; stairs up/down
раздельно. Проверять завершение маршрута, collisions, terrain-relative clearance,
energy/slip/saturation; world-z Flat0,4–0,8 м на ступени не переносить.
Flat regression всегда сохраняет исходные ≥99/100 и RMS0,20/0,20/0,25, дополнительно
ограничивает деградацию относительно frozen parent. Полные budgets, геометрия,
пороги и stops — в [Rough/Stairs плане](ROUGH_STAIRS_PLAN.md).
Sim2sim: отсутствие NaN/перестановок, целевой разрыв success≤5 п.п.
Industrial лестницы, perceptive/history ABI и hardware limits — отдельные gates.

## Последующие задачи

- Завершено: короткий Flat transfer и qualification54/55/56 на новых cases.
- Завершено: [Rough R0](ROUGH_R0.md), safe curriculum, full evaluator,
  bounded physics и capacity;57–60 до350 завершены без quality acceptance.
- P0: corridor63/64 подготовлен после native64 train/resume preflight;
  выполнить ограниченные50+100+200 с неизменёнными quality gates. Reference/anchor
  random0 baseline завершён без quality pass и остаётся историческим comparator.
- P1: Rough2-seed development50+100+200 и Flat regression; только после общего
  pass —3 новых seeds/hold-outs. При fail — одна причинная проверка, без продления.
- P1: после Rough qualification — straight stairs up/down с отдельными геометриями,
  stop/landing метриками и прежними Rough/Flat gates.
- P1: artifact store с SHA256; Git хранит код/отчёты, но не training checkpoints.
- P1: saturation contract, zero-action PD просадка, actuator/contact/geometry;
  сохранить отдельный успешный seed49.
- P2: history/estimator/perception/constraints — только отдельная проверка после
  измеренного ограничения blind actor; новый ABI и соответствующая квалификация.
- P3: MuJoCo, SDK2 replay без actuation, firmware/signs/CRC/watchdog/latency,
  затем отдельно разрешаемые hardware gates.

Путь релиза: checkpoint → export/manifest → parity → Isaac evaluation →
MuJoCo → SDK2 dry-run → поэтапные реальные испытания. FSM должна обрабатывать
stale/nonfinite данные и deadline misses. p99 inference <20 ms с запасом;
low-level rate и безопасный stop/damping проверяются на конкретной прошивке.
Никакие симуляторные результаты не разрешают live robot actuation.

Исторические протоколы и JSON сохранены в [журнале](TRAINING_PROGRESS.md);
они объясняют принятые решения и не являются активной очередью.
