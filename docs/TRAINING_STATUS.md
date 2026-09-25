# B2W: аналитика последних экспериментов

Актуально на **25 сентября 2026**. Принятой Rough/Stairs policy нет. Текущий контракт — **57→16**; исторические 60-D artifacts остаются отклонённой абляцией.

**Уточнение scope пользователем:** принимается только низкоуровневая locomotion по
внешним командам скорости. Историческая таблица сохраняет результаты прежних протоколов;
cycle/corridor/landing scores больше не являются определяющими gates этой policy.
Development `locomotion57_v1` выполнен для upstream10000/15000/19999. Все три не приняты; остальные кандидаты еще не оценены по этому протоколу. Автоматического promotion нет.
Актуальные критерии — в [PROJECT_PLAN.md](PROJECT_PLAN.md).

## Новый low-level development-screen

Выполнены **5184 эпизода**: upstream10000/15000/19999, 54 сценария, 16 общих reset
seeds, Isaac и MuJoCo. Никакой навигационной коррекции; ABI57→16 и 50 Hz сохранены.

| Движок | Checkpoint | Flat | Rough | Stairs | Unsafe |
|---|---:|---:|---:|---:|---:|
| Isaac | 10000 | 138/320 | 207/256 | 181/288 | 4 |
| Isaac | 15000 | 125/320 | 170/256 | 166/288 | 1 |
| Isaac | 19999 | 150/320 | 240/256 | 275/288 | 0 |
| MuJoCo | 10000 | 138/320 | 211/256 | 157/288 | 18 |
| MuJoCo | 15000 | 112/320 | 138/256 | 125/288 | 22 |
| MuJoCo | 19999 | 182/320 | 203/256 | 116/288 | 21 |

Числа — эпизоды, выполнившие все применимые gates. Общая сумма не заменяет
проверку каждой terrain×command строки. Ни один checkpoint не принят: есть
поведенческие отказы; полная статистическая/hardware qualification не выполнена.
Это milestones одного training run, не независимые training seeds.
Протокол, строки и ограничения: [отчет](results/2026-09-25-upstream-locomotion57.md).

## Physics57: диагностика приводов и модели

Устранение лишнего passive damping увеличило success в парном micro-screen
10000 с8/20 до16/20, 19999 с5/20 до12/20; unsafe0 у исправленных вариантов.
Compiled inertia/actuation согласованы в отдельном adapter, contact parity остается
открытой. Policy promotion нет. [Physics report](results/2026-09-25-physics57-diagnostics.md).

## Contact57: геометрия столкновений

Последний contact57 этап перенес20 source collision
shapes и frames. У19999 micro success17/20 против8/20 mechanical control, unsafe0;
на лестнице при0.3m/s только1/4.192 short probes показали уменьшение leg-q mismatch,
но рост root-position mismatch. Cooked hulls и solver parity открыты, promotion нет.
[Contact57 evidence](results/2026-09-25-contact57-diagnostics.md).

**Upstream10000 исключен из дальнейших запусков по указанию пользователя.**
Его завершенные результаты сохраняются; продолжение upstream работы — с19999.

## Contact57b: cooking и локализация отказов19999

Последующий [Contact57b](results/2026-09-25-contact57b-19999.md): cooked-copy profiles,
runtime offsets и36 policy-free probes выполнены.19999:12/20 против17/20 source,
unsafe0. Из четырех slow-ascent episodes два застряли; два прошли марш, но нарушили
transition/zero gates. Следующий шаг — полный state capture/replay и reward ledger;
[план replay](../configs/locomotion57_19999_replay_plan_20260925.json) еще не выполнен.

## Исторические результаты

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

## Что показывали исторические эксперименты

1. **Больше updates не означает лучше.** В cycle57 полный long run научился избегать части stop-failures ценой недохода и incomplete. Похожий loophole повторился в payload C-long.
2. **Stop problem диагностирован, но локальные fixes исчерпаны.** Все 34/34 Isaac stop-failure сначала достигают безопасной скорости, затем повторно разгоняются. Wheel-only latch и late-hold reward не дают стабильного multi-row улучшения.
3. **Главный sim2sim blocker другой.** В MuJoCo финальная остановка чистая; аварии сосредоточены на подъёме: 35 calf velocity-limit и 2 calf position-limit stops, плюс длительное wheel saturation.
4. **Physics gap достаточно велик, чтобы мешать выводу о policy.** MuJoCo тяжелее training URDF на `4.750435 kg`, calf effort отличается, также не выровнены damping/contact/solver.
5. **Статистическая доказательность пока ограничена.** Evaluation содержит много environment variations, но большинство training branches — один seed. Это development evidence, не generalization claim.

### Уточнение повторного аудита 25 сентября

Числа и статусы исторических экспериментов сохраняются, но причины требуют более
осторожной интерпретации. В прежних evaluators Isaac `unsafe` не включал actuator
telemetry и проверялся иначе, чем MuJoCo:
post-policy sampling против physics-step abort, разные contact masks и limits.
В Isaac nominal-up с `unsafe=0` уже записаны leg/wheel speed utilization1.0118/1.2916
и wheel saturation12.28%. Calf14rad/s в DCMotor — no-load speed модели;
аппаратный hard speed limit еще не подтвержден.

В cycle57 effective frozen std составляет0.754…1.022 для ног и2.076…2.117 для колес,
несмотря на `init_noise_std=0.1`. Model3000 сохранен после двух новых updates.
Причинность деградации требует отдельного контроля exploration и reward return.
Текущий boundary-stop тест также не доказывает непрерывный hold.

Код, первичные JSON и интерпретация: [разбор обучения и приемки](results/2026-09-25-locomotion-training-review.md).

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

Новые PPO runs, stop controllers и payload continuation не запускать в рамках аудита.
Общий development evaluator уже исполняет внешние команды без навигационной
коррекции; проверены три upstream milestones. Следующий этап — закрыть оставшиеся
measurement/actuator/physics gaps и дополнить baseline reference/inverse57/cycle57.
Cooking-copy inspection и независимые impact probes выполнены. Приоритет — full-state
replay и reward-component diagnosis19999. Повторные запуски10000 исключены.
Исходный frozen MuJoCo suite сохраняется как историческая диагностика; новый
locomotion evaluator получает отдельный id `locomotion57_v1`. Training pilot допускается к проектированию после
локализации failure, без требования заранее получить stair pass старой policy.
Порядок и ограничения: [PROJECT_PLAN.md](PROJECT_PLAN.md).

Ручной viewer остаётся диагностическим инструментом. Наличие checkpoint, export parity и успешный Flat rollout не разрешают SDK2 actuation или испытания робота.
