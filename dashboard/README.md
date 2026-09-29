# Локальный dashboard B2W

```powershell
& .\scripts\run_local.ps1 dashboard/server.py
```

Открыть `http://127.0.0.1:8765`. Сервер работает только на loopback и не имеет
API управления обучением. Он показывает доступные локальные TensorBoard runs,
checkpoints и автоматически найденный последний checkpoint-selection.

Локальные evaluation-runner'ы запускают dashboard автоматически. Раздел
`Оценка policy` обновляется каждые 10 секунд и показывает активный batch,
готовые поверхности, предварительный unsafe-first рейтинг и ETA после первого
завершённого batch. Ручной polling evaluation не требуется.

Live logs читаются из `logs/rsl_rl`; их отсутствие после очистки не влияет на
registry. Постоянные веса и результат находятся в `policies/local/core_24650`
и `docs/results/evidence/core_24650_20260928`.
