# Episode Analysis: fixed_fridge_experiment3_20260317_110723

## Task Summary

| Task | Success | Time (sim) | Note |
|------|---------|------------|------|
| T1 drive_to_fridge | ✅ | 4.7 s | Approach to the fridge completed |
| T2 open_fridge | ❌ | 52.4 s | Door did not open (angle remained ~0°) |
| T3 close_fridge | ✅ | 23.2 s | Door closed (angle ≤ 20°) |
| T4 return_to_start | ❌ | 60 s (timeout) | Robot got stuck, did not reach (0,0) |

---

## 1. T2 open_fridge — why the door did not open

### What happened according to the logs

- **Approach:** base reached the target (-1.31, 2.21), handle at (-1.65, 2.96), angle=0°.
- **approach_and_grasp:** the base did not creep forward (creep=0), only the arm moved. The tool approached the handle (from ~(-1.77,2.93) to ~(-1.67,2.89)).
- **retreat_2cm:** reversed 2 cm: base_y from 2.130 to ~2.083 ✅.
- **pull_or_push:** the base started moving. The door angle remained at **~0.04°** (effectively 0) throughout. After ~51 s — TIMEOUT, success=False.

### Base trajectory during the pull

- t=12 s: base=(-1.17, 2.08)
- t=29 s: base=(-3.45, 1.85)
- Afterwards the base got stuck near (-3.55, 1.85).

In other words, the robot moved to the left (along X by ~2.4 m) and slightly downward along Y (by ~0.2 m), but the door angle did not change.

### Root cause: incorrect pull direction

In the code for **opening**, the "tangent" was computed as the direction of the **radius** from the hinge to the handle:

- Hinge: (-0.95, 3.05)
- Handle: (-1.65, 2.96)
- Radius: `(rx, ry) = (hx - hgx, hy - hgy) = (-0.7, -0.09)`
- In the code: `tang_wx = rx/r_len`, `tang_wy = ry/r_len` → direction **(-0.99, -0.13)** in world coordinates.

This direction is **from the hinge to the handle** (right-downward in world coordinates), not along the door arc. The door opens when the handle moves **along the arc** around the hinge — that is, along the **true tangent** to the circle (perpendicular to the radius).

To open the door into the room (handle moves downward along Y), the tangent to the circle is needed, for example:

- Tangent (handle movement direction): `(-ry, rx)` in world coordinates → **(0.09, -0.7)** → predominantly **-Y** (southward).

Summary: the robot was moving in the direction **(-0.99, -0.13)** (nearly along -X), whereas it should have been moving in the **tangent-to-arc** direction, predominantly **-Y** (southward), to pull the handle and open the door.

Additionally: with this incorrect pull direction there may not have been a reliable gripper–handle contact (or the handle was slipping out), which is why the door did not rotate.

---

## 2. T3 close_fridge — why it was counted as a success

- After T2 the base was near (-3.55, 1.85), door angle ~0°.
- T3 begins with **waypoints** for close: the base drives back to the fridge (to the point in front of the handle).
- Along the way: the logs show the angle briefly reaching ~9.3° and ~11.76° — this is most likely an artefact or slight door movement during transit/contact.
- By the time **approach_and_grasp** for close starts: base near (-0.69, 3.13), angle already ~11.5°.
- In **pull_or_push** for close: angle=11.97° ≤ 20° → immediate **close SUCCESS**.

In other words, the door was already nearly closed (~0° after T2); the criterion "angle ≤ 20°" for close was already satisfied, so T3 was correctly counted as a success without actually "closing" an open door.

---

## 3. T4 return_to_start — why the robot got stuck

- T4 start: base=(-0.70, 2.73), target (0, 0), dist≈2.82 m.
- Almost immediately: base=(-0.696, 2.726), then the position **does not change**, the logs show "STUCK" (phase 0,1,2,3), the stuck counter increases.
- Result: over 60 s the robot did not move towards (0,0), timeout, success=False.

Probable causes:

- Navigation considers the robot stuck (no progress towards the target distance), and activates anti-stuck manoeuvres (lateral/reverse), but they do not help.
- Possible collision with furniture/door, incorrect obstacle estimation, or overly aggressive stuck detection.

A separate investigation of navigation (zones, route, stuck parameters) is required.

---

## 4. What was already done correctly

- Approach (T1) and locking **approach_base_y** (do not drive forward past the approach point).
- Creep towards the fridge disabled in approach_and_grasp during opening.
- The **retreat_2cm** phase after grasping worked correctly (reversed 2 cm).
- Restriction "do not drive forward past approach" in pull (vwy is not allowed to go positive when by ≥ approach_base_y).

---

## 5. Recommended fix for T2 (opening)

Use the **tangent-to-arc** direction for **opening** (the handle moves along a circle around the hinge), rather than the radius direction:

- Radius: `(rx, ry) = (hx - hgx, hy - hgy)`.
- Tangent (e.g. for opening "into the room"): `tang_wx = -ry / r_len`, `tang_wy = rx / r_len` (or the opposite sign, depending on which direction the door opens).

This way the base will pull the handle along the arc, the door will be able to rotate around the hinge, and T2 has a chance of succeeding.

After fixing the tangent, it is worth re-running a single episode and checking the logs/video: the door angle during pull_or_push should increase, and the base should move predominantly along -Y (southward).
