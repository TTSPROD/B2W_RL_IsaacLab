# B2W: аналитика последних экспериментов

Актуально на **25 сентября 2026**. Принятой Rough/Stairs policy нет. Текущий контракт — **57→16**; исторические 60-D artifacts остаются отклонённой абляцией.

## Краткий результат

| Ветка | Наблюдение | Решение |
|---|---|---|
| Server upstream | 20000 updates завершены; финал `model19999` не лучший по общему suite | Хранить как experimental, не release |
| Server inverse57 | `update3000` выбран по development, но validation провалена | Research parent |
| Cycle57 long run | Coarse screen: `model3000` 61/64 циклов, `model3998` 19/64; у финала 5 unsafe и 39 incomplete | Late training деградировало задачу; `model3998` rejected |
| Cycle57 model3000 | Held-out `329/384`, минимум `49/64`; corridor `350/384`, unsafe 0 | Research-only, stair gate failed |
| Stop fixes | Filtered gains максимум `355/384`, но с row regressions; latch `348/384` без улучшения; late-hold `347/384` против parent `350/384` | Ветка закрыта |
| Payload57 | Лучший B model3098: up `107/128`, down `115/128`; C-long деградировал до `95/128` и `93/128` | Все payload candidates rejected |
| MuJoCo model3000 | Flat `80/80`, down `60/60`, up `23/60`, unsafe 37 | Sim2sim gate failed; SDK2 закрыт |

Machine-readable coarse screen сохранён в [evidence/cycle57_coarse_screen_20260924](results/evidence/cycle57_coarse_screen_20260924/summary.json). Полный сводный аудит: [2026-09-25-repository-experiment-review.md](results/2026-09-25-repository-experiment-review.md). Итоги всех веток без промежуточных запусков: [EXPERIMENT_MATRIX.md](results/EXPERIMENT_MATRIX.md).

## Что показывают данные

1. **Больше updates не означает лучше.** В cycle57 полный long run научился избегать части stop-failures ценой недохода и incomplete. Похожий loophole повторился в payload C-long.
2. **Stop problem диагностирован, но локальные fixes исчерпаны.** Все 34/34 Isaac stop-failure сначала достигают безопасной скорости, затем повторно разгоняются. Wheel-only latch и late-hold reward не дают стабильного multi-row улучшения.
3. **Главный sim2sim blocker другой.** В MuJoCo финальная остановка чистая; аварии сосредоточены на подъёме: 35 calf velocity-limit и 2 calf position-limit stops, плюс длительное wheel saturation.
4. **Physics gap достаточно велик, чтобы мешать выводу о policy.** MuJoCo тяжелее training URDF на `4.750435 kg`, calf effort отличается, также не выровнены damping/contact/solver.
5. **Статистическая доказательность пока ограничена.** Evaluation содержит много environment variations, но большинство training branches — один seed. Это development evidence, не generalization claim.

## Текущие артефакты

| Роль | Artifact | Статус |
|---|---|---|
| Research parent | inverse57 update3000, SHA `73fb165c…` | Validation rejected |
| Nominal diagnostic | cycle57 model3000, SHA `20c4a34c…` | Isaac и MuJoCo gates failed |
| Export | model3000 TorchScript, SHA `2af4c341…` | Exact parity пройдена; quality gate failed |
| Flat-only | Desktop Flat54, SHA `f3509a69…` | Только собственный Flat scope |
| Payload best-development | B model3098, SHA `4fac5e08…` | Rejected |
| Cycle57 final | model3998, SHA `1fc381f7…` | Coarse-screened, rejected |

Полные SHA и provenance: [POLICY_REGISTRY.md](POLICY_REGISTRY.md).

## Текущее решение

Новые PPO runs, stop controllers и payload continuation не запускать. Сначала завершить actuator/physics parity и повторить неизменённый frozen MuJoCo suite. Затем выполнить decision gate из [PROJECT_PLAN.md](PROJECT_PLAN.md).

Ручной viewer остаётся диагностическим инструментом. Наличие checkpoint, export parity и успешный Flat rollout не разрешают SDK2 actuation или испытания робота.
