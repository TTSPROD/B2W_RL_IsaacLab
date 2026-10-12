# B2W RL — обучение политики движения Unitree B2W

Репозиторий для обучения, оценки и подготовки к развёртыванию низкоуровневой
RL-политики колёсно-шагающего робота Unitree B2W. Обучение строится на
[Isaac Lab](https://github.com/isaac-sim/IsaacLab) и закреплённой версии
[Robot Lab](https://github.com/fan-ziqi/robot_lab); проверка переноса в другой
симулятор использует опубликованные модель B2W и SDK2 bridge из
[Unitree MuJoCo](https://github.com/unitreerobotics/unitree_mujoco).

Рабочая последовательность следует опубликованному подходу
[Unitree RL Lab](https://github.com/unitreerobotics/unitree_rl_lab#deploy):
обучение в Isaac Lab → sim2sim в MuJoCo → отдельная проверка перед sim2real.
Готового B2W training/deploy recipe в Unitree RL Lab нет: B2W task и исходный
training pipeline взяты из Robot Lab, а контракт, оценка и SDK2-интеграция
разрабатываются в этом проекте. Подробно источники и принятое решение описаны
в [методе sim2sim2real](docs/UNITREE_SIM2SIM_METHOD.md).

## Задача политики

Actor получает **57 observations** и с частотой **50 Гц** выдаёт **16 actions**:
12 целевых положений суставов ног и 4 целевые скорости колёс. Команду скорости
`(vx, vy, omega_z)` задаёт внешний уровень в системе координат корпуса. При
нулевой команде робот должен остановиться и сохранять устойчивость. Маршрут,
waypoints и абсолютный курс не входят в задачу этой политики.

Оцениваются следование команде, переходы между командами, длительная остановка,
устойчивость и нагрузка на приводы на Flat/Rough/Stairs. Точный порядок каналов,
масштабы и семантика предыдущего action закреплены в
[контракте 57→16](docs/POLICY_CONTRACT.md), критерии отбора — в
[протоколе оценки v2](docs/CORE_LOCOMOTION_EVALUATION.md).

## Как устроена работа

1. **Обучение.** Базой новых моделей служит закреплённый
   [Robot Lab `train.py`](vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py)
   со штатным RSL-RL PPO. Изменения task config и MDP находятся вне `vendor/`
   и вводятся по результатам измерений. Импортируемый пакет `rsl_rl` — отдельная
   зависимость `rsl-rl-lib==3.1.2`, а не исходники в `vendor/robot_lab`.
2. **Отбор.** Checkpoint экспортируется с проверкой ABI и численного совпадения;
   затем проходит сравнение по протоколу v2. Независимая validation использует
   новые reset seeds и запускается только после положительного screen.
3. **Sim2sim.** Один actor и mapper проверяются через исходные закреплённые
   B2W MJCF и C++ SDK2 bridge Unitree. Варианты с изменёнными DC law,
   `armature` или `damping` учитываются отдельно как диагностика и не
   подтверждают исходную модель.
4. **Sim2real.** Порядок сигналов, ограничения приводов, задержки и поведение
   при остановке должны пройти отдельные этапы
   [SDK2 deployment](docs/SDK2_DEPLOYMENT.md) до работы на роботе.

Обучением, оценкой и сравнениями управляет независимый supervisor в
`scripts/job_manager.py` и `scripts/job_worker.py`. Каждый managed запуск
автоматически открывает [монитор](dashboard/README.md) во внешнем браузере;
его сервер и worker живут отдельно от CLI и чата. Закрытие браузера не
останавливает job. Runtime, checkpoints, планы и результаты сохраняются с
provenance и SHA-256.

## Текущее состояние

На 12 октября 2026 основной development candidate —
[`core_24650`](policies/local/core_24650/export/manifest.json); сохранён его
[`upstream_19999`](policies/server/upstream_19999/export/manifest.json). В сравнительном v2 screen
24650 получил 107/160, 0 unsafe и прошёл 20/32 ячеек. Независимая validation
не выполнена. Полный S2 replay на исходной модели Unitree также остаётся
открытым; квалифицированной для робота политики пока нет.

Текущую очередность задаёт [план проекта](docs/PROJECT_PLAN.md), итоги
экспериментов — [статус обучения](docs/TRAINING_STATUS.md) и
[датированные отчёты](docs/results/README.md). Checkpoints и их хеши
приведены в [реестре политик](docs/POLICY_REGISTRY.md).

## Структура репозитория

| Каталог | Содержимое |
|---|---|
| [`vendor/`](vendor/README.md) | Закреплённые upstream snapshots Robot Lab, Unitree SDK2/MuJoCo и другие исходные материалы |
| [`scripts/`](scripts/README.md) | Training, evaluation, sim2sim, supervisor и проверки |
| [`configs/`](configs/README.md) | Frozen планы запусков, предложение нового recipe и шаблон deployment |
| [`policies/`](policies/README.md) | Сохранённые checkpoints, exports и provenance |
| [`docs/`](docs/README.md) | Контракт, методики, инфраструктура, результаты и решения |
| `sim2sim/` | Проектная нативная обвязка проверки через SDK2/MuJoCo |
| `tests/` | Поведенческие и интеграционные проверки |
| [`dashboard/`](dashboard/README.md) | Монитор состояния managed jobs |

## Локальная проверка

Подготовка окружений Isaac Lab и MuJoCo описана в
[INFRASTRUCTURE](docs/INFRASTRUCTURE.md). После подготовки CPU `.venv` из корня
репозитория можно запустить тесты через supervisor и проверить закреплённые
upstream-файлы и ссылки:

```bash
.venv/bin/python scripts/manage_runs.py start tests
python3 scripts/vendor_materials.py verify
.venv/bin/python scripts/verify_project.py
.venv/bin/python scripts/manage_runs.py status
```

Итог тестового job отображается в мониторе и в его `state.json`; команда `start`
завершается после постановки job, не после выполнения тестов.

Запуск нового обучения и работа с реальным B2W требуют отдельных решений по
[плану](docs/PROJECT_PLAN.md) и [этапам deployment](docs/SDK2_DEPLOYMENT.md).
