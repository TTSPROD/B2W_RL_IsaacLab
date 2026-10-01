# План B2W

Актуально на 1 октября 2026.

## Цель и контракт

Обучить низкоуровневую velocity-conditioned policy для Unitree B2W:
57 observations → 12 leg position + 4 wheel velocity actions, 50 Hz.
Внешний уровень задаёт body-frame (vx, vy, ωz), маршрут и момент смены команды.
Ноль требует остановки и устойчивости, без возврата в мировую точку/курс.
Flat/Rough/Stairs принимаются только в измеренном диапазоне условий.

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
4. **Реализован [пересмотренный план обучения](TRAINING_STRATEGY.md),**
   основанный на первичных работах по wheeled locomotion, CaT, MUJICA и Unitree:
   разобраны hard-limit traces; training safety согласован с evaluator,
   проверены terminal/timeout bootstrap и учёт violations на 200 Hz.
   Это новая общая постановка обоих плеч; старые результаты не переписывать.
5. **Исходный A/B:** оба от 24650 с одинаковой обработкой safety, LR cap 1e-5,
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
6. **Следующий шаг:** разобрать safety-reset по причинам/фазам и отсутствие
   promotions B даже на level 0; сверить termination с фактическими traces.
   Не продлевать A/B и не запускать повторные seeds отклонённого recipe.
   После диагностики отдельно зафиксировать опыт «ступень → короткий марш →
   полный марш» либо изменение обработки constraints, сохраняя один фактор.
   При подтверждении новой гипотезы повторить A/B на двух дополнительных training seeds.
   Следующая отдельная гипотеза — разнообразие порядка/длительности команд
   и промежуточных скоростей внутри trained envelope, до 3000 updates на плечо.
   Stair retention и улучшение малых команд оценивать раздельно. История/teacher–student,
   CaT/P3O и retrain с нуля остаются резервными, не автоматическими изменениями.
7. После успешного полного screen заморозить actor и выполнить 20 независимых reset seeds
   на ячейку. Не использовать этот набор для повторного выбора checkpoints.
8. S0–S2 software/DDS готовить параллельно; S3–S4 требуют данных целевого B2W
   и отдельного допуска к аппаратным действиям. Перенос параметров Go2-W недопустим.
9. Расширять принятый envelope по одному фактору. Не объявлять всё множество
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
