# D1.1: диагностика промежуточных fixed checkpoints

5 октября 2026 выполнены два diagnostic-only supervisor jobs без PPO:

- `0f2d2a0c50f94b1b960505425b8f009f`, exit 0 — fresh parent и fixed
  checkpoints после +51/+101/+151 updates, 240 episodes;
- `d073afe88e8044b4b4b1b976355317f8`, exit 0 — fresh parent и checkpoint
  после первого update, 120 episodes.

Первая техническая попытка `d7d0b2d7a07e42428ea500e0a27fda81` завершилась
до episodes: numeric parent ID был передан evaluator как строка. Она не входит
в метрики. Исправление покрыто unit test; raw не удалён.

## Результат

| Actor | Updates от parent | Success | Unsafe | lateral ±0.3 | yaw ±0.3 | Paired wins/losses |
|---|---:|---:|---:|---:|---:|---:|
| core_24650 | 0 | 27/60 | 0 | 0.683 | 0.667 | — |
| fixed 24650 | 1 | 26/60 | 0 | 0.648 | 0.653 | 3/4 |
| fixed 24700 | 51 | 23/60 | 0 | 0.708 | 0.681 | 0/4 |
| fixed 24750 | 101 | 22/60 | 0 | 0.683 | 0.673 | 1/6 |
| fixed 24800 | 151 | 22/60 | 0 | 0.659 | 0.674 | 0/5 |

Fresh parent воспроизвёл 27/60 и одинаковые raw metrics в обоих jobs.
Все actors исполнялись в отдельных fresh processes с одинаковыми case/reset
slots. Checkpoint +1 уже не проходит strict retention: Flat longitudinal 4/5
против 5/5, descent stop/restart 4/5 против 5/5, lateral response ниже tolerance.
При +51 ascent traverse падает 2/5→0/5 и descent stop/restart 5/5→3/5.
При +101 дополнительно ухудшается Flat longitudinal; +151 также нарушает
wheel-saturation gate.

Actor +1 отличается от parent всего на `1.4448e-4` по relative L2
(`max_abs=1.9392e-4`), но меняет семь paired outcomes: три wins и четыре losses.
Это показывает высокую чувствительность граничных 5-seed outcomes к малому
изменению weights. Оно не доказывает, что любой PPO update принципиально вреден:
дискретный success объединяет tracking, transitions, stop и traversal, а stair
trajectories ранее показали чувствительность к малым simulation differences.
Но текущий fixed continuation не даёт безопасного budget cap даже в одной update
по frozen strict retention gate.

## Решение

- Ни один intermediate checkpoint не продвигается и не становится PPO parent.
- Не запускать counterbalanced sampler или иной 50–300 update A/B до разбора
  cohort-specific objective/gradient conflict: command-order imbalance сам по
  себе не объясняет раннюю stair regression.
- Следующий этап — no-update audit на parent: reward/GAE/gradient norm и cosine
  по retention, Flat, Rough, stairs-up/down и command phase; отдельно контекст
  поздних hard-joint событий. Optimizer step запрещён.
- Только после этого зафиксировать один фактор: sampler/order, stair retention
  mix либо constraint formulation. Final actor всё равно обязан пройти parent
  retention, полный v2 screen и независимую validation.

## Evidence

- `docs/results/evidence/schedule_checkpoint_diagnosis_20261005/summary.json` —
  SHA-256 `5bbd4832d2937e121acdc694e1ba41bae8e155c9ae6238a61e2ab884bdf0f661`.
- Intermediate decision —
  `6d298404618b944b2890f3806c16cf1ba2c32676cd154f7602e5318f95aa96cf`.
- First-update decision —
  `0514ca6cbda7090d82abc6bbc8e42160e4605416382bc9f9fe3945f49e6d3ccb`.
- Analysis source SHA-256 —
  `1c6de4a25ce345fd504e9d55f9a19729a5ebf82d3b6077fa954a351ace86ca58`.

Анализатор проверил hashes captured sources/checkpoints, 360 episode records,
тождество slots/runtime, повтор fresh parent и точное совпадение обоих решений.
Ограничения: один training seed, пять reset seeds; диагностика локализует drift,
но не измеряет причинность градиентов. Server training, validation и hardware
actions не выполнялись.
