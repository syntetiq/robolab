# Сенсоры по ТТХ в сцене бенча (test_robot_bench)

## Какие сенсоры предусмотрены по ТТХ TIAGo (PAL)

По спецификации и по реализации в `data_collector_tiago.py` у TIAGo в симуляции доступны:

| Сенсор | Описание | Данные |
|--------|----------|--------|
| **Head camera** | Камера на голове (`head_2_link`) | RGB, depth (distance_to_camera), pointcloud, semantic |
| **Wrist camera** | Камера на звене руки (`arm_tool_link`) | RGB, depth, pointcloud |
| **External camera** | Фиксированная камера в мире | RGB, depth (опционально) |
| **Contact sensors** | На пальцах гриппера (left/right finger link) | Контакты/силы при захвате |

В **test_robot_bench** по умолчанию используются только **фиксированные камеры сцены** (top_kitchen, isometric_kitchen, front_kitchen) и **нет** камер на роботе, depth и контактных сенсоров.

---

## Что сделать, чтобы в сцене робот использовал сенсоры по ТТХ

### 1. Включить сенсоры флагами при запуске

В `run_task_config.ps1` добавлены ключи (передаются в `test_robot_bench.py`):

- `-RobotHeadCamera` — камера на `head_2_link`
- `-WristCamera` — камера на `arm_tool_link`
- `-ExternalCamera` — фиксированная внешняя камера
- `-ReplicatorDepth` — писать depth (distance_to_camera) и pointcloud
- `-ContactSensors` — включить контактные сенсоры на пальцах гриппера

Примеры:

```powershell
# Камера на голове робота (вид от первого лица) и depth
.\scripts\run_task_config.ps1 -Config config/tasks/fixed_fridge_experiment3.json -RobotHeadCamera -ReplicatorDepth

# Полный набор по ТТХ: голова + запястье + внешняя камера + depth + контактные сенсоры
.\scripts\run_task_config.ps1 -Config config/tasks/fixed_fridge_experiment3.json -RobotHeadCamera -WristCamera -ExternalCamera -ReplicatorDepth -ContactSensors
```

### 2. Включить сенсоры через конфиг задачи

В JSON конфиге задачи (например `fixed_fridge_experiment3.json`) можно добавить секцию `sensors`:

```json
{
  "sensors": {
    "robot_head_camera": true,
    "wrist_camera": false,
    "external_camera": true,
    "replicator_depth": true,
    "contact_sensors": true
  }
}
```

Если секция есть, бенч выставит соответствующие флаги перед запуском камер и сенсоров.

### 3. Где лежат данные

- **Видео:** в папке эпизода `heavy/`:  
  `head_robot.mp4`, `wrist_robot.mp4`, `external_robot.mp4` (если включены),  
  плюс по‑прежнему `top_kitchen.mp4`, `isometric_kitchen.mp4`, `front_kitchen.mp4`.
- **Depth/pointcloud:** в подпапках Replicator, например  
  `replicator_head_robot/distance_to_camera_*.npy`, `pointcloud_*.npy` (если включён `replicator_depth`).
- **Контактные сенсоры:** данные доступны через Isaac Sim ContactSensor API во время симуляции; при необходимости их можно логировать в physics_log или отдельный файл.

---

## Итог

- Чтобы в сцене бенча робот использовал сенсоры по ТТХ: включите **robot-head-camera** (и при необходимости wrist, external, replicator-depth, contact-sensors) через **флаги** или через секцию **sensors** в конфиге задачи.
- После этого в сцене будут задействованы камера на голове (и опционально на запястье и внешняя), при включённом depth — данные Replicator по глубине/облаку точек, и при включённых contact-sensors — контактные сенсоры на гриппере, как в data_collector и по ТТХ.
