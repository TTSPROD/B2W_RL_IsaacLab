# Инфраструктура и синхронизация

**Цель уточнена 20.09.2026. Qualified Flat54 подходит как reference-compatible
actor-parent57→16. U1 seeds69/70 выполнен последовательно одним4096-env
процессом до quality stop150. Critic60→247 и50 frozen-actor updates прошли;
после100 PPO seed70 не сохранил Flat regression, поэтому следующие200 и U2
не запускались. [Evidence](results/unified_u1_training_20260920.json).**

U1 preflight20.09 прошёл5 stages: два evaluator fixtures, полный100-case
locomotion baseline и GPU train/resume2+2. После завершения GPU idle:
866MiB/12282MiB, utilization5%,55°C — датированный замер, не гарантия будущей
нагрузки. [Evidence](results/unified_u1_preflight_20260920_1.json). Основной
запуск подтвердил peak GPU6616MiB на critic-only stage; два одновременных4096
по-прежнему не помещаются в12282MiB. Измеренный2×2048 режим медленнее aggregate
и меняет зарегистрированный recipe, поэтому seeds выполнялись последовательно.
U1.1 preflight и seeds71/72 выполнены последовательно1×4096; quality stop150,
следующие200 не запускались. Параллельность и capacity assumptions не менялись.
U1.2 preflight и seeds73/74 также выполнены последовательно1×4096 и остановлены
на150. Репликация неизменного U1.1 seeds75/76 выполнена21.09 после нового
preflight5/5 тем же последовательным1×4096 режимом и остановлена quality gate
на150. После завершения GPU idle:853MiB/12282MiB, utilization5%,57°C;
активных training jobs нет. [Evidence](results/unified_u11_replication_20260920.json).

Desktop runtime не менялся. Ниже датированные прежние измерения.

**Последний принятый 57-input результат 20.09:** wide65/66 завершился 18:28:16 МСК на 150
с quality stop,28 stages exit0. Rough564/1600, Flat400/400 safe,
4/4 absolute и0/4 relative gates. [Аудит91hash](results/2026-09-20-wide150-audit.json).
При проверке18:46МСК GPU занимала975MiB/12282MiB, utilization5%; это датированный
замер. Позднейший teacher247 seed67 выполнил100 updates, но эксперимент отклонён
по ABI и упал на diagnostic reset; seed68 не запускался. Новых training updates
после него и U1 ещё не было.

Серия использовала тот же desktop runtime: single4096, seeds последовательно,
training y±1,8м, прежний evaluator y±0,9м, X[−0,6;5,4], tile12×12м.
197CPUтестов,1290vendor hashes и native64 train/resume2+2 пройдены.
[Протокол проведённого опыта](ROUGH_WIDE_CORRIDOR.md),
[действующий план](ROUGH_STAIRS_PLAN.md), [журнал](TRAINING_PROGRESS.md).

Checkpoints остаются в исключённых из Git `logs/`; исторические jobs/PID
не являются текущим состоянием. Git push переносит код, docs и опубликованные
JSON, но не checkpoints/runtime и не обновляет ноутбук или сервер.
Серверные и hardware gates не меняются.

## Разделение данных

| Назначение | Путь |
|---|---|
| GitHub | `https://github.com/TTSPROD/B2W_RL_IsaacLab` |
| Настольный ПК | `D:\Work\GitProjects\B2W_RL_IsaacLab` |
| Квалифицированный ноутбук | `192.168.1.129`, `D:\Work\GitProjects\B2W_RL_IsaacLab` |
| Исходная рабочая копия ноутбука, исторический путь | `C:\Users\ra.suragin\Documents\ChatGPT\B2W_RL_IsaacLab` |
| Выделенная серверная копия | `user@10.126.161.7:/home/user/projects/B2W_RL_IsaacLab` |
| Только transfer bundles | `/home/user/.cache/B2W_RL_IsaacLab-sync` |

Предыдущие B2W проекты не открывать и не использовать. Глобальные драйверы,
пакеты и чужие jobs не менять. Runtime, caches, logs и окружение нового проекта
держать в его каталоге; серверные записи разрешены только в двух выделенных
путях выше.

В Git сохраняются код, документация, runtime lock и vendor manifest с
hashes/licenses. Logs, новые checkpoints, `.venv`, `.runtime` и caches не
коммитятся. Небольшие исходные эталонные политики входят в неизменяемые vendor
snapshots. Новым checkpoints нужен отдельный artifact store с manifest/SHA256;
постоянное хранилище ещё не выбрано. Git push не переносит runtime, результаты
обучения и не обновляет автоматически ноутбук или сервер.

## Настольный ПК

Обследование 17 сентября 2026: Windows 11 Pro build 26200, Ryzen 9 5900X
(12 ядер / 24 потока), 31.9 GiB RAM, RTX 4070 Ti 12 282 MiB, driver 616.92.
До установки на D было свободно около 528 GiB; это исторический замер.
Отдельный runtime: Python 3.11.13, Isaac Sim 5.1.0, Isaac Lab v2.3.2,
RSL-RL 3.1.2. [Версии и установка](DESKTOP_SETUP.md).

**Headless Flat квалифицирован для этого runtime.** Пройдены Compatibility
Checker, 10 000 шагов GPU PhysX/Fabric, PPO/resume и sweep 256–2048.
Длительный pilot покрыл 9 624 s без telemetry errors. Benchmark 2×4096 дал
63 907,87 transitions/s суммарно, peak VRAM 9 583 MiB, минимальный запас 21,98%.
Ограничения измерений и длительные прогоны — в [COMPUTE_DECISION](COMPUTE_DECISION.md).

20 сентября Rough capacity: один4096-env процесс дал26153 transitions/s
по времени между updates; два2048-env процесса —21170 суммарно в overlap.
Оба режима завершили по50 updates на процесс; dual peak10803MiB, запас12,04%.
Для Rough выбран один4096-env процесс, два сида последовательно.2×4096 Rough
не запускались: прогноз13130MiB превышает12282MiB устройства.
[Измерения](results/rough_capacity_20260919.json),
[протокол завершённой серии](ROUGH_WIDE_CORRIDOR.md);
[следующая диагностика](ROUGH_NEXT_DIAGNOSTICS.md) пока не запускалась.

19 сентября GUI Flat replay ускорен до примерно 48,8 policy frames/s и 0,976×
real time: Isaac Sim5.1,1 B2W seed54, Xbox XInput. Рабочий default — Storm/Vulkan
raster rendering, CPU PhysX и CPU TorchScript с 1 потоком; physics dt0,005 с,
decimation4 сохранены. Проектный `apps/b2w.gamepad.storm.kit` включает Hydra pxr,
отключает Fabric и обновляет pose через USD. RTX/ray tracing/DLSS не используются.
PXR extensions из официального registry хранятся в проектном cache. Headless
training runtime не менялся; CPU playback не расширяет его квалификацию.
[Управление и ограничения](GAMEPAD_PLAY.md), [замер](results/2026-09-19-gamepad-performance.json).
Первый GPU/RTX D3D12 viewer0,34× real time сохранён в
[историческом отчёте](results/2026-09-19-gamepad-gui.json); legacy-путь доступен явно.
Viewer не совмещать с benchmark/training на той же GPU.

Техническая квалификация не означает приёмку политики. Rough runtime проверен,
но Rough quality, Stairs и sim2sim gates открыты; GUI относится только к
описанному Flat replay. Ubuntu 26.04 на ПК не
использовалась и не входит в опубликованную матрицу Isaac Sim 5.1.

## Ноутбук и сервер

**Ноутбук:** Windows 11 Enterprise build 26200, i9-14900HX (24 ядра / 32 потока),
31.6 GiB RAM, RTX 4080 Laptop 12 282 MiB, driver 616.92. Отдельный runtime нового
проекта квалифицирован 18 сентября: physics 10 000 шагов, PPO/resume и 4096-env
benchmark с фиксированными P-ядрами. Скорость — 38 007,8 transitions/s по PPO
timers. Основное обучение в рамках этой квалификации не назначалось.
[Подключение, пути и результаты](LAPTOP_WORKER.md).
Найденный ранее `D:\isaacsim51` был привязан к другому editable checkout;
этот runtime и код не используются.

**Сервер:** Ubuntu 22.04.5, kernel 5.15.0-191, Xeon 6527P (96 logical CPUs),
503 GiB RAM; 4 Hopper GPU, PCI `10de:233f`, NVML `NVIDIA Graphics Device`,
по 95 830 MiB, driver 580.178.04. Коммерческое имя GPU не подтверждено.
Git, Python 3.10, rsync и Docker 29.4.1 доступны. Обследование 18 сентября
показало GPU0 D2D 1,752 TB/s чтения+записи; SGEMM остановлен по timeout при
инициализации cuBLAS. Это не измерение скорости Isaac Lab.

Проектного Isaac runtime и Vulkan loader при проверке не было; сервер не
квалифицирован. Для Sim 5.1 нужен отдельный Python 3.11, затем RT/Vulkan,
Compatibility Checker и B2W physics smoke. Занятость GPU проверять перед новым
назначением; автоматически занимать четыре GPU нельзя. Существующие чужие
окружения и проекты не исследуются. [Датированный отчёт](SERVER_PERFORMANCE.md).

## GitHub и DNS

Использовать обычные `git clone/fetch/push`. Только после подтверждённой ошибки
DNS применять [github-dns-bypass](../skills/github-dns-bypass/SKILL.md).
Навык получает текущие A-record через HTTPS DoH и передаёт IP одной Git/curl
операции, сохраняя hostname и TLS. Hosts и global Git config не меняются;
существующая авторизация сохраняется, секреты не входят в репозиторий.
SSH key сервера не означает GitHub SSH-доступ.

Windows Git в проверенной среде поддерживает `schannel`; не задавать `openssl`
без проверки поддержки. Блокировка schannel/SSH credential access sandbox-процессом
сама по себе не доказывает неисправный DNS.

Git 2.34.1 на обследованном сервере игнорирует `http.curloptResolve`. При реальном
DNS-сбое там используется `python3 skills/github-dns-bypass/scripts/github_dns.py --git-transport proxy git fetch origin`:
временный loopback CONNECT tunnel соединяется с DoH-адресом, TLS проверяет имя
GitHub. На новом Windows Git используется transport `resolve`. Предпочтительный
push — локально через существующие credentials.

## Синхронизация

Перед синхронизацией проверить дерево и ветки. Изменения фиксировать обычным
commit, получить актуальный `origin/main` и интегрировать без reset/force push.
Расхождение истории и незакоммиченные чужие изменения сохранять и разрешать явно.
После push проверить равенство локального `main` и `origin/main`; состояние
ноутбука и сервера указывать отдельно только после фактической проверки.

Для сервера используется `git bundle`, передаваемый SCP в выделенный cache.
`scripts/sync_server.ps1` не удаляет файлы: существующую копию принимает только
с тем же origin и чистым tracked состоянием, допускает только fast-forward.
При синхронизации проверить равенство локального/GitHub/server SHA и
`vendor_materials.py verify`. Использовать DNS-навык внутри проекта; глобальное
серверное окружение не менять.

## Launchers и артефакты

Используются отдельная `.venv` и `scripts/smoke_b2w.py`, `scripts/train_b2w.py`,
`scripts/benchmark_b2w.py`. B2W-only bootstrap подключает нужные upstream задачи
без зависимостей других роботов. В `vendor/` ничего не устанавливать и не адаптировать.

Manifest сохраняет конфигурации, runtime, source hashes и checkpoints;
launch sources записываются в `params/source`, `progress.json` — после каждого
update. Для результата требуются фактический exit code, проверка артефактов
и отдельная оценка политики. Координаторы завершённых опытов привязаны к
локальным артефактам и не являются командами для чистого clone.
[Каталог scripts](../scripts/README.md), [актуальные jobs](TRAINING_PROGRESS.md).
