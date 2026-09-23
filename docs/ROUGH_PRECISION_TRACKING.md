# Rough: точность отслеживания скорости

20.09.2026. Следующий ограниченный development опыт после route59/60.
Основание: [итог350](results/rough_route_continue_20260920.json),
[диагностика](results/2026-09-20-rough-route-diagnosis.json) и
[исследование методов](ROUGH_RESEARCH_2026-09-20.md).
Этот протокол фиксируется до GPU preflight и основной очереди.

## Измеренная проблема и гипотеза

Route59/60 завершили350: 2653/4800 успешных Rough эпизодов, но0/48 полных
family/level/profile suites. Первые отказы:1888 corridor,249 body contact,
10 route incomplete. Flat400/400 safe и все absolute tracking pass, но3/4
relative regression gates не пройдены. Curriculum `[0,1,2,2,1]` у обоих.

Среди corridor failures ближайшая к root граница — forward1146 и negative-y742.
Это только proxy: gate проверяет колёса, их координаты в first_failure не сохранены.
Средний signed vx bias traverse +0,02905/+0,03596 м/с для59/60; измерение
охватывает весь эпизод, включая время после первого отказа. Корреляция и поздний
overshoot поддерживают гипотезу накопления ошибки, но не доказывают её причинность.
У старого58 random0 был существенно лучше; variance между seeds велика.

Меняем один общий параметр точности: std обоих exponential tracking kernels
0,5→0,25. Функции из immutable robot_lab, веса linear3/yaw1,5, frames и upright
factor сохраняются. При ошибке0,05 снижение linear kernel меняется примерно
с1% на3,9%; локальная чувствительность возрастает в4 раза. Это наша проверяемая
гипотеза, а не найденный в статье оптимальный коэффициент. Ширина применяется
одинаково на Flat и Rough training tiles, чтобы избегать второй ветви reward.

Actor57 не наблюдает позицию маршрута, линейную скорость или историю.
Более точная награда не добавляет position/heading feedback и не гарантирует
долгий проход коридора. Curriculum проверяет root square±5,4 м и progress,
evaluation — узкий wheel corridor и полное прохождение: promotion не равно pass.

## Reference, recipe и бюджет

- Свежие seeds61/62, actor от квалифицированного Flat54, свежие critic247 и
  optimizer. Исходный reference уже является предком54. Failed349 не продолжаются.
  Drift сравнивается с54 на Rough states и frozen Flat bank; это stop guard,
  не BC/KL loss. Reference/anchor random0 full gates failed, поэтому имитацию
  исходной reference на всём Rough не добавляем.
- По50 critic-only +100+200 PPO, максимум68812800 transitions на пару.
  Single4096 последовательно на RTX4070Ti. Smoke64:2+2 updates с warmup1,
  все эти веса discard. Новые seeds позволяют проверить повторяемость;
  сравнение с59/60 историческое, не строгий paired causal experiment.
- PPO LR1e-4 fixed, clip0,1, entropy0, exploration std0,1 fixed, rollout24;
  actor57→16 и critic247. Route distribution/reset/22с, Flat30%, terrain,
  physics, randomization, tilt terminal>60°/>0,1с и drift limits0,25 прежние.
  Никаких других reward изменений, новых observations или скрытой навигации.

## Проверки и остановки

Перед очередью: CPU tests,1290 vendor hashes, native64 route/tilt fixtures,
проверка обеих native reward functions на synthetic и live CUDA tensors,
PPO/resume2+2, optimizer/export parity. Serialized effective env/agent configs
сравниваются с историческим route run: разрешены только tracking std,
задекларированные seed/env-count/log-path и штатные workload поля.

После50/150/350 — по4 Flat reports (2seeds×2profiles×100cases): safety≥99,
absolute scenario RMS≤0,20/0,20/0,25 и прежний relative gate к54.
После150 — ещё16 Rough reports (2seeds×4families×2profiles, level0),
development success≥90% отдельно по traverse/stand/turn, прежний tracking.
На150 собирается весь блок Flat+Rough даже при quality failure одной оценки;
затем любой fail запрещает следующие training updates. После50 Flat fail
также останавливает дальнейшие updates. Technical/drift failure — немедленный stop.

Только если150 полностью пройден: ещё200updates/seed до350, затем4Flat+
48Rough (levels0/1/2),≥95% каждого kind/family/profile и curriculum level2
на всех четырёх rough families. Это development pass; policy acceptance
и qualification автоматически не объявляются. Cases раскрытые, не hold-out.
Evaluator/corridor/contact/route thresholds и hashes сохраняются.

Source/protocol/cases/checkpoint SHA256 frozen; child launch требует≥50% свободной
VRAM, во время≥5%; train timeout3600с, evaluation1800с. Только собственные
дочерние процессы. Нет автопродления бюджета, замены seed или выбора удобного
checkpoint после результата. Старые fails и протоколы сохраняются.

## Следующие решения

1. Проверить, уменьшились ли signed bias и corridor failures при сохранении
   Flat. Сравнивать все seeds/profiles/kinds, учитывать post-failure bias limitation.
2. Если остаётся только Flat regression при улучшении Rough, отдельно проверить
   ограниченный Flat distillation/BC к54 на frozen и свежих Flat states;
   не смешивать это изменение с текущим reward опытом.
3. Если bias мал, а corridor fail сохраняется, сначала сохранять wheel pose,
   heading и velocity до первого отказа. Отдельно согласовать curriculum
   boundaries с реальной wheel geometry; это изменение training criterion,
   старый evaluator остаётся контрольным. Не продолжать бесконечный reward sweep.
4. При недостаточной наблюдаемости — отдельный контракт history/velocity estimator
   и teacher/student либо отдельный navigation controller. Для нового ABI нужны
   собственные export/runtime/Flat gates; нынешняя57-policy молча не заменяется.
5. После полного development pass — новые qualification seeds/cases; затем Stairs.
   Hardware и серверные gates остаются отдельными.

## Запуск

`scripts/run_rough_precision_preflight.py --attempt 1`

`scripts/run_rough_precision_training.py --preflight docs/results/rough_precision_preflight_20260920_1.json`

Требуются локальные runtime,anchor и исторические config/report artifacts.
Job: `logs/rough/rough_precision_training_20260920/job.json`.
Итог: `docs/results/rough_precision_training_20260920.json`.
Ориентир до150 с полными проверками —45–60мин от старта; если пройдено,
до финала350 — ещё90–100мин. ETA вычислительный, сходимость не обещается.
Текущая стадия и фактический старт — в [TRAINING_PROGRESS](TRAINING_PROGRESS.md).
