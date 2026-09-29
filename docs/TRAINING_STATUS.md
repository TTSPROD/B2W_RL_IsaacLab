# Текущий статус B2W

Дата актуализации: 29 сентября 2026.

## Выбранная policy

- ID: **core_24650**
- Checkpoint: `policies/local/core_24650/model_24650.pt`
- SHA-256: `458f08260f310e0d29d30d7aef3235df5d9c1c8b31d9e0f9637b1dc7f7466123`
- TorchScript SHA-256: `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36`
- ABI: 57→16, 50 Hz
- Статус: development candidate; simulation/hardware qualification отсутствует

Последний paired checkpoint screen: 194/300 успехов, 0 unsafe. По условиям:
Flat 40/75, Rough 31/75, Stairs up 52/75, Stairs down 71/75.

## Открытые проблемы

- tracking и transitions на Flat/Rough далеки от gate;
- остановка и traversal на лестницах не дают 99% надёжности;
- actuator torque-speed, current, thermal limits и задержки B2W не измерены;
- MuJoCo/SDK2 transport qualification и hardware mapping не завершены.

Новых training jobs нет. Следующий эксперимент должен иметь одну заранее
зафиксированную гипотезу, отдельные seeds и regression gates относительно 24650.
