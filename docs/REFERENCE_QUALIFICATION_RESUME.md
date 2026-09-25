# Возобновление квалификации: исправление проверки load_run

<!-- locomotion-scope-2026-09-25 -->
> Исторический документ. С 25.09.2026 цель — низкоуровневая locomotion57→16 по
> внешним командам скорости. Cycle/corridor/landing-stop и навигационные условия
> ниже относятся к исходному протоколу; его результаты, статусы и текст сохранены.
> Прежние следующие шаги не являются текущим планом. Актуальная приемка и порядок
> работ: [PROJECT_PLAN.md](PROJECT_PLAN.md). Состояние новой приемки указано в действующем плане.
<!-- /locomotion-scope-2026-09-25 -->

19.09.2026. Дополнение к неизменённому REFERENCE_QUALIFICATION.md.
Исходный job остановился21:37:39 МСК после успешных150 updates seeds54/55.
Оба training exits0; checkpoints model_149 сохранены, telemetry errors0.
Причина — ошибка оркестратора: сравнение agent.yaml требовало одинаковый
load_run у независимых seeds, хотя каждый обязан продолжать своего parent.
Это не quality failure и не изменение PPO/среды.

Исправление проверяет load_run/load_checkpoint против собственного checkpoint,
его SHA256, parent/current seed и manifest resume с load_optimizer=true.
Только после этих проверок load_run нормализуется для сравнения configs.
Остальные поля PPO и среды сравниваются полностью, кроме ранее разрешённых
seed/run_name/log_dir. Никакие обучающие параметры и критерии не меняются.

Возобновление допускается только для конкретного failed job этой серии,
с validated stages50/150, без начатых350/seed56 или оценки новых cases.
Проверяются старые hashes исходников (старый coordinator сохранён в source),
checkpoints, own-seed lineage, finite tensors, configs и actor/critic/std.
Исходный failed job и его final JSON сохраняются неизменными.

Продолжить54/55 от собственных model_149: ещё200 upright PPO updates.
Затем56 fresh50+100+200. Итого сохраняется350 на каждом,103219200 transitions;
остаётся73728000 transitions. Повторно обучать первые150 не требуется.
Остановка не добавляет simulator restart сверх уже зарегистрированной границы150.
Новые evaluation seeds/cases, guards, budget и порядок финальных оценок прежние.

Запуск: `.venv/Scripts/python.exe -B -u scripts/run_reference_qualification.py --resume-validated-prefix`.
Новый job: `logs/transfer/flat_reference_qualification_20260919_resume1/job.json`.
Итог: `docs/results/2026-09-19-reference-qualification-resume-final.json`.
