# Reference transfer: короткое дообучение B2W

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

Протокол зарегистрирован19.09.2026 до основного запуска. Статус: подготовлен.
Актуальный статус — [TRAINING_PROGRESS](TRAINING_PROGRESS.md).
Это новый метод обучения, а не пятая абляция contact/height weight.

## Гипотеза и основание

Сохранение проверенного motor skill через actor initialization с critic
calibration даст полезный Flat-кандидат с меньшим бюджетом, чем random-init PPO.
Reference ранее прошёл оба профиля; его наличие не называется новым обучением.

[Parkour in the Wild §2.3](https://arxiv.org/html/2505.11164v1#S2.SS3)
описывает деградацию naive fine-tuning и использует сниженный action noise,
консервативный PPO и предварительное обучение critic при замороженном actor.
Там другая платформа/задача; параметры ниже — наша проверяемая инженерная
гипотеза, не готовый рецепт Unitree. [Обзор](REWARD_RESEARCH.md).

## Зафиксированная конфигурация

| Параметр | Значение |
|---|---|
| Исходный actor | vendor/rl_sar/policy/b2w/robot_lab/policy.pt |
| SHA256 |38155076408e8eccb22690c6c5be14bd1dcb9149245ca5e493308a9f6ff93b34|
| Сеть |57→512→256→128→16, ELU, Identity normalizer |
| Seeds |52/53; общий pretrained actor, свежие critic/optimizer/RNG |
| Основные stages |50 critic-only →100 PPO →200 PPO, cumulative50/150/350 |
| Среды/rollout |4096/24, два trainer параллельно |
| Rewards/physics/reset |Upstream без новых overrides |
| Команды |MeasuredYaw mix0,25; yaw reward1,5, contact−1, height отключён |
| PPO |Native RSL-RL3.1.2, LR1e−4 fixed, clip0,1, entropy0 |
| Action std |0,1 фиксирован для всех16; не обучается |
| Critic warmup |Actor frozen первые50 cumulative updates; critic обучается |
| Drift guard |Raw action RMS относительно frozen reference ≤0,25 на текущих состояниях |
| Ресурсы |Desktop; ≥50% свободной VRAM до training, guard5%, telemetry5 s |
| Бюджет |2×350×4096×24 =68 812 800 transitions максимум |

Остальные PPO параметры upstream, в том числе rollout/epochs/batches/gamma/lambda.
В начальном переносе копируются только actor weights. Случайный critic другой
политики не загружается. Native PPO не переписывается. Между milestones —
сохранение model/optimizer и одинаковые simulator/RNG restarts в обеих ветвях;
iteration49→50 и149→150 без повторных labels. Resume не копирует reference поверх
дообученного actor и проверяет lineage/std/LR/протокол.

## До основного обучения

CPU: architecture/normalizer/finite/295 probes и parity, критик не меняется от
импорта. GPU:16 environments,2 critic updates+resume2, discarded smoke.
Проверить critic/optimizer updates, actor/std invariance, manifests/exits,
checkpoint/export parity. Полный warmup50 также оценивается отдельно.

Замороженные reference и seed49 оцениваются на одинаковых новых cases:
nominal eval seed2026091951, bounded_v1 seed2026091952.
Reference обязан пройти оба; seed49 — comparator, его исходные файлы сохраняются.
Обнаруженный seed49 regression публикуется и не подменяется новым checkpoint.
CPU tests и GPU smoke не доказывают качество.

## Ранние gates и решение

После cumulative50,150,350 —4 evaluations:2 seeds×2 профиля, по100 эпизодов.
Cases и physical digest совпадают с reference; sets после первого просмотра
служат development и не называются нетронутым hold-out.

Каждый gate: ≥99/100 без sticky failures и pooled RMS каждого семейства
vx/vy≤0,20, yaw≤0,25. Оба seeds проходят оба профиля, иначе очередь
останавливается без следующего stage. Only final350 считается кандидатом.
Нет выбора лучшего checkpoint, продления бюджета или автоматического Rough.

Технические ошибки/NaN/hash mismatch/telemetry failures/VRAM<5% также останавливают
очередь. Training VRAM контролируется каждые5 s; неполная telemetry и ресурсы
exports/evaluations проверяются перед следующим stage. Stage timeout3600 s; отдельные exports/evaluations ограничены supervisor.
Drift — только дополнительный ограничитель, не safety guarantee: сравниваются
teacher/student действия на одинаковых текущих состояниях. При critic-only
stage actor parity должна сохраняться; после unfreeze drift измеряется каждый
update и записывается в progress/reference_drift.

Development успех означает, что мы действительно обучили critic и дообучили
actor, сохранив требуемое поведение. Он не доказывает превосходство над reference,
не закрывает three-seed release gate и не является обучением с нуля.
Для acceptance нужен отдельный frozen recipe,3 новых fine-tuning seeds
и2 новых набора. При отказе не повторять автоматически другой std/LR/weight.

## Воспроизведение и артефакты

Команда после commit/push и проверки отсутствия проектных jobs:

~~~powershell
$env:OMNI_KIT_ACCEPT_EULA = 'YES'
.venv/Scripts/python.exe -B -u scripts/run_reference_transfer.py
~~~

Coordinator уникален для этой серии и требует локальные артефакты seed49.
Job: logs/transfer/flat_reference_transfer_20260919/job.json.
Оценки: logs/qualification/flat_reference_transfer_20260919/.
Snapshot источников, protocol, vendor/parent hashes сохраняются до training;
исходники после запуска не менять. Final summary сохраняется в docs/results.
Большие checkpoints и TensorBoard остаются локально вне Git.
