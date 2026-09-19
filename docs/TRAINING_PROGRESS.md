# Результаты обучения B2W

**19.09.2026,21:04:52 МСК: upright continuation завершён успешно.**
Оба seeds52/53 достигли350 updates; все четыре nominal/bounded_v1 оценки
прошли100/100 и scenario tracking. Hashes source/checkpoints/exports/reports
проверены; actor отличается от reference, critic обновлён, std0,1 сохранён.
[Полный итог](results/2026-09-19-reference-upright-final.json).

| Policy/profile | Safe | Худший scenario RMS vx/vy/yaw |
|---|---|---|
|52 nominal|100/100|0,07497 /0,16763 /0,14924|
|52 bounded_v1|100/100|0,08183 /0,15839 /0,16734|
|53 nominal|100/100|0,05856 /0,15219 /0,16517|
|53 bounded_v1|100/100|0,06424 /0,15036 /0,19387|

Пороги0,20/0,20/0,25 выполнены отдельно в каждом семействе. Это сохранение
навыка на раскрытых development cases, не доказанное превосходство reference.
Минимальный запас VRAM17,90%, peak10084 MiB,64°C, telemetry errors0.

Следующая очередь подготовлена: [квалификация seeds54/55/56](REFERENCE_QUALIFICATION.md)
с двумя новыми наборами cases, точный successful lineage50 recovery critic +
100 recovery PPO +200 upright PPO. На каждый350 updates, всего103219200 transitions.
54/55 параллельно, затем56; только итоговые checkpoints, без перебора и продления.
Flat transfer gate открыт до завершения этой проверки; Rough ещё не запускался.

Исходный recovery-only final остановлен20:06:06 МСК: drift seed53 был0,25163
до update и0,25031 после при guard0,25. [Исходный failed job](results/2026-09-19-reference-transfer-final.json)
не переписан. Успешное продолжение началось от model_149; failed/probe updates
отброшены, единственная MDP-поправка — reset roll/pitch±0,1 рад после150.
[Диагностика/протокол](REFERENCE_RESUME.md). Reference/seed49 и все родители сохранены.

## Что установлено

| Опыт | Результат | Решение и источник |
|---|---|---|
| Seed42,5000 updates |96/100 safe,4 calf contacts; reference100/100 |Flat не пройден; [baseline](results/2026-09-17.json) |
| Seeds43/44 |По96/100 safe; yaw RMS выше0,25 |[Исходная серия и yaw mix](YAW_ABLATION.md) |
| Command mix seed44 |Safety99/100 и100/100, yaw RMS0,280–0,318 |Чаще yaw помогает контактам, но не закрывает tracking |
| Yaw weight1,5/3 |Оба single-policy gates; yaw2x улучшил yaw RMS32–48% |[Протокол](YAW_REWARD_ABLATION.md); правило выбрало control |
| Fresh45/46/47,2500 |Nominal91/94/92; bounded91/90/89 safe |[Отказ](FLAT_QUALIFICATION.md); разные restart histories |
| Schedule seed48,4000 |Staged100/100 на обоих, constant99/92 |[Один development seed](FLAT_SCHEDULE_ABLATION.md) |
| Staged49/50/51,4000 |Safe nominal100/88/96, bounded100/93/100 |Только49 прошёл оба; [серия](STAGED_QUALIFICATION.md) |
| Contact−1/−3,50/51 |Отказы23→14;−3 safe50:88/98,51:100/100 |[Кандидата нет](CONTACT_WEIGHT_ABLATION.md) |
| Height L2 0/−10 |Отказы14→23; variant50:85/93,51:99/100 |[Кандидата нет](HEIGHT_WEIGHT_ABLATION.md) |
| Height lower-L1 |Отказы14→23; variant50:87/91,51:99/100 |[Кандидата нет](HEIGHT_FLOOR_ABLATION.md) |
| Contact−3/−6 |Отказы14→20;−6 safe50:98/99,51:85/98 |[Кандидата нет](CONTACT6_ABLATION.md) |

Safe — отсутствие падения/запрещённого контакта; числа не заменяют tracking gate.
Четыре последние серии по4×1500 новых updates от исходных staged model_2499;
они не являются последовательным дообучением финалов.
Controls в последних сериях точно воспроизвели прежние оценки.

Последний contact6 завершён19.09 в18:53:57 МСК:4 train,4 exports/parity,
10 evaluations с exit0. [Итог и23 verified artifacts](results/2026-09-19-contact6-final.json).
У seed50 nominal yaw RMS0,32453>0,25; у seed51 nominal negative-yaw
vx RMS0,24745>0,20. Все20 отказов variant — rear-calf contacts при pure yaw.
Это не20 доказанных падений. Монотонной пользы усиления contact penalty нет.

## Диагностика и сохранённые навыки

[Staged diagnosis](STAGED_DIAGNOSIS.md), [contact replay](results/2026-09-19-contact-yaw-diagnosis.json),
[height matched analysis](HEIGHT_DIAGNOSIS.md) связывают отказы с малым зазором
голеней и просадкой. Постоянное leg torque saturation не подтверждено в
исследованных окнах; clearance — геометрический proxy, не точное расстояние
collision meshes. Контактный history3/decimation4 пропускает часть событий,
но не объясняет большинство прежних отказов. Причинность contact6 regression
не установлена отдельным matched replay.

Seed49 прошёл оба профиля100/100, worst yaw RMS0,21230/0,20578,
CPU export parity295 входов max error0.
[Артефакты и hashes](STAGED_QUALIFICATION.md#сохранённый-кандидат-seed49).
Его не дообучают и не перезаписывают. Reference имеет проверенный motor skill,
но скачан; новый transfer должен отдельно доказать updates и качество.

## Продолжение от150 updates

[REFERENCE_RESUME](REFERENCE_RESUME.md): seeds52/53 от исходных model_149,
по200 новых updates с roll/pitch reset±0,1 рад. Порог drift0,25 сохраняется.
Два успешных upright resume probes отброшены; из их weights не продолжаем.
Предыдущие failed/probe transitions отражены отдельно от основного бюджета.

[Решение и matched pre/post данные](results/2026-09-19-reference-resume-decision.json).
Job: logs/transfer/flat_reference_upright_resume_20260919/job.json.
Исходный job завершён с failed; новая очередь не переписывает этот результат.

## Инфраструктура и открытые gates

Desktop Flat headless2×4096:63 907,87 transitions/s в коротком benchmark,
+67,32% относительно2×2048. Это throughput, не скорость сходимости.
Runtime/VRAM/сервер/ноутбук описаны один раз в [INFRASTRUCTURE](INFRASTRUCTURE.md)
и [COMPUTE_DECISION](COMPUTE_DECISION.md). Сервер в этих обучениях не участвовал.

Zero-action PD:16/16 отказов около0,79 s; это не тест активной политики.
[Policy contract](POLICY_CONTRACT.md): nominal parity пройдена,
saturation и hardware mapping не закрыты. [Модели](ROBOT_MODEL_COMPARISON.md):
MuJoCo тяжелее training URDF на4,750435 kg, различаются COM/inertia/limits.
Rough/Stairs/GUI/sim2sim/SDK/hardware не выполнены и не следуют из Flat pass.

## Доказательства и хранение

Датированные JSON и исторические протоколы сохраняют source hashes, конкретные
paths, process exits, restart histories, failed runs и ограничения.
Они не являются текущими заданиями. [Инструменты](../scripts/README.md).
Git содержит код, документацию, небольшие результаты и immutable vendor.
Training checkpoints, runtime, caches, TensorBoard остаются локально вне Git;
постоянный artifact store ещё не выбран. Git push не синхронизирует их на другие машины.

Проверки текущего изменения записаны в launch snapshot.
Исторические counts тестов относятся к датированным запускам, а не к нынешнему HEAD.
