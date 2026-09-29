# Локальный dashboard B2W

```powershell
& .\scripts\run_local.ps1 dashboard/server.py
```

Открыть `http://127.0.0.1:8765`. Сервер работает только на loopback и не имеет
API управления обучением. Он показывает доступные локальные TensorBoard runs,
checkpoints и сводку выбранной policy 24650.

Live logs читаются из `logs/rsl_rl`; их отсутствие после очистки не влияет на
registry. Постоянные веса и результат находятся в `policies/local/core_24650`
и `docs/results/evidence/core_24650_20260928`.
