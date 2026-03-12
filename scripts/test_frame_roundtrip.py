#!/usr/bin/env python3
"""Round-trip frame conversion test.

Verifies that world -> base_footprint -> world conversion is consistent
across different robot yaw angles. Both the bridge's _world_to_base_footprint
and the collector's local->world conversion must agree.

Usage:
    python scripts/test_frame_roundtrip.py
"""
from __future__ import annotations

import math
import sys

import numpy as np


def world_to_base_footprint(world_pos, robot_pos, robot_orient):
    """Bridge-side conversion (from moveit_intent_bridge.py)."""
    dx = world_pos[0] - robot_pos[0]
    dy = world_pos[1] - robot_pos[1]
    dz = world_pos[2] - robot_pos[2]
    w, x, y, z = robot_orient
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    cos_y, sin_y = math.cos(-yaw), math.sin(-yaw)
    local_x = cos_y * dx - sin_y * dy
    local_y = sin_y * dx + cos_y * dy
    local_z = dz
    return (local_x, local_y, local_z)


def base_footprint_to_world(local_pos, robot_pos, robot_orient):
    """Collector-side conversion (fixed version from data_collector_tiago.py)."""
    w, x, y, z = robot_orient
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    cos_y = math.cos(yaw)
    sin_y = math.sin(yaw)
    lx, ly, lz = local_pos
    world_x = cos_y * lx - sin_y * ly + robot_pos[0]
    world_y = sin_y * lx + cos_y * ly + robot_pos[1]
    world_z = lz + robot_pos[2]
    return (world_x, world_y, world_z)


def base_footprint_to_world_OLD(local_pos, robot_pos, robot_orient):
    """Old collector-side conversion (translation only, no yaw)."""
    return (
        local_pos[0] + robot_pos[0],
        local_pos[1] + robot_pos[1],
        local_pos[2] + robot_pos[2],
    )


def yaw_to_quaternion(yaw_deg: float):
    """Convert yaw angle (degrees) to [w, x, y, z] quaternion."""
    yaw_rad = math.radians(yaw_deg)
    return [math.cos(yaw_rad / 2), 0.0, 0.0, math.sin(yaw_rad / 2)]


def run_tests():
    test_points = [
        (1.5, 0.0, 0.85),
        (1.2, -0.3, 0.75),
        (0.9, 0.5, 1.0),
        (2.0, -1.0, 0.5),
        (0.5, 0.2, 0.9),
        (1.8, 0.8, 0.6),
        (0.3, -0.5, 1.2),
        (1.0, 0.0, 0.08),
        (1.5, 1.5, 0.3),
        (0.0, 0.0, 0.0),
    ]

    robot_pos = (0.8, 0.0, 0.08)
    yaw_angles = [0, 15, 30, 45, 60, 90, 135, 180, -45, -90]

    total_tests = 0
    passed = 0
    failed = 0
    max_error_new = 0.0
    max_error_old = 0.0

    print(f"{'='*70}")
    print("Frame Round-Trip Test: world -> base_footprint -> world")
    print(f"{'='*70}")
    print(f"Robot position: {robot_pos}")
    print(f"Test points: {len(test_points)}")
    print(f"Yaw angles: {yaw_angles}")
    print()

    for yaw_deg in yaw_angles:
        orient = yaw_to_quaternion(yaw_deg)
        yaw_errors_new = []
        yaw_errors_old = []

        for wp in test_points:
            total_tests += 1

            local = world_to_base_footprint(wp, robot_pos, orient)
            reconstructed_new = base_footprint_to_world(local, robot_pos, orient)
            reconstructed_old = base_footprint_to_world_OLD(local, robot_pos, orient)

            err_new = math.sqrt(sum((a - b) ** 2 for a, b in zip(wp, reconstructed_new)))
            err_old = math.sqrt(sum((a - b) ** 2 for a, b in zip(wp, reconstructed_old)))

            yaw_errors_new.append(err_new)
            yaw_errors_old.append(err_old)
            max_error_new = max(max_error_new, err_new)
            max_error_old = max(max_error_old, err_old)

            if err_new < 0.001:
                passed += 1
            else:
                failed += 1
                print(f"  FAIL yaw={yaw_deg:>4}deg point={wp} -> local={tuple(round(v,4) for v in local)} "
                      f"-> new={tuple(round(v,4) for v in reconstructed_new)} err={err_new:.6f}m")

        avg_new = sum(yaw_errors_new) / len(yaw_errors_new)
        avg_old = sum(yaw_errors_old) / len(yaw_errors_old)
        max_new = max(yaw_errors_new)
        max_old = max(yaw_errors_old)
        status = "PASS" if max_new < 0.001 else "FAIL"
        print(f"  yaw={yaw_deg:>4}deg: [{status}] new_max={max_new:.6f}m new_avg={avg_new:.6f}m | "
              f"old_max={max_old:.6f}m old_avg={avg_old:.6f}m")

    print(f"\n{'='*70}")
    print(f"Results: {passed}/{total_tests} passed, {failed} failed")
    print(f"Max round-trip error (FIXED):   {max_error_new:.6f}m {'PASS' if max_error_new < 0.001 else 'FAIL'}")
    print(f"Max round-trip error (OLD/BUG): {max_error_old:.6f}m")
    if max_error_old > 0.01:
        print(f"  -> Old conversion had up to {max_error_old:.3f}m error at non-zero yaw!")
    print(f"{'='*70}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())
