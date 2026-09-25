# Rough R0: первая техническая очередь

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

Зарегистрирована 19.09.2026 до запуска. Родитель — qualified Flat seed54,
checkpoint/actor SHA256 из ROUGH_STAIRS_PLAN.md. Все новые веса discard.
Основная R1 и лестницы этой очередью не запускаются.

Последовательно на desktop RTX4070Ti: 64 env / 10000 physics steps с frozen actor;
64 env / 2 train + 2 resume updates (seed5700, warmup1); 1024 и2048 env /50
updates (seeds5701/5702, warmup1). 4096 сейчас не назначаются.
Bench измеряет полный PPO после одного critic-only update. Первые5 updates
из timings исключены. Основной R1 warmup50 не меняется.
Timeout3600 с/stage, free VRAM≥50% до старта и≥5% во время; telemetry fail останавливает.

Геометрия seed2026091970: 3rows×10cols, tiles12×12 м, spawn square3×3 м;
3Flat/3random/1slope-up/1slope-down/2blocks. Уровни0/1/2 соответствуют плану,
noise и slopes quantization0,005 м на сетке0,1 м, blocks — точные mesh cells0,45 м.
На R0 environments только level0, promotion выключена. Это ещё не safe curriculum.
Reset roll/pitch±0,1; x/y±0,5 на плоском spawn, z относительно terrain origin.
Rewards, actions, physics и yaw sampler0,25 прежние.

Actor57→16, свежий privileged critic247, fixed std0,1, LR1e−4, clip0,1,
entropy0. Drift≤0,25 измеряется на Rough rollout-end observations и неизменном
банке4096 Flat observations из seed54 stage2/reference_update_150.pt.
Это эмпирический Flat bank, не новая независимая приёмка; hash сохраняется.
Actor-only copy, critic changes, optimizer advance после resume и export parity
≤1e−5 проверяются по фактическим артефактам. Исходники/hash сохраняются до старта.

Physics smoke проверяет реальный collision mesh/rays/горизонтальный spawn,
CUDA PhysX/Fabric, finite tensors,187 rays и contacts на каждом physics step.
Дополнительная80-step fixture помещает корпус в землю и требует non-wheel force>1N.
Контакты/маршруты smoke не являются оценкой качества политики.

После технических проверок до R1 остаются safe traversal curriculum, полный
Rough evaluator (route/clearance/slip/energy/limits), bounded physics fixtures
и Flat regression с frozen parent. Наличие checkpoint не закрывает эти gates.
Любой fail сохраняет очередь/weights/logs и останавливает последующие этапы.

Первый запуск rough_r0_20260919 остановился до создания environment: неверный
порядок импорта локального command sampler. Исправлена регистрация robot_lab
перед импортом. Артефакты fail сохранены. Повтор rough_r0_20260919_fix1
использует прежние seeds, поскольку ни physics, ни PPO ещё не выполнялись.
Уточнение текста benchmark warmup1 соответствует фактической команде;
в исходной очереди benchmark не дошёл до запуска.

Повтор fix1 завершил10000 physics steps с finite telemetry, но contact injection
после цикла вызвал PyTorch inference-mode error. Контактная fixture теперь также
выполняется внутри inference_mode. Новый fix2 повторяет весь physics gate;
PPO updates в предыдущих попытках не выполнялись. Пороги не меняются.
