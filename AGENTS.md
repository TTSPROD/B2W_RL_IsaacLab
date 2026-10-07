# B2W: правила работы

## Цель и текущий scope

Разрабатываем низкоуровневую политику движения Unitree B2W для последующего
деплоя через Unitree SDK2. Actor принимает ровно 57 observations и выдаёт 16 actions:
12 leg position targets + 4 wheel velocity targets, 50 Hz.
Команды `(vx, vy, omega_z)` приходят извне в body frame.
Маршрут, waypoint, абсолютный heading и момент смены команды принадлежат внешнему уровню.
Ноль требует остановки и устойчивости, без возврата в прежнюю точку или курс.

Источник очередности — `docs/PROJECT_PLAN.md`; перед training work читать также
`docs/INFRASTRUCTURE.md`.

Текущий development candidate — `policies/local/core_24650/`; сохранённый
server ancestor — `policies/server/upstream_19999/`.

Активная методика оценки — `docs/CORE_LOCOMOTION_EVALUATION.md` (v2).
Обучение, evaluation и сравнение выполняет независимый supervisor
(`scripts/job_manager.py`, `scripts/job_worker.py`). Запуск/остановка — через
`scripts/manage_runs.py` или managed CLI entrypoints. Дашборд только читает
состояние, логи и метрики; HTTP-сервер и браузер не нужны для выполнения jobs.
`scripts/start_dashboard.ps1` открывает монитор. Закрытие дашборда не завершает run.
Не восстанавливать закрытую relkernel-ветку как текущий план без нового решения.

## Инженерные правила

- Для новых моделей использовать стандартный pinned Robot Lab
  `vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py` как источник
  training pipeline; upstream bytes не менять. Адаптации task config/MDP делать
  снаружи и только для участков с подтверждённым отставанием по оценкам.
  Новый recipe не должен автоматически наследовать весь стек прежних runner hooks.
- Сохранять ABI 57→16, порядок каналов, units, scales, previous-action semantics.
- Оценивать tracking, смену команд, непрерывный ноль, устойчивость и приводы.
  Навигационные метрики не являются acceptance gates низкоуровневой policy.
- Не выдавать скачанный checkpoint, viewer или offline test за принятую policy.
- Сохранять upstream bytes в `vendor/`; адаптации делать снаружи. Явно разрешённое
  изменение состава snapshots фиксировать в `vendor/manifest.json` и
  `docs/VENDOR_INVENTORY.md`, проверять pinned Git blobs и SHA-256.
- Сохранять байты raw evidence последней проверки и hashes экспортированных
  24650 и ancestor 19999.
  Изменения implementation hashes отделять от hashes реально выполненного запуска.
- Конфиги Isaac Lab MDP писать чисто, использовать тензорные операции PyTorch.
  При работе с наградами учитывать массу B2W и нагрузку на 12+4 привода.
- Не добавлять среды, caches и live logs в Git. Policies хранить с происхождением и SHA.
- Локальные `.venv`, `.runtime` и vendor snapshots сохранять при чистке результатов.

## Инфраструктура и разрешения

Линии RTX4070Ti desktop, RTX4080 Laptop и сервер используют общий репозиторий;
runtime и checkpoints разных машин не считать взаимозаменяемыми по одному seed.
Основной серверный каталог: `/home/user/projects/B2W_RL_IsaacLab`.
Transfer cache: `/home/user/.cache/B2W_RL_IsaacLab-sync`.
Завершённые разрешённые серверные runs `upstream_b2w_20000_4gpu_20260922` и
`inverse57_4gpu_20260923` расположены в `/home/user/B2W_RL_IsaacLab_Server`.
Их собственные конфиги, логи и checkpoints можно читать; новые server training jobs
требуют отдельного явного решения. Предыдущие разрешения завершённых runs не являются
разрешением перезапуска или продолжения обучения. Не изменять чужие проекты,
jobs, общие драйверы и глобальные пакеты. Локальная чистка не разрешает удаление на сервере.

При GitHub DNS failure использовать `skills/github-dns-bypass/SKILL.md`, сохранять TLS,
не делать force push. Реальное управление роботом требует отдельного явного допуска
и этапов из `docs/SDK2_DEPLOYMENT.md`. Настройка репозитория и симуляции его не дают.

Отвечать кратко по-русски; проверенные факты, планы и ограничения различать явно.

## Проектные skills для интерактивной симуляции

Эти файлы входят в репозиторий и являются основными версиями на любом ПК.
При запросе соответствующего skill читать проектный файл, даже если installed
копия отсутствует или устарела:

- [mujoco-b2w-gamepad-window](skills/mujoco-b2w-gamepad-window/SKILL.md) — выбор checkpoint и карты, gamepad в MuJoCo.
- [isaacsim-b2w-gamepad-window](skills/isaacsim-b2w-gamepad-window/SKILL.md) — тот же выбор, gamepad в Isaac Sim.

Единый workflow: [GAMEPAD_VIEWERS](docs/GAMEPAD_VIEWERS.md). Установка/синхронизация
в пользовательский каталог skills — `scripts/install_gamepad_skills.ps1`.
