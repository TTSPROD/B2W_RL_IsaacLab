# Обзор репозитория и корректировка плана обучения

1 октября 2026. Выполнен offline обзор документов, конфигов, MDP adapters,
монитора coverage, сохранённого training environment и результатов оценки.
Новых simulation episodes и PPO updates нет. Числа и hashes входов —
[машиночитаемая сводка](evidence/training_plan_review_20261001/summary.json).

## Проверенные факты

Development candidate остаётся core_24650. Последний matched probe:
parent/A/B — 27/23/25 successes из 60, unsafe 0/0/1.
Подъём — 2/10, 0/10, 0/10. B отклонён; его продолжение не является следующим опытом.
[Результат](2026-09-30-stair-comparison-1350.md) и frozen configs не изменены.

В **фактически сохранённом** `pilot_environment.yaml` B reset задаёт roll/pitch
равномерно в [−3.14, 3.14] рад. Pinned Robot Lab `reset_root_state_uniform`
применяет эти углы через quaternion к исходной ориентации; target stairs не
относятся к исключению для pits. Safety adapter завершает эпизод при
`projected_gravity_b.z > −0.5`, то есть наклоне более 60°.
Reset допускает состояния вне области, в которой разрешено продолжать эпизод.
Это подтверждённое противоречие постановки, а его вклад в результат требует replay.

Счётчики B на +1350 совпадают с ранее опубликованным побайтным evidence:

| Cohort | Завершившиеся эпизоды, включая early reset | Unsafe resets | Доля unsafe | Средняя длина |
|---|---:|---:|---:|---:|
| Retention | 255036 | 209212 | 82.03% | 3.61 с |
| Flat | 32631 | 27097 | 83.04% | 11.89 с |
| Rough | 33041 | 27526 | 83.31% | 11.72 с |
| Stairs up | 53626 | 44409 | 82.81% | 12.01 с |
| Stairs down | 21592 | 17911 | 82.95% | 11.92 с |

Глобальные reason counters: nonfinite 0, tilt 325576, base/hip contact 65,
hard joint 523. Tilt составляет 99.82% суммы reason counts. Эти counts считаются
на policy ticks по всем cohorts, хотя snapshot хранит их внутри `retention`;
они не являются распределением первых причин reset и могут пересекаться.
Называть их только ошибками retention или только hard-joint проблемой неверно.

Promotions B: 0; demotions: 1296. Все 1024 up и 409 down environments в конце
на level 0; attempts уровней 3–9 отсутствуют. На up средняя длина 12 с при
70-секундном target horizon. Большое число transitions не подтверждает освоение
длинных последовательностей и верхних уровней.

Captured `stair_curriculum_monitor.py` и `b2w_curriculum_env.py` побайтно совпали
с текущими. Hashes сохранённого environment, progress, audit, executed adapters,
решения сравнения и pinned reset source записаны отдельно в новой сводке.

## Ограничения вывода

Saved counters не содержат времени первого нарушения после reset и разбивки
reason × phase × cohort. Не установлено, сколько tilt events произошло сразу
после reset, а сколько позже при exploration/контакте. Не доказано, что
исправление начальной ориентации само по себе улучшит лестницы.

Нулевые training zero passes измерены с exploration/noise/randomization и не
доказывают отказ deterministic остановки. Геометрический exposure proxy
монитора и условия promotion требуют отдельной проверки на фактическом mesh;
нулевые promotions сами по себе не отличают отсутствие навыка от слишком
трудного составного условия. Privileged critic уже присутствует в parent.

## Изменение очередности

Сначала инструментировать начальное состояние и первое событие safety,
затем выполнить bounded preflight без PPO: прежний reset против допустимого
upright reset при том же parent и неизменных constraints. Следующий обучающий
пилот меняет только reset roll/pitch, если preflight подтвердит гипотезу.
После него отдельно решать, нужен ли curriculum геометрии/поднавыков,
изменение обработки constraints или разнообразие команд.

Не ослаблять evaluator safety, не отключать его первые ticks и не повышать
friction ради прохождения. Reward, LR и history не менять одновременно с reset.
CaT остаётся отдельной гипотезой: авторы используют stochastic terminations,
а не наш deterministic terminal adapter
([первоисточник, проверен 01.10](https://arxiv.org/html/2403.18765v1)).
Идея «ступень → марш» имеет опубликованный пример, но их position-based actor
не совпадает с нашим velocity ABI
([Blind Stair Climbing, проверен 01.10](https://arxiv.org/html/2402.06143v1)).

Исполняемый следующий recipe ещё не реализован. Его frozen config, audit,
бюджет и критерии должны появиться до запуска. Подробная очередь —
[PROJECT_PLAN](../PROJECT_PLAN.md), постановка опытов —
[TRAINING_STRATEGY](../TRAINING_STRATEGY.md).

## Уточнение основы pipeline

Пользователь указал использовать стандартный Robot Lab train.py и менять только
участки с отставанием по оценкам. Прочитаны pinned train.py/cli_args и installed
RSL-RL OnPolicyRunner: штатный resume поддерживает загрузку optimizer, train.py
вызывает learn с `init_at_random_ep_len=True`, iteration labels при resume
следуют saved index. Export/parity нужно выполнять отдельным этапом.

Исторический project launcher уже вызывает vendor train.py, но дополнительно
заменяет runner, вводит LR cap и выключает random initial episode lengths.
Новый baseline планируется на штатном pipeline; эти hooks не наследуются
автоматически. Такой переход явно меняет общую execution recipe, поэтому старые
метрики не становятся результатом новой реализации. Внешние adaptations
ограничены runtime/task registration, evidence и проверяемыми MDP interventions.
Изменений train.py, runner или PPO в этом обзоре нет.
