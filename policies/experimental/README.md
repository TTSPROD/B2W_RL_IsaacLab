# Экспериментальные политики — НЕ ПРИНЯТЫ

> Это неизменяемый Git snapshot на 23 сентября. Текущее состояние, включая завершённые позже inverse57, cycle57 и payload57, находится в [каноническом реестре](../../docs/POLICY_REGISTRY.md). Ни один более новый checkpoint не принят.

Архив снимков на 23 сентября 2026. Ни один файл здесь не является принятым релизом или разрешением управления роботом.
Сохранены последние доступные checkpoints локальных non-smoke запусков (включая остановленные/неполные), а также пять проверенных серверных milestones. Промежуточные periodic saves и smoke здесь не дублируются. Файл не доказывает успешного окончания обучения; результаты и ограничения указаны в отчётах.
57→16 — текущий контракт. Исторические basevel60 snapshots имеют 60 входов: они отдельно маркированы и несовместимы с 57-входовым контроллером.
Серверный inverse57 позднее завершён; его политика, как и локальные cycle57/payload57, в этот снимок не включена. Автоматическая доставка не публикует файлы в Git.

[Общий статус и сравнения](../../docs/TRAINING_STATUS.md) · [Manifest с SHA-256 и происхождением](manifest.json) · [Референс rl_sar](../../vendor/rl_sar/policy/b2w/robot_lab/policy.pt)

Файлы — полные RSL-RL checkpoints с optimizer, не экспортированный TorchScript. Для воспроизведения нужны соответствующие конфиги, runtime и ABI. Исходные лицензии upstream находятся в vendor; архивирование не меняет правовой статус производных весов.

| Место | Checkpoint | ABI | Seed | Сохранённая итерация |
|---|---|---:|---:|---:|
| local | [local/unitree_b2w_flat/2026-09-21_11-09-49_pilot_4080_256/model_1.pt](local/unitree_b2w_flat/2026-09-21_11-09-49_pilot_4080_256/model_1.pt) | 57→16 | 42 | 1 |
| local | [local/unitree_b2w_flat/2026-09-21_11-12-48_pilot_4080_1024/model_9.pt](local/unitree_b2w_flat/2026-09-21_11-12-48_pilot_4080_1024/model_9.pt) | 57→16 | 42 | 9 |
| local | [local/unitree_b2w_flat/2026-09-21_11-15-37_flat_seed42_4080/model_0.pt](local/unitree_b2w_flat/2026-09-21_11-15-37_flat_seed42_4080/model_0.pt) | 57→16 | 42 | 0 |
| local | [local/unitree_b2w_rough/2026-09-21_11-26-48_rough_warmstart_pilot/model_9.pt](local/unitree_b2w_rough/2026-09-21_11-26-48_rough_warmstart_pilot/model_9.pt) | 57→16 | 54 | 9 |
| local | [local/unitree_b2w_rough/2026-09-21_11-28-19_rough_warmstart_1024_pilot/model_9.pt](local/unitree_b2w_rough/2026-09-21_11-28-19_rough_warmstart_1024_pilot/model_9.pt) | 57→16 | 54 | 9 |
| local | [local/unitree_b2w_rough/2026-09-21_11-29-39_rough_from_flat54_stage1/model_349.pt](local/unitree_b2w_rough/2026-09-21_11-29-39_rough_from_flat54_stage1/model_349.pt) | 57→16 | 54 | 349 |
| local | [local/unitree_b2w_rough/2026-09-21_12-00-49_rough_tilt03_stage2/model_548.pt](local/unitree_b2w_rough/2026-09-21_12-00-49_rough_tilt03_stage2/model_548.pt) | 57→16 | 54 | 548 |
| local | [local/unitree_b2w_rough/2026-09-21_12-37-33_rough_all_levels_stage3/model_548.pt](local/unitree_b2w_rough/2026-09-21_12-37-33_rough_all_levels_stage3/model_548.pt) | 57→16 | 54 | 548 |
| local | [local/unitree_b2w_rough/2026-09-21_13-56-09_rough_from_flat54_seed55_stage1/model_349.pt](local/unitree_b2w_rough/2026-09-21_13-56-09_rough_from_flat54_seed55_stage1/model_349.pt) | 57→16 | 55 | 349 |
| local | [local/unitree_b2w_rough/2026-09-21_14-11-55_rough_from_flat54_seed56_stage1/model_349.pt](local/unitree_b2w_rough/2026-09-21_14-11-55_rough_from_flat54_seed56_stage1/model_349.pt) | 57→16 | 56 | 349 |
| local | [local/unitree_b2w_rough/2026-09-21_14-27-34_rough_scratch_seed54_equal_budget/model_300.pt](local/unitree_b2w_rough/2026-09-21_14-27-34_rough_scratch_seed54_equal_budget/model_300.pt) | 57→16 | 54 | 300 |
| local | [local/unitree_b2w_rough/2026-09-22_16-03-30_upstream_scratch_seed42_20k/model_1200.pt](local/unitree_b2w_rough/2026-09-22_16-03-30_upstream_scratch_seed42_20k/model_1200.pt) | 57→16 | 42 | 1200 |
| local | [local/unitree_b2w_rough/2026-09-22_18-00-37_rough_inverse25_2048_20260922_seed54_full/model_398.pt](local/unitree_b2w_rough/2026-09-22_18-00-37_rough_inverse25_2048_20260922_seed54_full/model_398.pt) | 57→16 | 54 | 398 |
| local | [local/unitree_b2w_rough/2026-09-22_18-00-37_rough_inverse25_2048_20260922_seed55_full/model_398.pt](local/unitree_b2w_rough/2026-09-22_18-00-37_rough_inverse25_2048_20260922_seed55_full/model_398.pt) | 57→16 | 55 | 398 |
| local | [local/unitree_b2w_rough/2026-09-22_18-04-46_rough_control_2048_20260922_seed54_full/model_398.pt](local/unitree_b2w_rough/2026-09-22_18-04-46_rough_control_2048_20260922_seed54_full/model_398.pt) | 57→16 | 54 | 398 |
| local | [local/unitree_b2w_rough/2026-09-22_18-04-46_rough_control_2048_20260922_seed55_full/model_398.pt](local/unitree_b2w_rough/2026-09-22_18-04-46_rough_control_2048_20260922_seed55_full/model_398.pt) | 57→16 | 55 | 398 |
| local | [local/unitree_b2w_stair/2026-09-21_15-15-36_stair1_from_rough54/model_448.pt](local/unitree_b2w_stair/2026-09-21_15-15-36_stair1_from_rough54/model_448.pt) | 57→16 | 64 | 448 |
| local | [local/unitree_b2w_stair/2026-09-21_15-30-15_stair2_safe_replay/model_448.pt](local/unitree_b2w_stair/2026-09-21_15-30-15_stair2_safe_replay/model_448.pt) | 57→16 | 65 | 448 |
| local | [local/unitree_b2w_stair/2026-09-21_16-10-58_stair3_landing_stability/model_448.pt](local/unitree_b2w_stair/2026-09-21_16-10-58_stair3_landing_stability/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-21_16-23-18_stair4_stop_hold/model_448.pt](local/unitree_b2w_stair/2026-09-21_16-23-18_stair4_stop_hold/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-21_16-31-22_stair5_full_cycle/model_448.pt](local/unitree_b2w_stair/2026-09-21_16-31-22_stair5_full_cycle/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-21_16-46-16_stair6_replay30/model_448.pt](local/unitree_b2w_stair/2026-09-21_16-46-16_stair6_replay30/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-21_16-59-05_stair7_stopspeed6/model_448.pt](local/unitree_b2w_stair/2026-09-21_16-59-05_stair7_stopspeed6/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-21_17-32-17_stair8_approach05/model_448.pt](local/unitree_b2w_stair/2026-09-21_17-32-17_stair8_approach05/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-21_17-45-02_stair9_up50/model_448.pt](local/unitree_b2w_stair/2026-09-21_17-45-02_stair9_up50/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-22_09-40-25_stair10_landing_control/model_448.pt](local/unitree_b2w_stair/2026-09-22_09-40-25_stair10_landing_control/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-22_09-43-33_stair10_landing_start/model_448.pt](local/unitree_b2w_stair/2026-09-22_09-43-33_stair10_landing_start/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-22_10-13-30_stair11_prob05/model_448.pt](local/unitree_b2w_stair/2026-09-22_10-13-30_stair11_prob05/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-22_10-30-15_stair12_landing_seed55/model_448.pt](local/unitree_b2w_stair/2026-09-22_10-30-15_stair12_landing_seed55/model_448.pt) | 57→16 | 55 | 448 |
| local | [local/unitree_b2w_stair/2026-09-22_10-46-16_stair13_expanded/model_448.pt](local/unitree_b2w_stair/2026-09-22_10-46-16_stair13_expanded/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-22_10-56-25_stair14_inverse/model_448.pt](local/unitree_b2w_stair/2026-09-22_10-56-25_stair14_inverse/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-22_11-15-30_stair15_safe_passage/model_375.pt](local/unitree_b2w_stair/2026-09-22_11-15-30_stair15_safe_passage/model_375.pt) | 57→16 | 54 | 375 |
| local | [local/unitree_b2w_stair/2026-09-22_11-18-13_stair15_safe_passage_v2/model_448.pt](local/unitree_b2w_stair/2026-09-22_11-18-13_stair15_safe_passage_v2/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-22_11-48-14_stair16_failure_replay/model_448.pt](local/unitree_b2w_stair/2026-09-22_11-48-14_stair16_failure_replay/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-22_12-04-44_stair17_long_budget/model_548.pt](local/unitree_b2w_stair/2026-09-22_12-04-44_stair17_long_budget/model_548.pt) | 57→16 | 54 | 548 |
| local | [local/unitree_b2w_stair/2026-09-22_12-39-08_stair18_strict_stop/model_448.pt](local/unitree_b2w_stair/2026-09-22_12-39-08_stair18_strict_stop/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-22_13-04-56_stair19_brake/model_448.pt](local/unitree_b2w_stair/2026-09-22_13-04-56_stair19_brake/model_448.pt) | 57→16 | 54 | 448 |
| local | [local/unitree_b2w_stair/2026-09-22_13-14-25_stair20_4096_equal_samples/model_373.pt](local/unitree_b2w_stair/2026-09-22_13-14-25_stair20_4096_equal_samples/model_373.pt) | 57→16 | 54 | 373 |
| local | [local/unitree_b2w_stair/2026-09-22_14-37-29_v3_A_seed54/model_373.pt](local/unitree_b2w_stair/2026-09-22_14-37-29_v3_A_seed54/model_373.pt) | 57→16 | 54 | 373 |
| local | [local/unitree_b2w_stair/2026-09-22_14-40-04_v3_B_seed54/model_373.pt](local/unitree_b2w_stair/2026-09-22_14-40-04_v3_B_seed54/model_373.pt) | 57→16 | 54 | 373 |
| local | [local/unitree_b2w_stair/2026-09-22_14-41-49_v3_A_seed55/model_373.pt](local/unitree_b2w_stair/2026-09-22_14-41-49_v3_A_seed55/model_373.pt) | 57→16 | 55 | 373 |
| local | [local/unitree_b2w_stair/2026-09-22_14-43-35_v3_B_seed55/model_373.pt](local/unitree_b2w_stair/2026-09-22_14-43-35_v3_B_seed55/model_373.pt) | 57→16 | 55 | 373 |
| local | [local/unitree_b2w_stair/2026-09-22_15-00-17_v3_2048_control_seed54_full/model_398.pt](local/unitree_b2w_stair/2026-09-22_15-00-17_v3_2048_control_seed54_full/model_398.pt) | 57→16 | 54 | 398 |
| local | [local/unitree_b2w_stair/2026-09-22_15-00-17_v3_2048_control_seed55_full/model_398.pt](local/unitree_b2w_stair/2026-09-22_15-00-17_v3_2048_control_seed55_full/model_398.pt) | 57→16 | 55 | 398 |
| local | [local/unitree_b2w_stair/2026-09-22_15-04-14_v3_2048_passage_bonus_seed54_full/model_398.pt](local/unitree_b2w_stair/2026-09-22_15-04-14_v3_2048_passage_bonus_seed54_full/model_398.pt) | 57→16 | 54 | 398 |
| local | [local/unitree_b2w_stair/2026-09-22_15-04-14_v3_2048_passage_bonus_seed55_full/model_398.pt](local/unitree_b2w_stair/2026-09-22_15-04-14_v3_2048_passage_bonus_seed55_full/model_398.pt) | 57→16 | 55 | 398 |
| local | [local/unitree_b2w_stair/2026-09-22_15-08-03_v3_2048_late_brake_seed54_full/model_398.pt](local/unitree_b2w_stair/2026-09-22_15-08-03_v3_2048_late_brake_seed54_full/model_398.pt) | 57→16 | 54 | 398 |
| local | [local/unitree_b2w_stair/2026-09-22_15-08-03_v3_2048_late_brake_seed55_full/model_398.pt](local/unitree_b2w_stair/2026-09-22_15-08-03_v3_2048_late_brake_seed55_full/model_398.pt) | 57→16 | 55 | 398 |
| local | [local/unitree_b2w_stair/2026-09-22_15-38-18_v3_2048_stop_speed_seed54_full/model_398.pt](local/unitree_b2w_stair/2026-09-22_15-38-18_v3_2048_stop_speed_seed54_full/model_398.pt) | 57→16 | 54 | 398 |
| local | [local/unitree_b2w_stair/2026-09-22_15-38-18_v3_2048_stop_speed_seed55_full/model_398.pt](local/unitree_b2w_stair/2026-09-22_15-38-18_v3_2048_stop_speed_seed55_full/model_398.pt) | 57→16 | 55 | 398 |
| local | [local/unitree_b2w_stair/2026-09-22_15-48-32_v3_2048_stop_speed_1_seed54_full/model_398.pt](local/unitree_b2w_stair/2026-09-22_15-48-32_v3_2048_stop_speed_1_seed54_full/model_398.pt) | 57→16 | 54 | 398 |
| local | [local/unitree_b2w_stair/2026-09-22_15-48-32_v3_2048_stop_speed_1_seed55_full/model_398.pt](local/unitree_b2w_stair/2026-09-22_15-48-32_v3_2048_stop_speed_1_seed55_full/model_398.pt) | 57→16 | 55 | 398 |
| local | [local/unitree_b2w_stair/2026-09-23_09-10-41_stair_replay_diverse_replay_2048_20260923_seed54_full/model_398.pt](local/unitree_b2w_stair/2026-09-23_09-10-41_stair_replay_diverse_replay_2048_20260923_seed54_full/model_398.pt) | 57→16 | 54 | 398 |
| local | [local/unitree_b2w_stair/2026-09-23_09-10-41_stair_replay_diverse_replay_2048_20260923_seed55_full/model_398.pt](local/unitree_b2w_stair/2026-09-23_09-10-41_stair_replay_diverse_replay_2048_20260923_seed55_full/model_398.pt) | 57→16 | 55 | 398 |
| local | [local/unitree_b2w_stair/2026-09-23_09-14-58_stair_replay_control_2048_20260923_seed54_full/model_398.pt](local/unitree_b2w_stair/2026-09-23_09-14-58_stair_replay_control_2048_20260923_seed54_full/model_398.pt) | 57→16 | 54 | 398 |
| local | [local/unitree_b2w_stair/2026-09-23_09-14-58_stair_replay_control_2048_20260923_seed55_full/model_398.pt](local/unitree_b2w_stair/2026-09-23_09-14-58_stair_replay_control_2048_20260923_seed55_full/model_398.pt) | 57→16 | 55 | 398 |
| local | [local/unitree_b2w_stair/2026-09-23_10-54-54_stair_basevel_basevel60_2048_20260923_seed54_full/model_398.pt](local/unitree_b2w_stair/2026-09-23_10-54-54_stair_basevel_basevel60_2048_20260923_seed54_full/model_398.pt) | 60→16 | 54 | 398 |
| local | [local/unitree_b2w_stair/2026-09-23_10-58-10_stair_basevel_basevel60_2048_20260923_seed55_full/model_398.pt](local/unitree_b2w_stair/2026-09-23_10-58-10_stair_basevel_basevel60_2048_20260923_seed55_full/model_398.pt) | 60→16 | 55 | 398 |
| local | [local/unitree_b2w_stair/2026-09-23_11-02-18_stair_basevel_control57_2048_20260923_seed54_full/model_398.pt](local/unitree_b2w_stair/2026-09-23_11-02-18_stair_basevel_control57_2048_20260923_seed54_full/model_398.pt) | 57→16 | 54 | 398 |
| local | [local/unitree_b2w_stair/2026-09-23_11-04-25_stair_basevel_control57_2048_20260923_seed55_full/model_398.pt](local/unitree_b2w_stair/2026-09-23_11-04-25_stair_basevel_control57_2048_20260923_seed55_full/model_398.pt) | 57→16 | 55 | 398 |
| local | [local/unitree_b2w_stair/2026-09-23_12-03-15_stair_ascent45_57d_2048_20260923_seed54_full/model_398.pt](local/unitree_b2w_stair/2026-09-23_12-03-15_stair_ascent45_57d_2048_20260923_seed54_full/model_398.pt) | 57→16 | 54 | 398 |
| local | [local/unitree_b2w_stair/2026-09-23_12-03-15_stair_ascent45_57d_2048_20260923_seed55_full/model_398.pt](local/unitree_b2w_stair/2026-09-23_12-03-15_stair_ascent45_57d_2048_20260923_seed55_full/model_398.pt) | 57→16 | 55 | 398 |
| local | [local/unitree_b2w_stair/2026-09-23_13-23-37_stair_landing20_short_2048_20260923_seed54_full/model_422.pt](local/unitree_b2w_stair/2026-09-23_13-23-37_stair_landing20_short_2048_20260923_seed54_full/model_422.pt) | 57→16 | 54 | 422 |
| local | [local/unitree_b2w_stair/2026-09-23_13-23-37_stair_landing20_short_2048_20260923_seed55_full/model_422.pt](local/unitree_b2w_stair/2026-09-23_13-23-37_stair_landing20_short_2048_20260923_seed55_full/model_422.pt) | 57→16 | 55 | 422 |
| local | [local/unitree_b2w_stair/2026-09-23_13-56-42_stair_physical_rollin_2048_20260923_seed54_full/model_422.pt](local/unitree_b2w_stair/2026-09-23_13-56-42_stair_physical_rollin_2048_20260923_seed54_full/model_422.pt) | 57→16 | 54 | 422 |
| local | [local/unitree_b2w_stair/2026-09-23_13-56-42_stair_physical_rollin_2048_20260923_seed55_full/model_422.pt](local/unitree_b2w_stair/2026-09-23_13-56-42_stair_physical_rollin_2048_20260923_seed55_full/model_422.pt) | 57→16 | 55 | 422 |
| local | [local/unitree_b2w_stair/2026-09-23_14-39-04_stair_wheel_head_only_2048_20260923_seed54_full/model_422.pt](local/unitree_b2w_stair/2026-09-23_14-39-04_stair_wheel_head_only_2048_20260923_seed54_full/model_422.pt) | 57→16 | 54 | 422 |
| local | [local/unitree_b2w_stair/2026-09-23_14-39-04_stair_wheel_head_only_2048_20260923_seed55_full/model_422.pt](local/unitree_b2w_stair/2026-09-23_14-39-04_stair_wheel_head_only_2048_20260923_seed55_full/model_422.pt) | 57→16 | 55 | 422 |
| local | [local/unitree_b2w_stair/2026-09-23_14-54-17_stair_moving_anchor10_2048_20260923_seed54_full/model_422.pt](local/unitree_b2w_stair/2026-09-23_14-54-17_stair_moving_anchor10_2048_20260923_seed54_full/model_422.pt) | 57→16 | 54 | 422 |
| local | [local/unitree_b2w_stair/2026-09-23_14-54-17_stair_moving_anchor10_2048_20260923_seed55_full/model_422.pt](local/unitree_b2w_stair/2026-09-23_14-54-17_stair_moving_anchor10_2048_20260923_seed55_full/model_422.pt) | 57→16 | 55 | 422 |
| server | [server/upstream_5000/upstream_model_5000.pt](server/upstream_5000/upstream_model_5000.pt) | 57→16 | 44 | 5000 |
| server | [server/upstream_10000/upstream_model_10000.pt](server/upstream_10000/upstream_model_10000.pt) | 57→16 | 44 | 10000 |
| server | [server/upstream_15000/upstream_model_15000.pt](server/upstream_15000/upstream_model_15000.pt) | 57→16 | 44 | 15000 |
| server | [server/upstream_18100/upstream_model_18100.pt](server/upstream_18100/upstream_model_18100.pt) | 57→16 | 44 | 18100 |
| server | [server/upstream_19999/upstream_model_19999.pt](server/upstream_19999/upstream_model_19999.pt) | 57→16 | 44 | 19999 |

Всего 75 snapshots, 413.5 MiB до Git compression.
Проверка целостности: `python scripts/archive_experimental_policies.py --verify`.
