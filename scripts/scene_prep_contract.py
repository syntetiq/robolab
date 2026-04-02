#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[1] / "config" / "scene_prep_manifest.json"


@dataclass
class ScenePrepContract:
    floor_half_height: float
    floor_size_xy: float
    floor_top_z: float
    contact_offset: float
    rest_offset: float
    spawn_x: float
    spawn_y: float
    spawn_z: float
    spawn_pad_size_x: float
    spawn_pad_size_y: float
    spawn_pad_height: float
    nav_probe_targets: list[list[float]]
    manip_probe_joint_targets: list[float]
    profile_id: str


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _find_profile(name: str, profiles: list[dict[str, Any]]) -> dict[str, Any] | None:
    from fnmatch import fnmatch

    for profile in profiles:
        for pattern in profile.get("patterns", []):
            if fnmatch(name, str(pattern)):
                return profile
    return None


def resolve_scene_prep_contract(scene_name: str, manifest_path: Path | None = None) -> ScenePrepContract:
    manifest_file = manifest_path or DEFAULT_MANIFEST_PATH
    data = json.loads(manifest_file.read_text(encoding="utf-8"))

    defaults = data.get("defaults", {})
    profile = _find_profile(scene_name, data.get("profiles", []))
    merged = _deep_merge(defaults, profile or {})

    floor = merged.get("floor", {})
    spawn = merged.get("spawnPose", {})
    spawn_pad = merged.get("spawnPad", {})
    probes = merged.get("fitProbes", {})

    return ScenePrepContract(
        floor_half_height=float(floor.get("halfHeightM", 0.1)),
        floor_size_xy=float(floor.get("sizeXYM", 100.0)),
        floor_top_z=float(floor.get("topZ", 0.0)),
        contact_offset=float(floor.get("contactOffset", 0.02)),
        rest_offset=float(floor.get("restOffset", 0.0)),
        spawn_x=float(spawn.get("x", 1.0)),
        spawn_y=float(spawn.get("y", -1.0)),
        spawn_z=float(spawn.get("z", 0.03)),
        spawn_pad_size_x=float(spawn_pad.get("sizeX", 2.0)),
        spawn_pad_size_y=float(spawn_pad.get("sizeY", 2.0)),
        spawn_pad_height=float(spawn_pad.get("heightM", 0.2)),
        nav_probe_targets=[[float(x), float(y)] for x, y in probes.get("navProbeTargets", [[1.4, -1.0], [1.0, -0.6]])],
        manip_probe_joint_targets=[float(v) for v in probes.get("manipProbeJointTargets", [1.5, 0.0, 0.0, 0.0, -1.57, 0.0, 0.0])],
        profile_id=str((profile or {}).get("id", "default")),
    )
