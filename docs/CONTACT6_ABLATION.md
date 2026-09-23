# Контактный штраф −3 против −6

> Исторический протокол завершённого опыта. Результаты и условия ниже сохранены;
> актуальные решения и очередь: [план](PROJECT_PLAN.md), [журнал](TRAINING_PROGRESS.md).

**Статус 19.09.2026: очередь −3/−6 завершена в18:53 МСК; кандидата нет.**
Все4 training runs по1500 новых updates,4экспорта/parity и10 evaluations завершены
с exit0. SHA256 всех23 итоговых артефактов проверены; controls точно повторили
предыдущую серию. [Полный итог](results/2026-09-19-contact6-final.json).

| Контактный вес | Seed50 nominal/bounded | Seed51 nominal/bounded | Отказы |
|---|---|---|---|
| −3 (control) | 88/98 | 100/100 | 14 |
| −6 | 98/99 | 85/98 | 20 |

Числа — безопасные эпизоды из100. Вариант−6 улучшил safety seed50, но ухудшил
seed51. Seed50 nominal также нарушил yaw RMS0,32453>0,25; seed51 nominal —
vx RMS0,24745>0,20 в negative-yaw сценарии. Только seed50 bounded прошёл gate.
Все20 отказов варианта — контакты задних голеней при pure yaw. Reference прошёл
оба профиля. Flat gate остаётся открытым; seed49 сохранён без дообучения.

Предыдущее поручение о следующей очереди выполнено этим опытом; на момент
его завершения дополнительное обучение не назначалось. Усиление контактного
штрафа не дало монотонного улучшения. Новый подход к обучению и бюджет
описаны в [плане](PROJECT_PLAN.md) и [reference transfer](REFERENCE_TRANSFER.md).
Rough/sim2sim/hardware сохраняют отдельные gates.
**Ниже — протокол, зарегистрированный до запуска; условия не менялись.**

Протокол зарегистрирован 19.09.2026 после проверки завершённого lower-L1 опыта.
Решение до запуска: [JSON](results/2026-09-19-contact6-next-decision.json).
Итоги и диагностика: [lower-L1](results/2026-09-19-height-floor-final.json).

## Основание

Lower-L1: seed50 nominal/bounded 87/91 безопасных эпизодов из100, seed51 99/100.
Контроль без height term: 88/98 и100/100; его результаты/первые отказы/cases точно
повторили предыдущую серию. Всего14 отказов у control и23 у lower-L1. Все37 первых
отказов — контакт задней голени при pure yaw. Seed50 lower-L1 также нарушил yaw
tracking: positive0,30083/0,28041рад/с, negative nominal0,27571 при пороге0,25.
Контроль seed50 нарушил negative nominal0,28950. Lower-L1 отклонён.

Ранее усиление прямого контактного штрафа −1→−3 сократило отказы23→14. Проверяется
гипотеза: следующий заранее фиксированный шаг −3→−6 уменьшит оставшиеся контакты
без нарушения tracking. Оптимальный вес и монотонное улучшение не установлены.
Данные первого контакта не доказывают причинную динамику до контакта; новые
lower-L1 traces не снимались. Историческая пассивная диагностика применима к
повторившимся controls, но не заменяет измерения новых lower-L1 траекторий.

## Единственный фактор и бюджет

Control: undesired_contacts.weight=−3; contact6: −6. Оба height terms выключены.
Остальные rewards, commands (pure_yaw_fraction0,25; yaw weight1,5), physics,
contact threshold/history, PPO, termination и policy ABI одинаковы.
Обе ветви seeds50/51 заново от исходных staged model_2499 с сохранённым optimizer
и adaptive LR; одинаковый restart simulator/RNG на границе2500. По1500 новых
updates на4096 средах×rollout24, финальные model_3999; всего589824000 transitions.
Seed49 и результаты завершённых опытов сохраняются.

Сначала seed50 обе группы по12 smoke updates на16 средах с проверкой resume;
smoke checkpoints исключены. Проверить manifest и фактические env.yaml:
единственные различия — log_dir и вес undesired_contacts. Затем пара seed50,
потом пара seed51; RTX4070Ti, не более2×4096. Preflight≥50% свободной VRAM,
guard5% каждые5s, smoke timeout600s и4h на основную пару. Ошибки telemetry,
provenance, resume или finite values блокируют переход. Без restart/продления.

## Оценка и правило выбора

Четыре финальных экспорта и CPU parity; reference+4политики на прежних disclosed
nominal20261201 и bounded_v1 20261202 — десять evaluations по100 эпизодов.
Cases и physical digests должны совпасть с исходной staged-серией.
Каждый gate: ≥99/100 без sticky failure и pooled RMS КАЖДОГО семейства
vx/vy≤0,20м/с, yaw≤0,25рад/с. Публиковать все p95/max, контакты и hashes.

Reference обязан пройти оба профиля. Если оба controls проходят оба профиля,
предпочесть control. Иначе contact6 — кандидат только при pass всех4 seed/profile
и меньшем общем числе отказов. Любой иной исход — без кандидата. Один удачный seed,
средние показатели или промежуточный checkpoint не заменяют gate. Это development,
не fresh-seed приёмка; Rough, sim2sim и hardware не запускаются.

## Выполнение

Coordinator: `scripts/run_contact6_ablation.py`.
Job: `logs/ablations/flat_contact6_dev50_51_20260919/job.json`.
Журнал однократного продолжения: `logs/ablations/lower_l1_followup.json`.
В исходном поручении heartbeat lower-l1 должен был завершиться после
подтверждения PPO progress этой очереди; последующие назначения ведутся отдельно
в актуальном плане. Эта запись не описывает текущее состояние automation.
