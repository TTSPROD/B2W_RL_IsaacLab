# A/B пилот posture tracking · 30.09.2026

Текущий кандидат остаётся **core_24650**. Автоматической promotion нет.
[Исходная диагностика и гипотеза](2026-09-30-tracking-diagnosis.md).
Оба плеча завершили по 100 PPO updates от одинакового parent с восстановлением Adam,
4096 сред, seed 9901, LR cap 1e-5. Защищённые config audits пройдены.
Все шесть checkpoint exports прошли actual checkpoint→TorchScript parity.
Paired probe: 7 actors × 60 эпизодов = 420, одинаковые 5 selection seeds.
100 updates — 48 simulated seconds на среду; это ограниченный пилот, не доказательство сходимости.

| Actor | Успех / 60 | Unsafe | Малый lateral ratio | Малый yaw ratio |
|---|---:|---:|---:|---:|
| 24650 | 27/60 | 0 | 0.683 | 0.667 |
| control_24675 | 27/60 | 0 | 0.695 | 0.699 |
| control_24700 | 24/60 | 1 | 0.725 | 0.692 |
| control_24750 | 26/60 | 1 | 0.697 | 0.698 |
| posture_24675 | 25/60 | 0 | 0.702 | 0.694 |
| posture_24700 | 26/60 | 1 | 0.732 | 0.697 |
| posture_24750 | 25/60 | 0 | 0.652 | 0.664 |

Response ratio усреднён по ±0.3, Flat μ1 и Rough 10 см. Он не заменяет
проверки RMSE, остановки, traversal и safety. Значения относятся к этому paired probe;
число successes нельзя напрямую сравнивать с прежним 160-episode screen.

## Решение

- На 50 updates добавочный эффект B относительно A составляет только +0.008 lateral
  и +0.005 yaw response ratio; основная прибавка уже есть в контрольном continuation.
- Подъём: parent 3/10, каждый контроль 1/10, каждый вариант B 0/10.
  Ухудшение есть и без изменения reward; его нельзя целиком приписать новой функции.
- Unsafe: hard_joint_position при stairs_up_18/traverse_0.7 у control_24700 и
  control_24750 (seed 73004), а также posture_24700 (seed 73001).
- В новом probe parent имеет 9/10 спусков: один stop/restart не выдержал требование
  остановки на ступенях (exposure fraction 0.736 < 0.9). В прежнем full screen этот
  эпизод прошёл. Actor/reset/program совпадают, состав simulation batch изменился;
  причина расхождения не установлена. Небольшие разницы счётчиков не считаются
  доказательством эффекта reward. Все сравнения пилота используют текущий paired parent.

- posture_24675: REJECT — lateral: insufficient gain vs parent; lateral: insufficient gain vs matched control; yaw: insufficient gain vs parent; yaw: insufficient gain vs matched control; longitudinal: success regression; stairs_up: success regression
- posture_24700: REJECT — unsafe; lateral: insufficient gain vs parent; lateral: insufficient gain vs matched control; yaw: insufficient gain vs parent; yaw: insufficient gain vs matched control; stairs_up: success regression; wheel: saturation regression
- posture_24750: REJECT — lateral: insufficient gain vs parent; lateral: insufficient gain vs matched control; yaw: insufficient gain vs parent; yaw: insufficient gain vs matched control; stairs_up: success regression

Ни один checkpoint не выполнил правило advancement. Full screen и независимая
validation не запускались. Этот reward-вариант не продлевается; кандидат 24650 сохранён.
Отрицательный результат ограничен данным seed, фактором и бюджетом: он не доказывает
невозможность улучшения 24650 или необходимость обучения с нуля.

## Evidence

[Машиночитаемая сводка](evidence/tracking_posture_pilot_20260930/summary.json) содержит
training manifests/audits, checkpoint/export hashes, полный план probe, raw hashes и решения.
Dashboard job: `d3c316481f4b4954b65656b82dc00e67`. Raw summary SHA: `53430332bb4ac0864d39ab27969ff8090b07eba6dc773917417942258f635711`.
Parent policies, vendor и прежние raw traces не изменены. Сервер и робот не использовались.
Сравнение одного training seed не является статистическим подтверждением причинности.
