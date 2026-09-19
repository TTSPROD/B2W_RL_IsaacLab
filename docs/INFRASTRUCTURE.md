# Инфраструктура и синхронизация

Проверенное окружение и границы проекта — ниже. Текущая очередь и результаты
обучения ведутся в [TRAINING_PROGRESS](TRAINING_PROGRESS.md), следующие решения
и gates — в [PROJECT_PLAN](PROJECT_PLAN.md). Датированные протоколы и JSON
сохраняют историю; промежуточные PID и статусы не являются текущими.

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

19 сентября отдельно запущен GUI Flat replay: Isaac Sim5.1, D3D12,1 B2W,
квалифицированный seed54, Xbox XInput. Viewport и live parity проверены;
[инструкция/ограничения](GAMEPAD_PLAY.md), [снимок проверки](results/2026-09-19-gamepad-gui.json).
Vulkan GUI native-crash обойдён process-local D3D12; headless runtime не менялся.
RTX sensor extensions не входят в успешный GUI gate. Viewer не совмещать
с benchmark/training на той же GPU.

Техническая квалификация не означает приёмку политики. Rough, Stairs,
GUI/rendering и sim2sim требуют отдельных проверок. Ubuntu 26.04 на ПК не
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
