# Диагностика tracking 24650 и первый A/B пилот

Источник: сохранённые 480 эпизодов v2 от 30.09.2026. Повторные симуляции для этой
диагностики не выполнялись. [Полные численные данные](evidence/tracking_diagnosis_20260930/summary.json)
содержат SHA raw JSON/NPZ и исходника анализа.

## Наблюдения

- При yaw ±0.3 средний response ratio по terrain/sign ячейкам 0.571–0.811;
  при ±0.7 и ±1 он существенно лучше. Отрицательный знак хуже положительного,
  но знак смешан с порядком команд: это пока не доказательство механической асимметрии.
- При lateral −0.3: 0.715 на Flat μ1, 0.702 на Rough 2 см, 0.503 на Rough 10 см.
- На Flat для этих steady окон в 10 Hz samples нет wheel torque saturation.
  На Rough 10 см она присутствует. Это не подтверждает отсутствие кратких пиков
  между samples и не является измерением аппаратного тока.
- Поздняя скорость на Flat остаётся ниже команды: дефект не объясняется только
  двухсекундным settling. На Rough остаются дополнительные колебания.
- Штраф nominal leg pose составляет примерно 0.13–0.30 reward units/s,
  потеря yaw tracking до идеала при ±0.3 — 0.11–0.37. Они сопоставимы.
  Это значения вдоль одной policy, не измерение градиента или доказательство причинности.
- Nominal масса модели — 82.42 кг. Нагрузки, inertia и gains не меняем.

Исходник joint_pos_penalty корректно учитывает ненулевой yaw в норме команды:
ошибки «yaw считается standstill и получает множитель 5» не обнаружено.
Сужение yaw kernel уже присутствует в родительской policy; повторять прежний
relative-kernel эксперимент как новую гипотезу нельзя.

## Проверка конфигурации

V2 использует тот же asset/action/observation контракт и 200/50 Hz. В raw metadata
есть проверка observation parity и точной передачи команды. Evaluation намеренно
отключает noise/events/rewards/curriculum, использует объявленные reset seeds и
геометрию. Training сохраняет randomization и parent terrain tiles; это различие
фиксируется, а не объявляется побитовым совпадением сред.

Для нового обучения восстанавливаются **исходные веса command banks 24650**,
из сохранённого stage-1 source snapshot; повышенные stage-3 веса не используются.
Перед PPO обязательный audit сравнивает observations/actions/events/physics/robot,
terrain/rewards/PPO с сохранёнными env.yaml/agent.yaml. Разрешены новые имена
эквивалентных command/timeout adapters и единственная объявленная reward intervention.

## Заранее объявленный эксперимент

[Конфиг A/B](../../configs/24650_tracking_posture_ab_20260930.json): оба плеча от
того же checkpoint 24650 с actor/critic/std/Adam; seed 9901, 4096 сред, 100 updates,
24 steps/update, 50 Hz, LR cap 1e-5. Это 9 830 400 transitions на плечо и 48 s
simulated time на среду, недостаточно для обещания сходимости всех длинных программ.

A — неизменённый parent reward. B — множитель 0.5 только для joint_pos_penalty
на чистых lateral/yaw командах |c|∈[0.2,0.6] в target Flat/Rough cohorts.
Нулевые команды, longitudinal, mixed, stairs, retention cohort и все остальные
reward terms/limits/gains остаются прежними. Гипотеза — ограничение адаптации позы
может мешать малым скоростям; A/B должен проверить, даёт ли его ослабление пользу.

Checkpoints сохраняются через 25 updates. Для ограниченного пилота checkpoints
25/50/100 обоих плеч оцениваются **после** двух 100-update runs, одним paired probe.
Это сокращает перезапуски Isaac; NaN/Inf останавливают training немедленно,
а любой unsafe в probe запрещает дальнейшее продвижение checkpoint.

Probe: Flat μ1/Rough 10 см — stand, longitudinal, lateral, yaw; up/down 18 см —
traverse 0.7 и stop/restart 0.5. Пять известных selection seeds, 60 эпизодов/actor.
Для advancement оба малых response ratio должны вырасти минимум на 0.05 к parent
и на 0.02 к matched-update control; регрессионные группы не теряют successes,
unsafe=0, рост максимальной saturation fraction ограничен +0.02 wheels/+0.01 legs.
Это инженерные pilot rules, не статистическое доказательство или hardware gate.

Полный v2 screen — только для прошедшего probe финалиста вместе с parent/control.
Если никто не прошёл, пилот заканчивается без увеличения бюджета и без promotion.
При воспроизводимом улучшении следующий шаг — повтор A/B с training seed 9902.
Независимые validation seeds пока не используются. Server/hardware не запускаются.
