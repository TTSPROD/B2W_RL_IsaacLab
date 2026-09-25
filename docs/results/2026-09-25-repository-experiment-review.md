# Сводный аудит репозитория и последних B2W экспериментов

Дата: **25 сентября 2026**. Новое обучение и управление роботом не выполнялись. Аудит охватил код, configs, registry, локальные machine-readable summaries и отчёты 23–25 сентября.

## Проверка репозитория

- `vendor_materials.py verify`: 1290 файлов из 6 pinned sources проверены.
- Полный test suite через проектный runtime: 267 tests, `OK`.
- Системный Python ожидаемо не подходит для полного suite из-за отсутствия Torch/Isaac dependencies; это не регрессия кода.
- В коде и configs активной линии сохранён actor ABI 57→16.

## Консолидированные результаты

| Проверка | Результат | Вывод |
|---|---|---|
| Cycle57 coarse trajectory screen | model3000 `61/64`; model3998 `19/64`, 5 unsafe, 39 incomplete | Финальный checkpoint деградировал; status `rejected`, не `not evaluated` |
| Cycle57 held-out | model3000 `329/384`, minimum `49/64`, unsafe 10 | Release gate не пройден |
| Corridor post-selection | `350/384`, passage `384/384`, unsafe 0 | Stop/restart остаётся blocker в Isaac |
| Full hold traces | 34/34 stop failures = late reacceleration after settle | Ошибка локализована, но причинность wheel action не доказана |
| Settled latch | `348/384` против `348/384` baseline | Wheel-only clamp недостаточен |
| Late-hold PPO | `347/384` против `350/384`; stop failures 36 против 34 | Fine-tune отклонён |
| Payload C-long | B parent `107/128` up, `115/128` down; final `95/128`, `93/128` | Reward loophole: incomplete растёт |
| Frozen MuJoCo | Flat `80/80`, down `60/60`, up `23/60`, unsafe 37 | Главный blocker — ascent dynamics/actuator limits |

Coarse evidence: [summary.json](evidence/cycle57_coarse_screen_20260924/summary.json), SHA-256 `15d64be9…`; [summary.csv](evidence/cycle57_coarse_screen_20260924/summary.csv), SHA-256 `1228388b…`.

## Аналитика

1. **Плато перешло в деградацию.** Cycle57 после первых 50–200 updates теряет completion, а payload C-long повторяет тот же шаблон. Продление по training reward методически неверно.
2. **Isaac stop issue и MuJoCo ascent issue — разные режимы отказа.** Stop micro-tuning не должен использоваться для лечения calf-limit и wheel-saturation на подъёме.
3. **Transfer gap пока не отделён от policy gap.** Разница массы `4.750435 kg`, calf effort и passive/contact параметров достаточно велика, чтобы сначала выполнить parity audit.
4. **Нет основания менять PPO на SAC/TD3.** Текущий blocker находится в task/physics/evaluation contract; смена алгоритма разрушит reference-compatible pipeline без проверки причины.
5. **Нет release evidence.** Большое число vectorized episodes не заменяет несколько training seeds и held-out geometries. Текущие таблицы — development/diagnostic evidence.

## Исправленные противоречия

- `model3998` переклассифицирован из `not evaluated` в `coarse-screened, rejected`.
- Старые планы stop-controller/late-hold больше не указаны как будущая работа: они выполнены и отклонены.
- Следующий шаг единообразно определён как actuator/physics parity и повтор frozen suite.
- Активная документация отделена от датированных reports и архивных proposals.

## Решение

Новые PPO, payload continuation, stop controllers и SDK2 actuation заблокированы. Следовать [PROJECT_PLAN.md](../PROJECT_PLAN.md): parity → неизменённый MuJoCo rerun → decision gate → при необходимости один bounded training pilot.
