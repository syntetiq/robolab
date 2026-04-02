#!/usr/bin/env python3
"""
Checks scene resolution compatibility across web rollout config and runners.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []

    rollout = REPO_ROOT / "config/scene_rollout.json"
    if not rollout.exists():
        errors.append("scene_rollout.json missing")
    else:
        try:
            data = json.loads(rollout.read_text(encoding="utf-8"))
            if data.get("defaultSceneFilter") != "fixed_only":
                errors.append("scene_rollout.json: defaultSceneFilter must remain 'fixed_only'")
            if data.get("enableExperimentalScenes") not in (False, True):
                errors.append("scene_rollout.json: enableExperimentalScenes must be boolean")
        except Exception as exc:
            errors.append(f"scene_rollout.json invalid json ({exc})")

    local_runner = REPO_ROOT / "src/server/runner/localRunner.ts"
    ssh_runner = REPO_ROOT / "src/server/runner/sshRunner.ts"
    for file_path in (local_runner, ssh_runner):
        if not file_path.exists():
            errors.append(f"missing runner file: {file_path}")

    if local_runner.exists():
        txt = local_runner.read_text(encoding="utf-8")
        if "scene?.stageUsdPath" not in txt:
            errors.append("LocalRunner: scene stageUsdPath must be considered")
        if "launchProfile?.environmentUsd" not in txt:
            errors.append("LocalRunner: launchProfile environmentUsd must be considered")
        if "Small_House_Interactive" not in txt:
            errors.append("LocalRunner: fixed fallback home scene missing")

    if ssh_runner.exists():
        txt = ssh_runner.read_text(encoding="utf-8")
        if "scene?.stageUsdPath" not in txt or "launchProfile?.environmentUsd" not in txt:
            errors.append("SshRunner: scene/profile resolution contract missing")
        # Keep default office fallback contract stable.
        if not re.search(r"Office_Interactive\.usd", txt):
            errors.append("SshRunner: default office fallback path missing")

    if errors:
        print("[FAIL] Scene resolution regression failed:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("[OK] Scene resolution regression passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
