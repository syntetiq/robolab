from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SceneVideoSmoke:
    rotate_omega: float
    rotate_timeout_sec: float
    forward_vx: float
    forward_max_dist_m: float
    forward_timeout_sec: float


@dataclass
class SceneVideoProfile:
    profile_id: str
    duration_sec: int
    capture_width: int
    capture_height: int
    external_camera_pos: list[float]
    external_camera_target: list[float]
    smoke: SceneVideoSmoke


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _as_float3(name: str, values: list[Any]) -> list[float]:
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError(f"{name} must be an array of 3 numbers")
    return [float(values[0]), float(values[1]), float(values[2])]


def resolve_scene_video_profile(scene_name: str, config_path: Path | None = None) -> SceneVideoProfile:
    cfg_path = config_path or (Path(__file__).resolve().parents[1] / "config" / "scene_video_profiles.json")
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})
    matched_profile: dict[str, Any] = {}

    for profile in raw.get("profiles", []):
        for pattern in profile.get("patterns", []):
            if fnmatch.fnmatch(scene_name, pattern):
                matched_profile = profile
                break
        if matched_profile:
            break

    merged = _deep_merge(defaults, matched_profile)
    smoke = merged.get("smoke", {})
    return SceneVideoProfile(
        profile_id=str(merged.get("id", "default")),
        duration_sec=int(merged.get("durationSec", 180)),
        capture_width=int(merged.get("captureWidth", 1280)),
        capture_height=int(merged.get("captureHeight", 720)),
        external_camera_pos=_as_float3("externalCameraPos", merged.get("externalCameraPos", [])),
        external_camera_target=_as_float3("externalCameraTarget", merged.get("externalCameraTarget", [])),
        smoke=SceneVideoSmoke(
            rotate_omega=float(smoke.get("rotateOmega", 0.55)),
            rotate_timeout_sec=float(smoke.get("rotateTimeoutSec", 22.0)),
            forward_vx=float(smoke.get("forwardVx", 0.18)),
            forward_max_dist_m=float(smoke.get("forwardMaxDistM", 1.0)),
            forward_timeout_sec=float(smoke.get("forwardTimeoutSec", 22.0)),
        ),
    )
