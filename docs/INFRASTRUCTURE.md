# Инфраструктура B2W

Baseline runtime: Isaac Lab 2.3.2, Isaac Sim 5.1, Python 3.11, RSL-RL 3.1.2.
Исходники robot_lab и остальных upstream компонентов закреплены в `vendor/manifest.json`.
Точный [состав vendor](VENDOR_INVENTORY.md) включает докачанные SDK2/MuJoCo bridge
и ROS2 packages. Их Linux build и DDS qualification пока не выполнены.
Текущий локальный MuJoCo viewer исполняет policy внутри процесса и не проверяет
SDK2 transport. Будущий C++/ROS2 runtime собирается отдельно от vendor и Windows
окружения; выбор MuJoCo engine version фиксируется до сравнения результатов.

## Локальное окружение

Проект: `C:\Users\ra.suragin\Documents\ChatGPT\B2W_RL_IsaacLab`.
Локальный launcher `scripts/run_local.ps1` использует `.venv`, `.runtime/IsaacLab`
и Sim packages из `D:\isaacsim51`; путь можно задать через `B2W_ISAAC_SIM_ENV`.
Системный Python и `.venv` без launcher могут не видеть Torch/Isaac dependencies.
Конфигурация Windows runtime и lock-файлы находятся в `requirements/`.
`scripts/setup_desktop.ps1` — отдельный installer проектного desktop окружения;
его не нужно запускать при уже работающем runtime ноутбука.

Линии RTX4080 Laptop, RTX4070Ti desktop и server сохраняют отдельные runtime
характеристики. Текущая проверка 19999 выполнена на RTX4080 Laptop, Isaac headless.

```powershell
python scripts/vendor_materials.py verify
& .\scripts\run_local.ps1 -m unittest discover -s tests -q
& .\scripts\run_local.ps1 scripts/verify_project.py
```

## Evidence и воспроизводимость

Постоянные данные последней проверки: `docs/results/evidence/operating57_19999_20260925/`.
Raw JSON и NPZ перенесены из logs без изменения байтов. Пути внутри raw JSON
фиксируют место исходного запуска; актуальное расположение задаёт manifest рядом.
Captured protocol/source hashes относятся к выполненному запуску, current source
hashes — к коду после рефакторинга. Сравнение по сохранённым traces проверяет
неизменность всех 1152 оценок без повторной симуляции.

Перестроение таблиц и рисунка:

```powershell
& .\scripts\run_local.ps1 scripts/summarize_operating57.py
& .\scripts\run_local.ps1 scripts/report_operating57.py
```

Новый запуск screen записывается в отдельный путь и не заменяет retained evidence:

```powershell
& .\scripts\run_local.ps1 scripts/eval_operating57_isaac.py --terrain flat --output logs/operating57_new/isaac_flat.json
```

Live logs/outputs/caches игнорируются Git. Единственный текущий report и его
проверяемые raw данные хранятся в `docs/results/`; веса — в `policies/server/`.

## Сервер

- Рабочий каталог: `/home/user/projects/B2W_RL_IsaacLab`.
- Transfer cache: `/home/user/.cache/B2W_RL_IsaacLab-sync`.
- Завершённые разрешённые runs: `/home/user/B2W_RL_IsaacLab_Server`.

`scripts/sync_server.ps1` переносит committed HEAD через Git bundle и fast-forward.
Чистка выполнена локально; удалённые jobs и файлы этим действием не изменяются.
Новые server training jobs требуют отдельного явного решения.
При сбое GitHub DNS использовать [проектный skill](../skills/github-dns-bypass/SKILL.md).
