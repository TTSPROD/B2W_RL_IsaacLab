# Текущий статус B2W

Дата актуализации: 29 сентября 2026.

## Выбранная policy

- ID: **core_24650**
- Checkpoint: `policies/local/core_24650/model_24650.pt`
- SHA-256: `458f08260f310e0d29d30d7aef3235df5d9c1c8b31d9e0f9637b1dc7f7466123`
- TorchScript SHA-256: `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36`
- ABI: 57→16, 50 Hz
- Статус: development candidate; simulation/hardware qualification отсутствует

Экраны кандидата:

- Stage-2 selection (seeds 66001–66005, 4 условия): 194/300, 0 unsafe
  (Flat 40, Rough 31, Stairs up 52, Stairs down 71).
- Stage-3 paired screen (seeds 68001–68005, 12 вариантов, 3 на условие):
  181/300, 0 unsafe (Flat 37, Rough 30, Stairs up 48, Stairs down 66).
  Continuation 24675–24750 гипотезу не подтвердил и не продвигается:
  [selection](results/2026-09-29-core-stage3-selection.md).

## Открытые проблемы

- системный недоход pure-axis команд 0.3 (lateral/yaw) на Flat/Rough —
  подтверждённая причина: баланс tracking-reward, не exposure и не приводы
  ([диагностика](results/2026-09-29-stage3-trace-diagnostics.md));
- longitudinal ±1.0 на rough: 1-s moving-RMSE окна (12–22/30 эпизодов);
  на rough_10 те же эпизоды теряют нулевые сегменты (4 longitudinal, 1 yaw);
- лестницы вверх 0.12–0.18 м: медленный подъём 0.3 m/s и удержание на
  ступенях 0.18 м — сатурация момента колёс до 30% / 12.5 s, вопрос
  acceptance-envelope;
- actuator torque-speed, current, thermal limits и задержки B2W не измерены;
- MuJoCo/SDK2 transport qualification и hardware mapping не завершены.

Новых training jobs нет. Следующий эксперимент — одна гипотеза: сузить kernel
трекинга малых величин (lateral + yaw, focused_std ~0.15 в [0.2, 0.6]) от 24650,
бюджет 100 updates, selection seeds 69001–69005, regression gates по 0.7/1.0,
mixed, stand, нулевым окнам и лестницам.
