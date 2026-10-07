# План дообучения B2W low-level policy (ветка deepseek)

Статус: рабочий документ на ветке `deepseek`, 1 октября 2026.
Базируется на первичных источниках [обзор мировых практик](research/2026-10-01-finetune-world-practices.md)
и на текущем состоянии проекта ([PROJECT_PLAN](PROJECT_PLAN.md),
[TRAINING_STRATEGY](TRAINING_STRATEGY.md), [v2 evaluation](CORE_LOCOMOTION_EVALUATION.md)).

## 0. Цель и границы

Дообучить существующий development candidate **core_24650** (57→16, 50 Гц) до
кандидата, проходящего полный v2 screen и независимую validation Flat/Rough/Stairs.
Это **continuation PPO**, не обучение с нуля и не teacher–student.

Жёсткие границы (AGENTS.md):

- Actor строго 57→16; privileged critic 247 остаётся, но **не** расширяет actor.
- Не менять rewards без подтверждённой причины; один фактор на эксперимент.
- Без отдельного допуска: новое server training, аппаратный запуск.
- Vendor не изменяется; новое обучение — только через независимый supervisor
  (dashboard `status/stop`), raw evidence + SHA сохраняются.

## 1. Исходная точка

| Поле | Значение |
|---|---|
| Parent | `policies/local/core_24650/model_24650.pt`, SHA `458f08…6123` (тыс. SHA в [POLICY_REGISTRY](POLICY_REGISTRY.md)) |
| v2 screen | 107/160, 0 unsafe, 20/32 ячеек (Flat 40–…, см. [отбор](results/2026-09-30-locomotion-v2-selection.md)) |
| Отклонено до нас | posture A/B (seed 9901), LR pilot 1e-5/1e-6, stair curriculum A/B +1350 (B: unsafe 1, 0 promotions, 1296 demotions, coverage/ascent/yaw/saturation fail) |
| Окончание stair A/B | [сравнение +1350](results/2026-09-30-stair-comparison-1350.md) |

Итог stair A/B показал: адаптивный curriculum «по уровням тайла» не дал
promotions даже на level 0; целевые лестничные cohorts остались на уровне 0.
Направление «больше апдейтов» и «сложнее уровни» без другой задачи не работает.
Из этого **не следует** невозможность улучшить PPO вообще.

## 2. Ключевые решения, взятые из мировых практик

1. **Задача лестницы ставится как «марш», а не абстрактный уровень тайла.**
   Blind Stair Climbing (Chamorro) и ETH (Lee) учат подъём по отдельной ступени,
   затем короткий марш, затем полный марш, с физическим контактом и безопасностью
   как критерием. Наш B-опыт подтверждает: промоушен, считаемый по displacement,
   не отражает успеха прохождения марша.
2. **Опасный «ложный навык» сцепления колеса.** Literature явно предупреждает:
   колёсно-ногий подъём учит трение колеса о вертикальную грань, который не
   переносится (kick-back / проскальзывание). Обязательны умеренный friction
   range, контроль wheel slip/contact и отдельная проверка.
3. **Малосигнальные команды.** v2 диагностика показала недобор малых
   lateral/yaw; MUJICA и другие используют curriculum/командное распределение
   внутрь envelope. Нужно больше выборки около ±0.3, чередование знаков, реверсы —
   отдельным фактором.
4. **DR — только как уже анонсированный слой.** Friction/pushes/delay в 24650
   уже есть; менять его распределение — отдельная зарегистрированная гипотеза,
   не «тихая» правка в этом плане.
5. **Тестирование — paired seeds, отдельные процессы, каждая ячейка отдельно;**
   0 unsafe не компенсируется tracking; retention-гейты против frozen parent.

## 3. Порядок: диагностика → один фактор → оценка

Принцип: один зафиксированный фактор, свои новые seeds, без продления бюджета
и без ретроспективной настройки порогов. Каждый запуск — через supervisor;
промежуточные checkpoints — только как остановка, не как выбор.

### 3.1 Этап D: диагностика (без PPO, до нового обучения)

Прочитать-only, как требует PROJECT_PLAN/TRAINING_STRATEGY (статья 6/после 1350):

1. Разбор частых safety-reset по причинам/фазам на сохранённых traces stair A/B:
   q/dq, targets, command phase, torque, contact. Сверить termination-условия
   с фактическими traces до старта нового обучения.
2. Причина «0 promotions» B даже на level 0. Гипотеза: критерий промоушена
   (успех марша по displacement/времени) не срабатывает из-за того, что команды
   для stairs дают слишком мало успешных полных окон. Проверить, где именно
   окно «успех» не открывается.
3. Подтверждение: недобор малых команд — reverse из v2 диагностики
   (tracking/pauses) на отдельных fresh-эпизодах, посмотреть response по осям.

Выход D: `decision.json` с одной основной гипотезой; без гипотезы новое PPO не
запускается.

### 3.2 Этап F1: геометрия «короткий марш» (первичная рабочая гипотеза)

От родителя 24650 (exact restore actor/critic/std/Adam), свежий seed 9904.

- Задача: дообучение подъёма И спуска на **коротких лестничных маршах**
  (несколько ступеней, высота ступени в среднем из trained envelope ~0.05–0.12 м,
  tread 0.30 м), с обязательным физическим контактом колёс и устойчивым нулём на
  марше. Переход геометрии: короткий марш → полный марш только после положительного
  уровня.
- Curriculum: обучение лестничных cohorts через демкон/promotion по **реальному
  успеху марша** (пересечение внешней границы, ≥1 с wheel contact, progress ≥0.8,
  устойчивые нули), а не по тайл-уровням; те же retention-окошки для Flat/Rough.
- Rewards/PPO/ABI/geometry остальных terrain и DR — неизменные против parent.
- LR cap 1e-5; 4096 envs; budget **1500 updates**; checkpoints каждые 100.
- Gates (после 1500, только финальный checkpoint):
  - v2 screen 160 эпизодов отдельными процессами, parent и F1 в одинаковых
    case/reset slots;
  - Базовый порог из логики staircase: на stairs up и down по отдельности
    F1 ≥ parent 24650 в success, unsafe=0, ни одна ячейка не теряет успехи
    против parent;
  - ascent gain ≥2 episodes/10 против parent и против matched control (если оба).
  - tracking малых lateral/yaw и остановка без деградации >0.02;
  - wheel saturation не растёт (симуляционная metrika, отдельно от B2W limits).

### 3.3 Этап F2: командное разнообразие (после положительного F1 или отдельно)

Если F1 подтверждает локомоушн-навык на лестницах, следующий отдельный фактор —
распределение команд (см. TRAINING_STRATEGY этап 2):

- Дообучение от проверенной базы (parent либо F1) на перемешанные знаки/скорости/
  длительности внутри выходного envelope: чистые оси ±0.3/±0.5/±0.7/±1,
  mixed, реверс +1→−1, длинный ноль. Для stairs 0.3–0.7 м/с.
- Budget **3000 updates**; mid 1500 только diagnostic; LR cap 1e-5.
- Primary: прибавка по малым осям (+0.05 к parent, +0.02 к matched control)
  при сохранении safety/stop/stairs.

### 3.4 Повтор и валидация

- После положительного F1 → повтор F1 на двух дополнительных seeds (9905, 9906),
  публиковать все пары; без cherry-pick удачного seed.
- Только после полных gates → независимая validation: те же ячейки, 20 новых
  reset seeds (74001–74020, 640 эпизодов), ≥19/20 и 0 unsafe **в каждой ячейке**,
  Wilson lower публикуется как оценка неопределённости.

## 4. Оценка (протокол v2, без изменений порогов)

- Software/ABI: `check_policy_contract.py`, export parity (295 inputs, 0.0 error).
- Screen: [v2](CORE_LOCOMOTION_EVALUATION.md) 8 вариантов × 5 программ × 5 seeds
  = 160 эпизодов/policy; paired slots; отдельные процессы.
- Flat/Rough tracking: после 2 s settling RMSE ≤[0.20,0.20,0.25]; response ≥0.8.
- Остановка: непрерывные 10 s, |vxy|≤0.10, |ωz|≤0.10.
- Лестница: завершение программы, реальное crossing, ≥1 s exposure,
  progress/commanded≥0.8; stop на марше exposure ≥90%.
- Актуаторы: RMS/p99/peak torque, speed, saturation, hard joint margin, slew —
  ноги и колёса отдельно (симуляционные модели, не B2W current/thermal).

## 5. Запуск и evidence

Все запуски — через независимый supervisor:

```powershell
& .\scripts\start_dashboard.ps1            # монитор (read-only)
& .\scripts\run_local.ps1 scripts/run_locomotion.py --policies 24650,F1 --stage screen
& .\scripts\run_local.ps1 scripts/run_stair_curriculum.py ...   # новый зарегистрированный workflow
```

Новые фиксированные конфиги/plans кладём в `configs/` и `scripts/` с SHA в
manifest; raw traces, status, notes и hashes сохраняются в
`logs/dashboard/jobs/<id>/<stage>/` и компактной сводкой в
`docs/results/evidence/<experiment>/`. Implementation hashes отделяются от hashes
реально выполненного запуска. Координаторы создают собственные выходные каталоги;
существующие отчёты не переписываются.

## 6. Чек-лист перед запуском PPO

- [ ] Прочитаны PROJECT_PLAN, INFRASTRUCTURE, правильная ветка `deepseek`.
- [ ] Команда обновлена до проверенной; `git pull`/DNS при необходимости.
- [ ] GPU idle (server training — нет допуска); supervisor запущен.
- [ ] Compatibility/parity и новый fixed config с SHA.
- [ ] Одна зафиксированная гипотеза (decision.json из Этапа D).
- [ ] Fresh seeds, budget, проверка exact restore Adam.

## 7. Границы и стоп-правила

- Любой unsafe в v2 probe блокирует promotion соответствующего checkpoint.
- NaN/Inf, повреждение artifacts, ABI/drift — немедленный stop workflow.
- Не подбирать reward по общему success; продление бюджета не автоматическое.
- Отрицательный результат закрывает опыт; следующая гипотеза — другая.
- Новая server training и реальный робот — только после отдельного явного решения;
  sim-only результаты не являются hardware approval.
