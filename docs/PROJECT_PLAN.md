# План проекта B2W

Актуализирован 19 сентября 2026. Цель — воспроизводимое полезное управление B2W
по Flat, затем Rough/обычным лестницам и отдельно sim2real. Текущий запуск:
[reference transfer](REFERENCE_TRANSFER.md) после Git push начат и подтверждён
[датированным снимком](results/2026-09-19-reference-transfer-launch.json).
Фактическое состояние и результаты — в [журнале](TRAINING_PROGRESS.md).
Flat release gate пока не закрыт; seed49 сохранён как прошедший локальный кандидат.

## Почему меняем подход

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

## Следующий ограниченный цикл

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

После успеха заморозить весь recipe и проверить три ещё не использованных
fine-tuning seeds с новыми двумя наборами cases. Они разделяют pretrained actor:
это воспроизводимость переноса, не обучения с нуля. Каждый финал должен отдельно
пройти оба профиля. При неуспехе — сохранить рабочий reference/seed49, проверить
drift и mismatch recovery/Flat; следующая гипотеза — распределение reset либо
явные safety costs, но не автоматический contact−12 или новый sweep.

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
| Flat transfer |3 одинаково проведённых fine-tuning seeds, каждый2 профиля | Development подготовлен |
| Rough | Отдельный GPU smoke; performance curriculum и Flat regression | Не запускался |
| Stairs | Удержанные семейства up/down, размеры геометрии | Не запускался |
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

Rough/Stairs: предварительно ≥95% успешных эпизодов/проходов на каждом
удержанном семействе, energy/slip/saturation и все нарушения опубликованы.
Flat regression после этапа: success хуже не более2 п.п., tracking не более10%.
Sim2sim: отсутствие NaN/перестановок, целевой разрыв success≤5 п.п.
Конкретные industrial лестницы и hardware limits требуют измерений.

## Последующие задачи

- P0: выполнить короткий transfer с ранними gates и зафиксировать фактический итог.
- P1: при успехе — три новых fine-tuning seeds и новые hold-outs; при отказе —
  один причинный пересмотр с ограниченным бюджетом.
- P1: artifact store с SHA256; Git хранит код/отчёты, но не training checkpoints.
- P1: saturation contract, zero-action PD просадка, actuator/contact/geometry;
  сохранить отдельный успешный seed49.
- P2: Rough GPU qualification, curriculum по измеренному успеху и сохранение Flat
  в task mix. History/estimator/constraints только отдельным изменением ABI.
- P3: MuJoCo, SDK2 replay без actuation, firmware/signs/CRC/watchdog/latency,
  затем отдельно разрешаемые hardware gates.

Путь релиза: checkpoint → export/manifest → parity → Isaac evaluation →
MuJoCo → SDK2 dry-run → поэтапные реальные испытания. FSM должна обрабатывать
stale/nonfinite данные и deadline misses. p99 inference <20 ms с запасом;
low-level rate и безопасный stop/damping проверяются на конкретной прошивке.
Никакие симуляторные результаты не разрешают live robot actuation.

Исторические протоколы и JSON сохранены в [журнале](TRAINING_PROGRESS.md);
они объясняют принятые решения и не являются активной очередью.
