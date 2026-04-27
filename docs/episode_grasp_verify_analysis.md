# Episode Analysis: Why the Gripper Did Not Lift the Mug

## What you observed

- Alignment was **good**, the mug was **between the fingers**.
- The gripper **did not clamp** (or the system considered it unclamped), the mug **was not lifted** and **not relocated**.

## What actually happened

### 1. The gripper closed and the mug was between the fingers

In the episode log at the moment of verify:

```
TOP retry 2/2: verify failed: xy_ok=False opening=0.041248979046940804
```

- **opening ≈ 0.041 m (4.1 cm)** — this is the typical width when the fingers are clamped on the mug (the mug diameter between the fingers). In other words, **the grasp physically occurred**: the gripper closed, the mug was between the fingers.

### 2. Why then "verify failed"?

In the code the transition from `verify_grasp` to `lift_mug` is permitted only if **both** conditions are met:

- **xy_ok** — horizontal distance between **tool** (gripper frame, finger base) and **mug centre** ≤ `top_xy_tol` (default **0.01 m = 1 cm**).
- **hold_ok** — the gripper is "holding" something: `opening >= 0.01` (in your case 0.041 — condition satisfied).

In your episode at the moment of verify the values were approximately:

- **tool** ≈ (1.997, -0.018, 0.867)
- **mug**   ≈ (2.018, -0.022, 0.814)

XY distance: sqrt((2.018−1.997)² + (−0.022+0.018)²) ≈ **0.021 m ≈ 2.1 cm**.

So **xy_ok = False**, because 2.1 cm > 1 cm. Therefore the system considered the verify unsuccessful, even though visually the alignment was good and the mug was between the fingers.

### 3. Why do tool and mug differ by 1–2 cm in XY with "good" alignment?

- **Tool** in the code refers to the position of the **gripper_right_grasping_frame** (gripper base / wrist), not the fingertips.
- During a vertical grasp the **mug centre** is in front of and slightly below this frame; additionally, after contact the mug shifts slightly.
- Therefore, even with ideal alignment the **tool–mug XY distance** is often **1.5–3 cm**. A 1 cm threshold is too strict and produces false "verify failed" results.

### 4. Consequence

- Verify is considered unsuccessful → a **retry** fires (the arm rises, re-aligns, descends, closes again).
- After two retries the system transitions to `lift_mug` anyway, but:
  - either the grasp is physically worse after two "releases",
  - or the timeout/lift conditions are not met.
- The result: **grasp_success = False**, the mug is essentially not lifted and not relocated, even though at one point it was between the fingers.

## Conclusion

- **Cause**: the **xy_ok** condition in `verify_grasp` uses a **very strict** tolerance of 1 cm between the **gripper frame** position and the **mug centre**, which does not match the top-grasp geometry (the frame is always slightly offset from the mug centre).
- **Consequence**: even when alignment is good and the mug is between the fingers (opening indicates a grasp), verify returns **xy_ok=False** → retry → unstable/incomplete lift and relocation cycle.

## Fix (applied in code)

- A separate tolerance **for verify only** has been added: `--top-verify-xy-tol` (default **0.03 m**).
- In the `verify_grasp` state the **xy_ok** check now uses **top_verify_xy_tol** rather than `top_xy_tol` (0.01 m).
- This preserves precise alignment before descent (top_xy_tol = 0.01) but prevents good grasps from being rejected due to 1–2 cm tool–mug offset after gripper closure.

After this fix, with good alignment and the mug between the fingers, verify should pass, and the "clamp → lift → relocate" cycle will execute correctly.
