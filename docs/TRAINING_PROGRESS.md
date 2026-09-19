# Результаты обучения B2W

**19.09.2026,22:26:37 МСК: квалификация Flat transfer завершена успешно.**
Tри новых seeds54/55/56 достигли350 updates. Все шесть nominal/bounded_v1
оценок —100/100 и scenario tracking pass; reference прошёл оба набора100/100.
**Flat transfer gate пройден** в зарегистрированном покрытии.
[Полный итог](results/2026-09-19-reference-qualification-resume-final.json),
[независимая проверка66 artifacts/hashes](results/2026-09-19-reference-qualification-verification.json).

| Policy/profile | Safe | Худший scenario RMS vx/vy/yaw |
|---|---|---|
|reference nominal|100/100|0.06274 / 0.15614 / 0.18812|
|reference bounded_v1|100/100|0.06669 / 0.16566 / 0.20019|
|seed54 nominal|100/100|0.07274 / 0.16361 / 0.17009|
|seed54 bounded_v1|100/100|0.07994 / 0.17686 / 0.17140|
|seed55 nominal|100/100|0.08311 / 0.16114 / 0.17033|
|seed55 bounded_v1|100/100|0.09149 / 0.16298 / 0.15879|
|seed56 nominal|100/100|0.06437 / 0.16010 / 0.16601|
|seed56 bounded_v1|100/100|0.06911 / 0.17542 / 0.16940|

Пороги vx/vy≤0,20 м/с и yaw≤0,25 рад/с выполнены в каждом семействе.
Raw reports пересчитаны; policy/checkpoint/source hashes, export/live parity и
одинаковые cases/physical samples проверены. Все финальные actors отличаются от
reference, critics обновлены, std0,1 сохранён. Это воспроизводимость переноса
общего pretrained actor, не обучение с нуля и не доказанное общее превосходство
над reference. Worst yaw ниже, но worst vx у новых политик выше контрольного.

Основной бюджет:103219200 transitions, включая сохранённые первые150 у54/55.
Ни повторов, ни продления. Минимальный запас VRAM16,49%, max65°C, telemetry errors0.
Рабочие checkpoints model_349 и exports для всех трёх seeds сохранены; точные
пути/SHA256 — в verification JSON. Weights/runtime не входят в Git.

Очередь завершена; низкая загрузка GPU после22:26 ожидаема. Следующий этап по
плану — отдельный Rough GPU smoke и curriculum с Flat regression. Не запущен.

История: development52/53 успешно завершён21:04, все4 оценки100/100.
[Development итог](results/2026-09-19-reference-upright-final.json).
Qualification остановилась21:37 после150 у54/55 из-за ошибочного сравнения
load_run; оба train были успешны. [Исходный failed job](results/2026-09-19-reference-qualification-final.json)
сохранён. Проверка собственного parent исправлена, продолжение21:54 использовало
те же model_149 без повторных updates. [Протокол исправления](REFERENCE_QUALIFICATION_RESUME.md).

Ещё более ранний recovery-only final52/53 остановлен drift guard:
[исторический отчёт](results/2026-09-19-reference-transfer-final.json).
Его failed/probe updates не вошли в принятые lineage; upright после150
был отдельным зарегистрированным изменением. Reference/seed49 сохранены.

## Интерактивный просмотр и следующий план

19.09 запущен Isaac Sim GUI с1 Flat B2W, финалом seed54 и Xbox-геймпадом.
Рендер D3D12, runtime/physics/weights неизменны; viewport и live parity проверены.
[Управление](GAMEPAD_PLAY.md), [GUI свидетельство](results/2026-09-19-gamepad-gui.json).
Новая training очередь не запущена. [План Rough/Stairs](ROUGH_STAIRS_PLAN.md)
обновлён по успешному transfer: отдельный Rough smoke, actor-only перенос,
свежий critic, короткие бюджеты, Flat regression, stairs up/down отдельным gate.

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
