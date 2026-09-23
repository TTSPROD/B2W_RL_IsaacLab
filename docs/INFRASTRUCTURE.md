# Инфраструктура и синхронизация

**Актуально на 23 сентября 2026,18:41 МСК:** серверный 4-GPU upstream завершил 20000 updates; новый inverse57 от upstream10000 запущен автономно с лимитом 15 часов. Локальная RTX4080 Laptop используется для оценки/выгрузки; локальные rough/stair эксперименты документированы отдельно. ABI57→16 сохраняется, stair-v4 отложена. Параллельная настольная RTX4070Ti уже имеет отдельную Flat-квалификацию; см. DESKTOP_SETUP.md. [Статус](TRAINING_STATUS.md), [активный серверный план](results/2026-09-23-inverse57-overnight-plan.md).

## Завершённый upstream и активный inverse57

Upstream завершён 23 сентября 17:36:05 МСК, ExitCode0, OOMKilled=false; model19999 соответствует 20000 updates. Reward256.58, curriculum5.9018. Новый inverse57 на снимке 18:41 МСК обучается автономно, его итог неизвестен. Dedicated paths: `/home/user/B2W_RL_IsaacLab_Server/logs/inverse57_4gpu_20260923` и соответствующий `tmp/inverse57_4gpu_20260923`. Общий дедлайн 24 сентября 09:18:50 МСК. Старые ресурсные снимки ниже сохраняются как история.

По прямому указанию пользователя от 23 сентября checkpoints публикуются в `policies/experimental/` как **не принятые**: это исключение из исходного запрета ниже хранить новые веса в Git. Кэши, среды, полные training logs и изменяемая доставка не коммитятся; компактные проверенные evidence находятся в `docs/results/evidence/`.

## Разделение данных

GitHub: `https://github.com/TTSPROD/B2W_RL_IsaacLab`.
Локальный проект: `C:\Users\ra.suragin\Documents\ChatGPT\B2W_RL_IsaacLab`.
Сервер: `user@10.126.161.7`, новый каталог `/home/user/projects/B2W_RL_IsaacLab`.

Предыдущие B2W проекты не открывать и не использовать. Глобальные драйверы/пакеты и чужие jobs не менять. Runtime, caches, logs и окружение нового проекта держать в его каталоге; исключение — transfer bundles в выделенном `/home/user/.cache/B2W_RL_IsaacLab-sync`. Logs/checkpoints не коммитить. В Git держать маленькие эталонные политики; новые большие checkpoints — в отдельном artifact store с manifest/hash, выбор хранилища позже.

## Обследование 2026-09-17

Локально: Windows11 Enterprise build26200, Intel i9-14900HX (24 cores/32 threads), 31.6GiB RAM, RTX4080 Laptop12282MiB, driver616.92; свободно примерно 361GiB на C и 1.50TiB на D. Найден `D:\isaacsim51`: Python3.11.9, IsaacSim5.1.0.0, torch2.7.0+cu128, rsl-rl-lib3.1.2. Установленные IsaacLab distributions ссылаются editable-path на другой локальный проект, поэтому это не считается чистым/воспроизводимым runtime нового проекта. Его код и конфиги в новый проект не переносились. Создать отдельное окружение на этапе 0.

**Обновление 2026-09-21:** в этом проекте создано отдельное `.venv` и локальная копия Isaac Lab v2.3.2; бинарные пакеты Isaac Sim по-прежнему берутся из `D:\isaacsim51`, поэтому runtime остаётся гибридным. На RTX 4080 Laptop пройдены headless qualification и короткое обучение rough политик. Конкретные версии, hashes, конфигурации и результаты: [локальный отчёт](results/2026-09-21-local-4080.md) и [runtime lock](results/2026-09-21-local-4080-runtime.json). Длительные задания на сервере не запускались.

**Масштабирование 2026-09-22:** на локальной RTX 4080 Laptop обучающий smoke с 4096 средами прошёл; полный stair run 4096 × 25 PPO-обновлений выполнил 2 457 600 переходов за 74.35 с. Наблюдаемое `nvidia-smi` использование VRAM было около 6.9 из 12.3 GiB; это снимок, не гарантированный peak. При тех же переходах run 1024 × 100 занял 160.55 с. Checkpoint 4096 × 25 не прошёл stair gate, поэтому результат подтверждает работоспособность и throughput конфигурации, а не качество политики. [Отчёт](results/2026-09-22-4096-env-scaling.md).

Визуальная проверка IsaacSim/sim2sim выполняется локально. После последующей квалификации сервер используется для разрешённого длинного upstream headless baseline; это не означает поддержку GUI/RTX rendering или произвольных Isaac Sim задач. См. [решение по вычислениям](COMPUTE_DECISION.md).

Пользователь также располагает отдельным настольным ПК с RTX4070Ti12GB, RAM32GB, Windows11 и Ubuntu26.04: его рассматриваем первым для длительных тренировок. Адрес доступа и CPU пока не предоставлены; к нему не подключались, настройки не меняли. Для Sim5.1 опубликованы Ubuntu22.04/24.04 и Windows11; Ubuntu26.04 не считать проверенной конфигурацией.

Ubuntu22.04.5, kernel5.15.0-191, Xeon6527P (96 logical CPUs), RAM503GiB, disk free~1.6TiB. Четыре Hopper GPU, PCI10de:233f, NVML `NVIDIA Graphics Device`, 95830MiB каждая, driver580.178.04. На момент чтения VRAM занята примерно 26/80/26/80GiB. Git, Python3.10, rsync и Docker29.4.1 доступны. Существующие Python environments и проекты намеренно не исследовались.

На момент первичного обследования Isaac runtime не был установлен и проверен. **Обновление 22–23 сентября:** для изолированного `/home/user/B2W_RL_IsaacLab_Server` подготовлен контейнерный Isaac Sim 5.1/Python 3.11 runtime с внешним compatibility adapter; vendor остаётся неизменным. Headless upstream B2W прошёл 1/2/4-GPU smoke. Разрешённое продолжение `upstream_b2w_20000_4gpu_20260922` возобновило только собственный `model_100.pt`; снимок 23 сентября 11:38 МСК — iteration 14950/20000, контейнер работает, последний checkpoint `model_14900.pt`. Завершение и качество политики ещё не проверены. Поддержка RT/Vulkan/GUI не подтверждена; чужие workloads не изменялись.

## GitHub без системного DNS

На настольном ПК с RTX4070Ti GitHub доступен штатно (подтверждено пользователем). Там использовать обычные `git clone/fetch/push`; устанавливать или вызывать DNS-bypass skill не требуется. Ниже описан только обход для машин, где DNS действительно не работает (исходный ноутбук/сервер).

См. [skill](../skills/github-dns-bypass/SKILL.md). Скрипт получает текущие A-record через HTTPS DoH и передаёт IP только текущей Git/curl операции, сохраняя hostname/TLS verification. Не меняет hosts и global Git config. Git Credential Manager на Windows содержит аккаунт TTSPROD; секреты не входят в репозиторий. SSH key для сервера не означает наличие GitHub SSH-доступа.

Windows Git в этой среде поддерживает `schannel`; не задавать `openssl`, не проверив поддержку. Из ограниченной sandbox schannel и SSH credential access могут не работать: это ограничение процесса, не признак неисправного DNS workaround.

## Начальная синхронизация

Для первого переноса используется `git bundle`: содержимое зафиксированного commit передаётся SCP в новый каталог и клонируется локально на сервере. Это не требует GitHub credentials на сервере. После синхронизации проверить equality локального/GitHub/server SHA и `vendor_materials.py verify`.

Повторяемая синхронизация: `scripts/sync_server.ps1`. Скрипт не удаляет файлы; существующую копию принимает только с тем же origin, чистым tracked состоянием и допускает только fast-forward. Незакоммиченные изменения и расхождение истории требуют отдельного решения, а не reset/force.

Git2.34.1 на сервере игнорирует `http.curloptResolve`. Для него использовать `python3 skills/github-dns-bypass/scripts/github_dns.py --git-transport proxy git fetch origin`: временный loopback CONNECT tunnel соединяется с полученным через DoH адресом, а Git сохраняет TLS-проверку имени GitHub. На новом Windows Git работает стандартный transport `resolve`. Для push с сервера потребуются отдельно настроенные credentials; локальный push через существующий GCM — предпочтительный путь. Не копировать секреты на сервер.

## Размещение навыка

Версионируемая исходная копия: `skills/github-dns-bypass/`. Локальная установка: `C:\Users\ra.suragin\.codex\skills\github-dns-bypass`. На сервере копия доступна внутри проекта и указана в AGENTS.md; глобальное окружение сервера не изменяется.

## Исходный план запуска baseline после квалификации

Следующие команды сохранены как исходная схема установки, а не журнал фактически выполненных локальных прогонов. Фактические прогоны использовали проектный launcher `scripts/run_local.ps1` и гибридный runtime, описанный в отчёте выше. Для полностью независимой установки ещё нужна проверка полной зависимости robot_lab; vendor содержит зафиксированный B2W reference. На Windows native robot_lab требует отдельной проверки зависимостей, включая pinocchio/cusrl из upstream setup.py; не выполнять слепой install поверх существующего окружения.

```bash
# Inside the dedicated Python 3.11 + Isaac Sim/Lab v2.3.2 environment:
python -m pip install -e vendor/robot_lab/source/robot_lab
python vendor/robot_lab/scripts/tools/list_envs.py
python vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py \
  --task RobotLab-Isaac-Velocity-Flat-Unitree-B2W-v0 --headless --num_envs 1024
```

Перед запуском убедиться, что необходимые asset references разрешаются; другие роботы намеренно исключены из vendor. Никакой training job не должен автоматически занимать все четыре GPU.
