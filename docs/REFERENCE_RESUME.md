# Продолжение reference transfer: вертикальные resets для Flat

Протокол19.09.2026, до запуска продолжения. Текущий статус и timestamps — в
[TRAINING_PROGRESS](TRAINING_PROGRESS.md). Исходный [протокол](REFERENCE_TRANSFER.md)
и его неуспешный final-stage job сохранены, задним числом не исправляются.

## Установленная причина и проверка

Исходная очередь остановилась20:06:06 МСК после прохода всех gates на150 updates.
У seed53 на первом rollout после resume drift уже был0,2516298 **до** PPO-update,
а после стал0,2503078. Пассивная инструментация точно воспроизвела исходный
post-update drift. Непосредственной причиной превышения не был этот PPO-update:
его изменение actions RMS0,01627 и он немного уменьшил reference drift.

На одинаковых observations сильно наклонённые состояния (g_z>−0,5) составляли
11,50% выборки seed53, но дали78,06% squared action error. В upright подмножестве
RMS0,12530, в остальных0,65560. Это указывает на mismatch recovery resets и
сохранения Flat навыка; это не доказательство полной утраты recovery-поведения.

[Однократная диагностика](results/2026-09-19-reference-resume-diagnosis.json)
и [сравнение upright](results/2026-09-19-reference-resume-upright-diagnosis.json).
По одному update каждого seed в каждом варианте:4×4096×24=393216 transitions,
отброшены; из этих checkpoints основное продолжение не начинается.
При upright старте оба exit0 и прежний guard0,25 соблюдён.
Probe records сравнивают до/после на идентичных tensors, без дополнительного RNG.

## Единственное изменение MDP

events.randomize_reset_base.params.pose_range.roll/pitch:
от[-3,14;3,14] к[-0,1;0,1] рад.
Позиция, yaw, линейные/угловые скорости reset, rewards, commands, physics,
actions, observation noise и PPO параметры сохраняются.
Это явный curriculum для движения по Flat из вертикальной позы; успешный итог
не будет означать квалификацию восстановления из перевёрнутых положений.

Guard reference action RMS≤0,25 сохранён, не округлён и не отключён.
LR1e−4 fixed, clip0,1, std0,1 frozen, entropy0, pure-yaw mix0,25.
Пассивный probe записывает pre/post drift и первый rollout, не меняя objective.

## Продолжение и приёмка

Seeds52/53 от исходных проверенных model_149 + optimizer, по200 новых updates
на4096 средах; финалы model_349. Всего39 321 600 новых transitions основной пары.
Один одинаковый restart; исключённые diagnostic/failed updates учтены отдельно.
Ни seed49, ни reference, ни исходные checkpoints не перезаписываются.

Прежние control и update150 evaluations повторно используются после проверки
hashes, cases, физического digest, source и gate. Они уже раскрыты: development.
Финальные2 exports/parity и4 evaluations nominal2026091951/bounded2026091952.
Каждый seed/profile≥99/100 safe, каждый сценарий RMS vx/vy≤0,20; yaw≤0,25.
Только оба финала349 могут быть development-кандидатами. Никакого выбора
промежуточных checkpoint, автоматического продления, fresh replication или Rough.

До training≥50% VRAM free; guard5% во время пары, telemetry5 s, timeout3600 s.
Ошибки/NaN/drift/source/hash/resource failures останавливают очередь.
Ресурсы exports/evaluations проверяются после stage, до следующего.
Конфиги сравниваются с parent: допустимы только log_dir и указанные roll/pitch;
PPO/obs/action параметры должны совпасть. Snapshot источников сохраняется.

Команда из корня после публикации:
~~~powershell
.venv/Scripts/python.exe -B -u scripts/run_reference_upright_resume.py
~~~
Job: logs/transfer/flat_reference_upright_resume_20260919/job.json.
Итог: docs/results/2026-09-19-reference-upright-final.json.
Новая исследовательская ветвь имеет общий pretrained actor и историю50+100+200;
она не превращает исходную остановленную очередь в успешно законченную.
