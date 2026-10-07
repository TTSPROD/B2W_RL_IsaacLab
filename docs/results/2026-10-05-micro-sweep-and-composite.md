# Micro-sweep и command-gated composite

## 2×2 screen

Training job `a22e1ee2d3e94fd7a8f08bed0410aaf6` выполнил четыре ветви
от `core_24650`: 25 standard PPO updates, 512 envs, 307 200 transitions
на ветвь, общий seed 9912. Evaluation recovery job
`10d747f88f7f432896b60eda4a139c32` повторно не обучал actors и завершил
300 fresh matched episodes с exit 0.

| Вариант | Порядок знаков | PPO | Success | Unsafe | Lateral | Yaw |
|---|---|---|---:|---:|---:|---:|
| parent 24650 | исходный | — | 27/60 | 0 | 0.6831 | 0.6666 |
| standard/order | исходный | LR 1e-5, 5 epochs | 26/60 | 0 | 0.6797 | 0.6911 |
| standard/balanced | counterbalanced | LR 1e-5, 5 epochs | 24/60 | 0 | 0.7355 | 0.6804 |
| conservative/order | исходный | LR 1e-6, 1 epoch | 25/60 | 2 | 0.6931 | 0.6686 |
| conservative/balanced | counterbalanced | LR 1e-6, 1 epoch | 25/60 | 0 | 0.6783 | 0.6623 |

Ни одна цельная дообученная policy не сохранила parent retention. Standard/balanced
подтвердил причинный эффект counterbalanced command order на lateral response,
но потерял stairs-up traversal `2/5 → 0/5` и stairs-down stop/restart `5/5 → 3/5`.
Conservative PPO эту межзадачную интерференцию не устранил. Stage 2 автоматически
не запускался.

## Composite без новых updates

Job `605cb4fb65d84a83b1fe2edc67a4d79d` собрал один TorchScript actor ABI
`57→16`: parent обслуживает zero, чистый longitudinal и mixed commands;
standard/balanced обслуживает только чистые lateral и yaw. Команды читаются
из frozen observation slice `[6:9]` с scale 1.0. На 1024 fixtures после
save/reload получена точная branch parity, max error `0.0`.

Свежий изолированный probe: 120 episodes, одинаковые case/reset slots,
по одному actor на процесс.

| Метрика | 24650 | Composite | Δ |
|---|---:|---:|---:|
| Success | 27/60 | 27/60 | 0 |
| Unsafe | 0 | 0 | 0 |
| Lateral response | 0.6831 | 0.7243 | +0.0412 |
| Yaw response | 0.6666 | 0.6909 | +0.0243 |
| Max wheel saturation | 0.1275 | 0.1275 | 0 |
| Max leg saturation | 0.0074 | 0.0074 | 0 |

Все 60 бинарных outcomes совпали (`0 wins / 0 losses / 60 ties`), все cells
и failure counts сохранены, retention reasons пусты. Поэтому результат
**диагностически положительный**: измеримый response gain без behavioral/safety
регрессии. Это не simulation qualification и не новая принятая policy:
lateral/yaw cells всё ещё `0/5`, общий success не вырос, mixed-command region
остаётся полностью на parent, validation и hardware checks не выполнены.

## Вывод и следующий ограниченный опыт

Причина отрицательных fine-tunes теперь локализована лучше: общий actor получает
конфликтующие обновления разных cohorts; исправление sampling улучшает малые оси,
но теми же weights портит лестничный навык. Уменьшение learning rate/epochs
не меняет знак компромисса за 25 updates.

Самый короткий путь к росту именно success — продолжать только balanced specialist
до заранее выбранных cumulative checkpoints (например 75/100/150), проверяя его
только внутри composite. Parent-ветвь при этом должна оставаться байт-в-байт
неизменной. До нового обучения надо отдельно заморозить критерий выбора checkpoint,
mixed-command/blending probe и второй seed; текущий результат не даёт автоматического
разрешения на stage 2 или promotion.

Raw results:

- `logs/dashboard/jobs/10d747f88f7f432896b60eda4a139c32/result.json`, SHA-256
  `47bc94ba8808b05e127b7dca80b7fbe383cea7bd4b3bc37e5aae3fe5c6033858`;
- `logs/dashboard/jobs/605cb4fb65d84a83b1fe2edc67a4d79d/result.json`, SHA-256
  `68c163feb114f00cb729b57c863edc5896ddd34ef71dcf2d0aa9cffd33c9ed4f`;
- composite export SHA-256
  `ea9129d95375524bdece6b28d37f008c706a726bccda0160f0bb98e5f0f0d96c`.
