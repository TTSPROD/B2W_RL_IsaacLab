# Результаты обучения B2W

**20.09, актуальный итог:** route continuation59/60 завершено12:47:42МСК,
54stages exit0. Rough2653/4800 successes,0/48 full suites; первые failures:
1888corridor,249body_contact,10route_incomplete. Curriculum[0,1,2,2,1] у обоих.
Flat400/400 safe, все4absolute gates pass, relative pass только59bounded_v1.
Ни development protocol, ни policy acceptance не пройдены.
[Итог](results/rough_route_continue_20260920.json),
[разбор причин](results/2026-09-20-rough-route-diagnosis.json).

**Следующая очередь:** [precision tracking61/62](ROUGH_PRECISION_TRACKING.md).
Изменяется только ширина обоих tracking kernels0,5→0,25. Actor отFlat54,
свежие critic/optimizer;50+100+200, single4096, все прежние quality gates.
Preflight64 завершён14:58МСК: train/resume2+2 exit0, optimizer40→80,
native reward/route/tilt fixtures и полный effective config diff прошли.
Все165 CPU-тестов и45 frozen input hashes проверены; vendor1290 проверены.
Rough drift0,04796, Flat-bank0,05626 при лимите0,25; smoke веса discard.
[Отчёт](results/rough_precision_preflight_20260920_1.json).
Основная очередь запущена20.09 в15:08МСК: seed61 фактически выполняет critic calibration,
seed62 ожидает; actor пока frozen, drift0. [Launch evidence](results/2026-09-20-rough-precision-launch.json).
[Живой job](../logs/rough/rough_precision_training_20260920/job.json).
ETA до150 с полными оценками15:55–16:10МСК; при полном pass финал350
с проверками ориентировочно17:25–17:50МСК. Это вычислительный прогноз, не гарантия качества.
После150 весь диагностический блок4Flat+16Rough завершается до решения stop/pass.
Следующий бюджет при любом fail не исполняется.
Уточнение наблюдаемости: actor57 видит предыдущее действие, но не имеет стека
наблюдений, рекуррентной памяти, прямого измерения линейной скорости или позиции маршрута.

## История route59/60

**20.09: пользователь запросил продолжение route59/60 после quality stop150.**
Исходная очередь завершилась09:59:13МСК:12stages exit0; оба150,
уровни curriculum `[0,1,1,1,1]`. Все4 Flat100/100 safe и absolute tracking pass.
Seed60 bounded/lateral yaw RMS0,03469683 против relative limit0,03414651;
это единственный относительный отказ. Rough150 ещё не оценивался.
[Исходный окончательный job](results/rough_route_correction_20260920.json) сохранён.

В11:13МСК запущено [продолжение150→350](ROUGH_ROUTE_CONTINUATION.md), ещё200updates
на каждый seed от своегоmodel149 с critic/optimizer/curriculum. Route/trainer/
evaluator/PPO/drift/VRAM guards не менялись;8 новых CPU guard tests прошли.
Предстартовая проверка исходников,checkpoint/export/optimizer и полных Flat rows
пройдена, включая точное раскрытое превышение. Финал соберёт4Flat+48Rough
оценок без автоматической qualification; quality fail150 не отменяется.
[Новый живой job](../logs/rough/rough_route_continue_20260920/job.json).
Supervisor PID10260; seed59 фактически выполняет PPO начиная сiteration150.
[Запись запуска и resume evidence](results/2026-09-20-rough-route-continuation-launch.json).

Записи ниже описывают исходный запуск и предшествующую историю.

**20.09.2026,04:44МСК: Rough57/58 завершили350, общий quality gate не пройден.**
[Аудит](results/2026-09-20-rough-latest-audit.json):54 stages exit0,
199 hashes без расхождений. В48 Rough reports2250/4800 successes;
первые failures:2211 corridor,246 body contact,93 route incomplete.
Все48 tracking gates прошли, но только10 full gates — все у58.
[Полный результат](results/rough_requested_continue_20260920.json):
seed57 прошёл0/24, seed58 —10/24 Rough family/level/profile suites.
У обоих cap2 открыт, но финальные curriculum levels `[0,0,0,0,0]`.
Flat safety —400/400 и абсолютные tracking gates пройдены; относительная
regression к anchor прошла только у58 bounded_v1. Checkpoint350, export
и успешное выполнение вычислений не означают Rough acceptance.

20.09 в09:32 МСК запущена [Rough route correction](ROUGH_ROUTE_CORRECTION.md): seeds59/60
от qualified Flat seed54 actor, свежие critic247/optimizer,50 critic-only
+100+200 PPO, single4096 последовательно; максимум68812800 transitions.
Rough70% получает согласованные команды/reset и22с эпизоды; Flat30% сохраняет
20с и прежний random sampler. Tilt terminal, LR1e-4/std0,1/clip0,1/entropy0,
drift0,25, frozen cases и все regression/quality gates сохраняются.
[Новый job](../logs/rough/rough_route_correction_20260920/job.json) — источник
фактического статуса. Supervisor PID12512; seed59 начал critic calibration,
первые updates и source hashes подтверждены в [launch record](results/2026-09-20-rough-route-launch.json).
Seed60 ожидает своей очереди.144 CPU-теста,1290 vendor hashes и native GPU
train/resume2+2 пройдены; optimizer40→80, обе route/tilt fixtures прошли.
[Верификация](results/2026-09-20-rough-route-validation.json).

[Исследование20.09](ROUGH_RESEARCH_2026-09-20.md) отделяет velocity tracking
от скрытого маршрута и обосновывает проверку выполнимости команд на tile.
Исходный reference уже использован через Flat transfer и anchor54.
Отдельный [baseline runner](../scripts/run_rough_reference_baseline.py)
завершил frozen reference/anchor54 на random0 nominal/bounded_v1,4×100 cases:
reference42/45, anchor39/47 successes; все четыре full gates failed.
[Фактические отчёты](results/rough_reference_baseline_20260920.json).
Это evaluation раскрытого поднабора, не обучение, hold-out или полная qualification.

## История запусков и решений

Записи ниже относятся к указанному времени. Старые PID, ссылки на jobs и
глаголы «запущено/выполняет» сохранены как история, а не текущее состояние.

**20.09.2026,03:09 МСК: по прямому запросу продолжено обучение150→350.**
[Живой job](../logs/rough/rough_requested_continue_20260920/job.json), supervisor
PID29092 на момент запуска. Оба seeds57/58 получают ещё200 updates от
собственных `model_149.pt` с сохранением optimizer/critic/curriculum;4096 env
последовательно. [Отдельный протокол](ROUGH_REQUESTED_CONTINUATION.md).
Открывается предусмотренный stage2 cap2, safe-traversal promotion остаётся прежней.

Предыдущая tilt-correction очередь штатно остановилась в01:31:31МСК:
оба сида завершили150, все4 Flat evaluations100/100 и tracking прошли.
Drift0,04979/0,04729 при лимите0,25. Rough level0: seed57 от22 до44/100,
seed58 от44 до69/100; все первые failures — corridor, tracking RMS прошли.
[Окончательный результат150](results/rough_tilt_correction_20260920.json).

После сообщения об этом пользователь прямо поручил продолжить. Новая очередь
выполняет оставшиеся200 updates/seed и собирает4 Flat +48 Rough evaluations
всех levels0/1/2. Промежуточный fail150 не переписывается; это диагностическое
продолжение и оно не закрывает исходный development protocol. Drift0,25,
VRAM/finite/timeout/export checks сохранены. Технические ошибки прекращают
очередь; после финальных оценок новых training updates не назначается.
Перед стартом повторно проверены hashes/source и первичные20 отчётов,
actor/critic/optimizer обоих родителей.3 новых теста guards продолжения прошли;
training/evaluator код совпадает с пройденным GPU preflight7.

**20.09.2026,00:55 МСК: запущена корректирующая Rough серия.**
[Текущий job](../logs/rough/rough_tilt_correction_20260920/job.json), supervisor
PID30460 на момент запуска. Seeds57/58 последовательно по4096 env, каждый от
своего проверенного `model_49.pt`, optimizer/critic сохранены; далее100+200
updates. [Протокол и полный учёт бюджета](ROUGH_TILT_CORRECTION.md).

Исходная серия остановлена в00:42:10МСК на iteration115 сида57: drift0,25273
при лимите0,25. Оба calibration этапа50 и все4 Flat evaluations100/100 прошли.
[Исходный окончательный результат](results/rough_development_20260920.json).
[Диагностика сохранённого probe](results/2026-09-20-rough-drift-diagnosis.json):
превышение было ДО update0,26653; update его уменьшил.12 сильно наклонённых
наблюдений из4096 дали84,95% squared drift; Flat bank0,06943. Это не основание
исключать их из guard или объявлять policy принятой.

Единственное изменение новой серии — true terminal после tilt>60° дольше0,1с.
Rewards/PPO/terrain/curriculum и все Flat/Rough evaluation gates сохранены.
[GPU preflight7](results/rough_r1_preflight_20260920_7.json) прошёл: реальный
искусственный переворот завершился native terminal через0,12с, time_out=false,
sticky/timer очищены;train/resume2+2 и полная100-case оценка завершены exit0.
YAML comparison: только новый terminal, плюс имена логов и smoke seed.
134 CPU-теста и1290 vendor hashes прошли. Новая серия — проверка причинной
гипотезы; успешное устранение дрейфа и качество locomotion ещё оцениваются.
Неудачные66 updates исходного сида57 сохранены отдельно и явно учтены.

**20.09.2026,00:26 МСК: запущено Rough R1 обучение, seeds57/58.**
Один4096-env процесс за раз, от qualified Flat seed54; по50 critic-only +100 PPO
+200 PPO. Supervisor PID17628; это отметка запуска, текущий статус —
[живой job.json](../logs/rough/rough_development_20260920/job.json).
После50/150/350 обязательны Flat regression; после150 Rough level0,
после350 все уровни0/1/2. Ошибка runtime/drift/VRAM или quality gate прекращает
дальнейшую очередь. Никаких автоматических продлений/замен seeds.
[Фиксированный протокол](ROUGH_DEVELOPMENT.md).

4096 проверены50 updates:26153 transitions/s по времени между updates,
peak7222MiB. Одновременная пара2048+2048 также прошла по50 updates,
aggregate21170 transitions/s,peak10803MiB,minfree12,04%. Single4096 на23,54%
быстрее этой пары.2×4096 Rough не запускались: прогноз13130MiB выше12282MiB.
Все capacity веса discard. [Измерения](results/rough_capacity_20260919.json).

[Финальный preflight](results/rough_r1_preflight_20260920_6.json) прошёл:
nominal blocks level2 и bounded random level2 fixtures, полный100-case random
level0 (4400 physics steps), safe-curriculum train/resume2+2. Исходный Flat actor
прошёл39/100 маршрутов;61 отказ — corridor, запрещённых contacts/tilt отказов
в этой партии нет. Это исходный Rough baseline, не принятие политики и не
неисправность evaluator. Geometry/energy/slip/limits/physical readback сохранены.
Ранние технические попытки1–4 и успешная5 сохранены;6 дополнительно проверяет
полную100-case оценку и JSON-roundtrip cases.131 CPU-тест и1290 vendor hashes
прошли. Основные R1 результаты пока не получены; R2/Stairs не запущены.

Ниже — исторические результаты на указанное время.

**19.09.2026,23:46 МСК: техническая очередь Rough R0 завершена.**
Перенос actor от qualified Flat seed54, новый critic247 и level0 mix выполнены.
GPU PhysX/Fabric:64 env,10000 physics steps +80-step contact fixture; проверены
187 rays и270 spawn probes collision mesh. Train/resume2+2 прошёл, optimizer
step40→80; затем по50 updates на1024/2048 env. Все exit0, export parity0,
finite telemetry;104 updates,3692544 PPO transitions. Все эти веса discard.
[Проверенный итог и hashes](results/2026-09-19-rough-r0-verification.json),
[полная очередь](results/rough_r0_20260919_fix2.json), [протокол](ROUGH_R0.md).

| R0 benchmark | Transitions/s (после первых5 updates) | Минимальный запас VRAM | Финальный drift Rough / Flat bank |
|---|---:|---:|---:|
|1024 env,50 updates|10055,19|55,08%|0,0660 /0,0581|
|2048 env,50 updates|17165,68|50,87%|0,0634 /0,0465|

Измерение относится к одному процессу,level0 и этому mesh;2048 быстрее среди
двух проверенных конфигураций.4096 и два Rough процесса не квалифицированы.
Общий max62°C, telemetry errors0, drift limit0,25 не превышен. Пройдены34 CPU
теста;1290 vendor files и исходные Flat anchors54/55/56 сохранили hashes.

**Полный R0 gate и R1 пока не закрыты.** Следующий обязательный шаг — safe traversal
curriculum вместо выключенной promotion, полный Rough evaluator с route,
collision-shape clearance/slip/energy/limits, bounded physics readback и Flat
regression относительно frozen parent. Основная350-update серия и Stairs не
запускались. Очередь завершилась штатно; низкая загрузка GPU теперь ожидаема.

Две технические ошибки до PPO сохранены: первый bootstrap import остановился
до env;fix1 прошёл10000 physics steps, затем упал на inference-mode contact
injection. Fix2 исправил harness и повторил весь gate без ослабления порогов.
Контакты в smoke не являются policy acceptance:21/64 environments хотя бы раз
имели non-wheel contact за несколько auto-reset episodes; это не success rate
100-case evaluator и не основание считать Rough safe.

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

Очередь Flat завершена после22:26. Следующий Rough R0 выполнен позже;
актуальное состояние и оставшиеся gates приведены в начале журнала.

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
На момент GUI просмотра новая training очередь не запускалась; позднее
выполнен Rough R0, см. начало журнала. [План Rough/Stairs](ROUGH_STAIRS_PLAN.md)
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
