# B2W RL · Isaac Lab

Проект обучения и проверки локомоции Unitree B2W в Isaac Lab/RSL-RL. Текущая линия сохраняет референсный контракт **57 наблюдений → 16 действий**: 12 position targets ног и 4 velocity targets колёс, policy rate 50 Hz.

## Состояние на 25 сентября 2026

- Принятой общей политики Rough/Stairs нет; SDK2 и испытания реального робота не открыты.
- Серверные `upstream20000` и `inverse57` завершены. `inverse57 update3000` — непринятый research parent.
- Локальный `cycle57 model3000` — research-only. Isaac held-out gate и frozen MuJoCo gate провалены.
- MuJoCo: Flat `80/80`, спуск `60/60`, подъём только `23/60` и `37` unsafe. Основные признаки — calf-limit stops и длительное насыщение колёс.
- Финальный `cycle57 model3998` coarse-screened и отклонён: `19/64` полных циклов против `61/64` у `model3000`, `5` unsafe и `39` incomplete.
- Stop-controller, settled latch, late-hold fine-tune и payload A/B/C не дали кандидата для promotion.

Следующий шаг — **не новый PPO run**, а выравнивание actuator/physics-моделей Isaac↔MuJoCo и повтор неизменённого 200-episode suite. После этого принимается отдельное решение о bounded training experiment.

## С чего читать

1. [Карта документации](docs/README.md)
2. [Скорректированный план](docs/PROJECT_PLAN.md)
3. [Краткий журнал экспериментов](docs/TRAINING_PROGRESS.md)
4. [Аналитика экспериментов и текущий статус](docs/TRAINING_STATUS.md)
5. [Реестр checkpoint/SHA/статусов](docs/POLICY_REGISTRY.md)
6. [Контракт 57→16](docs/POLICY_CONTRACT.md)
7. [Карта логов и матрица результатов](docs/LOGS_AND_RESULTS.md)

Датированные отчёты в [docs/results](docs/results/README.md) — evidence на момент запуска. Их старые «следующие шаги» не заменяют текущий план.

## Проверка репозитория

```powershell
python scripts/vendor_materials.py verify
& .\scripts\run_local.ps1 -m unittest discover -s tests -q
```

На текущем runtime проверены 1290 vendor-файлов и пройдены 267 unit tests. Обычный системный Python не содержит Isaac/PyTorch-зависимости; для полного набора нужен `scripts/run_local.ps1`.

Стек baseline: robot_lab/Isaac Lab 2.3.2, Isaac Sim 5.1, Python 3.11, RSL-RL 3.1.2. `vendor/` — неизменяемые upstream snapshots; их происхождение и лицензии описаны в [vendor/README.md](vendor/README.md).
