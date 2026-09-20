# План проекта B2W

**Цель уточнена 20.09.2026: одна обучаемая reference-compatible lineage
Flat → Rough → Stairs. Deployable actor всегда строго57→16 с той же сетью,
observations/actions/scales/50Hz, что `rl_sar/policy/b2w/robot_lab`.
Flat foundation54/55/56 уже квалифицирован. U1, U1.1, U1.2 и независимая
репликация U1.1 seeds75/76 остановлены quality gates на cumulative150.
Последняя репликация сохранила reference reward contact−1: seed75 прошёл Flat,
но slope_up95/89 и slope_down100/88; seed76 провалил relative Flat при safety
200/200. Rough не принят, U2/Stairs заблокирован.**

Действующий контракт и состояние: [ROUGH_STAIRS_PLAN](ROUGH_STAIRS_PLAN.md).

## Исторические решения до teacher пересмотра

Разделы ниже описывают завершённый blind путь, включая его бюджеты и gates.
Все следующие разделы — история. Единый reference-compatible recipe U0→U1→U2
зарегистрирован отдельно в [Rough/Stairs плане](ROUGH_STAIRS_PLAN.md); старые
бюджеты не являются разрешённой активной очередью.

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
terrain и evaluator проверены; последняя серия описана в
[ROUGH_WIDE_CORRIDOR](ROUGH_WIDE_CORRIDOR.md). Активный статус —
[остановка и контракт57→16](ROUGH_STAIRS_PLAN.md). Route59/60 завершены без
quality pass и сохранены как история. Старые evaluation cases теперь
раскрыты: годятся для regression, но не должны выдаваться за новую независимую
приёмку после подбора параметров. Автопродление Flat ради reward не требуется.

## Архитектура и границы

Isaac Lab v2.3.2 + immutable robot_lab v2.3.2, Isaac Sim5.1.0,
Python3.11 и RSL-RL3.1.2; версии и commits зафиксированы в requirements/vendor.
Flat/blind contract: actor57, privileged critic. Отклонённая экспериментальная ветка
имела actor247 и critic247; она не входит в дальнейший план. Actions:
12 joint position targets и4 wheel velocity targets, 50 Hz.
[Контракт](POLICY_CONTRACT.md), [модели](ROBOT_MODEL_COMPARISON.md).

Reference импортируется только как actor; у него нет исходного training
critic/optimizer. Их нельзя выдумать или взять от другой политики.
Рекуррентный SRU/другой observation ABI не взаимозаменяем с этим экспортом.
History/velocity estimator и constrained RL — отдельные возможные этапы,
а не часть текущего короткого опыта.

Desktop Windows/RTX4070Ti: Flat headless и2×4096 квалифицированы.
Ноутбук квалифицирован отдельно; новая очередь ему не назначена.
Сервер не прошёл Isaac gate, несмотря на Hopper/CUDA.
[Инфраструктура](INFRASTRUCTURE.md), [решение по вычислениям](COMPUTE_DECISION.md).
Предыдущие проекты и их jobs не используются; vendor не изменяется.

## Этапы и выходные критерии

| Этап | Требуемое свидетельство | Статус |
|---|---|---|
| Runtime Flat | GPU smoke, PPO/resume, длительная telemetry, throughput | Desktop пройден |
| Policy contract | Объективная export/live parity, order/scales/history | Nominal пройден; saturation/hardware открыты |
| Flat transfer |3 одинаково проведённых fine-tuning seeds, каждый2 профиля | Пройден19.09:54/55/56, все6 оценок100/100 и tracking pass |
| Foundation57 | Qualified Flat actor57, resumable checkpoints54/55/56 | Пройден; terrain parent seed54 |
| Rough57 | U1 critic migration, затем Rough PPO | U1/U1.1/U1.2 и репликация75/76 остановлены на150; qualified policy нет |
| Stairs57 | U2 full resume от qualified Rough | Не запускался; заблокирован Rough gate |
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
- Завершено: frozen compatibility/U1 preflight; Flat54 locomotion baseline
  random level0 nominal100/100, но это не qualification.
- Завершено: U1.1 с единственным изменением terrain proportions:
  flat/random/slope_up/slope_down/blocks `0,4/0,1/0,2/0,1/0,2`; rewards/PPO/
  budget/ABI неизменны. Seeds71/72 остановлены на150 из-за одного относительного
  Flat fail каждый; slope_up100/100 против77/100 показал высокую seed variance.
- Завершено/отклонено: U1.2 `undesired_contacts −1→−3`; seeds73/74 остановлены
  на150, Flat relative fail и slope_up74/73 из100. Этот reward не продолжать.
- P0: спроектировать Flat-bank actor anchoring поверх U1.1 без изменения reward;
  сначала unit/gradient/native preflight, затем только новые seeds.
- P1: только qualified Rough продолжать full resume в U2/Stairs. Route control —
  отдельный поздний navigation gate.
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
