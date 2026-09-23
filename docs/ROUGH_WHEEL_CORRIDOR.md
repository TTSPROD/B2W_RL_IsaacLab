# Rough: согласовать обучение с wheel corridor

20.09.2026. Зарегистрирован следующий bounded development опыт после
[precision150](results/rough_precision_training_20260920.json).
Используются ограничения исходного evaluator, без ослабления приёмки.

## Основание

Seeds61/62 штатно остановились15:56:59МСК на150. Flat400/400 safe,
все4 absolute/relative regression checks passed. Rough level0:1124/1600
successes,0/16 полных suites, все476 первых отказов — corridor.
Оба curriculum достигли `[0,1,1,1,1]`, что не означает прохождения evaluation.

Training проверял root square±5,4м, тогда как evaluation использует центры
четырёх колёс: x∈[−0,6;5,4], y∈[−0,9;0,9]. Боковой уход и пересечение передним
колесом могли считаться successful training traversal. Это расхождение
постановки задачи; его устранение ещё не доказывает достаточность actor57.

[Passive traces](results/rough_corridor_trace_20260920.json) повторили random0
nominal100 на обоих финалах150. Все200 raw rows побитово совпали с прежними
числовыми JSON values: command/action/physics и gates не менялись.
У61 точные первые пересечения:18 negative-y/4forward; у62:7negative-y/16forward.
Положения колёс, heading, velocities и команды сохранены20Hz, первый выход200Hz,
bias только до первого failure. Это поднабор; выводы не обобщаются на все terrains.

## Единственная связанная поправка

В Rough training вводится wheel-corridor constraint по тем же строгим
неравенствам, что в evaluator. На каждом physics step200Hz пересечение
любой границы любым колесом становится sticky failure до native reset.
При ближайшем policy step50Hz это true terminal (`time_out=False`), поэтому
PPO не bootstrap-ит нарушение как штатный timeout. Такая же sticky запись
запрещает curriculum promotion этого episode. Отдельного reward penalty нет.

Это один constraint, согласованно включённый в termination и curriculum;
эффекты этих двух точек отдельно данный опыт не идентифицирует.
Flat terrain columns0–2 исключены из нового terminal; их прежние условия
reset, sampler и timeout сохраняются. Действующий sustained tilt terminal
и остальные failure checks остаются. Partial sticky flags очищаются на reset;
family levels/optimizer восстанавливаются только из собственного нового checkpoint.

Actor57→16 сохраняется: он видит previous action, но не наблюдает global
route position, linear velocity, history stack или recurrent state.
Никакого navigation feedback, коррекции команд или скрытого heading controller
нет. Terminal обучает избегать плохих переходов при прежних наблюдениях;
он не добавляет отсутствующую информацию и не гарантирует удержания коридора.

## Recipe и бюджет

Свежие seeds63/64 от qualified Flat54 actor; у каждого новый critic247 и
optimizer. Failed150 не продолжаются с изменённой terminal/value function.
Исходная reference уже является предком54; frozen Rough и Flat-bank drift
guards0,25 сохраняются. Это transfer общей линии, не независимый from-scratch.
Сравнение с61/62 историческое, не paired causal control.

По50critic-only +100PPO +200PPO, максимум68812800 transitions на пару.
Single4096 последовательно на квалифицированной RTX4070Ti; GUI не совмещать.
LR1e-4 fixed, clip0,1, entropy0, action std0,1 fixed, rollout24;
tracking kernelsstd0,25 с weights3/1,5, все остальные rewards прежние.
Route commands/reset/22с, Flat30%, terrain geometry/mix, actuator/physics,
randomization и actor ABI сохраняются.

## Предстартовые проверки

CPU boundary/Flat-mask/sticky/partial-reset/curriculum/resume tests и vendor
hashes. Passive replay diagnostics завершены до подготовки основной очереди.
Discard64: native PhysX injections по всем4границам для Rough и Flat;
проверяются term manager, true-terminal/time_out, sticky clear и Flat exemption.
Прежние native route/tilt/precision fixtures,2+2PPO/resume, optimizer steps
и export parity обязательны. Все64-env веса discard.

Полные serialized env/agent configs сравниваются с frozen historical route:
разрешены прежние два precision std и ровно один новый wheel terminal.
Одновременно manifest/checkpoint подтверждают wheel-aware curriculum.
Остальные dynamics, PPO и observation/action настройки не нормализуются.
Source/protocol/cases/historical configs/anchor SHA256 фиксируются до запуска.

## Milestones и stops

После50/150/350 —4Flat reports, каждый100cases, прежние≥99safe,
absolute scenario RMS0,20/0,20/0,25 и relative gate к54.
После150 — все16Rough reports level0:2seeds×4families×2profiles,
≥90% success отдельно traverse/stand/turn плюс прежний tracking.
На150 весь Flat+Rough блок завершается даже при quality fail; затем любой fail
останавливает дальнейшие updates обоих seeds. Flat fail50 также останавливает.

Только при полном pass150: ещё200updates/seed, затем4Flat+48Rough,
levels0/1/2,≥95% каждого kind/family/profile и curriculum level2 всех rough families.
Нет автопродления, замены seeds или выбора удобного промежуточного checkpoint.
Technical/nonfinite/drift/export/hash failure прекращает очередь немедленно.
VRAM≥50% свободно до child,≥5% во время; train timeout3600с, evaluation1800с.
Останавливаются только собственные child trees.

Все раскрытые evaluation cases остаются development/regression.
Даже полный development pass не означает автоматическую policy acceptance:
далее отдельные новые qualification seeds/cases, только затем Stairs.

## Следующее решение и запуск

При fail сравнить early term rates, причины по границам, длину эпизода и
полное route completion: одна только низкая доля выходов может означать
застревание/отказ двигаться. Не продолжать wheel curriculum по одному reward.
При устойчивом Flat и оставшихся corridor failures — оценить наблюдаемость
по prefailure traces; следующий отдельный контракт history/velocity estimator
или navigation controller требует своих Flat/export/runtime gates.
Flat BC сейчас не добавляется: precision150 уже сохранил все Flat gates.

`scripts/run_rough_corridor_preflight.py --attempt 1`

`scripts/run_rough_corridor_training.py --preflight docs/results/rough_corridor_preflight_20260920_1.json`

Job: `logs/rough/rough_corridor_training_20260920/job.json`.
Итог: `docs/results/rough_corridor_training_20260920.json`.
Нужны локальные runtime/anchor/historical artifacts; Git не переносит checkpoints.
ETA до150 с проверками45–65мин; при pass ещё90–105мин до350.
Точное время старта и живой статус — в [TRAINING_PROGRESS](TRAINING_PROGRESS.md).
