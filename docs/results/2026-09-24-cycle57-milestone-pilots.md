# Cycle57 milestone pilots без payload

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](../PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

Дата: 24 сентября 2026. Платформа: RTX 4080 Laptop, Isaac Sim 5.1,
RSL-RL/PPO. Это development-screen, а не release qualification и не разрешение
управлять реальным роботом.

## Решение

Оба 50-update варианта с одноразовыми milestone-наградами отклонены. Ни один не
улучшил worst-direction полный цикл относительно сопоставимого control A. Длинное
обучение до 1000 updates не запускалось.

Payload-вариант D был остановлен по указанию пользователя до завершения и не
считается обученной или проверенной политикой. Все результаты ниже получены на
штатной модели B2W без `B2W_PAYLOAD_URDF`.

## Контролируемый протокол

- Общий parent: inverse57 update3000,
  SHA-256 `73fb165c4d9bb0b17ae3128a445d5f3801d66360efc5286469872199726ecafa`.
- Actor ABI неизменен: 57 observations → 16 actions; critic 247-D.
- Для A/C/D одинаковы seed54, 4096 environments, fixed LR `5e-5`, восстановленный
  optimizer, замороженный exploration std, terrain mix, DR, команды и sample budget.
- Control A: существующий `model_3050.pt`, 50-update milestone исходного run,
  без дополнительной milestone-награды.
- C: `safe_passage=100` + `safe_hold=100`, один раз на фазу.
- D: только `safe_hold=100`, один раз на успешной границе 100-step hold.
- Development evaluation: deterministic actor, seed3201, 128 environments × 900
  policy steps, stairs 6 × 14 cm / 32 cm, отдельно up/down, cycle protocol v3.
- Closed validation seeds4101–4104 не открывались.

Smoke C и D (64 environments × 1 update) завершились с exit code 0. Reset,
inverse-terrain и replay-command probes прошли; observations конечны; action space
12 position + 4 wheel velocity, actor 57→16.

## Результаты

| Вариант | Награда | Up cycle | Down cycle | Worst row | Passage up/down | Stop failed up/down | Unsafe up/down | Решение |
|---|---|---:|---:|---:|---:|---:|---:|---|
| A `model_3050` | control | 104/128 | 111/128 | 81.25% | 119 / 125 | 13 / 11 | 6 / 3 | Текущий control |
| C `model_3048` | passage + hold | 109/128 | 104/128 | 81.25% | 118 / 119 | 5 / 8 | 10 / 5 | Rejected |
| D `model_3048` | hold only | 111/128 | 99/128 | 77.34% | 121 / 125 | 10 / 25 | 5 / 2 | Rejected |

SHA-256:

- A: `6273d54f57d684499a7b63d07bde2c63cd8da208bf4c2252af9c3122c535680f`.
- C: `caac62c1f240572c9ae1fac1a80929b7b94de75f53c0dadd46b4115cd6c88acf`.
- D: `16e0ff46b29e05cb0425af6427444e101cefd1233fd270a9f72461fe22a9c62e`.

C уменьшил stop failures, особенно вверх, но ухудшил passage/unsafe и не поднял
worst row. D улучшил вверх, но удвоил stop failures вниз относительно control.
Следовательно, training reward и улучшение одной фазы/направления не являются
достаточным сигналом для продолжения.

Первичные JSON:

- `logs/eval_cycle57_A_model3050_stair_up14.json`
- `logs/eval_cycle57_A_model3050_stair_down14.json`
- `logs/eval_cycle57_C_model3048_stair_up14.json`
- `logs/eval_cycle57_C_model3048_stair_down14.json`
- `logs/eval_cycle57_D_model3048_stair_up14.json`
- `logs/eval_cycle57_D_model3048_stair_down14.json`

## Следующий эффективный шаг

Не продолжать weight sweep и не открывать validation. Сначала расширить evaluator
actuator-safety метриками и проверить сохранённые A-checkpoints на development.
Следующий train A/B должен менять механизм покрытия stop-состояний (phase-balanced
sampling или отдельные landing/hold rollouts), а не добавлять ещё один скалярный
бонус. Продолжение разрешать только при ≥5 п.п. улучшения worst row без регрессии
passage, unsafe и actuator limits; затем повторить на нескольких training seeds.
