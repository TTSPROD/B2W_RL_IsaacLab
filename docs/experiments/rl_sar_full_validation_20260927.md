# RL SAR: сравнение по последнему fullcycle-протоколу

27 сентября 2026 пользователь запросил проверить референс RL SAR по последним
тестам и добавить его на локальный сайт сравнения.

Выбран неизменённый `vendor/rl_sar/policy/b2w/robot_lab/policy.pt`, snapshot
`fan-ziqi/rl_sar@376d42c9b128f963ab08579762d5a216a976ce39`. SHA-256 и Git blob
проверяются по vendor manifest перед запуском. Это внешний TorchScript actor,
не checkpoint с известным номером iteration. Исходный training checkpoint
недоступен; проверка eager/TorchScript на тех же весах не является export parity
с исходным training checkpoint.

Протокол повторяет [последний тест 23999](23999_full_validation_20260927.md):
234 сценария × 32 reset seeds × 2 policies = **14 976 новых эпизодов**.
Flat — по отдельности; terrain — парно, RL SAR в первой половине batch,
23999 во второй (позиция 23999 сохранена относительно прошлого теста).
Свежий контроль 23999 сравнивается с предыдущим по outcomes и failure flags.
Результаты 19999/21999 доступны как сохранённые контроли.

Без изменений: 11 геометрий, schedules, seeds, номинальная физика, gains,
масса, scoring, safety 200 Hz, наблюдения 57→16 и policy 50 Hz. В этом тесте
RL SAR actor исполняется с тем же Isaac Robot Lab adapter, что и наши actors:
raw previous action, clipping observation terms до scales и physical targets
после scales. Это сравнение весов в общей Isaac-среде; C++ runtime RL SAR,
его иной порядок clipping и clipped action history здесь не оцениваются.

До запуска сохраняются `declared_plan.json`, identity/export manifest и копии
исходников в `logs/rl_sar_fullcycle_20260927/`. Raw JSON/NPZ пишутся отдельно
от предыдущих результатов. Summary публикуется на сайте после проверки hashes,
полноты, replay traces и stair exposure. Во время проверки показывается прогресс.

Это development comparison. 32/32 не доказывает 99% надёжность; hardware
approval отсутствует. Обучение, новые серверные jobs и upstream10000 не запускаются.
