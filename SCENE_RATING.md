# Scene Rating for Tiago Manipulation Tasks

Evaluated: March 2026

## Active Scenes (Tier S + A) — used in production collection

| # | Scene file | Tier | Score | Justification |
|---|-----------|------|-------|---------------|
| 1 | `Kitchen_TiagoCompatible.usda` | **S** | 9.5/10 | Full kitchen: countertops, sink, fridge, dishwasher, shelves at reachable heights. Maximum diversity of pick-place tasks. Tested and validated with all intents. |
| 2 | `L-Shaped_Contemporary_Modular_Kitchen_TiagoCompatible.usda` | **S** | 9.0/10 | L-shaped layout forces navigation between zones. Multiple counter surfaces at different heights. Good for nav+manipulation combos (`nav_pick_place_table_to_sink`). |
| 3 | `Modern_Kitchen_TiagoCompatible.usda` | **A** | 8.5/10 | Clean modern surfaces, island counter. Fewer built-in appliances than Kitchen but excellent for open-space pick-place and mobile base tasks. |
| 4 | `Small_House_Interactive.usd` | **A** | 8.0/10 | Multi-room layout (kitchen + living room + hallway). Best scene for navigation intents and long-horizon tasks. Lower density of manipulation targets per room but compensated by spatial diversity. |

## Excluded Scenes (Tier B + C) — documented, not used

| # | Scene file | Tier | Score | Reason for exclusion |
|---|-----------|------|-------|---------------------|
| 5 | `Fridge_TiagoCompatible.usda` | B | 6.5/10 | Single-appliance scene (fridge only). Good for `open_close_fridge` / `plan_pick_fridge` but too narrow for diverse dataset. Redundant — Kitchen and L-Kitchen already contain fridges. |
| 6 | `Dishwasher_TiagoCompatible.usda` | B | 6.0/10 | Single-appliance scene (dishwasher only). Same issue as Fridge — Kitchen scene covers dishwasher intents with richer context. |
| 7 | `Fridge_Zil_TiagoCompatible.usda` | B | 5.5/10 | Soviet-era fridge model. Non-standard proportions, unusual handle geometry. Niche visual domain that would skew dataset distribution. |
| 8 | `Dish_set_bowl_cup_mug_spoon_teapot_vase.._TiagoCompatible.usda` | C | 4.0/10 | Props-only scene, no surrounding environment. Objects float on a flat plane. No surfaces/containers for meaningful pick-place context. Spawn geometry conflicts with Tiago reach envelope. |
| 9 | `60s_Office_Props_TiagoCompatible.usda` | C | 3.5/10 | Retro office furniture, no kitchen/manipulation surfaces. Objects are primarily decorative (lamps, typewriter). Minimal overlap with target task distribution. |
| 10 | `Office_Interactive.usd` | C | 3.0/10 | Generic office — desks, chairs, monitors. No kitchen appliances or food-type objects. Not relevant for manipulation tasks in the current task set (pick, fridge, dishwasher, sink). |

## Selection Criteria

1. **Task coverage** — scene must support ≥3 of the 5 core intents (`plan_pick_sink`, `plan_pick_fridge`, `plan_pick_dishwasher`, `open_close_fridge`, `open_close_dishwasher`)
2. **Surface diversity** — multiple reachable surfaces at different heights for varied grasp demonstrations
3. **Navigation space** — sufficient clearance for mobile base movement between manipulation zones
4. **Visual domain** — realistic textures/lighting that generalize to real-world kitchens
5. **Tested stability** — scene runs reliably with Tiago articulation without physics explosions or spawn collisions

## Re-enabling Excluded Scenes

To bring a Tier B/C scene back into rotation:

```sql
-- In prisma/dev.db
UPDATE Scene SET enabled = 1 WHERE stageUsdPath LIKE '%Fridge_TiagoCompatible%';
```

Then add the scene entry back to `$scenes` array in `scripts/run_batch_with_objects.ps1` and update the filter in `scripts/run_web_collection.ps1`.
