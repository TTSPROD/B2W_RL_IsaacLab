# План B2W

Актуально на 7 октября 2026.

## Цель и контракт

Обучить низкоуровневую velocity-conditioned policy для Unitree B2W:
57 observations → 12 leg position + 4 wheel velocity actions, 50 Hz.
Внешний уровень задаёт body-frame (vx, vy, ωz), маршрут и момент смены команды.
Ноль требует остановки и устойчивости, без возврата в мировую точку/курс.
Flat/Rough/Stairs принимаются только в измеренном диапазоне условий.

Основа новых training runs — стандартный pinned
[Robot Lab train.py](../vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py)
и его штатный RSL-RL runner/PPO. Внешние task/MDP адаптации ограничить участками
с подтверждённым отставанием по оценкам. Старые runner hooks не наследовать
автоматически; переход на стандартную базу отразить в manifest и preflight.

## Текущее решение

Сохранены исходный upstream_19999 и development candidate core_24650;
rl_sar участвует как внешний actor из той же Robot Lab линии по сообщению владельца.
Simulation qualification и hardware-approved policy пока нет.
[Реестр](POLICY_REGISTRY.md) · [Статус](TRAINING_STATUS.md).

Ветка relkernel-500-20260929 закрыта и удалена локально; её raw evidence,
компактные сводки и восстановимый Git bundle сохранены.
Ни stage-3, ни focus/relative-kernel continuation не дали подтверждённого
основания автоматически заменить 24650. Из этих опытов **не следует**
доказанная невозможность улучшения PPO или необходимость полного переобучения.

## Очередность

1. **Выполнено:** [v2 сравнение трёх actor](results/2026-09-30-locomotion-v2-selection.md),
   480 эпизодов. Оставлен 24650: 107/160, 0 unsafe, 20/32 ячеек.
2. **Выполнено:** [диагностика сохранённых traces](results/2026-09-30-tracking-diagnosis.md),
   выделен недобор малых lateral/yaw команд. Проверка pose regularization
   не подтвердила достаточного выигрыша; значения reward причинность не доказывают.
3. **Выполнен и отклонён [первый A/B пилот](results/2026-09-30-tracking-posture-pilot.md):**
   parent 24650, seed 9901, 100 updates × 2 плеча, 420 probe episodes.
   Ослабление pose penalty не дало достаточного преимущества перед control;
   подъём ухудшился у обоих плеч, у части checkpoints появились unsafe.
   [Зафиксированный конфиг](../configs/24650_tracking_posture_ab_20260930.json)
   сохранён для воспроизведения; бюджет не продлевается, seed 9902 пока не запускается.
   **Диагностика выполнена:** [310 новых эпизодов](results/2026-09-30-stair-continuation-diagnosis.md).
   Same-order replay точен; перестановка actor меняет 7/140 success. В одинаковых
   слотах parent/control+25/control+100 дают 2/10, 1/10, 2/10 без unsafe, но
   разные успешные stair cases. Общая потеря навыка или её единственная причина
   не доказана; малые multi-actor differences не являются чистым эффектом weights.
   **Выполнен и отклонён [LR-пилот 1e-5 против 1e-6](results/2026-09-30-lr-pilot-result.md):**
   300 updates на плечо, 420 эпизодов, одинаковые case/reset slots.
   Job `72ef5d9d71f04597a9a07585a1cafcc9` завершён с exit 0.
   На +300 оба плеча дают 25/60 против parent 27/60; low LR имеет один unsafe
   и не достигает требуемого tracking gain. Строгий full-cycle gate также не пройден.
   [Frozen plan](results/2026-09-30-lr-pilot-plan.md) сохранён; бюджет не продлевается.
4. **Выполнена подготовка прежнего stair A/B:**
   разобраны hard-limit traces; training safety согласован с evaluator,
   проверены terminal/timeout bootstrap и учёт violations на 200 Hz.
   Это общая постановка обоих плеч; её самостоятельная польза не установлена.
5. **Закрыт stair A/B:** оба от 24650 с одинаковой обработкой safety, LR cap 1e-5,
   4096 envs, до 1500 updates на плечо, seed 9903. A — прежнее распределение
   сложности, B — адаптивный curriculum только целевых лестничных cohorts.
   В A target levels остаются случайными; в B они меняются по исходу эпизода.
   Не менять rewards/ABI/geometry одновременно. Frozen rules promotion/demotion,
   coverage закреплены в revision 2; обе ветки прошли simulation preflight.
   [Карточка запуска и evidence](results/2026-09-30-stair-curriculum-plan.md).
   **Текущее указание пользователя:** A не продолжать, использовать +1350;
   **выполнено:** B от 24650 обучен 1350 updates, parent/A/B проверены в 180 эпизодах.
   Результаты: 27/60, 23/60, 25/60; unsafe 0/0/1. B отклонён: coverage,
   ascent, yaw retention и wheel saturation gates не пройдены.
   [Итог и evidence](results/2026-09-30-stair-comparison-1350.md).
6. **Выполнен [offline обзор 01.10](results/2026-10-01-training-plan-review.md):**
   в executed environment reset roll/pitch остаются ±3.14 рад, тогда как tilt
   terminal разрешает наклон только до 60°. У B около 83% target эпизодов
   завершились unsafe; tilt — 99.82% суммы глобальных reason counts.
   Время первого нарушения не записано: причинность ещё не подтверждена.
7. **D0 выполнен — reset/terminal audit без обучения.** Добавлен учёт initial
   state и первого violation по cohort/phase/возрасту эпизода. Полные preflights
   parent с прежним и upright reset: 128 сред × 72 с, 0 PPO updates.
   Initial tilt-invalid 1673/2019 → 0/354; early tilt rate 0.180881 → 0;
   stale contact buffers нет, длинные zero phases доступны. Отменённая зависшая
   попытка сохранена отдельно. Подробные gates — [TRAINING_STRATEGY](TRAINING_STRATEGY.md).
   Safety evaluator и его thresholds сохраняются; grace period для unsafe нет.
8. **Reset-only pilot завершён и отклонён:** по 300 updates на плечо,
   180 probe episodes, job `37198e6459844450a190984e03beef16`, exit 0,
   01.10 12:03 МСК. Parent/A/B: 27/21/18 successes из 60; unsafe 0/0/0.
   Upright reset устранил initial tilt-invalid (88 926/108 787 → 0/21 103),
   но B потерял stair tempo и малые lateral/yaw. Кандидат 24650 сохранён;
   A/B24949 не использовать как новые PPO parents, seed 9910 и бюджет закрыты.
   [Результат и проверка raw](results/2026-10-01-reset-pilot-result.md).
9. **D1.1 завершён и отклонён — native adaptive/fixed schedule.**
   Job `2eaf04619ca64678a110e6cc9fa96ff9`, exit 0: по 300 updates и
   180 fresh probe episodes. Parent/adaptive/fixed — 27/24/22 successes,
   unsafe 0/0/0. Fixed сохранил малые оси лучше adaptive, но потерял Flat
   longitudinal, ascent traversal, descent stop/restart и увеличил wheel
   saturation. Retention и schedule-hypothesis gates не пройдены; оба final
   checkpoints отклонены, бюджет закрыт. [Результат и raw-проверка](results/2026-10-01-schedule-pilot-result.md).
   Read-only анализ подтвердил поздние hard-joint события и 1.6–1.8× signed
   phase imbalance из-за фиксированного порядка `+` перед `−`; причинность
   ещё не доказана.
   **Диагностика без PPO завершена:** первая попытка
   `d7d0b2d7a07e42428ea500e0a27fda81` завершилась до episodes из-за передачи
   numeric parent ID как строки; исправленный job
   `0f2d2a0c50f94b1b960505425b8f009f` и first-update job
   `d073afe88e8044b4b4b1b976355317f8` завершены с exit 0, всего 360 episodes.
   Parent/+1/+51/+101/+151: 27/26/23/22/22 successes, unsafe везде 0.
   Уже +1 не проходит strict retention; intermediate actors отклонены.
   [Итог](results/2026-10-05-schedule-checkpoint-diagnosis.md).
   **No-update cohort reward/GAE/gradient audit выполнен:** job
   `216011ab5a7e43fcb5d16129b2c2ee55`, 512 × 3600 steps, 1 843 200 transitions,
   model/Adam exact до и после, PPO/optimizer steps 0. Подтверждены сильный
   signed phase imbalance и конфликт sampled actor-gradient между cohort/phase;
   общего NaN/exploding GAE нет. [Итог](results/2026-10-05-gradient-audit.md).
   **2×2 screen выполнен:** четыре ветви по 25 updates при 512 envs,
   300 fresh evaluation episodes. Ни одна цельная policy не сохранила retention.
   Counterbalanced standard PPO улучшил lateral response, но ухудшил лестницы;
   conservative PPO конфликт не устранил. Stage 2 не запускался.
   **Command-gated composite выполнен без новых PPO updates:** ещё 120 fresh
   episodes, parent/composite оба 27/60, unsafe 0, 60/60 outcomes совпали;
   lateral response `0.6831→0.7243`, yaw `0.6666→0.6909`, saturation без изменений.
   Это первый диагностически положительный результат, но не acceptance: целевые
   lateral/yaw cells остаются 0/5. [Итог и raw hashes](results/2026-10-05-micro-sweep-and-composite.md).
   **Продолжение specialist выполнено:** cumulative 77/102/150. На +150 probe
   вырос `27/60→28/60`, unsafe 0, paired 1 win/0 losses. Условный полный v2
   screen также положителен: `107/160→109/160`, unsafe 0, paired 2 wins/0 losses;
   gains в `flat_mu_100/lateral` и `rough_02/lateral`, mixed/stairs сохранены.
   All-cells gate не пройден; composite-150 — finalist, не новая candidate policy.
   [Итог и raw hashes](results/2026-10-05-specialist-stage2.md).
   **Независимый repeat seed 9913 выполнен и отрицателен:** 150 updates заново
   от 24650, probe `27/60→27/60`, unsafe 0, 0 wins/0 losses. Yaw response вырос
   `0.6666→0.6984`, но lateral снизился `0.6831→0.6625` и вышел за retention
   tolerance; условный full screen не запускался. Эффект seed 9912 не воспроизведён,
   composite-150 не продвигается. [Итог](results/2026-10-07-specialist-repeat.md).
   **Раздельные lateral-only и yaw-only specialists выполнены:** seed 9914,
   по 150 updates от неизменённого 24650. Оба эффекта направленные и локальные:
   lateral response `0.6831→0.7628`, yaw `0.6666→0.6969`; остальные cells,
   saturation и unsafe сохранены. Но success остался `27/60`, paired
   0 wins/0 losses, поэтому full screen не запускался и promotion нет.
   **Продление до cumulative 300 выполнено и отклонено:** lateral response
   деградировал до `0.6463`, в rough почти схлопнулся; yaw остался `0.6946`.
   Dense curve локализовала полезное lateral-окно на cumulative 152–177 и выбрала
   iteration 24825. **Mixed lateral-177/yaw-150 прошёл оба сравнительных gate:**
   probe `27/60→30/60`, paired 3/0; full v2 `107/160→112/160`, paired 5/0,
   unsafe 0, success-cell regressions отсутствуют, saturation не вырос. Выигрыш
   узкий: +2 flat_mu_100/lateral и +3 rough_02/lateral; rough_10/lateral response
   ухудшился, yaw cells всё ещё 0/5. Это первый
   подтверждённый положительный результат независимых осевых specialists.
   All-cells gate всё ещё не пройден, поэтому parent остаётся development
   candidate, а mixed — finalist без promotion/hardware approval.
   [Итог, endpoints и raw hashes](results/2026-10-07-axis-specialists.md).
   Следующий ограниченный шаг: короткий осевой checkpoint search вокруг найденного
   окна для всё ещё слабых lateral/yaw cells; не продолжать до 300 и не менять
   одновременно reward/MDP/PPO. Parent сохранять для нуля, `vx` и mixed-команд.
   **Endpoint search выполнен без PPO:** последовательный shortlist выбрал
   lateral-152 и yaw-252. Их composite дал `108/160` против `107/160`, paired
   1/0, unsafe 0, но `rough_10/lateral` response заметно различается между
   axis-only и full protocol при exact branch parity. Третий axis-only repeat
   точно воспроизвёл первый: причина — другой case order/RNG-reset slot, а не
   случайная межзапусковая variance. Endpoint screen оставлять только prefilter;
   следующий отбор выполнять с полным prefix/order cases или full v2. Новые
   updates и promotion по axis-only метрикам не выполнять.
10. **После сохранения retention — отдельные навыки.** B физически пересекает
   последний riser в 20/20 stair episodes; главный отказ — tempo, а на ascent
   stop/restart также stop/exposure. Не начинать geometry/promotion curriculum
   только по низкому общему success. Следующий фактор — command order/duration
   для малых осей либо stair skill sampling/geometry при подтверждённом дефиците.
   Late hard-joint события разобрать отдельно; constraints/PPO redesign,
   history и retrain с нуля пока резерв. Proposed длинные бюджеты 1500/3000
   не являются текущим заданием: coverage и gates замораживать перед новым опытом.
11. После положительного probe и повторов — полный matched v2 screen.
   После 5/5 и 0 unsafe во всех 32 ячейках заморозить actor и выполнить
   20 независимых reset seeds на ячейку: 640 эпизодов, ≥19/20 и 0 unsafe
   в каждой. Не использовать validation для повторного выбора checkpoints.
12. S0–S2 software/DDS готовить параллельно; S3–S4 требуют данных целевого B2W
   и отдельного допуска к аппаратным действиям. Перенос параметров Go2-W недопустим.
13. Расширять принятый envelope по одному фактору. Не объявлять всё множество
   скоростей/поверхностей принятым по небольшому числу samples.

Training, тесты и сравнение выполняет независимый supervisor;
[дашборд](../dashboard/README.md) только показывает процесс.
Не подбирать reward коэффициенты по общему success и не продлевать бюджет
по итогам неудачного отбора. Новое серверное обучение требует отдельного решения.

## Sim2real milestones

| Этап | Проверяемый результат | Сейчас |
|---|---|---|
| S0 | Frozen policy/export/runtime/deployment manifest | Software ABI есть; hardware поля открыты |
| S1 | Offline observations/actions/LowCmd parity, reset/stop | Export parity есть; SDK2 adapter отсутствует |
| S2 | Тот же executable через официальный MuJoCo DDS bridge; timing/fault tests | Не выполнен |
| S3 | B2W motor order/signs/units/IMU, firmware, read-only telemetry | Не выполнен |
| S4 | Actuator/latency identification и nominal/variation validation | Не выполнен |
| S5 | Стенд с поддержкой корпуса, ownership/stop, zero policy | Только после отдельного допуска |
| S6 | Ограниченный Flat hardware envelope | После S1–S5 и допуска |
| S7 | Rough/Stairs, затем длительность/payload | После проверки конкретных условий |

Подробности и Unitree sources — [SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md).
Runtime, cache, vendor и raw последней проверки сохраняются; implementation hashes
после рефакторинга не подменяют hashes реально выполненных запусков.
