# Sim2sim timing: GC и deferred telemetry, 12 октября 2026

**Timing/measurement failures устранены в bounded replay без увеличения
лимитов.** Все5 programs/9400 ticks выполнены, measurement valid5/5,
transport faults0, capture drops0, stop5/5, unsafe0. Runtime gate passed.
Stand/mixed success, осевые tracking gates всё ещё failed: policy promotion
или полная simulation qualification отсутствует.

Job `0e574426bf7b4b94a56c0e5ef2595990`, exit0, завершён14:53:51 МСК.
Raw: `logs/dashboard/jobs/0e574426bf7b4b94a56c0e5ef2595990/sim2sim_timing/`.
[Summary](evidence/sim2sim_timing_20261012/summary.json),
[analysis](evidence/sim2sim_timing_20261012/analysis.json),
[frozen plan](evidence/sim2sim_timing_20261012/frozen_plan.json),
[guard/deadlines](evidence/sim2sim_timing_20261012/frozen_guard_plan.json),
[manifest](evidence/sim2sim_timing_20261012/manifest.json).

## Разбор прежних failures

В [предыдущем replay](2026-10-12-sim2sim-pd-guard.md) physics timeline yaw
остановился на24.149784мс: sim time продвинулся только с33.290 до33.292,
DDS tick/generation в этот промежуток также стоял. Actor в соседних ticks
занимал0.44–0.65мс и выполнялся вовремя. Это stall physics producer,
а не потеря данных при offline CSV parsing или медленный actor.

В failed yaw repeat inference38.870064мс, в то время как physics произвёл
19 samples сmaxinterval2.020455мс. Блокировался Python actor. В отличие от
основного runner repeat не отключал cyclic GC. Старые aggregate timestamps
не содержат per-stage CPU/GC trace: нельзя точно назначить historical
physics pause конкретному syscall вместо scheduling, или доказать событие
GC именно на historical tick342. Эти границы причинного вывода сохранены.

## Воспроизведение механизмов

Managed CPU fixture replay `7e06c0fced81463c9396957ab22b64cc`:
6000 steps сGC и6000 без него, unchanged exported actor иstate изfailed tick.
[Probe summary](evidence/sim2sim_timing_20261012/probe_summary.json),
[executed hashes](evidence/sim2sim_timing_20261012/probe_manifest.json).
Automatic gen2 GC дал47.083845 и61.317023мс step, почти полностью CPU time,
внутри make_observation; сам actor forward около0.115мс. Maxgen2 collection
60.749589мс. БезGC maxstep0.581802мс, автоматических collections0.
Значит memory/GC pause может превышать20мс даже при быстром neural forward.
Семантика [Python GC](https://docs.python.org/3.11/library/gc.html): automatic
cyclic collection дополняет reference counting; scoped disable не отменяет
обычное освобождение acyclic objects. Probe instrumentation добавляет
allocations, поэтому его collection tick numbers не являются replay
historical GC schedule. Raw CPU result сохранён неизменным локально.

Controlled IO A/B в native DDS stand, по одному12s program на arm:
один CSV write задержан25мс через per-child test-only preload library.
[IO evidence](evidence/sim2sim_timing_20261012/io_probe.json).
Уlegacy synchronous-CSV bridge sample age13.447785мс, measurement invalid;
уfixed bridge age2.197808мс, valid. Injector сработал уfixed **после последнего
physics sample**, задержав только post-run serialization. Native model,
actor иguards в обоих arms одинаковые. Это демонстрирует иустраняет IO stall
механизм; исходный historical physics syscall не был traced.

## Изменения

`bounded_gc` перенесён на boundary общего trial, чтобы standalone repeats
также не запускали automatic collection внутри policy loop. GC collect
происходит до запуска live physics, restore — после остановки native services,
включая exception path. Parent disabled-GC state сохраняется корректно.

В новом `b2w_mujoco_timed_bridge` samples копируются в заранее выделенную,
потроганную память. Clock timestamp фиксируется сразу после реального mj_step;
CSV serialization выполняется после остановки physics иdestruction DDS bridge.
Нет timestamp backdating, interpolation, overwrite илиsilent drop; при
capacity exhaustion/read-write failure execution fails. Maximum duration60s,
каждыйcase≤55s сexisting shutdown margin. Physical abort checks прежние;
finite checks дополнительно охватывают всеlogged q/dq/force/root q.

Added wall/thread-CPU timings для observation, forward, target mapping,
evidence snapshot иnative bridge/physics/capture; context-switch/page-fault
счётчики доступны вphysics timing CSV. CPU/thread time измеряется через
[thread_time_ns](https://docs.python.org/3.11/library/time.html#time.thread_time_ns)
иCLOCK_THREAD_CPUTIME_ID, а actual sample age — прежним monotonic clock.

Только собственные processes/threads job закреплены на отдельных физических
cores: actor9, physics10, watchdog11; siblings21/22/23 не выбирались для
второй роли. Глобальные scheduler/governor/drivers, чужие процессы иprojects
не изменены; realtime priority не запрашивалась. Torch intra/inter-op1.
Это bounded local scheduling arrangement, не hard realtime гарантия.

Actor/export/checkpoint/raw-history/ABI57→16, physics XML, reset73001,
friction1, mass/inertia/armature0.1/damping1, DC law/caps иPD/actual guard
сохранены. Guard binary тот же, что вprevious PD replay. Deadlines inference20,
state40,target60,command100мс; publishermaxinterval10мс иmeasurementage10мс
**не увеличены**. Legacy binaries/raw evidence сохранены.

## Проверки и повтор

В основном job46 tests:44 passed,2 skipped; vendor1463 files/6 sources verified;
DC grid1232+disabled240 points unchanged. Native39 guard +48 transport fault
cases повторно passed подчетырьмя CPU workers до role placement/motion.
Tests-only job `d445c6a03d2f4703803969abf206c50b` добавил3/3 focused checks:
GC restore success/exception/nested-disabled state, distinct-core topology,
256-state numeric parity против frozen previous runtime. Observations,
actions, targets, motors иraw history совпали точно.
[Focused result](evidence/sim2sim_timing_20261012/focused_tests_result.json).
Total49 tests:47 passed,2 skipped; full historical suite не повторялся.

Пять неизменённых v2 programs, independent reset/robot per case, один repeat.
IO A/B — отдельные mechanism tests, неpolicy successes или дополнительные
qualification repeats.

| Case | Policy ticks | Maxinference мс | Maxsample age мс | Maxphysics gap мс | Outcome |
|---|---:|---:|---:|---:|---|
| stand | 600 | 0.748116 | 0.261229 | 2.284495 | success |
| longitudinal | 2500 | 1.101495 | 0.912255 | 5.194305 | tracking_failure |
| lateral | 2500 | 0.872352 | 0.899579 | 2.295877 | tracking_failure |
| yaw | 2500 | 1.055969 | 1.150949 | 3.153831 | tracking_failure |
| mixed | 1300 | 0.832787 | 1.383178 | 3.810795 | success |

Maxinference1.101495мс, maxsampleage1.383178мс, maxphysicsgap5.194305мс,
maxpublisherinterval4.921599мс. Measurements valid5/5, continuouszero stop5/5,
physics force caps passed5/5, XML identical5/5. Full runtime gate passed;
performance/tracking acceptance2/5. Исторические runs сfailed gates
не пересчитаны по новым правилам иих hashes не подменены.

## Provenance и следующий шаг

Manifest SHA `d5c5a35703caa9ddd8db54109ff18b6df4436268c926841ac374f8f349494281`. Проверены229 raw files/45 executed
source snapshots, artifact/export/checkpoint hashes.
[Integrity](evidence/sim2sim_timing_20261012/integrity.json).

| Artifact | SHA-256 |
|---|---|
| Export24650 | `6d2b67e477d8c51f3d4260694f616dd2dcd93f0a961abca48a866012bc596d36` |
| Ancestor19999 export | `f2ce3266dac64d44f06dcb8e336470da4b33e33bb38cdd21b73b9b200d809bff` |
| Fixed telemetry bridge | `ac3f76169d2018aeb06a90cd2c8db7cdcda4749bfc975e198bc0c32732d1a58e` |
| Unchanged PD watchdog | `00667de1f9d10ee92cf6d6f436e3302ebe01ca5baa35dd180f8b0bf4b21c8a5f` |

После run добавлен managed focused-tests entrypoint иего pattern вfuture
preflight. Эти implementation hashes отдельно записаны вanalysis; изменённые
source metadata не выдаются за executed source hashes основного job.

Requested timing diagnosis/fix/replay выполнены. Следующий development scope:
matched physics/passive dynamics иосевой tracking, не увеличение timing
budgets. Single-seed bounded success не закрывает весь S2 envelope,
watchdog-process failure mitigation, hardware calibration илиqualification.
PPO/hardware actions не выполнялись, candidate24650 остаётся прежним.
