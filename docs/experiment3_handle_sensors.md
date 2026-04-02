# Experiment 3: габариты ручки холодильника и сенсоры симуляции

## 1. Габариты ручки холодильника (fixed kitchen)

Источник: `scenes/kitchen_fixed/kitchen_fixed_config.yaml` → `furniture.fridge.handle`.

| Параметр | Значение | Описание |
|----------|----------|----------|
| **type** | vertical | Вертикальная ручка |
| **length** | **0.50 м** | Высота ручки (по вертикали) |
| **width** | **0.06 м** | Ширина (по горизонтали вдоль двери) |
| **depth** | **0.06 м** | Глубина (выступ от двери) |
| **standoff** | 0.06 м | Зазор между дверью и ручкой |
| **center_height** | 1.10 м | Высота центра ручки над полом |

В коде (`kitchen_fixed_builder.py`) ручка собирается как куб `Bar` с размерами **depth × width × length** = **0.06 × 0.06 × 0.50 м** и двумя скобами (Bracket0, Bracket1). Путь в сцене: `/World/Kitchen/Furniture/Fridge/Door/Handle`.

**Итого габариты ручки:** 6 см × 6 см × 50 см (глубина × ширина × высота).

---

## 2. Сенсоры, используемые во время симуляции (test_robot_bench)

### 2.1 Камеры (Replicator, запись видео)

При запуске с видео (`run_task_config.ps1` без `-NoVideo`) создаются 3 камеры:

| Камера | Позиция (примерно) | Направление | Данные |
|--------|--------------------|-------------|--------|
| **top_kitchen** | (0, 1.7, 7) | Вниз на кухню | RGB, каждый кадр → `replicator_top_kitchen/rgb_*.png` → кодируется в `top_kitchen.mp4` |
| **isometric_kitchen** | (-3.5, -2, 3.5) | На центр кухни | То же → `isometric_kitchen.mp4` |
| **front_kitchen** | (0, -2, 1.5) | Спереди на кухню | То же → `front_kitchen.mp4` |

Разрешение задаётся аргументами `--width`, `--height` (по умолчанию 640×480). **Данные:** только RGB-изображения; в логику управления роботом не подаются (только запись для анализа и датасетов).

### 2.2 Состояние робота (логирование и управление)

Используются данные из **Articulation** (Isaac Sim):

| Данные | Источник | Использование |
|--------|----------|----------------|
| **Позиция и ориентация базы** | `articulation.get_world_pose()` | Навигация, расчёт целевой точки подъезда, расчёт yaw |
| **Позиции суставов (DOF)** | `articulation.get_joint_positions()` | Управление рукой/гриппером, проверка позы (pre_grasp_handle, handle_reach_left и т.д.) |
| **Скорости суставов** | `articulation.get_joint_velocities()` | Опционально в логере (physics_log), не в управлении дверью |
| **Позиция звена EE (tool/gripper)** | Через `get_prim_world_pose(ee_link_path)` по USD | Расстояние до ручки, переход в pull_or_push |

Точные имена DOF задаются в `resolve_dof_names(articulation)` (все револьютные и призматические суставы робота, включая колёса, торс, руки, гриппер).

### 2.3 Сцена (для логики двери)

| Данные | Источник | Использование |
|--------|----------|----------------|
| **Позиция ручки в мире** | `get_prim_world_position(handle_usd_path)` | Цель подъезда (drive_to_handle), расстояние до гриппера |
| **Угол двери** | RevoluteJoint или ориентация примитива двери | Критерий успеха open/close (min_angle_deg / max_angle_deg) |
| **Позиция петли (hinge_world_xy)** | Из конфига задачи | Направление pull/push по касательной к дуге двери |

### 2.4 Чего нет в test_robot_bench

- **Тактильные/контактные сенсоры** в bench не используются. В `data_collector_tiago.py` для реального/VR сценария есть контактные сенсоры на пальцах гриппера (Contact_Sensor на left/right finger link) — в симуляции bench их нет.
- **Depth/Lidar** не используются.
- **Силы/моменты** с суставов не считываются для управления.

---

## 3. Сохранение видео с эпизода

При запуске **с видео** (без `-NoVideo`):

- Выходная папка: `C:\RoboLab_Data\episodes\fixed_fridge_experiment3_<timestamp>\`
- Видео лежат в подпапке `heavy\`:
  - `top_kitchen.mp4`
  - `isometric_kitchen.mp4`
  - `front_kitchen.mp4`

Команда одного прогона с видео:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_task_config.ps1 -Config config/tasks/fixed_fridge_experiment3.json
```

Видео кодируются после симуляции из PNG-кадров Replicator и сохраняются автоматически.
