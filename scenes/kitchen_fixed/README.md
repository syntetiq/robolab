# Fixed Kitchen Scene for TIAGo Manipulation

An 8×8 m deterministic kitchen scene for Isaac Sim robot manipulation experiments with TIAGo.

## File Structure

```
scenes/kitchen_fixed/
  kitchen_fixed_builder.py   # Standalone Isaac Sim script — builds scene, saves USD
  kitchen_fixed_config.yaml  # All dimensions, positions, materials
  kitchen_fixed.usd          # Generated USD stage (created by builder)
  README.md                  # This file
```

## Coordinate System

| Property        | Value                       |
| --------------- | --------------------------- |
| World origin    | Center of room (0, 0, 0)   |
| Up axis         | Z                           |
| Units           | Meters                      |
| Floor bounds X  | -4.0 to +4.0               |
| Floor bounds Y  | -4.0 to +4.0               |
| Wall height     | 2.8 m                       |
| Wall thickness  | 0.15 m                      |
| North wall Y    | +4.0 (outer), +3.85 (inner)|

All furniture is placed along the **north wall** with rear faces flush to the inner wall surface at Y = 3.85.

Robot starts at **(0, 0)** and approaches furniture from the south (negative Y direction).

## Furniture Layout

All items are 0.80 m wide with 0.10 m gaps. Total span: 3.50 m, centered on X = 0.

Left-to-right along the north wall:

| Item           | Center X | Center Y | Width | Depth | Height | Top Z |
| -------------- | -------- | -------- | ----- | ----- | ------ | ----- |
| Refrigerator   | -1.35    | +3.45    | 0.80  | 0.80  | 2.00   | 2.00  |
| Sink Cabinet   | +0.45    | +3.45    | 0.80  | 0.80  | 0.90   | 0.93  |
| Table          | +1.35    | +3.45    | 0.80  | 0.80  | 0.80   | 0.80  |

Center Y = wall_inner - depth/2 = 3.85 - 0.40 = **3.45** for all items.

## Object Placements

Objects are placed on the table (center at X=1.35, Y=3.45, top at Z=0.80):

| Object | World X | World Y | World Z  | Dimensions          |
| ------ | ------- | ------- | -------- | ------------------- |
| Plate  | 1.60    | 3.45    | 0.8125   | r=0.15, h=0.025     |
| Apple  | 1.67    | 3.45    | ~0.88    | r=0.05 (sphere)     |
| Banana | 1.55    | 3.45    | ~0.86    | r=0.030, l=0.22     |
| Mug    | 1.15    | 3.30    | 0.85     | r=0.04, h=0.10      |

## Prim Hierarchy

```
/World/Kitchen/
  PhysicsScene
  Looks/                          # All PBR materials
    floor_tile, wall_paint, appliance_metal, appliance_door,
    handle_metal, cabinet_wood, sink_metal, table_wood,
    ceramic_white, apple_red, banana_yellow, mug_ceramic, shelf_metal
  Floor/Slab
  Walls/NorthWall, SouthWall, EastWall, WestWall
  Lights/DomeLight, CeilingLight0..3
  Cameras/top, front, isometric
  Furniture/
    Fridge/
      Cabinet/Body, Shelf0..3
      Door/Panel, Handle/Bar, Handle/Bracket0, Handle/Bracket1
      DoorHinge                   # RevoluteJoint 0-90°
    SinkCabinet/
      Cabinet/Body
      CounterTop/Slab
      Basin/Floor, WallN, WallS, WallE, WallW
    Table/
      Top/Slab
      Legs/Leg0..3
  Objects/
    Plate/Disc
    Apple/Body
    Banana/Body
    Mug/Body
```

## Graspable Handle Design

### Fridge Handle (vertical)

- **Bar:** 0.30 m tall × 0.02 m × 0.02 m
- **Standoff:** 0.04 m from door surface (finger clearance for parallel gripper)
- **Center height:** 1.20 m above floor
- **Graspable section:** 0.15 m (center portion of bar)
- **Mounting:** Two brackets at top and bottom connecting bar to door
- **Position:** Near the right edge of the door (Y offset = half_width - 0.08)
- **Collision:** Dedicated box collider on the bar — not decorative mesh

The 0.04 m standoff provides sufficient clearance for TIAGo's parallel gripper fingers to wrap around the bar from the front approach direction (-Y).

## Articulation

The fridge door uses `RevoluteJoint` (USD Physics):

| Appliance   | Joint Path                                        | Axis | Range   | Door Mass |
| ----------- | ------------------------------------------------- | ---- | ------- | --------- |
| Fridge      | /World/Kitchen/Furniture/Fridge/DoorHinge         | Y    | 0-90°   | 8 kg      |

Body0 = Cabinet (kinematic), Body1 = Door (dynamic).

## PBR Materials

All materials use the `OmniPBR` shader and are defined under `/World/Kitchen/Looks/`.

| Material         | Diffuse RGB           | Roughness | Metallic | Use                    |
| ---------------- | --------------------- | --------- | -------- | ---------------------- |
| floor_tile       | (0.85, 0.85, 0.82)   | 0.5       | 0.0      | Kitchen floor          |
| wall_paint       | (0.95, 0.93, 0.90)   | 0.9       | 0.0      | All walls              |
| appliance_metal  | (0.82, 0.82, 0.84)   | 0.3       | 0.6      | Fridge/DW cabinets     |
| appliance_door   | (0.88, 0.90, 0.92)   | 0.25      | 0.5      | Fridge/DW door panels  |
| handle_metal     | (0.35, 0.35, 0.38)   | 0.4       | 0.8      | All handles            |
| cabinet_wood     | (0.55, 0.40, 0.28)   | 0.7       | 0.0      | Sink cabinet body      |
| sink_metal       | (0.75, 0.75, 0.78)   | 0.3       | 0.7      | Sink basin + counter   |
| table_wood       | (0.62, 0.45, 0.30)   | 0.65      | 0.0      | Table top + legs       |
| ceramic_white    | (0.95, 0.95, 0.93)   | 0.3       | 0.0      | Plate                  |
| apple_red        | (0.75, 0.12, 0.10)   | 0.5       | 0.0      | Apple                  |
| banana_yellow    | (0.92, 0.82, 0.20)   | 0.6       | 0.0      | Banana                 |
| mug_ceramic      | (0.80, 0.20, 0.15)   | 0.35      | 0.0      | Mug                    |

Materials with physics friction are applied to floor, appliances, cabinet, and table surfaces.

For higher visual fidelity, replace diffuse colors with texture maps (albedo, normal, roughness) from Omniverse material libraries.

## Physics Setup

| Object             | Physics Type                    | Notes                              |
| ------------------ | ------------------------------- | ---------------------------------- |
| Floor, Walls       | CollisionAPI only (static)      | Infinite mass                      |
| Table, Sink Cab.   | CollisionAPI only (static)      | Stable surfaces                    |
| Fridge Cabinet     | RigidBody + kinematicEnabled    | Anchor for door joint              |
| Fridge Door        | RigidBody (dynamic, 8 kg)       | RevoluteJoint to cabinet           |
| Plate              | RigidBody (dynamic, 0.25 kg)    | Cylinder collider                  |
| Apple              | RigidBody (dynamic, 0.20 kg)    | Sphere collider                    |
| Banana             | RigidBody (dynamic, 0.05 kg)    | Cylinder collider                  |
| Mug                | RigidBody (dynamic, 0.30 kg)    | Cylinder collider                  |

Physics scene uses TGS solver at 120 Hz with stabilization enabled.

## Collision vs Visual Geometry

- All furniture bodies use **Cube** primitives — clean box colliders by default
- Handles use dedicated **Cube** colliders (not decorative mesh) for reliable grasp contact
- Tabletop objects use simple primitives (Cylinder, Sphere) — no concave decomposition needed
- Basin walls are thin box colliders forming a rectangular basin shape

## Lighting

- **Dome light:** 800 lux intensity, white
- **4 ceiling rect lights:** 3000 lux each, 0.6×0.6 m panels at Z=2.75, pointing downward
- Positions: (-1.5, 1.0), (1.5, 1.0), (-1.5, -1.5), (1.5, -1.5)

## Camera Presets

| Camera     | Position             | Target            |
| ---------- | -------------------- | ----------------- |
| top        | (0, 0, 7.0)         | (0, 3.45, 0.8)   |
| front      | (0, -2.0, 1.5)      | (0, 3.45, 0.8)   |
| isometric  | (-3.5, -2.0, 3.5)   | (0, 3.45, 0.8)   |

## Usage

### Standalone (generate USD)

```bash
# From Isaac Sim python environment
python.bat scenes/kitchen_fixed/kitchen_fixed_builder.py
# Output: scenes/kitchen_fixed/kitchen_fixed.usd
```

### With test_robot_bench.py

```powershell
# Via task config (recommended)
.\scripts\run_task_config.ps1 -Config config\tasks\fixed_scene_survey.json

# Via CLI flag
python.bat scripts/test_robot_bench.py --grasp --kitchen-scene fixed --task-config config/tasks/fixed_scene_survey.json
```

### Task Configs

New task configs with `"kitchen_scene": "fixed"` are in `config/tasks/`:

| Config                          | Description                     |
| ------------------------------- | ------------------------------- |
| fixed_scene_survey.json         | 15s video survey, no manipulation |
| fixed_fridge_open_close.json    | Open/close fridge door          |
| fixed_mug_to_sink.json          | Mug: table → sink → table      |
| fixed_banana_wash.json          | Banana: plate → sink → plate   |
| fixed_full_kitchen.json         | All tasks chained               |

## Path Mapping (Legacy → Fixed)

| Legacy Path                     | Fixed Path                                        |
| ------------------------------- | ------------------------------------------------- |
| /World/Fridge/Door/Handle       | /World/Kitchen/Furniture/Fridge/Door/Handle        |
| /World/Fridge/DoorHinge         | /World/Kitchen/Furniture/Fridge/DoorHinge          |
| /World/Mug                      | /World/Kitchen/Objects/Mug                         |
| /World/Table                    | /World/Kitchen/Furniture/Table                     |
| /World/SinkCabinet/Basin        | /World/Kitchen/Furniture/SinkCabinet/Basin          |
| /World/Banana1                  | /World/Kitchen/Objects/Banana                      |
| /World/Plate                    | /World/Kitchen/Objects/Plate                       |

## Assumptions and Notes

1. **Sink cabinet** dimensions (0.80×0.80×0.90 m) were chosen as reasonable defaults since no exact spec was provided. Basin depth is 0.18 m with 0.06 m margin from edges.
2. **No texture maps** are used — all materials are solid PBR colors. For production quality, replace with Omniverse material library textures.
3. **Handle bar cross-section** is square (0.02×0.02 m) approximating a round bar. This provides clean collision geometry for the parallel gripper.
4. **Banana** is approximated as a cylinder with slight tilt (8° pitch, 15° yaw) for visual realism.
5. The scene is fully deterministic — no randomization of any kind.
