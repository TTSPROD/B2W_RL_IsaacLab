# Инфраструктура и синхронизация

**Снимок 18 сентября, 15:12:52 МСК:** seeds 49/50 завершили первые 2500 updates
с exit 0 и проверкой артефактов. Выполняется вторая часть: **2596/4000** и
**2597/4000** соответственно; seed 51 ещё не запущен, evaluations — 0/8.
Исходники активной очереди совпадают с frozen SHA256. [Датированный снимок](results/2026-09-18-staged-qualification-status.json).
Ноутбук прошёл техническую [квалификацию](LAPTOP_WORKER.md), но обучение ему
не назначено. По последнему уточнению пользователя очередь остаётся на ПК:
49/50 параллельно до 4000, затем 51 отдельно. [Сервер проверен](SERVER_PERFORMANCE.md),
к Isaac Lab не допущен. Качество seeds 49/50/51 пока не оценено.
Git push обновляет origin, но не синхронизирует автоматически ноутбук или сервер;
их checkout/runtime и артефакты учитываются отдельно.

**Проверка сервера 18 сентября, 15:07 МСК:** доступ через ноутбук подтверждён.
4 Hopper GPU по 95 830 MiB; свободно 14–67 GiB на карту. Короткий GPU0 D2D-тест:
1,752 TB/s суммарного чтения+записи; SGEMM остановлен по timeout при инициализации
cuBLAS 11.5. Проектного Isaac runtime и Vulkan loader нет; server gate не пройден.
[Измерения и ограничения](SERVER_PERFORMANCE.md). По уточнению пользователя
действующая очередь обучения оставлена прежней.

**История запуска 18 сентября, 12:59 МСК:** пользователь разрешил продолжить обучение.
Зарегистрировано [повторение staged](STAGED_QUALIFICATION.md): fresh seeds 49/50/51,
4000 updates на каждом (2500 upstream + 1500 mix), одинаковый плановый restart.
Seeds 49/50 параллельно по 4096 сред, затем 51 отдельно; VRAM reserve 5%.
Новые hold-outs nominal 20261201 и bounded_v1 20261202. Job:
`logs/qualification_runs/flat_staged_seeds49_51_20260918/job.json`.
**Запуск подтверждён:** seeds 49/50 выполняют PPO updates, оба с нуля на 4096
средах. [Снимок запуска](results/2026-09-18-staged-qualification-launch.json)
фиксирует PID, счётчики, source/protocol hashes и ресурсы. 51 тест прошёл.
Качество новых seeds пока не оценено. Ниже — история предыдущего эксперимента.


**Итог 18 сентября, 12:49 МСК:** эксперимент seed 48 завершён. Staged прошёл
nominal и bounded_v1: по 100/100 без отказов и по 100/100 tracking; оба сценарных
gate пройдены. Constant: 99/100 и 92/100 без отказов; оба gate не пройдены.
Обе группы завершили 4000 updates, checkpoints/optimizer/TensorBoard и export
проверены. Последняя оценка прервалась вместе с координатором по неизвестной
причине; повторена на том же export, cases и physical profile с exit 0 и проверкой
digest. Обучение не перезапускалось. [Полный итог](results/2026-09-18-flat-schedule-final.json).
Выбран staged для будущего повторения на трёх новых независимых training seeds;
это пока один development seed, общий Flat release gate не закрыт. Очередь завершена.


**Обновление 18 сентября, параллельное ускорение:** constant передан без restart
(trainer PID 23476), staged запущен рядом (PID 13688), по 4096 сред каждый.
[Подтверждённый снимок передачи и скорости](results/2026-09-18-flat-schedule-parallel-launch.json).
Новый supervisor PID 11912; текущий job:
`logs/ablations/flat_schedule_parallel_seed48_20260918/job.json`.
Бюджет 4000 updates на группу и restart после 2500 сохранены; evaluations после
обучения последовательные. Порог свободной VRAM 5%. Первоначальные записи ниже
сохранены как история. Старый coordinator остановлен, его trainer продолжает работу.


**Новый этап 18 сентября:** по запросу пользователя подготовлена последовательная
[абляция расписания команд seed 48](FLAT_SCHEDULE_ABLATION.md), constant против
staged, по 4000 updates на 4096 средах, одинаковый restart после 2500.
Диагностика предыдущей серии сохранена в
[JSON](results/2026-09-18-flat-diagnosis.json). Запуск включает smoke/resume,
контроль VRAM (5%), проверку артефактов и новые nominal/bounded evaluations.
Фактический статус: `logs/ablations/flat_schedule_seed48_20260918/job.json`.
**Подтверждено 09:11:11 МСК:** четыре smoke train/resume сегмента прошли
с exit 0; основное обучение constant запущено на 4096 средах, seed 48.
В снимке 21/2500 updates первого сегмента; supervisor PID 18884,
trainer PID 23476. [Снимок запуска](results/2026-09-18-flat-schedule-launch.json).
Качество новой политики ещё не оценено.


**Итог на 18 сентября 2026, 00:11 МСК:** локальная Flat-серия seeds 45/46/47
завершена; все три checkpoints/exports проверены, но nominal/bounded оценки
дали 91/91, 94/90 и 92/89 из 100 при пороге ≥99. Reference — 100/100 на обоих
профилях. Flat gate открыт; Rough не запускался. Последняя параллельная часть
работала с запрошенным порогом свободной VRAM 5%, фактический минимум 20,40%,
telemetry errors 0. Полный job:
`logs/qualification_runs/flat_headroom5_20260917/job.json`;
[итоговый снимок](results/2026-09-18-flat-qualification-final.json) и
[протокол восстановления](FLAT_RECOVERY.md). Ниже — исторические записи.

**Обновление 21:32 МСК:** по запросу пользователя seeds45/46 снова работают
параллельно. Seed45 передан без перезапуска; текущий статус —
`logs/qualification_runs/flat_three_seed_parallel_recovery_20260917/job.json`.
Бюджеты, restartboundary1600 и порог VRAM15% прежние; [подробности](FLAT_RECOVERY.md).

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

Продолжения seeds 43/44 и последующая абляция команд завершены. У последней:
289 resource samples, telemetry errors 0, peak VRAM 9518 MiB, минимальный запас
22,50%, максимум 66 °C. Режим 2×4096 подтверждён несколькими завершёнными runs.

Абляция yaw-награды завершена 17 сентября в 18:17:25 МСК: по 1000 updates,
обе группы и все восемь evaluations exit 0. Пара работала 2951,7 s,
582 samples без telemetry errors, peak GPU 9632 MiB, запас ≥21,58%, максимум 63 °C.
[Итоги](YAW_REWARD_ABLATION.md): обе группы прошли single-policy thresholds;
по заранее заданному правилу для повторения выбран weight 1,5 / mix 0,25.

После остановки 21:00:59 МСК по запасу VRAM 14,42% использовался координатор —
scripts/run_flat_recovery.py; статус:
logs/qualification_runs/flat_three_seed_recovery_20260917/job.json.
Запуск 21:26:10 МСК, по одному4096-env trainer; [протокол](FLAT_RECOVERY.md).

Исходный координатор — scripts/run_flat_qualification.py, его историческое состояние —
logs/qualification_runs/flat_three_seed_20260917/job.json; оценки —
logs/qualification/flat_three_seed_20260917/. Очередь запущена в 19:31:30 МСК, supervisor PID 11652. [Протокол](FLAT_QUALIFICATION.md):
reference regression, bounded physical diagnostics и fresh smoke уже пройдены.
С 19:36:09 до 21:00:59 МСК обучались fresh seeds 45/46 параллельно; seed 47
к моменту остановки не запускался.
Каждый: 4096 сред × 2500 updates. [Датированный статус](results/2026-09-17-flat-qualification-status.json).
Координаторы используют конкретные локальные артефакты и не являются командами
после чистого clone. Source snapshots, protocol и hashes сохраняются при запуске.

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
