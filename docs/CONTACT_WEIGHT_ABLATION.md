# Flat: вес штрафа за контакты, development seeds 50/51

> Исторический протокол завершённого опыта. Результаты и условия ниже сохранены;
> актуальные решения и очередь: [план](PROJECT_PLAN.md), [журнал](TRAINING_PROGRESS.md).

**Завершено 19.09.2026 в 02:44:45 МСК. Кандидат не выбран.**
Все четыре main runs по1500 updates, четыре exports/parity и10 evaluations
завершены без технических ошибок. Минимальный запас VRAM: 18,34% для пары50,
22,20% для пары51; telemetry errors 0. Controls точно воспроизвели исходные
результаты и first_failures staged-серии.

| Политика | Nominal без отказа | Bounded без отказа | Gate nominal / bounded |
|---|---:|---:|---|
| Reference | 100/100 | 100/100 | pass / pass |
| Seed50 control −1 | 88/100 | 93/100 | fail / fail |
| Seed50 contact3x −3 | 88/100 | 98/100 | fail / fail |
| Seed51 control −1 | 96/100 | 100/100 | fail / pass |
| Seed51 contact3x −3 | 100/100 | 100/100 | pass / pass |

Отказов23→14 (−39%). Seed50/contact3x также нарушает nominal negative-yaw
tracking: RMS 0,2895 рад/с >0,25. Bounded tracking проходит, но safety98<99.
[Полные результаты, p95/max, контакты и provenance](results/2026-09-19-contact-weight-final.json).
Успех одного seed не выполняет зарегистрированный критерий всех четырёх gates.

Следом выполнены четыре пассивных replay: results и first_failures совпали точно.
[Повторная диагностика](results/2026-09-19-contact-yaw-diagnosis.json) выявила
просадку корпуса до контактов. Последующий [опыт высоты](HEIGHT_WEIGHT_ABLATION.md)
также завершён без кандидата: при contact weight−3 добавление height−10 увеличило
отказы 14→23. Вес−3 сохраняется только как development control, не принятая
конфигурация. [Парная диагностика высоты/позы/yaw](HEIGHT_DIAGNOSIS.md) завершена;
следующий отдельный [lower-L1 опыт](HEIGHT_FLOOR_ABLATION.md) запущен.

**Ниже — исходный протокол и история запуска.**

**Запущено 18 сентября в 23:57 МСК.** Smoke обеих групп прошёл (exit0,
checkpoint/optimizer/TensorBoard и effective weights проверены). Начат основной
этап seed50 control/contact3x; seed51 далее в очереди. Качество ещё не оценено.
Протокол зарегистрирован после [staged-диагностики](STAGED_DIAGNOSIS.md). Первичный статус:
`logs/ablations/flat_contact3x_dev50_51_20260918/job.json`.

**Подтверждено 19.09.2026 00:01 МСК:** control 55/1500, contact3x 54/1500 новых updates
seed50; обе effective weights проверены. Env configs отличаются только весом
контактного штрафа и log_dir. [Снимок запуска](results/2026-09-19-contact-weight-launch.json).

## Гипотеза и единственное изменение

У неуспешных политик малый зазор голени перед первым контактом; clipping
момента explicit приводов ног в предшествующих 0,5 s не зарегистрирован.
Проверяется, достаточно ли увеличить цену нежелательного контакта, чтобы
изменить позу при повороте без ухудшения tracking. Это гипотеза, а не установленная
причина или обещание успешного результата.

- Control: `undesired_contacts.weight = -1.0` (штатный).
- Variant: `undesired_contacts.weight = -3.0` (втрое сильнее).
- Форма награды, threshold 1 N, sensor history 3, termination, остальные rewards,
  commands, physics и PPO сохраняются. Sampling gap history 3 / decimation 4
  документируется в диагностике, но не меняется одновременно с весом.
- Pure-yaw fraction 0,25; yaw tracking weight 1,5 в обеих группах.

## Парное продолжение

Seeds 50 и 51 выбраны как известные неуспешные development случаи. У каждого
обе группы стартуют из одного исходного `model_2499.pt` staged-серии с теми же
model/optimizer/adaptive LR. Simulator и RNG одинаково переинициализируются
на границе 2500. Оригинальные checkpoints, финалы и оценки сохраняются.

Каждая группа: **1500 новых updates**, 4096 сред × rollout 24; финальный
`model_3999.pt`. Всего четыре runs, **589 824 000 новых transitions**.
Сначала control/contact3x seed50 параллельно, затем та же пара seed51.
Это отдельные ветви от 2500, а не продление финальных 4000-update runs.

Перед основными runs — обе группы по 12 updates/16 сред от seed50 model_2499;
smoke проверяет resume, фактические weights, optimizer, конечность и артефакты.
Smoke checkpoints не используются в основном эксперименте.

Desktop RTX 4070 Ti; reserve VRAM 5%, мониторинг каждые 5 s; перед запуском
свободно ≥50%. Timeout пары 4 h, smoke 10 min. Ошибка процесса, NaN, hashes,
артефактов или VRAM останавливает этап; ошибки telemetry блокируют переход.
Source/protocol snapshots сохраняются. Нет автоматического restart/продления.

## Оценки и заранее заданный выбор

После обучения: CPU export parity каждого финала; reference и четыре политики
на nominal 20261201 / bounded_v1 20261202, всего **10 evaluations × 100 cases**.
Cases раскрыты предыдущей серией и используются только как development.
Физические свойства/readback/digest и cases сверяются с исходной серией.

Каждый policy/profile gate: ≥99/100 без sticky failure; pooled RMS каждого
семейства vx/vy ≤0,20 м/с и yaw ≤0,25 рад/с. Опубликовать p95/max и контакты.

1. Если reference не проходит оба профиля — исследовать evaluator, без выбора.
2. Если оба control seeds проходят оба профиля — оставить штатный вес −1.
3. Иначе выбрать −3 только если оба variant seeds проходят оба профиля и
   суммарных отказов меньше, чем у control. Один удачный seed недостаточен.
4. Иначе гипотеза не дала кандидата; новая диагностика, без автопродления.

Успех этого опыта не закрывает Flat gate: продолжение выбранных по неуспеху
seeds и раскрытые cases не являются независимой приёмкой. Следующий этап
при успехе — отдельный протокол трёх новых seeds с нуля и новых hold-outs.
Автоматический запуск fresh-серии, Rough, sim2sim или hardware не назначен.

## Код

- `scripts/train_b2w.py --undesired_contact_weight`: opt-in отрицательный вес,
  requested/effective значения в manifest; default сохраняет upstream.
- `scripts/run_contact_weight_ablation.py`: frozen очередь и критерий выбора.
- `tests/test_contact_weight_ablation.py`: защита от чужого parent/budget,
  ошибочных weights и принятия по неполным/нечисловым результатам.
