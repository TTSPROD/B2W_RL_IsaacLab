# Windows RTX 4080 Laptop worker

## Актуальная область использования

Инструкции описывают runtime конкретной вычислительной линии; приведенные результаты
остаются квалификацией на дату запуска. Текущая цель policy — низкоуровневое
исполнение внешних команд, ABI57→16. Throughput, headless/GUI smoke и старые
cycle/corridor gates не являются новой приемкой locomotion.
Следующий запуск и бюджет задает [PROJECT_PLAN.md](PROJECT_PLAN.md), распределение
работ — [COMPUTE_DECISION.md](COMPUTE_DECISION.md). Development `locomotion57_v1`
уже выполнен локально для трех серверных checkpoints ([отчет](results/2026-09-25-upstream-locomotion57.md));
это не новая runtime qualification desktop/server. Команды исторических экспериментов не являются текущим
планом запуска или новым разрешением на server/hardware.

18 сентября 2026. Пользователь разрешил подключить ноутбук в локальной сети:
`192.168.1.129`, Windows 11, RTX 4080 Laptop 12 GB, RAM 32 GB.
Проект: `D:\Work\GitProjects\B2W_RL_IsaacLab`, пользователь SSH
`severstal\ra.suragin`. SSH public-key authentication проверена после установки
ключа пользователем. Приватный ключ не передаётся и не входит в проект.

## Фактическое состояние

Квалификация завершена **18 сентября в 15:01:11 МСК**. Ноутбук подключён к
штатному блоку питания; проверка выполнялась с привязкой процесса и его детей
к P-ядрам (логические CPU 0–15). Системные power/driver настройки не менялись.

| Проверка | Результат |
|---|---|
| Vendor / package RECORD | Проверены, exit 0 |
| GPU physics | 16 сред, 10 000 шагов, exit 0 |
| PPO / optimizer resume | 12 + 12 updates, обе части validated / exit 0 |
| Fixed P-core benchmark | 4096 сред × rollout 24, 210 updates, exit 0 |
| Измеряемое окно | 200 updates после 10 прогревочных |
| PPO collection + learning | 2,586 s/update; 38 007,8 transitions/s |
| По времени TensorBoard events | 37 461,5 transitions/s, без startup |
| Ресурсы | Peak VRAM 4386 MiB, запас ≥64,29%, максимум 63 °C |
| Телеметрия | 117 samples, 0 errors |

[Датированный результат](results/2026-09-18-laptop-qualification.json).
Первый benchmark включал смену affinity на 76 updates и считается диагностическим;
его смешанное среднее не используется как результат фиксированного режима.
Короткое сравнение до/после дало примерно 4,3 → 2,8 s/update; окончательное
значение 2,586 получено в отдельном запуске seed 992 с фиксированной affinity.

**Квалификация не назначает ноутбуку основное обучение.** Серия 49/50/51
завершена целиком на desktop. Текущие назначения и результаты ведутся в
[TRAINING_PROGRESS](TRAINING_PROGRESS.md), дальнейшие решения — в
[PROJECT_PLAN](PROJECT_PLAN.md). Качество ноутбучной policy не оценивалось;
benchmark не является принятой политикой.

## Изоляция и воспроизводимость

- Проверены чистый исходный checkout и общий baseline commit
  `097706b624b1dd2df1ffa68bea7a4aaf9f86432c`.
- Поверх него переданы актуальные на момент квалификации scripts/docs/requirements с покомпонентными
  SHA256 и резервными копиями заменённых файлов в `.cache/laptop-sync/before`.
  Исходники работавших desktop trainers при передаче не менялись. `vendor/` не переписывается.
- Ноутбук получает собственные `.cache/python`, `.venv`, `.runtime/IsaacLab`
  внутри этого проекта. Предыдущие проекты и их runtime не используются.
- Python 3.11.13, Isaac Sim 5.1.0, Isaac Lab v2.3.2 commit
  `37ddf626871758333d6ed89cf64ad702aef127d0`, torch 2.7.0+cu128, RSL-RL 3.1.2;
  все версии зависимостей закреплены desktop lock-файлом. Применяется уже
  документированная packaging-поправка starlette 0.45.3 вне `vendor/`.
- Недоступная запись Codex в PATH ноутбука обходится минимальным PATH только
  процесса SSH. Системные настройки и драйверы не меняются.
- На ноутбуке LongPathsEnabled=0. Для установки использован расширенный
  путь `\\?\D:\Work\GitProjects\B2W_RL_IsaacLab\.venv\Scripts\python.exe`,
  [поддерживаемый Windows](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation).
  Системный реестр не менялся. Расширенный путь применяется только к трём
  пакетам `isaacsim-extscache-*`; остальные зависимости устанавливаются
  обычным Python через `.cache/laptop-sync/setup_cached.ps1`. Попытка полной
  установки через расширенный путь не поддержала относительные paths CLI;
  восстановление pypng и файлов кэша затем проверено по RECORD.
- Из-за тайм-аута download.pytorch.org точные wheels torch/torchvision
  перенесены из кэша проекта с проверкой SHA256. TLS не отключается.

Первый GPU smoke остановлен до первого шага физики из-за недоступного
реестра NVIDIA; попытка сохранена как `laptop_seed51_20260918_attempt1_registry`.
На ноутбук перенесены 3346 файлов только из кэша этого проекта: URDF importer
`2.4.31+107.3.3.wx64.r.cp311`, `omni.kit.pip_archive-0.0.0+69cbf6ad.wx64.cp311`
и готовый USD B2W. Архив и каждый файл проверены по SHA256; исходники и MDP
не менялись. Повторная квалификация использует тот же runtime и asset cache,
что и desktop. Общий launcher `isaacsim.exe` объявлен несколькими пакетами;
его хеш проверен по RECORD фактического владельца с тем же entry point.

## Инструменты квалификации и исторические варианты передачи

`scripts/laptop_seed51_worker.py qualify` выполняет первичную квалификацию.
`scripts/qualify_laptop_pcores.py` повторяет 4096-env benchmark с фиксированными
P-ядрами через `laptop_pcore_runtime.py`. Статус worker по итогам квалификации —
`qualified_pending_tail_delegation`, это технический результат, а не назначение.
Job на ноутбуке: `logs/workers/laptop_seed51_20260918/job.json`.

Подготовлены, но **не выполнялись end-to-end** два варианта:

- `run_staged_laptop_parallel.py`: целиком fresh seed 51 на ноутбуке.
- `run_staged_tail_parallel.py` + `laptop_staged_tail_worker.py`: последние
  1500 updates seed 50 на ноутбуке, seed 51 раньше стартует на ПК.

Передача не выполнена. Второй вариант требует принятия очереди до окончания
первых сегментов 49/50; эта граница уже пройдена, оба continuation запущены
исходным координатором и завершены. Эти launchers относятся к прошедшей
серии; для нового назначения потребуется отдельная проверка условий.
Unit tests проверяют защитные условия, но не заменяют фактическую передачу.

Механизм проверяет cwd/commands/parent, удерживает Win32 process handles для
фактических exit codes, проверяет source/assignment/checkpoint SHA256 и
исключает повторное назначение seed. ZIP результатов допускает только
назначенные пути без перезаписи; CPU export и все evaluations предусмотрены
на исходном desktop. Ни один будущий перенос не меняет бюджет и не разрешает Rough.

Windows OpenSSH завершает дочерние процессы при закрытии SSH session.
Длительный worker требует открытого скрытого SSH client с keepalive на всё
время работы. Remote Start-Process с немедленным выходом из SSH для этого
не подходит. При обрыве не назначать seed заново без проверки фактического job.

Исторический завершённый desktop job:
`logs/qualification_runs/flat_staged_seeds49_51_20260918/job.json`.
История setup/кэшей остаётся в `.cache/laptop-sync` и `logs/setup` соответствующей
машины; runtime и checkpoints не входят в Git.
