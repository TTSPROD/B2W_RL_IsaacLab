# Проверка фиксированного checkpoint 23999

27 сентября 2026 пользователь запросил тест последнего checkpoint. Выбран
финальный **23999** локального recovery-run: ровно 2000 updates от 21999,
завершение 19:09:12 МСК, seed 9703. Другие промежуточные weights не отбираются.

Checkpoint SHA-256:
`780a8b486ff25c15f2eb1cadc2bc135a14534c5e5e31debd4583ce1c74c31f81`.
Проверенный actor export и manifest сохраняются до старта в
`logs/fullcycle23999_validation_20260927/contract/`.

Протокол повторяет [объявленную проверку 21999](21999_full_validation_20260927.md):
36 командных сценариев на Flat, Rough ±4 cm, блоках 5–10 cm, уклонах ±10°;
9 сценариев на каждой лестнице 6/12/18 cm вверх/вниз. Всего 234 сценария.
Flat seeds 8201–8232; terrain seeds 10201–10232; geometry seed 20260927.
Детерминированный actor, nominal physics, без training DR/noise и autoreset.
Команды меняются только по времени; положение и курс не корректируют policy.

**Новые запуски: 21999 и 23999, 14 976 эпизодов суммарно**. На terrain они
выполняются парно в одном batch. Flat выполняется отдельно для каждой policy
тем же frozen evaluator. Свежие результаты 21999 сверяются с её предыдущими
outcomes/flags. 19999 — сохранённый контроль предыдущего полного теста, без
нового запуска. Различия текущего кода перечисляются отдельно от captured hashes.

Gates сохранены: RMSE ≤(0.20,0.20,0.25), response ≥80%, все moving 1 s окна
после 2 s settling; непрерывный ноль ≤0.10 m/s и ≤0.10 rad/s в течение 10 s.
Safety на 200 Hz: finite, tilt≤60°, base/hip contact≤5 N, hard joint range
с tolerance 0.001 rad. Unsafe и incomplete остаются в denominator.
Для stair-stop отдельно оцениваются физическое покрытие ступеней ≥90% окна
и прохождение continuous-zero gate. Torque/speed/saturation/slew записываются
для всех 16 приводов; реальный current/thermal этим тестом не проверяется.

Решение принимается по каждой строке: full/zero/unsafe и потеря прежних 32/32.
Особое внимание yaw ±0.3/0.5, боковым командам, backward traverse и stop/restart
на лестницах 12/18 cm. Для отсутствия регресса нет потерь full/zero по строкам
и нет unsafe у кандидата. Общая сумма не компенсирует регресс отдельной строки.

Raw JSON/NPZ и live progress сохраняются в `logs/fullcycle23999_validation_20260927/`.
Retained evidence предыдущих тестов не изменяется. Это повторный development
screen после настройки по прошлому тесту, не независимая qualification.
32 reset seeds не оценивают вариативность между training seeds и не доказывают
99% надёжность. Hardware approval не предоставляется.
