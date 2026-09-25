# B2W RL · Isaac Lab

Проект обучения и проверки локомоции Unitree B2W в Isaac Lab/RSL-RL. Текущая линия сохраняет референсный контракт **57 наблюдений → 16 действий**: 12 position targets ног и 4 velocity targets колёс, policy rate 50 Hz.

Назначение policy — **низкоуровневое исполнение внешних команд скорости** `(vx, vy, omega_z)`.
Навигация находится снаружи. Приемка оценивает tracking, устойчивость, проходимость,
реакцию на смену/обнуление команды и приводы; прежние cycle/corridor scores остаются
историческими diagnostics. [Актуальные критерии](docs/PROJECT_PLAN.md#acceptance-gates-низкоуровневая-locomotion-policy).

## Состояние на 25 сентября 2026

- Принятой общей политики Rough/Stairs нет; SDK2 и испытания реального робота не открыты.
- `locomotion57_v1` реализован для development-screen: upstream10000/15000/19999 проверены в 5184 эпизодах Isaac/MuJoCo. Ни один не принят по полному набору критериев. [Результаты](docs/results/2026-09-25-upstream-locomotion57.md).
- Серверные `upstream20000` и `inverse57` завершены. `inverse57 update3000`, локальный `cycle57 model3000` и внешний reference — кандидаты для сопоставимого baseline по внешним командам.
- Исторический MuJoCo suite у model3000 дал Flat `80/80`, спуск `60/60`, подъём `23/60` и `37` unsafe. Различия физики и определения actuator limits требуют диагностики.
- Отрицательные результаты cycle57, stop-controller и payload-веток сохранены в [матрице](docs/results/EXPERIMENT_MATRIX.md); их прежние cycle/corridor gates не переносятся в новую приемку.
- [Contact57](docs/results/2026-09-25-contact57-diagnostics.md): source collision geometry перенесена в opt-in MuJoCo профиль;19999 получил17/20 в micro-screen, unsafe0. Полная parity/qualification открыта.
- [Contact57b](docs/results/2026-09-25-contact57b-19999.md): с cooked geometry тот же19999 дал12/20, unsafe0; выполнены36 policy-free probes, локализованы два slow-ascent stalls. Следующий шаг — full-state replay/reward ledger19999.

По указанию пользователя upstream10000 исключен из дальнейших запусков и обучения.
Сохранены его исторические результаты; основной upstream кандидат для продолжения —19999.

Следующий шаг — дополнить реализованный evaluator и согласовать
**actuator/physics-модели Isaac↔MuJoCo**, затем расширить парный baseline на
reference/inverse57/cycle57. Первое сравнение трех upstream milestones уже выполнено. По его результатам выбирается один ограниченный PPO A/B в задаче velocity
tracking без goal/landing state machine. Полная последовательность и численные
критерии находятся в [плане](docs/PROJECT_PLAN.md). Аудит исходных данных — в
[разборе обучения и приемки](docs/results/2026-09-25-locomotion-training-review.md).

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
