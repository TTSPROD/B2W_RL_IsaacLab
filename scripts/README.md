# Инструменты B2W

## Разделение параллельных линий

Ниже исторический каталог настольной линии. После объединения Git совпадавшие entrypoints этой линии называются `train_b2w_desktop.py`, `smoke_b2w_desktop.py`, `play_b2w_gamepad_desktop.py`; её callers и tests обновлены. Старые evidence сохраняют исходные имена и hashes на дату запуска.

Ноутбук использует `run_local.ps1`, `train_b2w.py`, `smoke_b2w.py`, `train_stair_b2w.py`, `eval_stair_suite.py`, `play_b2w_gamepad.py`. Серверный inverse57 — отдельный `server_inverse57/`. Эти runtime/CLI нельзя подменять друг другом. [Общий статус](../docs/TRAINING_STATUS.md).


Запускать из корня проекта в его отдельном runtime. Для Windows команды настройки
и необходимые environment settings указаны в [DESKTOP_SETUP.md](../docs/DESKTOP_SETUP.md).
Ни один перечисленный launcher не управляет реальным роботом. Vendor неизменяем.

## Завершённый Rough wide corridor experiment

65/66 завершились18:28МСК на150 с quality stop; продолжение350 не выполнялось.
[Следующая диагностика двух ширин](../docs/ROUGH_NEXT_DIAGNOSTICS.md) пока
не реализована и не запускалась. Приведённые ниже команды сохраняют provenance
проведённого опыта; существующие output directories повторно не запускаются.

[Протокол](../docs/ROUGH_WIDE_CORRIDOR.md): `run_rough_wide_preflight.py --attempt 1`,
затем `run_rough_wide_training.py --preflight docs/results/rough_wide_preflight_20260920_1.json`.
Opt-in `--rough_wide_corridor` требует `--rough_wheel_corridor`: только учебная
полуширина y0,9→1,8м, terminal и curriculum failure сохраняются. Strict evaluator
остаётся±0,9м. Seeds65/66 отFlat54,50+100+200,single4096; полный блок оценок150,
затем stop при любом fail. Проверки own-resume фиксируют ширину и seed.
Wide65/66, corridor63/64 иprecision61/62 завершились failed150; их launchers и
results сохранены как история. Существующие очереди не перезапускаются.

## Переиспользуемые инструменты

| Script | Назначение и ограничения |
|---|---|
| setup_desktop.ps1 | Настройка отдельного Windows runtime; сам не запускает обучение |
| b2w_runtime.py | Общие project paths/caches, headless настройки и B2W-only registration |
| smoke_b2w_desktop.py | GPU PhysX/Fabric smoke; техническая проверка, не качество policy |
| train_b2w_desktop.py | Flat PPO; project-local resume либо opt-in reference transfer; сохраняет configs/source/manifest/progress |
| reference_transfer.py | Строгий импорт совместимого reference actor, проверка Identity/ABI/parity, actor freeze и диагностика drift |
| run_reference_transfer.py | Ограниченная adaptation-очередь seeds 52/53: critic warmup, ранняя оценка и условный остаток бюджета; отдельный протокол |
| benchmark_b2w.py | Последовательный throughput sweep; не тест качества и не параллельный benchmark |
| check_stand_b2w.py | Zero-action PD stand без auto-reset; отдельный механический gate |
| check_policy_contract.py | CPU fixtures и экспорт реального project checkpoint через закреплённый exporter |
| play_b2w_gamepad_desktop.py | Isaac Sim Storm/Vulkan, CPU physics/policy,1 B2W Flat54/55/56 и Xbox; лимиты 1/1/1 через CLI, около real time; [управление](../docs/GAMEPAD_PLAY.md) |
| b2w_gamepad.py | Windows XInput, dead zone, body-frame velocity mapping, LB/stop/disconnect; simulator only |
| replay_reference_b2w.py | Diagnostic либо flat100, profiles nominal/bounded_v1; выбранный экспорт, по умолчанию скачанный reference |
| flat_evaluation.py | Детерминированные cases, статистика и thresholds evaluator |
| compare_robot_models.py | Таблицы source mass/COM/inertia; не динамическая sim2sim equivalence |
| vendor_materials.py | Верификация/управление manifest pinned materials; vendor policy см. AGENTS.md |
| sync_server.ps1 | Отдельная разрешённая синхронизация выделенного server project; не вызывается обычным Git push |

## Завершённая квалификация reference transfer

Завершена 19.09 в 22:26 МСК: все 6 итоговых оценок 100/100 и tracking pass.
`run_reference_qualification.py`: seeds54/55/56, по 50+100+200 updates,
upright reset только после 150. Новые cases только для финалов 350;
[замороженный протокол](../docs/REFERENCE_QUALIFICATION.md). Бюджет 103219200 transitions.
`--resume-validated-prefix` продолжает только подтверждённую техническую остановку
после 150 у 54/55; собственные parent hashes проверяются, бюджет не повторяется.
Статус — в журнале. Исходные координаторы ниже сохраняют историю development.

## Исходный reference transfer

Актуальный [протокол](../docs/REFERENCE_TRANSFER.md): общий pretrained actor
reference, fresh critic/optimizer у seeds 52/53, по 4096 сред. На каждый seed
50 critic-only updates, затем 100 PPO и ещё 200 PPO updates. После каждого
stage выполняется development evaluation; следующий stage разрешён только
при прохождении раннего правила. Автопродления бюджета нет.
Rewards сохранены upstream, pure-yaw mix 0,25; fixed std 0,1, LR 1e−4,
clip 0,1, entropy 0. Это проверка адаптации, не обучение с нуля.
Статус фактического запуска — в [журнале](../docs/TRAINING_PROGRESS.md).

`train_b2w_desktop.py --reference_init <project-policy.pt>` включает перенос actor;
`--critic_warmup_updates 50` задаёт число начальных updates с замороженным actor,
`--reference_drift_limit 0.25` — остановку при превышении raw-action RMS drift
на одинаковых фактических observations. Синтетическая parity и drift не заменяют
поведенческую оценку. Флаги reward overrides в этом протоколе не используются.

`--max_iterations` означает новые updates данного запуска. Продолжение после
раннего gate использует `--resume` и тот же transfer contract; actor не
инициализируется reference-весами повторно. Simulator/RNG после resume
запускаются заново. Координатор хранит source/protocol hashes и фактические exits;
повторный запуск в существующий output запрещён. Команды исторических опытов
ниже не продолжают эту очередь и требуют собственных локальных артефактов.

Для оценки flat100 нужны --suite flat100 --num_envs 100, 20 s измерения и 2 s
settling. --policy должен указывать на экспорт внутри проекта, --report — в
logs/qualification. Process exit 0 означает завершённое измерение; качество
определяется полями summary. Один flat100 report не закрывает три training seeds или sim2sim;
physical coverage ограничен явно записанным профилем. Nominal не включает
физические variations, bounded_v1 требует readback и persistence.

## Координаторы конкретной серии 17 сентября

| Script | Что он сохраняет |
|---|---|
| run_flat_baseline.py | Исходная последовательная очередь seeds 43/44, конкретные qualification paths |
| parallel_flat_baseline.py | Передача seed 43 без перезапуска и добавление seed 44; Windows process handles |
| measure_parallel_flat.py | Сравнение throughput конкретных logs до/после передачи |
| benchmark_parallel4096.py | Двойной benchmark 4096 и условное продолжение с точным учётом сохранённых transitions |

Эти четыре файла фиксируют проведённую оркестрацию и содержат даты/пути исходной
серии. Они **не являются универсальной командой fresh clone** и не должны
повторно запускаться поверх активного coordinator. Они требуют исключённых из
Git локальных job.json, reports и checkpoints; duplicate/path/hash guards
намеренно останавливают неподходящий запуск.

Для benchmark_parallel4096.py дополнительно использовались локальные
logs/benchmarks/dual4096_20260917/drain.json и baseline2048.json.
Одноразовая остановка на ближайших checkpoints выполнена
logs/qualification/drain_for_dual4096.py; script/record остались в локальных
артефактах этой сессии. Из checkout без этих артефактов нельзя воспроизвести
точное продолжение seed 43/44. Для нового эксперимента применять общие launchers
с отдельными run names и заранее определённым бюджетом/validation.

Полные training snapshots в локальных run directories фиксируют исходники
и observed byte hashes до публикации Git commit. [JSON результатов](../docs/results/2026-09-17.json)
даёт компактную трассировку; Git normalization может менять line endings текста.
Любые будущие правки coordinator проверять отдельно от уже запущенного процесса.

## Парная абляция yaw

run_yaw_ablation.py — ограниченное сравнение от локального финального seed 44,
не универсальный запуск после clone. [Протокол](../docs/YAW_ABLATION.md).
train_b2w_desktop.py принимает необязательный --pure_yaw_fraction: 0 добавляет измеритель
штатных команд, 0.25 включает описанное в протоколе распределение.
Без параметра исходный command class сохранён.
replay_reference_b2w.py всегда сохраняет имена звеньев первого контакта;
--reward_diagnostics дополнительно записывает weighted reward components.

## Абляция yaw reward

run_yaw_reward_ablation.py продолжает обе группы от одного завершённого mix
checkpoint: 1000 updates,4096 сред, weight1.5/3.0. После training сохраняет
exports, восемь evaluations и автоматический comparison.json.
[Протокол](../docs/YAW_REWARD_ABLATION.md). Привязан к локальным артефактам 17.09.2026.
train_b2w_desktop.py принимает --yaw_tracking_weight; без него вес upstream сохраняется.
Replay также записывает mean command, mean actual velocity и signed tracking bias.

## Контролируемая квалификация Flat

run_flat_qualification.py — очередь локального протокола 17.09.2026: regression
nominal evaluator, физическая диагностика, smoke fresh path, независимые seeds
45/46/47, экспорт и два новых набора оценок. Требует сохранённых локальных
артефактов предыдущего сравнения; не запускать повторно поверх существующей очереди.
[Протокол и бюджет](../docs/FLAT_QUALIFICATION.md).

replay_reference_b2w.py принимает --physical_profile nominal (default) или
bounded_v1. physical_evaluation.py включает ограниченные startup variations
и проверяет реальные PhysX/actuator properties, диапазоны, finite и persistence.
Координатор проверяет совпадение физических samples между политиками.

## Восстановление после VRAM guard

run_flat_recovery.py продолжает только сохранённый failed job17.09.2026:
45/46 по 899updates от model_1600, затем 47 с нуля 1601+resume899.
Одна тренировка 4096 за раз, прежний 15%headroom, проверки checkpoints/TB/source
и автоматические export/evaluations. Исходные отчёты не перезаписываются.
[Пересмотренный протокол](../docs/FLAT_RECOVERY.md).

run_flat_recovery_parallel.py принимает активный seed45 через Windows process
handle без перезапуска, останавливает только проверенный прежний координатор
и добавляет 46. После обоих продолжает 47 и оценки. Предыдущая очередь помечается
handed_off; повторный seed46 запрещён. Source snapshots и exit codes сохраняются.

run_flat_headroom5.py — завершённая очередь после второй остановки:45/46
от 1900/1700 на 599/799updates, затем 47 и оценки. Явно задаёт
minimum_gpu_headroom=.05; default run_pair остаётся.15. Не объявляет
разные restart histories контролируемой приёмкой. [Итог серии](../docs/results/2026-09-18-flat-qualification-final.json): все три новых seeds не прошли Flat gate.

## Flat schedule experiment (18 сентября 2026)

`diagnose_flat_qualification.py` сохраняет проверку первичных отчётов и последних
окон TensorBoard в `docs/results/2026-09-18-flat-diagnosis.json`.
`run_flat_schedule_ablation.py` выполняет frozen seed48 comparison: constant mix
против 2500 upstream + 1500 mix, обе группы с matched restart и final-only evaluation.
Протокол: [FLAT_SCHEDULE_ABLATION.md](../docs/FLAT_SCHEDULE_ABLATION.md).
Это локальный coordinator с зависимостью от существующих диагностических артефактов.

## Staged Flat qualification (18 сентября 2026)

`run_staged_qualification.py` выполняет fresh seeds 49/50/51 с расписанием
2500 upstream + 1500 mix, одинаковым restart и новыми evaluation cases.
Seeds 49/50 параллельны, затем 51 отдельно. Протокол:
[STAGED_QUALIFICATION.md](../docs/STAGED_QUALIFICATION.md).

## Дополнительные инструменты 18 сентября

| Script | Фактическое назначение / состояние |
|---|---|
| run_flat_schedule_parallel.py | Выполненная передача seed48 constant без restart и параллельное staged-сравнение; серия завершена |
| finish_flat_schedule_evaluation.py | Выполненное восстановление последнего evaluator seed48 без нового обучения |
| schedule_parallel_handoff.py | Win32 handles, проверка принадлежности процесса и фактических exit codes |
| connect_laptop_key.ps1 | Интерактивная установка существующего публичного ключа; пароль вводится только в SSH, ключ не хранится в Git |
| laptop_training_transport.py | SSH/SCP только в назначенный Windows project; пути/учётная запись привязаны к текущей инфраструктуре |
| laptop_seed51_worker.py | Первичная квалификация ноутбука выполнена; основной seed51 не назначался |
| qualify_laptop_pcores.py / laptop_pcore_runtime.py | Выполненный повторный benchmark с affinity P-ядер только у процесса и детей |
| run_staged_laptop_parallel.py | Исторический, не выполненный end-to-end перенос fresh seed51; повторное назначение требует нового протокола |
| run_staged_tail_parallel.py / laptop_staged_tail_worker.py | Подготовленный перенос seed50 после 2500; окно серии 49/50/51 уже пройдено, перенос не выполнялся |
| server_cuda_probe.cpp | GPU0 D2D пройден; cuBLAS init timeout. Synthetic CUDA, не Isaac/PPO benchmark |

[Квалификация ноутбука](../docs/LAPTOP_WORKER.md),
[замеры сервера](../docs/SERVER_PERFORMANCE.md). Подготовленные handoff scripts
зависят от локальных артефактов, исходных хешей и конкретного состояния очереди;
публикация в Git не означает разрешение или успешный запуск.

## Завершённые диагностика и абляции 18–19 сентября

| Script | Назначение |
|---|---|
| run_staged_yaw_diagnostics.py / analyze_staged_yaw.py | Завершённая пассивная диагностика staged seeds 49/50/51 и reference |
| yaw_trace.py / yaw_trace_analysis.py | Запись физического trace и анализ с проверкой provenance |
| run_contact_weight_ablation.py | Завершённая парная абляция −1/−3; локальные parent checkpoints |
| run_contact_yaw_diagnostics.py / analyze_contact_yaw.py | Завершённые replay и анализ contact−3 controls |
| run_height_weight_ablation.py | Завершённая парная абляция симметричного height L2 |
| b2w_height_rewards.py | Opt-in lower-L1 term вне vendor; не включается в reference transfer |

`run_height_yaw_diagnostics.py` воспроизводит восемь оценок завершённого опыта
control/height10 seeds50/51 и проверяет четыре сохранённые reference/seed49 traces.
Политики, cases, source/report/trace hashes и physical digests должны совпадать;
новые результаты записываются отдельно. Повторный запуск в существующий каталог
запрещён. Скрипт требует локальных артефактов и не является fresh-clone командой.

`analyze_height_yaw.py` после завершения replay сравнивает одинаковые интервалы
до более раннего первого отказа, отдельные предконтактные окна и training tails.
Пять reward terms реконструируются из trace и фактического training config;
calf contact — явно ограниченный proxy, не полный undesired_contacts reward.
Первичные файлы и [протокол](../docs/HEIGHT_DIAGNOSIS.md) сохраняются; результат
сам по себе не закрывает независимую Flat приёмку.

`run_height_floor_ablation.py` — завершённый lower-L1 опыт после height
диагностики: две пары seeds50/51,1500 новых updates/arm от исходных model_2499.
`train_b2w_desktop.py --base_height_form lower_l1 --base_height_weight -10` явно включает
локальный term `b2w_height_rewards.py`; без этих флагов defaults сохранены.
Нельзя повторно запускать coordinator в существующий output или менять frozen
исходники активной очереди. [Протокол](../docs/HEIGHT_FLOOR_ABLATION.md).


`run_contact6_ablation.py` — завершённый опыт contact−3/−6 после
завершения lower-L1. Height terms выключены; seed50 и 51 по две ветви от исходных
model_2499,1500 новых updates/ветвь,4096 сред. Smoke/resume, проверка единственного
различия env.yaml, source/decision hashes, VRAM guard5%,4exports и 10evaluations.
Не запускать повторно в существующий каталог; не менять frozen исходники.
[Протокол](../docs/CONTACT6_ABLATION.md), журнал `logs/ablations/lower_l1_followup.json`.

## Диагностика resume и продолжение upright

- diagnose_reference_resume.py: два отброшенных однократных updates от model_149;
  --upright повторяет их с reset roll/pitch±0,1, прежний drift guard.
- train_b2w_desktop.py --reference_update_probe: passive pre/post measurements на тех же
  observations; --flat_upright_resets: единственное изменение orientation reset.
- run_reference_upright_resume.py:200 updates/seed от проверенных 150, затем
  exports и 4 evaluations. [Протокол](../docs/REFERENCE_RESUME.md).

Исходный failed job и протокол сохраняются; retry не переписывает историю.


## Rough R0 (19 сентября 2026)

`run_rough_r0.py` — ограниченная локальная очередь от qualified Flat seed54:
collision geometry/64-env physics smoke,2+2 PPO с optimizer resume, затем50
updates на1024/2048 средах. Все веса discard; очередь не разрешает R1/Stairs.
Протокол: [ROUGH_R0](../docs/ROUGH_R0.md). Существующие output/seeds защищены
от повторного запуска; JSON и source snapshots сохраняют технические попытки.

`train_b2w_desktop.py --rough_r0` сохраняет actor ABI57→16 и создаёт critic247,
проверяет frozen parent hash, Rough и фиксированный Flat observation bank drift.
`b2w_rough_runtime.py` задаёт level0 mix и отключает upstream distance promotion;
`b2w_rough_terrain.py` создаёт проектные collision meshes с явной квантизацией.
`smoke_rough_b2w.py` проверяет GPU PhysX/Fabric,187 rays,spawn и contacts на каждом
physics step. Safe curriculum и полный Rough evaluator реализованы20сентября;
их отдельная проверка описана ниже.


## Rough development (20 сентября 2026)

`benchmark_rough_capacity.py`: завершённый discard benchmark single4096/dual2048;
выбран single4096. Повторно в существующие output не запускать.
`run_rough_preflight.py --attempt N`: collision fixtures nominal/bounded,
полный100-case evaluator и safe-curriculum train/resume2+2; веса discard.
`run_rough_development.py --preflight docs/results/rough_r1_preflight_20260920_6.json`:
фиксированные seeds57/58,4096 сред последовательно,50+100+200 updates. После
milestones обязательны Flat regression и Rough cases по протоколу. Координатор
запрещает повторное использование seeds, изменение source/protocol, продление
бюджета; хранит процессные exit codes, checkpoints, resource/quality guards.
Во время очереди исходники не менять и другие GPU jobs не запускать.

`rough_curriculum.py`: только safe directed traversal повышает level, state
сохраняется в checkpoint. `replay_rough_b2w.py`/`rough_metrics.py`:100 cases,
200Hz contacts и50Hz sampled collision geometry, physical-property readback,
route/tracking/energy/slip/limits. `rough_evaluation.py`: неизменяемые cases и
пересчёт quality gates по полным rows. [Протокол](../docs/ROUGH_DEVELOPMENT.md).


## Rough tilt correction (20 сентября 2026)

`diagnose_rough_drift.py` пересчитывает сохранённый iteration115 probe без PPO.
`rough_tilt_termination.py` добавляет только sustained-tilt terminal (>60°,>0,1с),
использует physics-rate telemetry и выполняет искусственный переворот только
на discard64-env smoke. В training opt-in `--rough_tilt_termination`.
`run_rough_preflight.py --attempt 7 --tilt_termination` завершён exit0;
fixture train/resume подтвердил reset после0,12с и очистку timer/sticky state.
`run_rough_tilt_correction.py --preflight docs/results/rough_r1_preflight_20260920_7.json`
запускает новую причинную серию57/58 от собственных validated model_49,
100+200 новых updates. Исторический stopped_115 не используется как parent.
YAML, source, parent, case hashes и прежние quality/VRAM/drift guards проверяются.
[Протокол](../docs/ROUGH_TILT_CORRECTION.md). Во время запуска frozen code не менять.


## Запрошенное Rough continuation150→350

`run_rough_requested_continuation.py --continue_after_failed_rough150`:
фиксированные seeds57/58, только собственные validated tilt-correction
`model_149.pt`, ещё200 updates/seed,4096 env последовательно. Запущено20.09
по прямому запросу пользователя после сообщения о Rough quality stop.
Проверяет предыдущие20 evaluations/source/hashes/optimizer; сохраняет
прежний fail150. Собирает4 Flat и48 Rough final evaluations с прежними
порогами; результат диагностический, без автоматической acceptance/qualification.
Training/evaluator код не менялся. [Протокол](../docs/ROUGH_REQUESTED_CONTINUATION.md).


## Rough route correction (20 сентября 2026)

`run_rough_reference_baseline.py` завершил сравнение исходной reference и
Flat anchor54: random level0,100 cases×2profiles на политику. Это диагностический
comparator, не Rough qualification.

`rough_route_commands.py` задаёт opt-in согласованные command/reset/episode
распределения на Rough70%, сохраняя Flat replay30%. `train_b2w_desktop.py
--rough_route_commands --rough_transfer --rough_tilt_termination` требует
новой серии stage0 и запрещает подмену режима при resume. Актор57→16,
rewards,physics и evaluator сохранены; random initial episode clock выключен.

`run_rough_route_preflight.py --attempt 1`: native reset/command/timeout/partial
reset fixtures и discard64-env GPU train/resume2+2.
`run_rough_route_correction.py --preflight docs/results/rough_route_preflight_20260920_1.json`:
свежие seeds59/60 от квалифицированного Flat actor54, новые critics,
50+100+200 updates, single4096, прежние Flat/Rough/drift/VRAM gates.
Зависит от локальных исключённых из Git артефактов; повторный запуск запрещён.
[Протокол](../docs/ROUGH_ROUTE_CORRECTION.md),
[исследование](../docs/ROUGH_RESEARCH_2026-09-20.md),
[проверенные последние результаты](../docs/results/2026-09-20-rough-latest-audit.json).


## Запрошенное route продолжение150→350

`run_rough_route_continuation.py --verify_only` проверяет собственные parents59/60,
исходники,optimizer и полные Flat rows без обучения.
`--continue_after_failed_flat150` разрешает только раскрытый relative failure
seed60 bounded/lateral yaw; продолжает по200updates с сохранением route recipe.
Все4Flat+48Rough финальных batches собираются диагностически, старый fail150
сохраняется. Technical/drift/VRAM/source guards прекращают очередь.
[Протокол](../docs/ROUGH_ROUTE_CONTINUATION.md). Повторный запуск запрещён.


## Отклонённый teacher locomotion T0 (20 сентября2026)

По уточнению пользователя actor строго57→16. Скрипты247-input оставлены
только как история; запуск заблокирован. Seed67 прошёл100updates до технического
сбоя diagnostic reset; seed68 не запускался.

`b2w_locomotion_teacher.py` создаёт отдельный sim ABI247→16 и выполняет
проверяемый zero-pad lift Flat57; `train_locomotion_teacher.py` запускает native
PPO со свежим critic,25critic-only updates и обучаемым std после warmup.
`run_locomotion_teacher_pilot.py --attempt 1` — bounded последовательная очередь:
64env2+2 discard smoke, затем seeds67/68 по100updates на1024env. Повторный
запуск в тот же output запрещён; использует локальный qualified Flat54 anchor.
`--smoke_only` ограничивает очередь только технической проверкой.

Каждый stage сохраняет manifest/config/source hashes, checkpoints/optimizer,
export parity и external exit code/resource telemetry. Pilot diagnostic
не является Rough/Stairs quality pass; mixed terrain не запускается автоматически.
[Протокол и этапы](../docs/ROUGH_TEACHER_REDESIGN.md).
