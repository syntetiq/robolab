# Конфигурация телеуправления Tiago (рабочая, 18.03.2026)

## Компоненты системы

### 1. Isaac Sim (data_collector_tiago.py)
- **Скрипт**: `scripts/data_collector_tiago.py`
- **Запуск**: через `kit.exe` с флагами `--gui --moveit --mobile-base`
- **Сцена**: `C:\RoboLab_Data\scenes\kitchen_fixed.usd`
- **Робот**: `/World/Tiago`, стартовая позиция `(0.8, 0.0, 0.08)`, yaw=0°
- **Физика**: `world.step(render=True)` — обязательно для продвижения физики в GUI-режиме

### 2. MoveIt Stack (start_moveit_stack.ps1)
- **move_group.exe** — MoveIt2 планировщик, `arm_torso` группа
- **ros2_fjt_proxy.py** — IPC-мост: `pending_*.json` → Isaac Sim → `done_*.json`
- **moveit_intent_bridge.py** — слушает `/tiago/moveit/intent`, выполняет последовательности
- **ROS_DOMAIN_ID**: 77, **ROS_LOCALHOST_ONLY**: 1

### 3. Web Application (Next.js)
- **Порт**: 3000
- **Launch Profile**: "GUI + MoveIt Teleop (Local)" (`enableGuiMode=true`, `enableMoveIt=true`)
- **Сцена по умолчанию**: "Kitchen Fixed (Experiments 1-3)"

## IPC-протокол

### Движение базы (base_cmd.json)
- **Путь**: `C:\RoboLab_Data\fjt_proxy\base_cmd.json`
- **Формат**: `{"vx": 0.3, "vy": 0.0, "vyaw": 0.0}`
- **Запись**: Node.js `fs.writeFileSync` (без BOM!)
- **Чтение**: Isaac Sim каждый кадр (60 Hz)
- **Expiry**: файл старше 500ms игнорируется → робот останавливается автоматически
- **Оси**: `vx` = мировая +X, `vy` = мировая +Y, `vyaw` = поворот вокруг Z

### Маппинг кнопок → скорости
| Кнопка | vx | vy | vyaw |
|--------|-----|-----|------|
| Forward (+X) | +0.3 | 0 | 0 |
| Backward (-X) | -0.3 | 0 | 0 |
| Left (+Y) | 0 | +0.3 | 0 |
| Right (-Y) | 0 | -0.3 | 0 |
| Rotate Left | 0 | 0 | +0.5 |
| Rotate Right | 0 | 0 | -0.5 |
| Stop / E-Stop | 0 | 0 | 0 |

### Диагностика позиции (base_pose.json)
- **Путь**: `C:\RoboLab_Data\fjt_proxy\base_pose.json`
- **Формат**: `{"x": 0.8, "y": 0.0, "z": 0.08, "yaw_rad": 0.0, "yaw_deg": 0.0, "t": ...}`
- **Обновление**: каждые 30 кадров (~0.5 сек)

### Управление рукой (MoveIt intent)
- **Путь**: ROS2 topic `/tiago/moveit/intent` (через `ros2_pub_string.py`)
- **Обработка**: `moveit_intent_bridge.py` → последовательности `move_direct` / `move` / `gripper`
- **IPC**: `pending_*.json` → Isaac Sim → `done_*.json` в `C:\RoboLab_Data\fjt_proxy\`

### Joint State (joint_state.json)
- **Путь**: `C:\RoboLab_Data\fjt_proxy\joint_state.json`
- **Запись**: Isaac Sim каждый кадр
- **Чтение**: `moveit_intent_bridge.py` для текущих позиций суставов

## Порядок запуска

1. `npm run dev` — web app на порту 3000
2. Создать эпизод (сцена: Kitchen Fixed, профиль: GUI + MoveIt Teleop)
3. Нажать "Start Episode" → запускается Isaac Sim с `--gui --moveit --mobile-base`
4. Дождаться загрузки (~90 сек), проверить `joint_state.json` обновляется
5. `scripts/start_moveit_stack.ps1 -RosDomainId 77` → MoveIt stack (~15 сек)
6. Открыть страницу эпизода → Teleoperation Control Panel

## Важные детали

- **BOM**: PowerShell `Out-File -Encoding utf8` добавляет BOM — Python не парсит. Использовать `[System.IO.File]::WriteAllText()` или Node.js `fs.writeFileSync()`.
- **`simulation_app.update()` vs `world.step()`**: НЕЛЬЗЯ использовать `simulation_app.update()` в основном цикле — не продвигает физику. Только `world.step(render=True)`.
- **`--mobile-base`**: без этого флага база зафиксирована, `base_cmd.json` игнорируется.
- **Home Kitchen** (`Small_House_Interactive.usd`): отключена (`enabled=false`), не использовать.

## Доступные MoveIt-команды (рука + гриппер)

| Команда UI | Intent | Действие |
|------------|--------|----------|
| MoveIt Home | `go_home` | Рука в нейтральную позу (move_direct) |
| Plan Pick | `plan_pick` | Открыть гриппер → pre-grasp → grasp → закрыть → поднять → к раковине → открыть → home |
| Plan Place | `plan_place` | К месту → открыть гриппер → home |
| Pick Sink | `plan_pick_sink` | Аналогично plan_pick, цель — раковина |
| Pick Fridge | `plan_pick_fridge` | Аналогично, цель — холодильник |
| Approach Workzone | `approach_workzone` | Рука в рабочую зону перед столом |
| Open/Close Fridge | `open_close_fridge` | Подъехать → схватить ручку → потянуть → отпустить → закрыть |
| Open/Close Dishwasher | `open_close_dishwasher` | Аналогично для посудомойки |
| Grasp Mug | `grasp_mug` | Через teleop intent (не MoveIt) |
