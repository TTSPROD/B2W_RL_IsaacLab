# Единая reference-compatible policy: Flat → Rough → Stairs

**Цель 20.09.2026:** продолжить уже квалифицированную Flat policy в одну lineage
B2W, чей deployable actor идентичен reference по контракту и формату, затем
дообучить её на Rough и обычных лестницах. Actor всегда57→16. Route navigation,
perception и расширение actor inputs не входят в первый этап.

Reference зафиксирован локальным snapshot `fan-ziqi/rl_sar` commit
`376d42c9b128f963ab08579762d5a216a976ce39`; `main` используется только для
сверки, но не как плавающая training dependency. Upstream:
<https://github.com/fan-ziqi/rl_sar/tree/main/policy/b2w>.

## Что означает «идентична reference»

| Поле | Обязательный контракт |
|---|---|
| Actor | `57→512→256→128→16`, ELU, Identity normalizer, без recurrence/history |
| Observations | `ang_vel(3), gravity(3), commands(3), dof_pos(16), dof_vel(16), previous actions(16)` |
| Scales | ang vel `0,25`, gravity/commands/position/action `1`, dof vel `0,05` |
| Actions | 12 leg position targets + 4 wheel velocity targets |
| Action scales | legs `[0,125;0,25;0,25]×4`, wheels `5,0×4` |
| Частота | physics `0,005 с`, decimation `4`, actor `50 Гц` |
| Joint order | FR, FL, RR, RL; hip/thigh/calf, затем wheels FR/FL/RR/RL |
| Export | TorchScript `policy.pt`, вход `[N,57]`, выход `[N,16]` |

`lin_vel_scale` присутствует в upstream config, но linear velocity не входит в
список observations и не добавляется actor. Reference weights могут совпадать
бит-в-бит только при инициализации. После PPO под «идентичностью» понимается
архитектурная, ABI и runtime совместимость; обученные веса закономерно другие.

Critic не экспортируется и может видеть privileged данные. Текущие Flat anchors
имеют critic60, поэтому на границе Flat→Rough необходим один явный переход к
critic247: blind prefix57 + body linear velocity3 + height scan187. Actor при
этом копируется без изменений. После перехода Rough→Stairs продолжается полным
resume actor+critic+optimizer. Это **не** teacher247: actor всегда получает57.

## U0: существующий Flat foundation

Flat foundation уже получен: seeds54/55/56 имеют actor57→16, resumable
checkpoints и прошли nominal/bounded_v1 по100/100 с tracking gates. Канонический
parent для terrain development — seed54, выбранный заранее по минимальному
номеру, а не по лучшей метрике. Seeds55/56 остаются frozen comparators.

Перед продолжением повторяется только compatibility gate: checkpoint/export
hashes, точные57 terms/order/scales, network/Identity,16 actions, PD/action
mapping, clip semantics и export/eager/live parity. Повторное Flat PPO не нужно.

## U1: переход critic60→247 и Rough locomotion

U1 создаёт две development-линии seeds69/70 из одного frozen actor seed54:
новые critic247, optimizer и RNG, один4096-env процесс последовательно. Первые50
updates — critic-only на зарегистрированном Flat+easy-Rough mix. После50 actor
должен bitwise совпадать с seed54, export/live parity и обе Flat evaluations
должны пройти. Это единственная граница, где full optimizer resume невозможен
из-за смены critic shape; provenance фиксируется явно.

После critic calibration U1 продолжает собственные checkpoints полным resume
actor+critic+optimizer и включает PPO для Rough locomotion.
Actor architecture и57 observations не меняются; повторная загрузка reference
или Flat54 actor после первых50 updates запрещена.

- Задача этапа — локальная locomotion по terrain при заданных `vx,vy,yaw`, а не
  абсолютная навигация по corridor. Position/heading route feedback не является
  частью policy acceptance.
- Flat rehearsal сохраняется вместе с rough families; curriculum повышает
  геометрию только после безопасного traversal. Level0 → level1 → level2,
  up/down slope и blocks оцениваются раздельно.
- Первый development budget:100 PPO updates/seed после warmup, то есть milestone150,
  затем общий Flat+Rough gate. Совокупно до150:29 491 200 transitions.
  Только pass обоих seeds разрешает следующие200. Один-factor изменения,
  заранее фиксированные rewards/PPO/terrain mix и никаких post-hoc sweeps.
- Rough acceptance: ≥95/100 для каждого family/level/profile/seed, tracking,
  progress, collision/tilt, terrain-relative clearance, slip, energy и
  saturation. Flat regression остаётся обязательной после каждого milestone.

Результаты57–66 сохраняются как важная отрицательная история: они смешивали
locomotion с open-loop route/corridor acceptance. Они не становятся parents и
не доказывают, что reference-compatible actor неспособен к Rough locomotion.

## U1.1: зарегистрированная коррекция sampling

Первый U1 показал две связанные границы: seed70 потерял Flat backward tracking,
а seed69 улучшил slope_up относительно Flat54 с88/100 до92/100, но не достиг95%.
U1.1 меняет **только** proportions training terrain при неизменных actor57,
critic247, rewards, PPO, командах, geometry,50+100+200 budget и thresholds:

| Family | U1 | U1.1 |
|---|---:|---:|
| flat |0,30|0,40|
| random |0,30|0,10|
| slope_up |0,10|0,20|
| slope_down |0,10|0,10|
| blocks |0,20|0,20|

Это даёт на33% больше Flat rehearsal и вдвое больше slope_up exposure; random
снижается, потому что seed69 уже прошёл random100/100. Новые development seeds
71/72 начинаются заново от actor54 и нового critic247. После50 actor bitwise
равен parent; после150 обязательны Flat gates. Rough level0 оценивается для
каждого seed, прошедшего Flat, даже если второй seed остановил общий acceptance;
это только диагностика, общий pass всё равно требует оба seed и все профили.
Только общий pass150 открывает штатные200 updates stage2. Post-hoc продолжение,
замена seed, изменение reward/contact penalty и ослабление95% запрещены.

Фактический итог U1.1: seeds71/72 остановлены на150. Оба сохранили safety, но
каждый превысил один relative Flat threshold в разных profile на малую величину.
Slope_up nominal дал100/100 у71 и77/100 у72; у72 все23 failures — calf contact.
Следовательно sampling полезен, но один не стабилизирует actor между seeds.
[Result](results/unified_u11_training_20260920.json),
[diagnostic](results/unified_u11_slope_diagnostic_20260920.json).

## U1.2: зарегистрированная contact-коррекция

U1.2 сохраняет весь U1.1 recipe и меняет ровно один коэффициент:
`undesired_contacts` с−1 на−3. Основание —23 calf-contact failures seed72 при
полностью пройденных stand/turn и более раннее снижение Flat contact failures
при−3. Actor57, critic247, std0,1, PPO, terrain proportions,50+100+200 budget,
cases и thresholds неизменны. Новые seeds73/74 начинаются от frozen actor54;
U1/U1.1 checkpoints не продолжаются. До main run обязателен отдельный discard
preflight, затем последовательный1×4096 запуск и прежние stop rules.

Фактический итог U1.2: quality stop150; Flat relative gates провалены у обоих
seeds, slope_up74/100 и73/100 с26/27 body contacts. Усиление contact penalty
ухудшило целевую метрику и отклонено. Следующий опыт не должен менять reward;
нужна явная стабилизация actor относительно frozen Flat bank поверх U1.1.
[Result](results/unified_u12_training_20260920.json),
[diagnostic](results/unified_u12_slope_diagnostic_20260920.json).

## Репликация U1.1 на seeds75/76

После сверки с upstream B2W/Go2W/Go2 подтверждено, что канонический вес
`undesired_contacts` равен−1; поэтому U1.2 не продолжался. Неизменный U1.1
recipe повторён на новых seeds75/76 после нового preflight5/5. Оба прошли
critic-only50 и Flat gates50. На150 seed75 прошёл оба Flat profile100/100;
seed76 сохранил safety200/200 и абсолютные tracking thresholds, но провалил
relative gate: stand/vx на0,00084 nominal, а bounded дополнительно lateral/vx
на0,00464 и lateral/yaw на0,00994 сверх допуска.

Seed75 Rough level0: random100/100 в обоих profiles, blocks100/100 в обоих,
slope_up95/100 nominal и89/100 bounded, slope_down100/100 nominal и88/100
bounded. Все28 failures — body contacts: slope_up5+11 на calf, bounded
slope_down12 на hip/base. Порог задаётся отдельно для traverse60, поэтому
slope_up nominal95/100 overall всё равно fail: traverse55/60<95%.
Общий результат — quality stop150, следующие200 и U2 не запущены. Простое
повторение U1.1 не дало воспроизводимого кандидата; следующие опыты не должны
перебирать reward weights или cherry-pick seed75.
[Preflight](results/unified_u11_preflight_20260920_2.json),
[result](results/unified_u11_replication_20260920.json).

## U2: обычные лестницы как продолжение U1

U2 открывается только после Rough qualification и продолжает собственные
U1 checkpoints с полным resume того же actor57, critic247 и optimizer.

1. Сначала frozen baseline без updates на прямых регулярных stairs: up/down,
   несколько заранее зарегистрированных высот/глубин ступени, nominal/bounded.
2. Затем curriculum от низких широких ступеней к целевой геометрии. Команда —
   только существующие `vx,vy,yaw`; будущий профиль лестницы actor не видит.
3. Rehearsal mix содержит Flat и пройденный Rough, чтобы контролировать forgetting.
   Up/down, остановка до/после лестницы, контакты, clearance, slip/energy и
   saturation имеют отдельные gates.
4. Если blind57 систематически не проходит из-за необходимости видеть ступень
   до контакта, это фиксируется как измеренное ограничение. Perceptive/history
   policy тогда создаётся отдельной будущей ABI-линейкой, но не подменяет
   текущую reference-compatible цель.

## Порядок ближайшей работы

1. Завершено20.09: compatibility и U1 GPU preflight,5 stages pass; frozen
   Flat54 прошёл locomotion random level0 nominal100/100. Это baseline, не
   qualification. [Evidence](results/unified_u1_preflight_20260920_1.json).
2. Завершено20.09: seeds69/70 дошли до150. Seed69 прошёл Flat, seed70 провалил
   relative Flat regression на backward/backward-stop `vx`; общий gate остановил
   очередь до Rough и до следующих200. [Evidence](results/unified_u1_training_20260920.json).
3. Post-stop frozen seed69 на Rough level0 nominal: random100/100, blocks100/100,
   slope_down99/100, slope_up92/100; все9 failures — body contact. Это diagnosis,
   не qualification; bounded не выполнялся.
   [Evidence](results/unified_u1_seed69_rough_diagnostic_20260920.json).
   Frozen Flat54 на slope_up дал88/100, поэтому U1 улучшил навык, но100 PPO
   updates не хватило до95%; простой rollback/заморозка actor проблему не решит.
4. U1.1 и его независимая репликация75/76 завершены quality stop150; U1.2
   отклонён. Следующий дизайн — actor anchoring относительно frozen Flat bank
   при неизменных reference rewards и U1.1 terrain sampling; до запуска нужны
   unit/gradient/native preflight и новые seeds.
5. После Rough qualification перейти к U2; route-controller/corridor вернуть
   позднее как отдельный системный navigation gate поверх готовой locomotion.
6. Sim2sim, SDK2 offline replay и hardware остаются отдельными этапами;
   live robot actuation не разрешается.

[Контракт](POLICY_CONTRACT.md), [фактическая история](TRAINING_PROGRESS.md),
[инфраструктура](INFRASTRUCTURE.md), [исторический blind план](ROUGH_STAIRS_PLAN_BLIND_ARCHIVE.md).
