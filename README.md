# B2W RL · Isaac Lab

Проект низкоуровневой policy Unitree B2W. Actor получает 57 observations и при
50 Hz выдаёт 16 actions: 12 leg position targets и 4 wheel velocity targets.
Команды `(vx, vy, omega_z)` задаются внешним уровнем в body frame.

## Текущий кандидат

**core_24650** — единственный активный development candidate. В компактном
paired screen он получил 194/300 полных успехов и 0 unsafe: Flat 40/75,
Rough 31/75, Stairs up 52/75, Stairs down 71/75. Это лучший проверенный
checkpoint, но не simulation qualification и не аппаратный допуск.

- [Результат 24650](docs/results/2026-09-28-core-selection-24650.md)
- [Policy registry](docs/POLICY_REGISTRY.md)
- [Контракт оценки](docs/CORE_LOCOMOTION_EVALUATION.md)
- [План проекта](docs/PROJECT_PLAN.md)
- [SDK2 deployment](docs/SDK2_DEPLOYMENT.md)
- [Инфраструктура](docs/INFRASTRUCTURE.md)

В `policies/` сохранены только 24650 и исходный upstream19999. Пакеты, тяжёлые
evidence и launchers неудачных веток удалены; минимальные lineage-материалы,
нужные для происхождения 24650, сохранены. Immutable upstream bytes остаются в
`vendor/`.

## Проверка

```powershell
python scripts/vendor_materials.py verify
& .\scripts\run_local.ps1 -m unittest discover -s tests -q
& .\scripts\run_local.ps1 scripts/verify_project.py
```

Реальное управление роботом требует отдельного явного допуска.
