# Проверка происхождения обучения 19999

27 сентября 2026 read-only прочитаны файлы завершённого серверного run
`user@10.126.161.7:/home/user/B2W_RL_IsaacLab_Server/logs/upstream_b2w_20000_4gpu_20260922/`.
Серверные jobs, checkpoints и настройки не изменялись.

- [launch.sh](launch.sh): стандартная B2W Rough task, 4 GPU × 1024 среды,
  продолжение с собственного checkpoint 100.
- [RUN.md](RUN.md): scratch происхождение, 19899 дополнительных updates и
  итоговый индекс 19999; runtime adaptations.
- [runtime_bootstrap.py](runtime_bootstrap.py): URDF compatibility и точное
  восстановление actor/critic/Adam, синхронизация LR; выполнение vendor entrypoint.
- [resume_rank0.json](resume_rank0.json): сохранённый серверный proof восстановления.
- [train.py](train.py): read-only копия серверного entrypoint.

Серверный train.py имеет CRLF, SHA-256
`115c977856b0b31e1d161b165a0aa2abbe7220dd7469cb5fae35354665a02d2a`.
Локальный pinned vendor имеет LF, SHA-256
`e80353fd15aded495c0f6c0bf66dd90cf541f53390dc486c44ef655e70fe927a`.
После замены CRLF на LF совпадают все байты; код одинаков. Локальный vendor
прошёл manifest verification, его байты не менялись.

Исходные env/agent configs находятся в `policies/server/upstream_19999/`.
Новый preflight сравнил текущий неизменённый upstream task с сохранёнными
observations, actions, rewards, DR, physics, actuators, terrains, command settings,
network и PPO. Итоговый report — `upstream_config_audit.json` внутри нового run.
Это проверка происхождения и конфигурации, не оценка качества policy.
