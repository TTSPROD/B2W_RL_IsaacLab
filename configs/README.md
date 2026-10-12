# Конфигурации B2W

На 12 октября 2026 в каталоге 35 JSON файлов. Побайтовых дубликатов нет.
Датированные планы являются frozen входами выполненных или закрытых опытов:
их paths, содержимое и hashes сохранены для проверки происхождения. Сходные
планы разных плеч или повторов не объединяются задним числом.

| Группа | Состав | Статус |
|---|---|---|
| `24650_*_202609*.json`, `24650_*_20261001.json`, `24650_*_20261005.json`, `24650_*_20261007.json` | Stage-3, posture, LR, stair, reset, schedule, DeepSeek F1, micro/specialist/axis | Исторические frozen планы; новые training jobs по ним не разрешены |
| `24650_native_continuation_20261012.json` | Локальный standard PPO A/B seed 9930 | Выполнен и отклонён; бюджет закрыт |
| `24650_trace_based_recipe_proposal_20261012.json` | Следующая training гипотеза | Предложение без разрешённого запуска; решение в [PROJECT_PLAN](../docs/PROJECT_PLAN.md) |
| `sim2sim_*_20261012.json` | Выполненные software/DDS, PhysX и изменённые MuJoCo diagnostic variants | Историческое evidence; DC/armature планы не являются исходным S2 baseline Unitree |
| `sdk2_deployment.template.json` | Поля будущего deployment manifest | Шаблон, без аппаратного допуска |
| `locomotion57_19999_operating_screen_20260925.json` | Старый operating57 screen | Историческая v1 методика; действующая оценка — v2 |

Исходный B2W S2 replay по [методу Unitree](../docs/UNITREE_SIM2SIM_METHOD.md)
требует отдельного объявленного плана и собственных executed hashes. Не менять
frozen JSON ради упрощения каталога. Исполняемые contract loaders продолжают
проверять точные входы; тесты поведения используют committed планы как
фикстуры и не требуют локальных `logs/`.
