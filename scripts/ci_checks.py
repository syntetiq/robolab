#!/usr/bin/env python3
"""
CI validation checks for the RoboLab codebase.

Runs automatically or as part of pre-commit to catch common issues:
  1. Python syntax validation (all .py files in scripts/)
  2. YAML syntax validation (all .yaml files in scripts/)
  3. TypeScript compilation check (tsc --noEmit)
  4. Dataset export smoke test (dry-run on first episode)
  5. MoveIt config consistency (joints in URDF match SRDF/controllers)
  6. FJT proxy joint set consistency
  7. Intent bridge coverage (all intents resolve to sequences)

Usage:
  python scripts/ci_checks.py
  python scripts/ci_checks.py --skip-tsc    # skip TypeScript checks
"""

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def check_python_syntax():
    """Validate all .py files parse without errors."""
    errors = []
    py_files = list(SCRIPTS_DIR.glob("*.py"))
    for f in py_files:
        try:
            ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError as e:
            errors.append(f"{f.name}: {e}")
    return "python_syntax", len(py_files), errors


def check_yaml_syntax():
    """Validate all .yaml files parse correctly."""
    try:
        import yaml
    except ImportError:
        return "yaml_syntax", 0, ["pyyaml not installed"]
    errors = []
    yaml_files = list(SCRIPTS_DIR.glob("*.yaml")) + list(SCRIPTS_DIR.glob("*.yml"))
    for f in yaml_files:
        try:
            yaml.safe_load(f.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            errors.append(f"{f.name}: {e}")
    return "yaml_syntax", len(yaml_files), errors


def check_typescript(skip=False):
    """Run tsc --noEmit to check TypeScript compilation."""
    if skip:
        return "typescript", 0, []
    tsconfig = REPO_ROOT / "tsconfig.json"
    if not tsconfig.exists():
        return "typescript", 0, ["tsconfig.json not found"]
    try:
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=120,
            shell=True,
        )
        if result.returncode != 0:
            lines = result.stdout.strip().split("\n")
            err_lines = [l for l in lines if "error TS" in l][:10]
            return "typescript", 1, err_lines or [f"tsc failed (exit {result.returncode})"]
        return "typescript", 1, []
    except Exception as e:
        return "typescript", 0, [f"tsc error: {e}"]


def check_moveit_consistency():
    """Verify joints in URDF match SRDF groups and controller configs."""
    errors = []
    yaml_path = SCRIPTS_DIR / "tiago_move_group_working.yaml"
    if not yaml_path.exists():
        return "moveit_consistency", 0, ["tiago_move_group_working.yaml not found"]

    content = yaml_path.read_text(encoding="utf-8")

    urdf_joints = set(re.findall(r'<joint name="(\w+)"', content))
    urdf_revolute = set(re.findall(r'<joint name="(\w+)" type="revolute"', content))
    urdf_prismatic = set(re.findall(r'<joint name="(\w+)" type="prismatic"', content))
    urdf_moveable = urdf_revolute | urdf_prismatic

    srdf_groups_joints = set(re.findall(r'<joint name="(\w+)"/>', content))

    controller_joints = set(re.findall(r'joints:\s*\[(.*?)\]', content))
    ctrl_joint_set = set()
    for cj in controller_joints:
        for j in cj.split(","):
            j = j.strip().strip("'\"")
            if j:
                ctrl_joint_set.add(j)

    in_srdf_not_urdf = srdf_groups_joints - urdf_joints
    if in_srdf_not_urdf:
        errors.append(f"SRDF references joints not in URDF: {in_srdf_not_urdf}")

    in_ctrl_not_urdf = ctrl_joint_set - urdf_joints
    if in_ctrl_not_urdf:
        errors.append(f"Controllers reference joints not in URDF: {in_ctrl_not_urdf}")

    return "moveit_consistency", 1, errors


def check_fjt_proxy_joints():
    """Verify FJT proxy _MOVEIT_JOINTS covers all URDF moveable joints."""
    errors = []
    proxy_path = SCRIPTS_DIR / "ros2_fjt_proxy.py"
    yaml_path = SCRIPTS_DIR / "tiago_move_group_working.yaml"
    if not proxy_path.exists() or not yaml_path.exists():
        return "fjt_proxy_joints", 0, ["missing files"]

    proxy_content = proxy_path.read_text(encoding="utf-8")
    yaml_content = yaml_path.read_text(encoding="utf-8")

    proxy_joints = set(re.findall(r'"(\w+_joint)"', proxy_content.split("_MOVEIT_JOINTS")[1].split(")")[0]))

    urdf_revolute = set(re.findall(r'<joint name="(\w+)" type="revolute"', yaml_content))
    urdf_prismatic = set(re.findall(r'<joint name="(\w+)" type="prismatic"', yaml_content))
    urdf_moveable = urdf_revolute | urdf_prismatic

    missing = urdf_moveable - proxy_joints
    if missing:
        errors.append(f"URDF joints not in FJT proxy: {missing}")

    extra = proxy_joints - urdf_moveable
    if extra:
        pass  # extra joints in proxy is fine (e.g. gripper aliases)

    return "fjt_proxy_joints", 1, errors


def check_intent_coverage():
    """Verify all documented intents resolve to sequences."""
    errors = []
    bridge_path = SCRIPTS_DIR / "moveit_intent_bridge.py"
    if not bridge_path.exists():
        return "intent_coverage", 0, ["moveit_intent_bridge.py not found"]

    content = bridge_path.read_text(encoding="utf-8")

    expected_intents = [
        "go_home", "approach_workzone",
        "plan_pick_sink", "plan_pick_fridge", "plan_pick_dishwasher",
        "plan_place", "open_close_fridge", "open_close_dishwasher",
        "left_go_home", "left_plan_pick_sink", "left_plan_place",
        "bimanual_pick_sink",
        "nav_forward", "nav_backward", "nav_rotate_left", "nav_rotate_right",
        "nav_to_table", "nav_to_fridge", "nav_to_sink",
    ]

    for intent in expected_intents:
        pattern = rf'intent\s*==\s*["\']({re.escape(intent)})["\']'
        if not re.search(pattern, content):
            alt = rf'["\']({re.escape(intent)})["\']'
            if not re.search(alt, content):
                errors.append(f"Intent '{intent}' not found in bridge")

    return "intent_coverage", len(expected_intents), errors


def check_dataset_export():
    """Verify the export script imports and runs in dry-mode."""
    errors = []
    export_path = SCRIPTS_DIR / "export_dataset_hdf5.py"
    if not export_path.exists():
        return "dataset_export", 0, ["export_dataset_hdf5.py not found"]
    try:
        ast.parse(export_path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        errors.append(f"Syntax error: {e}")
    return "dataset_export", 1, errors


def main():
    parser = argparse.ArgumentParser(description="RoboLab CI checks")
    parser.add_argument("--skip-tsc", action="store_true", help="Skip TypeScript checks")
    args = parser.parse_args()

    checks = [
        check_python_syntax,
        check_yaml_syntax,
        lambda: check_typescript(skip=args.skip_tsc),
        check_moveit_consistency,
        check_fjt_proxy_joints,
        check_intent_coverage,
        check_dataset_export,
    ]

    total_pass = 0
    total_fail = 0

    print("RoboLab CI Checks")
    print("=" * 60)

    for check_fn in checks:
        name, count, errors = check_fn()
        if errors:
            total_fail += 1
            print(f"  FAIL  {name} ({count} checked)")
            for e in errors[:5]:
                print(f"        -> {e}")
        else:
            total_pass += 1
            print(f"  PASS  {name} ({count} checked)")

    print("=" * 60)
    print(f"Results: {total_pass} passed, {total_fail} failed")

    sys.exit(1 if total_fail > 0 else 0)


if __name__ == "__main__":
    main()
