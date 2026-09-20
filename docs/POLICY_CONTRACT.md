# Контракт B2W57→16

**Обязательное уточнение20.09:** actor сохраняет57 входов и16выходов,
точно как reference, с прежними order/scales/50Hz. Teacher247 отклонён.
Privileged critic не расширяет actor ABI. Целевая trainable lineage сохраняет
reference actor `57→512→256→128→16`, ELU, Identity, без history. Qualified
Flat54 подходит как actor-parent. Один явный переход critic60→247 выполняется
с frozen actor; далее Rough→Stairs идёт full resume. Route controller не входит
в первый training этап; saturation/hardware gates открыты.

Проверено 17 сентября 2026. CPU export parity и live observation/action parity
в Isaac выполнены для reference, seeds 42/43/44 и завершённых yaw-абляций. Контракт
проверен частично: saturation и аппаратный mapping остаются открытыми,
`stage_1_complete=false`. Исходники `vendor/` не изменены.

## История blind57 до teacher пересмотра20.09.2026

Rough путь сохраняет actor57→16/Identity/50Hz, critic247 с187 height rays.
Critic не передаёт terrain или velocity estimates actor. Export/live checks
и завершение350 у57/58 не закрыли quality gate:
[аудит199 hashes](results/2026-09-20-rough-latest-audit.json),
[исследование ограничений blind57](ROUGH_RESEARCH_2026-09-20.md).

Проводился [route correction59/60](ROUGH_ROUTE_CORRECTION.md): actor qualified
seed54, новые critic/optimizer,50+100+200 single4096. Исходная reference
уже использована в lineage seed54; её повторный actor-only import не является
resume training state. Rough-only commands/reset/22с меняют episode protocol,
Flat30% сохраняет20с и прежние команды. Observation/action ABI, tilt terminal,
PPO/drift0,25, parity и Flat/Rough gates сохраняются. Экспорт новых финалов
проверяется отдельно; до их фактического pass acceptance не объявляется.
[Завершённый исторический job](../logs/rough/rough_route_correction_20260920/job.json).

Frozen reference/anchor54 comparator на random0 завершён4×100:
42/45 и39/47 successes nominal/bounded; ни один full gate не пройден.
[Отчёт](results/rough_reference_baseline_20260920.json) не меняет ABI и
не является полной Rough квалификацией. Saturation и hardware gates ниже открыты.

## Выполненные проверки

Дополнение после исходной проверки seed 42: оба финальных reward checkpoints
прошли экспорт на 295 входах с max error 0. Их bounded_v1 replay и reference
прошли 100/100 без отказа и tracking gate; live observation/action checks
выполнялись на каждом шаге. [Итог reward](results/2026-09-17-yaw-reward-final.json),
[физические diagnostics](results/2026-09-17-flat-qualification-preflight.json).
Ниже численные данные seed 42 сохранены как отдельный исторический результат.

- `scripts/check_policy_contract.py`: 39 fixtures — neutral/reset, каждый
  сустав по позиции и скорости, вращение колёс, ±yaw command, ±roll, stop
  с history и reset после stop.
- Реальный `vendor/rl_sar/policy/b2w/robot_lab/policy.pt` загружен на CPU.
  TorchScript и восстановленная eager-сеть с теми же экспортированными весами:
  max abs error **0**; batch против отдельных вызовов **2.15e-6**, допуск **1e-5**.
  Исходного training checkpoint rl_sar в snapshot нет; эта проверка его не заменяет.
- Финальный локальный PPO checkpoint seed 42 `model_4999.pt` после 5000 updates
  загружен в RSL-RL `ActorCritic`, экспортирован штатным Isaac Lab `exporter.py`
  и повторно загружен через `torch.jit.load`. `act_inference` против экспорта:
  **295 входов, max abs error 0**. Ранее тот же тест прошли smoke и benchmark checkpoints.
- В reference и проверенных локальных actor normalizer — `Identity`,
  recurrence отсутствует. Размеры actor input/output — 57/16.
- Сопоставлены upstream конфиги: порядок, default pose, scales, частоты,
  stiffness/damping и nominal effort limits. Штатная
  `joint_pos_rel_without_wheel` выполнена на CPU с перестановкой суставов.
- В live Isaac replay для reference и финального seed 42 проверены фактические
  joint indices, observations и physical action targets. Max abs error **0**;
  в пройденных траекториях saturation mismatch не возникал.
- 8 CPU-тестов контракта и 3 vendor tests прошли. При отсутствии torch/PyYAML
  8 тестов контракта в лёгком bootstrap CI пропускаются.

| Артефакт | SHA256 |
|---|---|
| Reference policy | `38155076408e8eccb22690c6c5be14bd1dcb9149245ca5e493308a9f6ff93b34` |
| Seed 42 `model_4999.pt` | `282e2ed8930c5d17a747ceae3ff8457ddb015df70b90029f98463ace564e902b` |
| Проверенный экспорт seed 42 | `68d4153285db3e2702fdf1e5346896aef9362f9d643ebcd75e5666c8fb14c0d1` |

Хэши конфигов, источников и exporter сохранены рядом с экспортом;
vendor hashes сверяются с `vendor/manifest.json` при CPU проверке.

## Результаты движения в Isaac

`scripts/replay_reference_b2w.py` использует прямые physics steps без auto-reset.
Падение или запрещённый контакт фиксируется на каждом physics step с начала
запуска и остаётся неуспехом даже после восстановления. Политика активна
в течение 2 s settling и последующих 20 s измерения.

| Проверка | Reference rl_sar | Обученный seed 42 |
|---|---|---|
| Nominal replay, 16 эпизодов | 16/16 без падения/запрещённого контакта; tracking пройден | 15/16; контакт при положительном yaw, tracking поворотов не пройден |
| Flat100, удержанные команды и начальные позы | 100/100 без падения/запрещённого контакта; tracking 100/100 | 96/100; tracking 84/100 |
| Single-policy Flat thresholds | Пройдены на этом наборе | **Не пройдены** |

Все четыре неуспеха seed 42 в Flat100 — запрещённые контакты при положительном
повороте; отрицательный поворот также не проходит tracking gate. Общий порог
без падений/контактов ≥99% не достигнут. 95% Wilson interval для 96/100:
90.16–98.43%; для reference 100/100: 96.30–100%. Интервалы описывают этот набор,
не учитывают variability training seeds или физическую randomization.
Evaluation seed — 20260917; mass/friction/actuator/push randomization отключена.
Это отдельная оценка качества после экспорта, а не следствие нулевой export error.

Zero-action PD stand — отдельная проверка механического удержания default pose:
она **не пройдена**, 16/16 сред нарушили contact gate на 0.79 s. Её нельзя
переименовать в успешный stand по результату активной reference policy.
Подробнее о физической модели и stand diagnostic — [ROBOT_MODEL_COMPARISON.md](ROBOT_MODEL_COMPARISON.md).

## Машиночитаемые результаты

- Финальный checkpoint:
  `logs/rsl_rl/unitree_b2w_flat/2026-09-17_07-17-25-907539_flat_pilot_seed42_20260917/model_4999.pt`.
- CPU fixtures и экспорт: `logs/qualification/flat_seed42_final/export/report.json`
  и `export/policy-contract-export/{policy.pt,manifest.json}` в том же каталоге.
- Live replay: `logs/qualification/reference_replay_20260917.json` и
  `logs/qualification/flat_seed42_final/nominal_replay.json`.
- Flat100: `logs/qualification/flat_seed42_final/flat100.json` и
  `reference_flat100.json`; независимые exit codes для export и evaluation
  равны 0 и сохранены в `external_exits.json` того же каталога.
- Исходная smoke-проверка: `logs/setup/policy-contract.json` и
  `logs/setup/policy-contract-export/`; её checkpoint содержал только два PPO updates.

Эти артефакты исключены из Git. Флаги `policy_quality_evaluated=false` в CPU
export report/manifest обозначают область CPU-проверки; отдельные evaluation
отчёты выше содержат фактическую оценку. Аналогично CPU-отчёт не включает
последующий live replay или отдельное сравнение моделей.

```powershell
.\.venv\Scripts\python.exe scripts/check_policy_contract.py --training-checkpoint logs/rsl_rl/unitree_b2w_flat/2026-09-17_07-17-25-907539_flat_pilot_seed42_20260917/model_4999.pt --report logs/qualification/flat_seed42_final/export/report.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Без `--training-checkpoint` проверяется только reference; отчёт сохраняет
`training_checkpoint_export_parity=false`. Для другого реального checkpoint
передать его путь; рядом должны быть исходные `params/agent.yaml`.

## Проверенный программный ABI

Policy order: FR, FL, RR, RL, для каждой ноги hip/thigh/calf; затем колёса
FR/FL/RR/RL. Конфиг `rl_sar joint_mapping` — identity, без инверсии знаков.
Это программное соглашение; firmware motor order и реальные знаки не проверены.

Порядок articulation в локальном runtime — FL/FR/RL/RR по группам
hip/thigh/calf/foot. Индексы выборки из articulation в policy order:
`[1,5,9,0,4,8,3,7,11,2,6,10,13,12,15,14]`. Эта перестановка проверена
CPU fixtures и фактическим live manager resolution в Isaac replay.

| Вход (индексы Python) | Содержание | Scale |
|---|---|---|
| 0:3 | angular velocity, body frame | 0.25 |
| 3:6 | gravity в body frame, quaternion wxyz | 1 |
| 6:9 | vx, vy, yaw commands | 1 |
| 9:25 | relative joint positions; wheel slots всегда 0 | 1 |
| 25:41 | joint velocities | 0.05 |
| 41:57 | previous raw action; reset = 0 | 1 |

Targets: 12 позиций в rad = default `[0,0.8,-1.5]` ×4 + action ×
`[0.125,0.25,0.25]` ×4; 4 скорости колёс в rad/s = action ×5.
Physics dt 0.005 s, decimation 4, policy 50 Hz.

## Reference transfer: выполненный путь адаптации

`reference_transfer.py` переносит только actor из зафиксированного
`vendor/rl_sar/policy/b2w/robot_lab/policy.pt` в новую RSL-RL policy.
ABI сохраняется: 57→16, MLP `[512,256,128]`, ELU, `Identity` normalizer,
тот же порядок суставов и action scales. Critic (Flat input 60) и optimizer
создаются заново; исходный reference не содержит их training state.

Это адаптация pretrained actor, не обучение с нуля и не точный resume
исходного PPO rl_sar. Один только импорт скачанной политики не считается
выполненным локальным обучением. Seeds 52/53 разделяют один начальный actor;
различаются новые critic/RNG, поэтому это seeds адаптации общего reference.

Исторический протокол включает50 updates только critic при замороженном actor, затем100 PPO
и ещё 200 PPO updates. После каждого stage выполняется development-оценка;
следующий stage допускается только по заранее заданному правилу. Фиксированные std 0,1, LR 1e−4, clip 0,1 и entropy 0
относятся к этому протоколу. Rewards и policy ABI не меняются.
[Точные условия](REFERENCE_TRANSFER.md).

Импорт требует проверки архитектуры, ключей/форм/конечности tensors, Identity,
SHA256 reference и parity на синтетических и фактических observations.
Resume adaptation должен сохранять обученный actor/critic/optimizer и не
копировать reference actor повторно. CPU-проверки нового пути и smoke сами
по себе не устанавливают качество; фактические результаты записываются в
[TRAINING_PROGRESS](TRAINING_PROGRESS.md). Для каждого результата остаются
отдельными gates экспорт, live parity и policy evaluation.

## Несовпадения и оставшиеся gates

**Saturation parity не проходит.** `rl_sar` масштабирует observation, затем
ограничивает ±100; Isaac Lab ограничивает каждый исходный term, затем
масштабирует. При joint velocity 200 rad/s получается 10 против 5.
`rl_sar` ограничивает raw action ±100 до scale; Lab ограничивает physical
position/velocity targets после scale/offset. При wheel raw action 200:
500 против 100 rad/s. Это fixture за границей рабочего диапазона, не разрешённая
команда роботу. Previous action также различается после raw-action saturation.
Отсутствие saturation в проверенных replay не устраняет это различие.
Upstream обучение оставлено без изменения этих правил.

Training observation noise отключён в детерминированном сравнении; body gravity
и C++ adapter воспроизведены в Python, C++ код не компилировался. Проверки NaN,
Inf, quaternion и age >20 ms относятся к локальному offline adapter; они
не доказывают наличие watchdog в rl_sar или безопасность остановки на роботе.
20 ms — период policy для теста, не утверждённый аппаратный timeout.

Следующие gates:

0. U1 seeds69/70 подтвердил runtime actor57→16 и critic247, но не quality pass:
   seed70 провалил Flat backward regression, а frozen seed69 diagnostic дал
   slope_up92/100 из-за calf contacts. До нового двухсидового запуска требуется
   зарегистрированный retention/contact recipe; ABI actor менять нельзя.

1. Для каждого нового финального checkpoint повторить CPU export и live parity,
   затем Flat100. Для seeds 42/43/44 и yaw-абляций это выполнено;
   для 45/46/47, seed48 schedule experiment и
   [staged seeds 49/50/51](STAGED_QUALIFICATION.md) parity также проверена.
   Staged-серия завершена, общий quality gate не пройден: только seed 49
   прошёл nominal и bounded. Parity не заменяет качество политики.
   Seed 42 quality gate остаётся непройденным.
2. Разрешить clipping/history различия в deployment adapter вне `vendor/`
   и проверить saturation, reset и invalid-input fixtures на его реальном коде.
3. На основе выполненного [сравнения моделей](ROBOT_MODEL_COMPARISON.md)
   согласовать kinematics, inertial, contact, limits и torque-speed model
   Isaac/MuJoCo; затем выполнить sim2sim на тех же сценариях.
4. Перед hardware trials отдельно проверить SDK order/signs, firmware modes,
   C++ replay, watchdog и stop behavior по этапам [плана](PROJECT_PLAN.md).

Программная parity и прохождение reference replay не дают sim2real допуска.
Текущее обучение и результаты его новых seeds: [TRAINING_PROGRESS.md](TRAINING_PROGRESS.md).
