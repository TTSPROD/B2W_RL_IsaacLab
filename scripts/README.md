# Инструменты B2W

Запускать из корня проекта в его отдельном runtime. Для Windows команды настройки
и необходимые environment settings указаны в [DESKTOP_SETUP.md](../docs/DESKTOP_SETUP.md).
Ни один перечисленный launcher не управляет реальным роботом. Vendor неизменяем.

## Переиспользуемые инструменты

| Script | Назначение и ограничения |
|---|---|
| setup_desktop.ps1 | Настройка отдельного Windows runtime; сам не запускает обучение |
| b2w_runtime.py | Общие project paths/caches, headless настройки и B2W-only registration |
| smoke_b2w.py | GPU PhysX/Fabric smoke; техническая проверка, не качество policy |
| train_b2w.py | Flat PPO; число сред, seed, updates, явный project-local resume; сохраняет configs/source/manifest/progress |
| benchmark_b2w.py | Последовательный throughput sweep; не тест качества и не параллельный benchmark |
| check_stand_b2w.py | Zero-action PD stand без auto-reset; отдельный механический gate |
| check_policy_contract.py | CPU fixtures и экспорт реального project checkpoint через закреплённый exporter |
| replay_reference_b2w.py | Diagnostic либо flat100, profiles nominal/bounded_v1; выбранный экспорт, по умолчанию скачанный reference |
| flat_evaluation.py | Детерминированные cases, статистика и thresholds evaluator |
| compare_robot_models.py | Таблицы source mass/COM/inertia; не динамическая sim2sim equivalence |
| vendor_materials.py | Верификация/управление manifest pinned materials; vendor policy см. AGENTS.md |
| sync_server.ps1 | Отдельная разрешённая синхронизация выделенного server project; не вызывается обычным Git push |

Пример самостоятельной новой Flat тренировки после настройки runtime:

~~~powershell
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
.venv/Scripts/python.exe -B scripts/train_b2w.py --headless --device cuda:0 --num_envs 4096 --seed 45 --max_iterations 2500 --run_name flat_fixed4096
~~~

Это пример upstream-команды, не выполненный эксперимент. Для выбранной
конфигурации квалификации нужны также --pure_yaw_fraction .25
--yaw_tracking_weight 1.5 и новый уникальный run_name. Seed/run_name выбираются для
конкретного плана. 2500 × 4096 × 24 = 245 760 000 transitions.
До запуска учитывать уже активные jobs; не добавлять этот пример к двум текущим
тренировкам. --max_iterations означает новые updates данного запуска, а не
желаемый глобальный checkpoint index. Resume сохраняет model/optimizer, но
переинициализирует simulator/RNG и не является побитовым продолжением.

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
train_b2w.py принимает необязательный --pure_yaw_fraction: 0 добавляет измеритель
штатных команд, 0.25 включает описанное в протоколе распределение.
Без параметра исходный command class сохранён.
replay_reference_b2w.py всегда сохраняет имена звеньев первого контакта;
--reward_diagnostics дополнительно записывает weighted reward components.

## Абляция yaw reward

run_yaw_reward_ablation.py продолжает обе группы от одного завершённого mix
checkpoint: 1000 updates,4096 сред, weight1.5/3.0. После training сохраняет
exports, восемь evaluations и автоматический comparison.json.
[Протокол](../docs/YAW_REWARD_ABLATION.md). Привязан к локальным артефактам17.09.2026.
train_b2w.py принимает --yaw_tracking_weight; без него вес upstream сохраняется.
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
