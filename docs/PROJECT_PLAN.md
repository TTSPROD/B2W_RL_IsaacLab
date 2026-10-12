# План B2W

Актуально на 12 октября 2026. Это источник очередности проекта.
Хронология выполненных опытов и их frozen решения находятся в
[индексе результатов](results/README.md).

## Цель и действующий контракт

Низкоуровневая policy Unitree B2W принимает ровно 57 observations и выдаёт
12 leg position targets + 4 wheel velocity targets с частотой 50 Hz.
Команды `(vx, vy, omega_z)` приходят извне в body frame. Маршрут, waypoint,
абсолютный heading и момент смены команды принадлежат внешнему уровню.
Ноль требует остановки и устойчивости без возврата в прежнюю точку или курс.
Приёмка касается tracking, переходов, непрерывного нуля, устойчивости и
нагрузки приводов; навигационные метрики не являются gates этой policy.

Основной development candidate — `core_24650`, сохранённый ancestor —
`upstream_19999`. В сравнительном v2 screen 24650 получил 107/160,
0 unsafe и 20/32 полностью пройденных ячеек. Все ячейки не пройдены,
независимая validation не запускалась, simulation qualification и допуска
к роботу нет. [Статус](TRAINING_STATUS.md) · [реестр и SHA](POLICY_REGISTRY.md) ·
[методика v2](CORE_LOCOMOTION_EVALUATION.md).

## Следующие шаги

1. **S2 на исходной модели Unitree.** Заморозить actor/export, один
   `PolicyRuntime`/SDK2 mapper, профиль actual-state/PD-reference guard,
   B2W MJCF и C++ bridge Unitree. Выполнить полный согласованный Flat
   command/zero protocol, DDS fault/recovery и timing checks на этой базе,
   записать raw evidence и executed hashes. Исходные MJCF/bridge не менять.
   [Основание и подробный протокол](UNITREE_SIM2SIM_METHOD.md).
2. **Разобрать failures исходного S2.** Отдельно оценить tracking малых
   lateral/yaw команд, реверсы, непрерывный ноль, actual safety и приводные
   ограничения. Успех 2/5 последнего timing replay относится к изменённой
   DC actuator law; `armature=0` также был диагностическим фактором.
   Эти результаты не являются acceptance исходной модели. Плановый
   `damping=0` снят с очереди. Из опубликованного Unitree workflow
   не следует обязательное выравнивание параметров PhysX/MuJoCo.
3. **Training decision после разбора traces.** Последний локальный native
   standard PPO A/B от 24650 завершён и отклонён: parent/control/focus
   103/100/104 из 160, unsafe 0/1/1; seed 9930 и бюджет 150 updates/плечо
   закрыты. Разобрать сохранённые unsafe/phase/saturation traces до нового
   recipe. [Результат](results/2026-10-12-native-continuation.md).
   [Trace-based proposal](../configs/24650_trace_based_recipe_proposal_20261012.json)
   остаётся предложением, не запуском. Основа новых моделей — стандартный
   pinned [Robot Lab train.py](../vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py)
   и штатный RSL-RL PPO; внешние MDP/task адаптации ограничивать измеренным
   дефицитом. Старые runner hooks автоматически не наследовать.
4. **После положительного screen.** Заморозить actor и выполнить независимую
   validation: 20 новых reset seeds на каждую из 32 ячеек, всего 640
   эпизодов, порог ≥19/20 и 0 unsafe в каждой. Не подбирать checkpoints
   повторно по validation. Принятый диапазон скоростей/поверхностей
   расширять по одному фактору.

Обучение, evaluation и сравнение выполняет независимый supervisor;
[дашборд](../dashboard/README.md) только читает состояние. Новое серверное
обучение требует отдельного решения. Реальное управление B2W требует
отдельного явного допуска и этапов ниже. Старые разрешения и frozen планы
не являются разрешением повторного запуска.

## Sim2real milestones

| Этап | Проверяемый результат | Состояние |
|---|---|---|
| S0 | Замороженные policy/export/runtime/manifest и SHA | Диагностические manifests есть; аппаратные поля открыты |
| S1 | Offline observations/actions/LowCmd parity, reset/stop | Native SDK2 software parity выполнена; physical mapping открыт |
| S2 | Тот же runtime через исходные B2W MJCF и официальный MuJoCo DDS bridge; полный command/zero, fault/timing envelope | Ограниченные software/DDS/fault checks выполнены; полный replay исходного baseline открыт |
| S3 | Motor order/signs/units/IMU, firmware, read-only telemetry целевого B2W | Не выполнен |
| S4 | Ограничения приводов, задержки и nominal/variation validation | Не выполнен |
| S5 | Стенд с поддержкой корпуса, ownership/stop, zero policy | Только после отдельного допуска |
| S6 | Ограниченный Flat hardware envelope | После S1–S5 и допуска |
| S7 | Rough/Stairs, длительность и payload | После проверки конкретных условий |

[SDK2_DEPLOYMENT](SDK2_DEPLOYMENT.md) описывает аппаратные зависимости.
Runtime, vendor, raw evidence и hashes 24650/19999 сохранять.
Implementation hashes после рефакторинга не подменяют hashes выполненных runs.
