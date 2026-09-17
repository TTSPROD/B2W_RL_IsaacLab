# Инфраструктура и синхронизация

## Разделение данных

GitHub: `https://github.com/TTSPROD/B2W_RL_IsaacLab`.
Локальный проект: `C:\Users\ra.suragin\Documents\ChatGPT\B2W_RL_IsaacLab`.
Сервер: `user@10.126.161.7`, новый каталог `/home/user/projects/B2W_RL_IsaacLab`.

Предыдущие B2W проекты не открывать и не использовать. Глобальные драйверы/пакеты и чужие jobs не менять. Runtime, caches, logs и окружение нового проекта держать в его каталоге; исключение — transfer bundles в выделенном `/home/user/.cache/B2W_RL_IsaacLab-sync`. Logs/checkpoints не коммитить. В Git держать маленькие эталонные политики; новые большие checkpoints — в отдельном artifact store с manifest/hash, выбор хранилища позже.

## Обследование 2026-09-17

Локально: Windows11 Enterprise build26200, Intel i9-14900HX (24 cores/32 threads), 31.6GiB RAM, RTX4080 Laptop12282MiB, driver616.92; свободно примерно361GiB на C и1.50TiB на D. Найден `D:\isaacsim51`: Python3.11.9, IsaacSim5.1.0.0, torch2.7.0+cu128, rsl-rl-lib3.1.2. Установленные IsaacLab distributions ссылаются editable-path на другой локальный проект, поэтому это не считается чистым/воспроизводимым runtime нового проекта. Его код и конфиги в новый проект не переносились. Создать отдельное окружение на этапе0.

Визуальная проверка IsaacSim/sim2sim выполняется локально. По запросу пользователя локальный headless training — первый кандидат; сервер пока синхронизированная копия и возможный ресурс после квалификации. См. [решение по вычислениям](COMPUTE_DECISION.md).

Пользователь также располагает отдельным настольным ПК с RTX4070Ti12GB, RAM32GB, Windows11 и Ubuntu26.04: его рассматриваем первым для длительных тренировок. Адрес доступа и CPU пока не предоставлены; к нему не подключались, настройки не меняли. Для Sim5.1 опубликованы Ubuntu22.04/24.04 и Windows11; Ubuntu26.04 не считать проверенной конфигурацией.

Ubuntu22.04.5, kernel5.15.0-191, Xeon6527P (96 logical CPUs), RAM503GiB, disk free~1.6TiB. Четыре Hopper GPU, PCI10de:233f, NVML `NVIDIA Graphics Device`, 95830MiB каждая, driver580.178.04. На момент чтения VRAM занята примерно26/80/26/80GiB. Git, Python3.10, rsync и Docker29.4.1 доступны. Существующие Python environments и проекты намеренно не исследовались.

Isaac runtime не установлен этим bootstrap и не проверен. Python3.10 системы не подходит для выбранного Sim5.1 runtime (нужен отдельный Python3.11). Поддержка RT/Vulkan не подтверждена; см. gate0 плана.

## GitHub без системного DNS

См. [skill](../skills/github-dns-bypass/SKILL.md). Скрипт получает текущие A-record через HTTPS DoH и передаёт IP только текущей Git/curl операции, сохраняя hostname/TLS verification. Не меняет hosts и global Git config. Git Credential Manager на Windows содержит аккаунт TTSPROD; секреты не входят в репозиторий. SSH key для сервера не означает наличие GitHub SSH-доступа.

Windows Git в этой среде поддерживает `schannel`; не задавать `openssl`, не проверив поддержку. Из ограниченной sandbox schannel и SSH credential access могут не работать: это ограничение процесса, не признак неисправного DNS workaround.

## Начальная синхронизация

Для первого переноса используется `git bundle`: содержимое зафиксированного commit передаётся SCP в новый каталог и клонируется локально на сервере. Это не требует GitHub credentials на сервере. После синхронизации проверить equality локального/GitHub/server SHA и `vendor_materials.py verify`.

Повторяемая синхронизация: `scripts/sync_server.ps1`. Скрипт не удаляет файлы; существующую копию принимает только с тем же origin, чистым tracked состоянием и допускает только fast-forward. Незакоммиченные изменения и расхождение истории требуют отдельного решения, а не reset/force.

На сервере возможен read-only `python3 skills/github-dns-bypass/scripts/github_dns.py git fetch origin`; для push потребуются отдельно настроенные credentials. Локальный push через существующий GCM — предпочтительный путь. Не копировать секреты на сервер.

## Размещение навыка

Версионируемая исходная копия: `skills/github-dns-bypass/`. Локальная установка: `C:\Users\ra.suragin\.codex\skills\github-dns-bypass`. На сервере копия доступна внутри проекта и указана в AGENTS.md; глобальное окружение сервера не изменяется.

## План запуска baseline после квалификации

Следующие команды — будущая установка/проверка, сейчас не выполнялись. Нужен отдельный совместимый Isaac Lab runtime и проверка полной зависимости robot_lab; vendor содержит зафиксированный B2W reference, а не установленную среду. На Windows native robot_lab требует отдельной проверки зависимостей, включая pinocchio/cusrl из upstream setup.py; не выполнять слепой install поверх существующего окружения.

```bash
# Inside the dedicated Python 3.11 + Isaac Sim/Lab v2.3.2 environment:
python -m pip install -e vendor/robot_lab/source/robot_lab
python vendor/robot_lab/scripts/tools/list_envs.py
python vendor/robot_lab/scripts/reinforcement_learning/rsl_rl/train.py \
  --task RobotLab-Isaac-Velocity-Flat-Unitree-B2W-v0 --headless --num_envs 1024
```

Перед запуском убедиться, что необходимые asset references разрешаются; другие роботы намеренно исключены из vendor. Никакой training job не должен автоматически занимать все четыре GPU.
