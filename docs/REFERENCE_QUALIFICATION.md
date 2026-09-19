# Квалификация воспроизводимости reference transfer

Зафиксировано 19.09.2026 перед запуском. Текущий статус — в
[журнале](TRAINING_PROGRESS.md); этот протокол после старта не редактируется.

Основание: seeds52/53 на cumulative350 прошли все четыре development evaluations
по100/100, включая scenario tracking. [Итог](results/2026-09-19-reference-upright-final.json).
Hashes checkpoints, exports, reports и замороженных исходников проверены21:18–21:22 МСК.
Исходный recovery-only final и диагностические updates остаются отдельными
непринятыми запусками. Успех продолжения не доказывает превосходство над reference.

## Зафиксированный режим

Три ранее не использованных training seeds **54/55/56**, у каждого свежий critic,
optimizer и RNG, общий исходный reference actor. Политики52/53 не являются parents.
Это воспроизводимость fine-tuning, не обучения с нуля.

| Новые updates | Cumulative | Reset roll/pitch | Обучение |
|---|---|---|---|
|50|50|±3,14 рад|Только critic, actor и std заморожены|
|100|150|±3,14 рад|PPO, std заморожен|
|200|350|±0,1 рад|PPO, std заморожен; passive pre/post probe|

После50 и150 simulator/RNG перезапускаются; model_49/model_149 и optimizer
передаются только своему seed. Это тот же порядок, что у успешного development
lineage:50 recovery critic +100 recovery PPO +200 upright PPO.
Неудачные и diagnostic updates в него не входят.
4096 environments,24 rollout steps, fixed std0,1, LR1e−4, clip0,1, entropy0,
pure-yaw fraction0,25, upstream rewards, native RSL-RL. Drift raw-action RMS≤0,25
каждый update. Конфигурации каждого stage сравниваются с сохранёнными успешными
configs: разрешены только seed/run_name/log_dir. Код обучения/оценки совпадает
с development по SHA256; изменяется оркестрация.

Порядок вычислений:54/55 параллельно до350, затем56 до350. Бюджет основной
очереди **103 219 200 transitions**. Ранее пройденные GPU smoke/resume и два
полных350-update lineage являются техническим основанием; новый simulator,
reward, ABI или optimizer здесь не вводится.

## Итоговая оценка

Новые evaluation seeds: nominal **2026091961**, bounded_v1 **2026091962**.
До старта подтверждено отсутствие этих seeds в локальных evaluation reports.
По100 cases заранее генерируются через make_cases(heldout=True), фиксируются
в protocol.json вместе с кодом и физическими профилями. Не используются в
обучении или промежуточном выборе checkpoints. Новые наборы принадлежат тем
же восьми семействам Flat; новые terrain families этим не покрыты.

Оцениваются только три model_349 и неизменённый reference: всего8 replay.
Reference проходит новые cases после обучения, перед оценками финалов;
результат не влияет на параметры уже завершённого обучения. Промежуточные
50/150 development replay из пилота не повторяются: они были stop-only и
не меняли training state. Restart boundaries сохраняются. Все восемь оценок
публикуются, даже если один quality gate не пройден; техническая ошибка
останавливает очередь. Выбор лучшего seed или более раннего checkpoint запрещён.

Каждая policy/profile:≥99/100 без sticky failure; в каждом семействе
pooled RMS vx/vy≤0,20 м/с, yaw≤0,25 рад/с. Требуются4400 physics steps,
export/live parity≤1e−5, согласованные hashes, cases и physical samples,
readback/persistence, отсутствие неоднозначного saturation. Среднее или
успех reference не заменяют шесть отдельных passes новых политик.

## Остановка и следующий этап

Finite checks, drift≤0,25; VRAM до stage свободно≥50%, во время training
запас≥5%; telemetry errors запрещены. Training timeout3600 s/stage,
export600 s, replay900 s. Проверки checkpoints/TensorBoard после каждого stage.
Ошибка одного train останавливает только его парный процесс этой очереди.
Исходники, протокол и сохранённые configs фиксируются hashes; повторный
запуск в существующий каталог запрещён. Бюджет не продлевается.

Полный pass закрывает только Flat transfer gate в указанном покрытии.
Далее — отдельный Rough GPU smoke и новый curriculum с Flat regression.
Автоматического запуска Rough, sim2real или реального робота здесь нет.
При отказе сохранить все результаты, исследовать конкретный fail;
не заменять провалившийся seed и не подбирать параметры по этим наборам.

Запуск из корня: `.venv/Scripts/python.exe -B -u scripts/run_reference_qualification.py`.
Job: `logs/transfer/flat_reference_qualification_20260919/job.json`.
Reports: `logs/qualification/flat_reference_qualification_20260919/`.
В Git идут код, протокол и компактные итоговые/launch JSON; runtime и weights
остаются вне Git. Публикация в TTSPROD/B2W_RL_IsaacLab разрешена пользователем.
