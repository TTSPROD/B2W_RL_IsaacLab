# Инфраструктура и синхронизация

## Разделение данных

| Назначение | Путь |
|---|---|
| GitHub | `https://github.com/TTSPROD/B2W_RL_IsaacLab` |
| Текущий настольный ПК | `D:\Work\GitProjects\B2W_RL_IsaacLab` |
| Исходный ноутбук | `C:\Users\ra.suragin\Documents\ChatGPT\B2W_RL_IsaacLab` |
| Выделенная серверная копия | `user@10.126.161.7:/home/user/projects/B2W_RL_IsaacLab` |
| Только transfer bundles | `/home/user/.cache/B2W_RL_IsaacLab-sync` |

Предыдущие B2W проекты не открывать и не использовать. Глобальные драйверы и пакеты, чужие jobs не менять. Runtime, caches, logs и окружение нового проекта держать в его каталоге; серверные записи разрешены только в двух выделенных путях выше.

В Git сохраняются код, документация, runtime lock и vendor manifest с hashes/licenses. Logs, новые training checkpoints, `.venv`, `.runtime` и caches не коммитятся. Маленькие исходные эталонные политики остаются частью зафиксированных vendor snapshots. Новым checkpoints нужен отдельный artifact store с manifest/SHA256; постоянное хранилище ещё не выбрано. Синхронизация Git сама по себе не переносит локальный runtime или результаты обучения.

## Текущая вычислительная площадка — 17 сентября 2026

Настольный ПК: Windows 11 Pro build 26200, AMD Ryzen 9 5900X (12 ядер / 24 потока), 31.9 GiB RAM, RTX 4070 Ti 12 282 MiB, driver 616.92. До установки на D было свободно около 528 GiB; это исторический замер, не текущее свободное место. Отдельное окружение проекта: Python 3.11.13, Isaac Sim 5.1.0, Isaac Lab v2.3.2, RSL-RL 3.1.2. Версии и воспроизводимая установка — в [DESKTOP_SETUP.md](DESKTOP_SETUP.md).

**Локальный headless Flat квалифицирован для зафиксированного runtime.** Пройдены Compatibility Checker, 10 000 шагов GPU PhysX/Fabric, PPO/resume и sweep 256–2048. Первый seed 42 завершил 5 000 PPO updates; sustained-профиль покрывает 9 624 s без telemetry errors. Затем benchmark двух одновременных запусков по 4096 сред дал 63 907.87 transitions/s суммарно, +67.32% к короткому наблюдению 2×2048, peak VRAM 9 583 MiB и минимальный запас 21.98%.

На снимке **17 сентября, 13:56 МСК**, seeds 43/44 продолжаются параллельно на одной GPU по 4096 сред; длительная проверка этого режима ещё не завершена. Текущий координатор — `scripts/benchmark_parallel4096.py`, статус — `logs/benchmarks/dual4096_20260917/job.json`. Скрипты координаторов привязаны к выполненным запускам и их локальным артефактам; они не являются командами запуска после чистого clone. [Сценарии скриптов](../scripts/README.md).

Технический результат не равен качеству политики: seed 42 получил 96/100 эпизодов без падения или неразрешённого контакта при пороге ≥99%, reference — 100/100. У seeds 43/44 были resume и смена PPO batch; их нельзя представлять как строго одинаковую с seed 42 серию из трёх seeds. [Протоколы и ограничения](TRAINING_PROGRESS.md), [решение по вычислениям](COMPUTE_DECISION.md).

Rough, Stairs, GUI/rendering и sim2sim этим результатом не квалифицированы. Ubuntu 26.04 на настольном ПК не использовалась и не входит в опубликованную матрицу Isaac Sim 5.1. Старые проекты и сервер в локальных тренировках не используются.

## Историческое обследование других машин

**Исходный ноутбук:** Windows 11 Enterprise build 26200, Intel i9-14900HX (24 ядра / 32 потока), 31.6 GiB RAM, RTX 4080 Laptop 12 282 MiB, driver 616.92. При обследовании свободно примерно 361 GiB на C и 1.50 TiB на D. Найденный `D:\isaacsim51` содержал Python 3.11.9, Isaac Sim 5.1.0.0, torch 2.7.0+cu128 и RSL-RL 3.1.2. Установленный Isaac Lab ссылался через editable-path на другой проект; этот runtime и код не использовались в новом B2W. Для работы на ноутбуке нужен отдельный runtime нового проекта.

**Сервер:** Ubuntu 22.04.5, kernel 5.15.0-191, Xeon 6527P (96 logical CPUs), RAM 503 GiB, около 1.6 TiB свободного диска при обследовании. Четыре Hopper GPU, PCI `10de:233f`, NVML `NVIDIA Graphics Device`, по 95 830 MiB, driver 580.178.04. В момент обследования VRAM была занята примерно на 26/80/26/80 GiB; текущая занятость не проверялась. Git, Python 3.10, rsync и Docker 29.4.1 доступны. Существующие environments и проекты не исследовались.

Серверный Isaac runtime этим проектом не установлен и не квалифицирован. Для Sim 5.1 требуется отдельный Python 3.11. RT/Vulkan capabilities не подтверждены; объём VRAM и поддержка CUDA не заменяют gate 0 плана. Перед любым серверным training нужен отдельный hardware/runtime smoke и проверка доступного ресурса. Автоматически занимать четыре GPU запрещено.

## GitHub и DNS

На настольном ПК GitHub доступен штатно: использовать обычные `git clone/fetch/push`. DNS workaround применять только после подтверждённой ошибки DNS, согласно [github-dns-bypass](../skills/github-dns-bypass/SKILL.md).

Навык получает текущие A-record через HTTPS DoH и передаёт IP только текущей Git/curl операции, сохраняя hostname и TLS verification. Он не меняет hosts или global Git config. Существующая авторизация сохраняется; секреты не входят в репозиторий и не копируются на сервер. SSH key сервера не означает GitHub SSH-доступ.

Windows Git в проверенной среде поддерживает `schannel`; не задавать `openssl`, не проверив поддержку. Ограниченная sandbox может блокировать schannel/SSH credential access: это ограничение процесса, а не подтверждение неисправного DNS.

Git 2.34.1 на обследованном сервере игнорирует `http.curloptResolve`. Только при неработающем DNS там используется `python3 skills/github-dns-bypass/scripts/github_dns.py --git-transport proxy git fetch origin`: временный loopback CONNECT tunnel соединяется с DoH-адресом, TLS проверяет имя GitHub. На новом Windows Git используется transport `resolve`. Предпочтительный push — локально через существующие credentials.

## Синхронизация Git и серверной копии

Перед синхронизацией проверить рабочее дерево и ветки. Изменения фиксировать обычным commit, получить актуальный `origin/main` и интегрировать без reset/force push. Расхождение истории и незакоммиченные чужие изменения сохранять и разрешать явно. После push проверить совпадение локального `main` и `origin/main`; состояние серверной копии указывать отдельно только после фактической проверки.

Для серверного переноса используется `git bundle`: содержимое commit передаётся SCP в выделенный cache и импортируется в новый проект. Скрипт `scripts/sync_server.ps1` не удаляет файлы; существующую копию принимает только с тем же origin, чистым tracked состоянием и допускает только fast-forward. Наличие локального/GitHub commit не означает автоматического обновления сервера. При выполнении серверной синхронизации проверить равенство локального/GitHub/server SHA и `vendor_materials.py verify`.

Версионируемая копия DNS-навыка находится в `skills/github-dns-bypass/`; на сервере используется эта копия внутри проекта. Историческая локальная установка на исходном ноутбуке: `C:\Users\ra.suragin\.codex\skills\github-dns-bypass`. Глобальное серверное окружение не меняется.

## Локальные launchers и артефакты

Используются отдельная `.venv` и `scripts/smoke_b2w.py`, `scripts/train_b2w.py`, `scripts/benchmark_b2w.py`. B2W-only bootstrap подключает нужные upstream задачи без широкого discovery и зависимостей других роботов. В `vendor/` ничего не устанавливать и не адаптировать.

Manifest сохраняет конфигурации, runtime, source hashes и checkpoints; launch sources записываются в `params/source`, `progress.json` — после каждого update. Для результата требуются также фактический exit code и проверка артефактов; наличие checkpoint не доказывает успешное завершение или качество управления. Текущие координаторы и логи перечислены в [TRAINING_PROGRESS.md](TRAINING_PROGRESS.md).
