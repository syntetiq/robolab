# scripts/data_collector_tiago.py
# Usage:
#   python.bat scripts/data_collector_tiago.py --env "C:\RoboLab_Data\scenes\Small_House_Interactive.usd" --output_dir "C:\RoboLab_Data\episodes\<id>"

import argparse
from collections import deque
import glob
import json
import math
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Tiago dataset collector for RoboLab.")
    parser.add_argument("--env", type=str, required=True, help="Path to environment USD.")
    parser.add_argument("--output_dir", type=str, required=True, help="Episode output directory.")
    parser.add_argument("--duration", type=int, default=120, help="Episode duration in seconds.")
    parser.add_argument("--headless", action="store_true", help="Run with no UI window.")
    parser.add_argument("--gui", action="store_true", help="Run with visible 3D viewport window (non-headless).")
    parser.add_argument("--vr", action="store_true", help="Enable OpenXR/VR profile when available.")
    parser.add_argument("--webrtc", action="store_true", help="Enable WebRTC streaming on port 8211.")
    parser.add_argument("--moveit", action="store_true", help="Enable MoveIt integration mode (metadata + hooks).")
    parser.add_argument(
        "--robot_pov_camera_prim",
        type=str,
        default="/World/Tiago",
        help="Prim path used as parent for robot POV camera.",
    )
    parser.add_argument(
        "--tiago-usd",
        type=str,
        default=os.environ.get("TIAGO_USD_PATH", "C:/RoboLab_Data/data/tiago_isaac/tiago_dual_functional_light.usd"),
        help="Path to Tiago USD file.",
    )
    parser.add_argument(
        "--require-real-tiago",
        action="store_true",
        help="Fail if Tiago articulation cannot be initialized (disables synthetic fallback).",
    )
    parser.add_argument(
        "--capture-width",
        type=int,
        default=640,
        help="Replicator camera width.",
    )
    parser.add_argument(
        "--capture-height",
        type=int,
        default=480,
        help="Replicator camera height.",
    )
    parser.add_argument(
        "--ros2-site-packages",
        type=str,
        default=os.environ.get("ROS2_PY_SITE_PACKAGES", "C:/Users/max/Mambaforge/envs/ros2_humble/Lib/site-packages"),
        help="Optional path to ROS2 Python site-packages (for control_msgs/trajectory_msgs imports).",
    )
    parser.add_argument(
        "--ros2-dll-dir",
        type=str,
        default=os.environ.get("ROS2_DLL_DIR", "C:/Users/max/Mambaforge/envs/ros2_humble/Library/bin"),
        help="Optional ROS2 DLL directory for Windows typesupport loading.",
    )
    parser.add_argument(
        "--trajectory-time-scale",
        type=float,
        default=1.0,
        help="Execution speed multiplier for FollowJointTrajectory playback in Isaac (1.0 = real-time).",
    )
    parser.add_argument(
        "--replicator-subsample",
        type=int,
        default=10,
        help="Write replicator data (depth/pointcloud/semantics) every Nth simulation step. "
             "RGB is always captured for video. 1=every frame, 10=every 10th (default).",
    )
    parser.add_argument(
        "--spawn-objects",
        action="store_true",
        help="Spawn diverse graspable objects (mugs, bottles, fruits) on tables.",
    )
    parser.add_argument(
        "--objects-dir",
        type=str,
        default=os.environ.get("ROBOLAB_OBJECTS_DIR", r"C:\RoboLab_Data\data\object_sets"),
        help="Directory containing object USD files for spawning.",
    )
    parser.add_argument(
        "--single-object",
        action="store_true",
        help="Spawn exactly one easy grasp object on the table.",
    )
    parser.add_argument(
        "--single-object-preferred",
        type=str,
        default="mug,can,box,carton,cup",
        help="Comma-separated preferred tokens when choosing the single spawned object.",
    )
    parser.add_argument(
        "--mobile-base",
        action="store_true",
        help="Enable mobile base (unfixed root). Base responds to velocity commands via base_cmd.json.",
    )
    parser.add_argument(
        "--wrist-camera",
        action="store_true",
        help="Add wrist-mounted camera on arm_tool_link for close-up manipulation view.",
    )
    parser.add_argument(
        "--external-camera",
        action="store_true",
        help="Add fixed external third-person camera for scene overview.",
    )
    parser.add_argument(
        "--external-camera-pos",
        type=str,
        default="auto",
        help="External camera position as x,y,z or 'auto' to follow robot.",
    )
    parser.add_argument(
        "--external-camera-target",
        type=str,
        default="auto",
        help="External camera look-at target as x,y,z or 'auto' to follow robot.",
    )
    parser.add_argument(
        "--task-label",
        type=str,
        default="",
        help="Task label/intent name for this episode (e.g. pick_from_table).",
    )
    parser.add_argument(
        "--robot-start-x",
        type=float,
        default=0.8,
        help="Robot start X position in world frame (default: 0.8).",
    )
    return parser.parse_known_args()[0]


def resolve_usd_path(candidate):
    if not candidate:
        return candidate
    local = Path(candidate)
    if local.exists():
        return str(local.resolve())
    return candidate


def safe_enable_extension(name):
    from omni.isaac.core.utils.extensions import enable_extension

    try:
        enable_extension(name)
        print(f"[RoboLab] Enabled extension: {name}")
        return True
    except Exception as err:
        print(f"[RoboLab] WARN: Failed to enable extension {name}: {err}")
        return False


def prepare_ros2_runtime_env(ros2_dll_dir: str, use_isaac_bridge_dlls: bool = True) -> None:
    """Prepare ROS2 env vars for Isaac bridge startup on Windows.

    When use_isaac_bridge_dlls=False (MoveIt mode with direct rclpy), we skip
    adding the Isaac Sim bridge's internal DLL directory. This prevents the
    Isaac-bundled rclpy DLLs from shadowing the conda ros2_humble DLLs that
    the direct rclpy publisher relies on.
    """
    ros_distro = os.environ.get("ROS_DISTRO", "humble")
    rmw = os.environ.get("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp")
    os.environ["ROS_DISTRO"] = ros_distro
    os.environ["RMW_IMPLEMENTATION"] = rmw

    # Build candidate paths in priority order (first = highest priority).
    candidate_paths = []
    if ros2_dll_dir:
        candidate_paths.append(str(Path(ros2_dll_dir)))
    if use_isaac_bridge_dlls:
        # Isaac Sim internal ROS2 bridge native libs.  Only add when using
        # the isaacsim.ros2.bridge extension to avoid DLL version conflicts.
        candidate_paths.append("C:/Users/max/Documents/IsaacSim/exts/isaacsim.ros2.bridge/humble/lib")

    current_path = os.environ.get("PATH", "")
    for p in candidate_paths:
        if not p:
            continue
        p_norm = p.replace("\\", "/").lower()
        if p_norm not in current_path.replace("\\", "/").lower():
            current_path = f"{p};{current_path}" if current_path else p
    os.environ["PATH"] = current_path
    print(f"[RoboLab] ROS2 env prepared (ROS_DISTRO={ros_distro}, RMW={rmw}, isaac_dlls={use_isaac_bridge_dlls}).")


def build_output_manifest(root_dir):
    manifest = []
    root = Path(root_dir)
    for file_path in root.rglob("*"):
        if file_path.is_file():
            manifest.append({
                "path": str(file_path.relative_to(root)).replace("\\", "/"),
                "bytes": file_path.stat().st_size,
            })
    return manifest


def extract_frame_num(filename):
    nums = re.findall(r"\d+", os.path.basename(filename))
    return int(nums[-1]) if nums else 0


def _as_list(values):
    if values is None:
        return []
    try:
        return list(values)
    except Exception:
        return []


def setup_joint_state_publisher(robot_prim_path: str) -> bool:
    """Add OmniGraph ROS2 Publish Joint State node for MoveIt integration."""
    try:
        import omni.graph.core as og
        for node_type in (
            "isaacsim.ros2.bridge.ROS2PublishJointState",
            "omni.isaac.ros2_bridge.ROS2PublishJointState",
        ):
            try:
                og.Controller.edit(
                    {"graph_path": "/ActionGraph", "evaluator_name": "execution"},
                    {
                        og.Controller.Keys.CREATE_NODES: [
                            ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
                            ("PublishJointState", node_type),
                            ("ReadSimTime", "omni.isaac.core_nodes.IsaacReadSimulationTime"),
                        ],
                        og.Controller.Keys.CONNECT: [
                            ("OnPlaybackTick.outputs:tick", "PublishJointState.inputs:execIn"),
                            ("ReadSimTime.outputs:simulationTime", "PublishJointState.inputs:timeStamp"),
                        ],
                        og.Controller.Keys.SET_VALUES: [
                            ("PublishJointState.inputs:targetPrim", robot_prim_path),
                        ],
                    },
                )
                print(f"[RoboLab] Joint state publisher added for {robot_prim_path} (node: {node_type})")
                return True
            except Exception:
                continue
        print("[RoboLab] WARN: Could not create ROS2 joint state publisher (no compatible node type)")
        return False
    except Exception as err:
        print(f"[RoboLab] WARN: Joint state publisher setup failed: {err}")
        return False


def resolve_dof_names(articulation) -> list:
    """Resolve joint/DOF names from articulation. Tries dof_names, dof_paths, then fallback."""
    if not articulation:
        return []
    names = _as_list(getattr(articulation, "dof_names", []))
    if names:
        return names
    paths = _as_list(getattr(articulation, "dof_paths", []))
    if paths:
        return [str(p).split("/")[-1] if "/" in str(p) else str(p) for p in paths]
    try:
        pos = articulation.get_joint_positions()
        if pos is None:
            pos = articulation.get_dof_positions()
        if pos is not None and len(pos) > 0:
            return [f"joint_{i}" for i in range(len(pos))]
    except Exception:
        pass
    return []


def encode_video_from_rgb(replicator_dir, output_video):
    rgb_files = glob.glob(os.path.join(replicator_dir, "**", "rgb_*.png"), recursive=True)
    rgb_files = sorted(rgb_files, key=extract_frame_num)
    if not rgb_files:
        print("[RoboLab] WARN: No RGB frames found for video encoding.")
        return False

    try:
        import imageio.v2 as imageio

        print(f"[RoboLab] Encoding {len(rgb_files)} RGB frames to {output_video}...")
        with imageio.get_writer(output_video, fps=30) as writer:
            for filepath in rgb_files:
                writer.append_data(imageio.imread(filepath))
        return True
    except Exception as encode_err:
        print(f"[RoboLab] WARN: Video encoding failed ({encode_err}), using last frame fallback.")
        shutil.copy(rgb_files[-1], output_video)
        return True


args = parse_args()
os.makedirs(args.output_dir, exist_ok=True)
print("[RoboLab] Starting Tiago Data Collector...")
print(f"[RoboLab] Environment: {args.env}")
print(f"[RoboLab] Output dir: {args.output_dir}")
print(f"[RoboLab] VR teleop mode: {args.vr}")
print(f"[RoboLab] MoveIt mode: {args.moveit}")
print(f"[RoboLab] Robot POV prim: {args.robot_pov_camera_prim}")

from isaacsim import SimulationApp

simulation_app = SimulationApp({
    # WebRTC on Windows is more reliable with an active display/session.
    # Keep headless for non-streaming runs, but default to windowed when --webrtc.
    "headless": args.headless or (not args.vr and not args.webrtc and not args.gui),
    "livestream": 2 if args.webrtc else 0,
    "width": args.capture_width,
    "height": args.capture_height,
})

try:
    safe_enable_extension("omni.isaac.core_nodes")
    # Decide bridge strategy before preparing PATH so DLL order is correct.
    # In MoveIt mode we skip the isaac bridge extension and use conda rclpy instead,
    # so we must NOT add the isaac bridge DLL dir to PATH (it would override conda DLLs).
    _skip_bridge_on_windows = (
        os.name == "nt"
        and args.moveit
        and os.environ.get("ROBOLAB_ROS2_BRIDGE_ORDER", "").strip().lower()
        not in {"legacy_first", "legacy", "new_first", "new"}
    )
    prepare_ros2_runtime_env(args.ros2_dll_dir, use_isaac_bridge_dlls=not _skip_bridge_on_windows)
    # ROS2 bridge extension loading strategy for Windows + Isaac Sim 5.1:
    #
    # isaacsim.ros2.bridge is the correct extension in Isaac Sim 5.1, but on
    # some Windows setups its rclpy.context.init() call triggers a native
    # access violation that kills the process – NOT catchable by Python.
    #
    # omni.isaac.ros2_bridge is the legacy bridge (Isaac Sim < 5.x) and is
    # typically NOT present in Isaac Sim 5.1, so enabling it silently fails.
    #
    # When --moveit is active we skip the bridge extension entirely: all
    # ROS2 communication (joint_states, FollowJointTrajectory action servers)
    # is handled by the direct rclpy node created further below, which uses
    # the Mamba ros2_humble environment and NOT Isaac's bundled rclpy.
    #
    # The bridge extension (OmniGraph nodes) is only needed for the non-MoveIt
    # teleop path; we still attempt it there, but only with a safe single
    # candidate to avoid the access-violation fallback.
    bridge_pref = os.environ.get("ROBOLAB_ROS2_BRIDGE_ORDER", "").strip().lower()
    ros2_bridge_enabled = False

    if bridge_pref == "skip" or _skip_bridge_on_windows:
        # Safe path: skip bridge on Windows in MoveIt mode to avoid crashes.
        print("[RoboLab] Skipping ROS2 bridge extension on Windows/MoveIt (using direct rclpy publishers).")
    else:
        if bridge_pref in {"legacy_first", "legacy"}:
            bridge_candidates = ["omni.isaac.ros2_bridge", "isaacsim.ros2.bridge"]
        elif bridge_pref in {"new_first", "new"}:
            bridge_candidates = ["isaacsim.ros2.bridge", "omni.isaac.ros2_bridge"]
        elif os.name == "nt":
            # On Windows (non-MoveIt) try legacy first; avoid new bridge that crashes.
            bridge_candidates = ["omni.isaac.ros2_bridge"]
        else:
            bridge_candidates = ["isaacsim.ros2.bridge", "omni.isaac.ros2_bridge"]

        for bridge_ext in bridge_candidates:
            if safe_enable_extension(bridge_ext):
                ros2_bridge_enabled = True
                print(f"[RoboLab] ROS2 bridge active: {bridge_ext}")
                break

        if not ros2_bridge_enabled:
            print("[RoboLab] WARN: ROS2 bridge extension is unavailable; OmniGraph joint_states fallback disabled.")
    safe_enable_extension("omni.replicator.core")
    safe_enable_extension("omni.replicator.isaac")

    if args.vr:
        safe_enable_extension("omni.kit.xr.profile.vr")
    if args.webrtc:
        import carb

        # Explicitly enable livestream extension. In some Isaac builds it is only
        # registered by default and does not start unless enabled.
        safe_enable_extension("omni.kit.livestream.webrtc")
        carb.settings.get_settings().set("/exts/omni.kit.livestream.webrtc/port", 8211)
        print("[RoboLab] WebRTC stream configured on port 8211.")

    simulation_app.update()

    import omni.replicator.core as rep
    import omni.isaac.core.utils.stage as stage_utils
    from omni.isaac.core import World
    from omni.isaac.core.articulations import Articulation
    from omni.isaac.core.prims import XFormPrim
    from omni.isaac.core.utils.semantics import add_update_semantics, get_semantics
    from pxr import Gf, Usd, UsdGeom, UsdPhysics, UsdLux
    try:
        from pxr import PhysxSchema
    except ImportError:
        PhysxSchema = None

    # Prepare stage and world — use 120 Hz physics for stable articulated contacts.
    world = World(physics_dt=1.0 / 120.0, rendering_dt=1.0 / 60.0)
    env_usd = resolve_usd_path(args.env)
    _env_basename = os.path.basename(env_usd or "")
    _use_kitchen_fixed_builder = "kitchen_fixed" in _env_basename
    _use_office_fixed_builder = "office_fixed" in _env_basename
    if _use_kitchen_fixed_builder or _use_office_fixed_builder:
        try:
            _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            import sys as _sys_tmp
            if _repo_root not in _sys_tmp.path:
                _sys_tmp.path.insert(0, _repo_root)
            if _use_kitchen_fixed_builder:
                from scenes.kitchen_fixed.kitchen_fixed_builder import build_kitchen_scene
                build_kitchen_scene(stage_utils.get_current_stage())
                print(f"[RoboLab] Built kitchen_fixed scene procedurally (same as experiments)")
            else:
                from scenes.office_fixed.office_fixed_builder import build_office_scene
                build_office_scene(stage_utils.get_current_stage())
                print(f"[RoboLab] Built office_fixed scene procedurally")
        except Exception as _kfe:
            print(f"[RoboLab] WARN: procedural builder failed ({_kfe}), falling back to USD reference")
            stage_utils.add_reference_to_stage(usd_path=env_usd, prim_path="/World/Environment")
    else:
        stage_utils.add_reference_to_stage(usd_path=env_usd, prim_path="/World/Environment")
    # Ensure scene is lit for camera capture; many lightweight USDs have no lights.
    _cur_stage = stage_utils.get_current_stage()
    dome_path = "/World/RoboLabDomeLight"
    if not _cur_stage.GetPrimAtPath(dome_path).IsValid():
        dome = UsdLux.DomeLight.Define(_cur_stage, dome_path)
        dome.CreateIntensityAttr(1500.0)

    # Interior fill light near the robot so enclosed rooms (Kitchen, Modern_Kitchen)
    # are not pitch-black when the dome light cannot penetrate walls/ceiling.
    _fill_path = "/World/RoboLabFillLight"
    if not _cur_stage.GetPrimAtPath(_fill_path).IsValid():
        _fill = UsdLux.SphereLight.Define(_cur_stage, _fill_path)
        _fill.CreateIntensityAttr(30000.0)
        _fill.CreateRadiusAttr(0.5)
        _fill.CreateColorAttr(Gf.Vec3f(1.0, 0.98, 0.95))
        _fill_xf = UsdGeom.Xformable(_fill.GetPrim())
        _fill_xf.AddTranslateOp().Set(Gf.Vec3d(1.0, -1.0, 2.5))

    # --- PhysX scene tuning: solver iterations + ground plane -----------------
    _stage_tmp = stage_utils.get_current_stage()
    _phys_scene_prim = None
    for _p in _stage_tmp.Traverse():
        if _p.IsA(UsdPhysics.Scene):
            _phys_scene_prim = _p
            break
    if _phys_scene_prim is None:
        UsdPhysics.Scene.Define(_stage_tmp, "/World/PhysicsScene")
        _phys_scene_prim = _stage_tmp.GetPrimAtPath("/World/PhysicsScene")
    if _phys_scene_prim and _phys_scene_prim.IsValid():
        _phys_api = UsdPhysics.Scene(_phys_scene_prim)
        _phys_api.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
        _phys_api.CreateGravityMagnitudeAttr(9.81)
        if PhysxSchema:
            _px = PhysxSchema.PhysxSceneAPI.Apply(_phys_scene_prim)
            _px.CreateSolverTypeAttr("TGS")
            _px.CreateMinPositionIterationCountAttr(64)
            _px.CreateMinVelocityIterationCountAttr(4)
            _px.CreateEnableStabilizationAttr(True)
            try:
                _px.CreateSleepThresholdAttr(0.00005)
                _px.CreateStabilizationThresholdAttr(0.00001)
            except Exception:
                pass
            print("[RoboLab] PhysX scene: TGS solver, posIter=64, velIter=4, stabilization=ON, sleepTh=5e-5")
        else:
            print("[RoboLab] WARN: PhysxSchema not available — using default solver settings")

    # Ground plane collider — top surface at z=0, prevents objects falling.
    _floor_path = "/World/RoboLabFloor"
    if not _stage_tmp.GetPrimAtPath(_floor_path).IsValid():
        _floor = UsdGeom.Cube.Define(_stage_tmp, _floor_path)
        _floor.CreateSizeAttr(1.0)
        _floor.AddScaleOp().Set(Gf.Vec3f(200, 200, 0.2))
        _floor.AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.1))
        _floor.CreateVisibilityAttr("invisible")
        UsdPhysics.CollisionAPI.Apply(_stage_tmp.GetPrimAtPath(_floor_path))
        print("[RoboLab] Added ground-plane collider at z=0")

    # Anchor ALL environment objects as kinematic so they don't move under
    # gravity or robot contact. Traverses the full /World/Environment subtree
    # recursively. Every prim with RigidBodyAPI gets kinematic=True; prims
    # matching furniture keywords get the API applied if missing.
    _ANCHOR_KEYWORDS = (
        "fridge", "refrigerator", "dishwasher", "sink", "counter",
        "table", "shelf", "cabinet", "oven", "microwave", "wall",
        "floor", "ceiling", "door", "drawer", "handle", "panel",
        "hood", "rack", "basket", "tray",
    )
    _env_root = _stage_tmp.GetPrimAtPath("/World/Environment")
    _anchored = 0
    _anchored_by_name = 0
    if _env_root and _env_root.IsValid():
        _anchor_stack = list(_env_root.GetChildren())
        while _anchor_stack:
            _ap = _anchor_stack.pop()
            _anchor_stack.extend(_ap.GetChildren())

            if _ap.HasAPI(UsdPhysics.RigidBodyAPI):
                _rb = UsdPhysics.RigidBodyAPI(_ap)
                _rb.CreateKinematicEnabledAttr(True)
                _anchored += 1
            else:
                _name_low = _ap.GetName().lower()
                if any(kw in _name_low for kw in _ANCHOR_KEYWORDS):
                    UsdPhysics.RigidBodyAPI.Apply(_ap)
                    UsdPhysics.RigidBodyAPI(_ap).CreateKinematicEnabledAttr(True)
                    _anchored_by_name += 1
    print(f"[RoboLab] Anchored {_anchored} existing rigid bodies + {_anchored_by_name} by name as kinematic")

    # --single-object: hide all small scene-native objects (cups, fruits, etc.)
    # so only furniture remains and our single spawned object is on the table.
    _FURNITURE_KEYWORDS = (
        "fridge", "refrigerator", "dishwasher", "sink", "counter",
        "table", "shelf", "cabinet", "oven", "microwave", "wall",
        "floor", "ceiling", "door", "drawer", "handle", "panel",
        "hood", "rack", "basket", "tray", "light", "lamp", "window",
        "chair", "sofa", "couch", "bed", "stair", "roof", "beam",
        "column", "pillar", "frame", "curtain", "blind", "vent",
        "pipe", "wire", "switch", "outlet", "socket", "knob",
    )
    _hide_scene_clutter = True
    if _hide_scene_clutter and _env_root and _env_root.IsValid():
        _hidden_count = 0
        _hide_stack = list(_env_root.GetChildren())
        while _hide_stack:
            _hp = _hide_stack.pop()
            _hp_name = _hp.GetName().lower()
            _is_furniture = any(kw in _hp_name for kw in _FURNITURE_KEYWORDS)
            if _hp.HasAPI(UsdPhysics.RigidBodyAPI) and not _is_furniture:
                _img = UsdGeom.Imageable(_hp)
                if _img:
                    _img.MakeInvisible()
                if _hp.HasAPI(UsdPhysics.CollisionAPI):
                    _hp.RemoveAPI(UsdPhysics.CollisionAPI)
                _hidden_count += 1
            else:
                _hide_stack.extend(_hp.GetChildren())
        print(f"[RoboLab] Hid {_hidden_count} scene-native small objects (clutter removal)")

    # Dump all environment prims for diagnostics (find fences, walls, barriers).
    if _env_root and _env_root.IsValid():
        _diag_stack = list(_env_root.GetChildren())
        _diag_names = []
        while _diag_stack:
            _dp = _diag_stack.pop()
            _dn = _dp.GetPath().pathString
            _diag_names.append(_dn)
            _children = _dp.GetChildren()
            if len(_children) < 50:
                _diag_stack.extend(_children)
        _diag_names.sort()
        print(f"[RoboLab] Environment prims ({len(_diag_names)}):")
        for _dn in _diag_names:
            print(f"  {_dn}")

    # Also dump top-level /World prims
    _world_prim = _cur_stage.GetPrimAtPath("/World")
    if _world_prim and _world_prim.IsValid():
        _world_children = [c.GetPath().pathString for c in _world_prim.GetChildren()]
        print(f"[RoboLab] /World top-level prims: {_world_children}")

    # Remove fences, railings, and barriers that obstruct robot workspace.
    _OBSTACLE_KEYWORDS = ("fence", "railing", "balustrade", "barrier", "guardrail", "banister", "handrail")
    _obstacle_removed = 0
    if _env_root and _env_root.IsValid():
        _obs_stack = list(_env_root.GetChildren())
        while _obs_stack:
            _op = _obs_stack.pop()
            _op_name = _op.GetName().lower()
            _op_path = _op.GetPath().pathString.lower()
            if any(kw in _op_name or kw in _op_path for kw in _OBSTACLE_KEYWORDS):
                _img = UsdGeom.Imageable(_op)
                if _img:
                    _img.MakeInvisible()
                if _op.HasAPI(UsdPhysics.CollisionAPI):
                    _op.RemoveAPI(UsdPhysics.CollisionAPI)
                if _op.HasAPI(UsdPhysics.RigidBodyAPI):
                    UsdPhysics.RigidBodyAPI(_op).CreateKinematicEnabledAttr(True)
                _obstacle_removed += 1
                print(f"[RoboLab] Removed obstacle: {_op.GetPath().pathString}")
            else:
                _obs_stack.extend(_op.GetChildren())
    if _obstacle_removed:
        print(f"[RoboLab] Removed {_obstacle_removed} obstacle(s) from scene")

    # Per-scene spawn zones: table bounding boxes in world coordinates.
    # Each zone is (x_min, x_max, y_min, y_max). Objects are scattered
    # within these bounds and raycasted downward to find the table surface.
    _SCENE_SPAWN_ZONES = {
        "Kitchen":        [(1.1, 1.5, -0.2, 0.2)],
        "L_Kitchen":      [(1.1, 1.5, -0.2, 0.2)],
        "Modern_Kitchen": [(1.1, 1.5, -0.2, 0.2)],
        "Small_House":    [(1.1, 1.5, -0.2, 0.2)],
    }
    _DEFAULT_SPAWN_ZONE = [(1.1, 1.5, -0.2, 0.2)]

    def _get_spawn_zones():
        """Pick spawn zones based on the scene USD path."""
        _scene_path = str(getattr(args, "env_usd", "") or "")
        for _key, _zones in _SCENE_SPAWN_ZONES.items():
            if _key.lower() in _scene_path.lower():
                return _zones
        return _DEFAULT_SPAWN_ZONE

    def _get_single_object_xy():
        """Deterministic easy-pick spot on the right half of the table."""
        _zone = _get_spawn_zones()[0]
        _x = min(_zone[1] - 0.04, max(_zone[0] + 0.04, 1.28))
        _y = min(_zone[3] - 0.04, max(_zone[2] + 0.04, -0.16))
        return float(_x), float(_y)

    def _apply_manipulation_physics(prim):
        """Apply contact/rest offsets, convex approximation, and friction material to a graspable object."""
        try:
            if PhysxSchema and prim.IsValid():
                _col_api = PhysxSchema.PhysxCollisionAPI.Apply(prim) if not prim.HasAPI(PhysxSchema.PhysxCollisionAPI) else PhysxSchema.PhysxCollisionAPI(prim)
                _col_api.CreateContactOffsetAttr(0.005)
                _col_api.CreateRestOffsetAttr(0.001)
        except Exception:
            pass
        try:
            if PhysxSchema and prim.IsValid():
                if not prim.HasAPI(PhysxSchema.PhysxConvexHullCollisionAPI) and not prim.HasAPI(PhysxSchema.PhysxConvexDecompositionCollisionAPI):
                    PhysxSchema.PhysxConvexDecompositionCollisionAPI.Apply(prim)
        except Exception:
            pass
        try:
            from pxr import UsdShade
            _obj_mat_path = "/World/Materials/ObjectFrictionMaterial"
            _obj_mat_prim = stage_utils.get_current_stage().GetPrimAtPath(_obj_mat_path)
            if not _obj_mat_prim.IsValid():
                UsdShade.Material.Define(stage_utils.get_current_stage(), _obj_mat_path)
                _obj_mat_prim = stage_utils.get_current_stage().GetPrimAtPath(_obj_mat_path)
                _phys_mat = UsdPhysics.MaterialAPI.Apply(_obj_mat_prim)
                _phys_mat.CreateStaticFrictionAttr(2.0)
                _phys_mat.CreateDynamicFrictionAttr(1.5)
                _phys_mat.CreateRestitutionAttr(0.1)
            _obj_mat = UsdShade.Material(_obj_mat_prim)
            UsdShade.MaterialBindingAPI.Apply(prim)
            UsdShade.MaterialBindingAPI(prim).Bind(
                _obj_mat, UsdShade.Tokens.weakerThanDescendants, "physics",
            )
        except Exception:
            pass

    # Spawn diverse graspable objects on table surfaces when --spawn-objects is set.
    # Objects are initially placed at Z=3.0 (above all furniture). After world.reset()
    # and physics warm-up, they are repositioned via raycast to actual table surfaces.
    _spawned_objects = []
    _spawn_needs_raycast = False
    if args.spawn_objects:
        import random as _rng
        _obj_dir = Path(args.objects_dir)
        _ycb_dir = Path(args.objects_dir).parent / "object_sets_ycb"
        _obj_usds = []
        _ycb_usds = []
        if _ycb_dir.exists():
            for _ext in ("*.usd", "*.usda", "*.usdc", "*.usdz"):
                _ycb_usds.extend(_ycb_dir.glob(_ext))
        if _obj_dir.exists():
            for _ext in ("*.usd", "*.usda", "*.usdc", "*.usdz"):
                _obj_usds.extend(_obj_dir.glob(_ext))
        _all_usds = _ycb_usds + _obj_usds
        _preferred_single_tokens = [
            _token.strip().lower()
            for _token in str(args.single_object_preferred or "").split(",")
            if _token.strip()
        ]
        if not _all_usds:
            _builtin_shapes = ["Cylinder"] if args.single_object else ["Cube", "Cylinder", "Sphere", "Cone"]
            print(f"[RoboLab] No object USDs found, spawning built-in shapes as graspable objects")
            _spawn_zones = _get_spawn_zones()
            for _si, _shape in enumerate(_builtin_shapes):
                _obj_path = f"/World/GraspableObjects/{_shape}_{_si}"
                _zone = _spawn_zones[_si % len(_spawn_zones)]
                if args.single_object:
                    _xoff, _yoff = _get_single_object_xy()
                else:
                    _xoff = _zone[0] + (_si / max(len(_builtin_shapes) - 1, 1)) * (_zone[1] - _zone[0])
                    _yoff = _zone[2] + ((_si % 2) * 0.5 + 0.25) * (_zone[3] - _zone[2])
                _scale = 0.04
                if _shape == "Cube":
                    _prim_def = UsdGeom.Cube.Define(_stage_tmp, _obj_path)
                    _prim_def.CreateSizeAttr(1.0)
                elif _shape == "Cylinder":
                    _prim_def = UsdGeom.Cylinder.Define(_stage_tmp, _obj_path)
                    _prim_def.CreateRadiusAttr(0.5)
                    _prim_def.CreateHeightAttr(1.0)
                elif _shape == "Sphere":
                    _prim_def = UsdGeom.Sphere.Define(_stage_tmp, _obj_path)
                    _prim_def.CreateRadiusAttr(0.5)
                elif _shape == "Cone":
                    _prim_def = UsdGeom.Cone.Define(_stage_tmp, _obj_path)
                    _prim_def.CreateRadiusAttr(0.5)
                    _prim_def.CreateHeightAttr(1.0)
                _obj_prim = _stage_tmp.GetPrimAtPath(_obj_path)
                _xf = UsdGeom.Xformable(_obj_prim)
                _xf.AddTranslateOp().Set(Gf.Vec3d(_xoff, _yoff, 3.0))
                _xf.AddScaleOp().Set(Gf.Vec3f(_scale, _scale, _scale))
                UsdPhysics.RigidBodyAPI.Apply(_obj_prim)
                UsdPhysics.CollisionAPI.Apply(_obj_prim)
                UsdPhysics.MassAPI.Apply(_obj_prim).CreateMassAttr(0.2)
                _apply_manipulation_physics(_obj_prim)
                add_update_semantics(_obj_prim, _shape.lower())
                _spawned_objects.append((_obj_path, _shape.lower()))
                print(f"[RoboLab]   spawned built-in: {_obj_path}")
        else:
            _rng.shuffle(_all_usds)
            if args.single_object:
                def _single_spawn_rank(_path: Path):
                    _name = _path.stem.lower()
                    _score = 100.0
                    for _idx, _token in enumerate(_preferred_single_tokens):
                        if _token in _name:
                            _score = min(_score, float(_idx))
                    if any(_bad in _name for _bad in ("plate", "bowl", "pitcher", "bottle", "wine", "glass", "fruit")):
                        _score += 20.0
                    return (_score, len(_name), _name)
                _all_usds = sorted(_all_usds, key=_single_spawn_rank)
                _to_spawn = _all_usds[:1]
            else:
                _to_spawn = _all_usds[:6]
            _spawn_zones = _get_spawn_zones()
            for _si, _obj_usd in enumerate(_to_spawn):
                _obj_name = _obj_usd.stem
                _safe_name = _obj_name if not _obj_name[0].isdigit() else f"obj_{_obj_name}"
                _obj_path = f"/World/GraspableObjects/{_safe_name}_{_si}"
                stage_utils.add_reference_to_stage(
                    usd_path=str(_obj_usd), prim_path=_obj_path,
                )
                _obj_prim = _stage_tmp.GetPrimAtPath(_obj_path)
                if _obj_prim.IsValid():
                    _xf = UsdGeom.Xformable(_obj_prim)
                    _zone = _spawn_zones[_si % len(_spawn_zones)]
                    if args.single_object:
                        _xoff, _yoff = _get_single_object_xy()
                    else:
                        _xoff = _rng.uniform(_zone[0], _zone[1])
                        _yoff = _rng.uniform(_zone[2], _zone[3])
                    _xf.AddTranslateOp().Set(Gf.Vec3d(_xoff, _yoff, 3.0))
                    if not _obj_prim.HasAPI(UsdPhysics.RigidBodyAPI):
                        UsdPhysics.RigidBodyAPI.Apply(_obj_prim)
                    if not _obj_prim.HasAPI(UsdPhysics.CollisionAPI):
                        UsdPhysics.CollisionAPI.Apply(_obj_prim)
                    _apply_manipulation_physics(_obj_prim)
                    add_update_semantics(_obj_prim, _obj_name)
                    _spawned_objects.append((_obj_path, _obj_name))
                    print(f"[RoboLab]   spawned: {_obj_path} from {_obj_usd.name}")
        _spawn_needs_raycast = len(_spawned_objects) > 0
        print(f"[RoboLab] Spawned {len(_spawned_objects)} graspable objects (pending raycast placement)")

    tiago_prim_path = "/World/Tiago"
    tiago_usd = resolve_usd_path(args.tiago_usd)
    tiago_usd_local = Path(tiago_usd)
    if tiago_usd_local.exists():
        print(f"[RoboLab] Tiago USD found: {tiago_usd_local}")
    else:
        print(f"[RoboLab] WARN: Tiago USD path does not exist locally: {tiago_usd}")
        print("[RoboLab] WARN: This may load an empty reference and force synthetic joint fallback.")
    stage_utils.add_reference_to_stage(usd_path=tiago_usd, prim_path=tiago_prim_path)
    stage = stage_utils.get_current_stage()
    tiago_prim = stage.GetPrimAtPath(tiago_prim_path)
    if not tiago_prim.IsValid():
        raise RuntimeError(f"Tiago prim not found after load: {tiago_prim_path}")
    add_update_semantics(tiago_prim, "tiago")

    _TIAGO_SEARCH_MIDS = [
        "/tiago_dual_functional_light",
        "/tiago_dual_functional/tiago_dual_functional",
        "/tiago_dual_functional",
        "",
    ]

    def _join_tiago_path(base_path, subtree_mid, leaf_name):
        if subtree_mid:
            return f"{base_path}{subtree_mid}/{leaf_name}"
        return f"{base_path}/{leaf_name}"

    # Stabilize known problematic Tiago rigid-body mass/inertia values that can
    # cause immediate toppling in PhysX.
    _mass_override_suffixes = {
        "base_footprint": (500.0, Gf.Vec3f(15.0, 15.0, 6.0)),
        "base_link": (45.0, Gf.Vec3f(3.0, 3.0, 1.5)),
        "gemini2_link": (0.5, Gf.Vec3f(0.01, 0.01, 0.01)),
        "wheel_front_left_link/mecanum_wheel_fl/wheel_link": (1.5, Gf.Vec3f(0.02, 0.02, 0.02)),
        "wheel_front_right_link/mecanum_wheel_fr/wheel_link": (1.5, Gf.Vec3f(0.02, 0.02, 0.02)),
        "wheel_rear_left_link/mecanum_wheel_rl/wheel_link": (1.5, Gf.Vec3f(0.02, 0.02, 0.02)),
        "wheel_rear_right_link/mecanum_wheel_rr/wheel_link": (1.5, Gf.Vec3f(0.02, 0.02, 0.02)),
    }
    mass_overrides = {}
    for _mid in _TIAGO_SEARCH_MIDS:
        for _suffix, _override in _mass_override_suffixes.items():
            mass_overrides[_join_tiago_path(tiago_prim_path, _mid, _suffix)] = _override
    for prim_path, (mass_value, inertia_value) in mass_overrides.items():
        prim = stage.GetPrimAtPath(prim_path)
        if not prim.IsValid():
            continue
        try:
            mass_api = UsdPhysics.MassAPI.Apply(prim)
            mass_api.CreateMassAttr(float(mass_value))
            mass_api.CreateDiagonalInertiaAttr(inertia_value)
            print(f"[RoboLab] Applied mass override at {prim_path} (mass={mass_value}).")
        except Exception as err:
            print(f"[RoboLab] WARN: Failed mass override at {prim_path}: {err}")

    tiago_articulation = None
    tiago_articulation_path = tiago_prim_path
    fallback_joint_names = ["base_x", "base_y", "base_yaw", "arm_lift", "arm_flex", "wrist_roll"]
    fallback_moveit_joint_names = [
        "torso_lift_joint",
        "arm_1_joint",
        "arm_2_joint",
        "arm_3_joint",
        "arm_4_joint",
        "arm_5_joint",
        "arm_6_joint",
        "arm_7_joint",
    ]
    if tiago_prim.HasAPI(UsdPhysics.ArticulationRootAPI):
        try:
            tiago_articulation = Articulation(prim_path=tiago_prim_path, name="tiago")
            world.scene.add(tiago_articulation)
        except Exception as err:
            print(f"[RoboLab] WARN: failed to initialize Tiago articulation, using fallback joints: {err}")
            tiago_articulation = None
    else:
        # Some Tiago USDs expose articulation root under a child prim.
        detected_root = None
        for prim in stage.Traverse():
            prim_path_str = str(prim.GetPath())
            if not prim_path_str.startswith(tiago_prim_path):
                continue
            if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
                detected_root = prim_path_str
                break
        if detected_root:
            tiago_articulation_path = detected_root
            print(f"[RoboLab] Detected Tiago articulation root at: {tiago_articulation_path}")
            try:
                tiago_articulation = Articulation(prim_path=tiago_articulation_path, name="tiago")
                world.scene.add(tiago_articulation)
            except Exception as err:
                print(f"[RoboLab] WARN: failed to initialize Tiago articulation at detected root, using fallback joints: {err}")
                tiago_articulation = None
        else:
            print("[RoboLab] WARN: Tiago prim has no ArticulationRootAPI. Falling back to synthetic joints.")

    if args.require_real_tiago and not tiago_articulation:
        raise RuntimeError(
            "Real Tiago articulation is required but was not initialized. "
            f"Check --tiago-usd path and asset contents (current: {tiago_usd})."
        )

    _robot_start_x = getattr(args, "robot_start_x", 0.8)

    # Replicator streams for rgb/depth/pointcloud/semantics.
    replicator_dir = os.path.join(args.output_dir, "replicator_data")
    camera_parent_prim = args.robot_pov_camera_prim or tiago_prim_path
    if not stage.GetPrimAtPath(camera_parent_prim).IsValid():
        print(f"[RoboLab] WARN: POV parent prim '{camera_parent_prim}' not found, falling back to {tiago_prim_path}")
        camera_parent_prim = tiago_prim_path

    # Camera setup: VR mode mounts camera at robot head for operator POV.
    # Non-VR mode uses a world-fixed overview camera for recording.
    if args.vr:
        head_link = camera_parent_prim
        for _base in [tiago_articulation_path, tiago_prim_path]:
            for _mid in _TIAGO_SEARCH_MIDS:
                _cand = _join_tiago_path(_base, _mid, "head_2_link")
                if stage.GetPrimAtPath(_cand).IsValid():
                    head_link = _cand
                    break
            if head_link != camera_parent_prim:
                break
        head_camera = rep.create.camera(
            position=(0.05, 0, 0.05), look_at=(1, 0, 0), parent=head_link
        )
        camera_parent_prim = head_link
        print(f"[RoboLab] VR head camera mounted at {head_link}")
    elif camera_parent_prim == tiago_prim_path:
        head_camera = rep.create.camera(position=(_robot_start_x + 1.7, -1.5, 2.0), look_at=(_robot_start_x + 0.3, 0.0, 0.8))
        camera_parent_prim = "/World"
    else:
        head_camera = rep.create.camera(position=(0, 0, 1.35), look_at=(1, 0, 1.15), parent=camera_parent_prim)
    render_product = rep.create.render_product(head_camera, (args.capture_width, args.capture_height))
    _rep_subsample = max(1, int(args.replicator_subsample))
    writer = rep.WriterRegistry.get("BasicWriter")
    writer.initialize(
        output_dir=replicator_dir,
        rgb=True,
        distance_to_camera=True,
        pointcloud=True,
        semantic_segmentation=True,
    )
    _all_render_products = [render_product]

    # Wrist camera: mounted on arm tool link for close-up manipulation view.
    _wrist_camera = None
    _wrist_render_product = None
    _wrist_replicator_dir = None
    if getattr(args, "wrist_camera", False):
        _wrist_link = None
        _wrist_candidates = [
            "arm_tool_link", "arm_7_link", "gripper_link",
            "arm_right_tool_link", "arm_right_7_link",
        ]
        for _base in [tiago_articulation_path, tiago_prim_path]:
            for _mid in _TIAGO_SEARCH_MIDS:
                for _name in _wrist_candidates:
                    _cand = _join_tiago_path(_base, _mid, _name)
                    if stage.GetPrimAtPath(_cand).IsValid():
                        _wrist_link = _cand
                        break
                if _wrist_link:
                    break
            if _wrist_link:
                break
        if not _wrist_link:
            _wrist_match_names = {"arm_tool_link", "arm_7_link", "arm_right_tool_link"}
            for _p in stage.Traverse():
                _pn = _p.GetName().lower()
                if _pn in _wrist_match_names or "tool_link" in _pn:
                    _pp = str(_p.GetPath())
                    if _pp.startswith(tiago_prim_path):
                        _wrist_link = _pp
                        print(f"[RoboLab] Wrist link found via traversal: {_wrist_link}")
                        break
        if _wrist_link:
            _wrist_camera = rep.create.camera(
                position=(0.0, 0.0, 0.05), look_at=(0.0, 0.0, 0.2), parent=_wrist_link
            )
            _wrist_render_product = rep.create.render_product(
                _wrist_camera, (args.capture_width, args.capture_height)
            )
            _wrist_replicator_dir = os.path.join(args.output_dir, "replicator_wrist")
            _wrist_writer = rep.WriterRegistry.get("BasicWriter")
            _wrist_writer.initialize(
                output_dir=_wrist_replicator_dir,
                rgb=True,
                distance_to_camera=True,
                pointcloud=True,
            )
            _wrist_writer.attach([_wrist_render_product])
            _all_render_products.append(_wrist_render_product)
            print(f"[RoboLab] Wrist camera mounted at {_wrist_link}")
        else:
            print("[RoboLab] WARN: wrist link not found, skipping wrist camera")

    # External camera: fixed third-person view for scene overview.
    _external_camera = None
    _external_render_product = None
    _external_replicator_dir = None
    if getattr(args, "external_camera", False):
        if args.external_camera_pos == "auto":
            _ext_pos = (_robot_start_x, 1.8, 1.6)
        else:
            _ext_pos = tuple(float(x) for x in args.external_camera_pos.split(","))
        if args.external_camera_target == "auto":
            _ext_tgt = (_robot_start_x + 0.3, 0.0, 0.8)
        else:
            _ext_tgt = tuple(float(x) for x in args.external_camera_target.split(","))
        print(f"[RoboLab] External camera: pos={_ext_pos} target={_ext_tgt}")
        _external_camera = rep.create.camera(position=_ext_pos, look_at=_ext_tgt)
        _external_render_product = rep.create.render_product(
            _external_camera, (args.capture_width, args.capture_height)
        )
        _external_replicator_dir = os.path.join(args.output_dir, "replicator_external")
        _ext_writer = rep.WriterRegistry.get("BasicWriter")
        _ext_writer.initialize(
            output_dir=_external_replicator_dir,
            rgb=True,
            distance_to_camera=True,
        )
        _ext_writer.attach([_external_render_product])
        _all_render_products.append(_external_render_product)
        print(f"[RoboLab] External camera at pos={_ext_pos} target={_ext_tgt}")

    writer.attach([render_product])
    _n_cameras = len(_all_render_products)
    print(f"[RoboLab] Total cameras: {_n_cameras} | Replicator subsample={_rep_subsample}")

    tracked_prims = []
    _tracked_paths: set = set()
    for prim in stage.Traverse():
        if not prim.HasAPI(UsdGeom.Xformable):
            continue
        semantic = get_semantics(prim)
        if semantic and semantic.get("class") and semantic["class"] != "class":
            _p = str(prim.GetPath())
            tracked_prims.append((_p, semantic["class"]))
            _tracked_paths.add(_p)
    # Recursively scan /World/Environment for furniture prims (fridge,
    # dishwasher, sink, etc.) that may lack USD semantic labels.
    # USD scenes often nest geometry several levels deep (e.g.
    # /World/Environment/Environment/Fridge).
    _FURNITURE_KW = ("fridge", "refrigerator", "dishwasher", "sink", "counter",
                     "table", "shelf", "cabinet", "oven", "microwave", "door")
    _env_prim = stage.GetPrimAtPath("/World/Environment")
    if _env_prim and _env_prim.IsValid():
        _env_stack = list(_env_prim.GetChildren())
        while _env_stack:
            _child = _env_stack.pop()
            _cp = str(_child.GetPath())
            _raw_name = _child.GetName().lower()
            _matched_kw = None
            for _kw in _FURNITURE_KW:
                if _kw in _raw_name:
                    _matched_kw = _kw
                    break
            if _matched_kw and _cp not in _tracked_paths:
                tracked_prims.append((_cp, _matched_kw))
                _tracked_paths.add(_cp)
                print(f"[RoboLab]   env object: {_cp} -> {_matched_kw}")
            else:
                _env_stack.extend(_child.GetChildren())
    for _sp_path, _sp_class in _spawned_objects:
        if _sp_path not in _tracked_paths:
            tracked_prims.append((_sp_path, _sp_class))
            _tracked_paths.add(_sp_path)
    print(f"[RoboLab] Tracking {len(tracked_prims)} semantic objects.")

    # Pin the articulation root BEFORE world.reset(). If --mobile-base is set,
    # the base is left unfixed so the robot can navigate.
    _use_fixed_base = not getattr(args, "mobile_base", False)
    if _use_fixed_base:
        from pxr import Sdf
        _art_prim = stage.GetPrimAtPath(tiago_articulation_path)
        if _art_prim.IsValid():
            _art_prim.CreateAttribute(
                "physxArticulation:fixedBase", Sdf.ValueTypeNames.Bool).Set(True)
            print(f"[RoboLab] Set physxArticulation:fixedBase=True at {tiago_articulation_path}")
            _art_prim.CreateAttribute(
                "physxArticulation:enabledSelfCollisions", Sdf.ValueTypeNames.Bool).Set(False)
            print(f"[RoboLab] Disabled self-collisions on articulation")

    # Configure joint drives BEFORE world.reset() so they are part of the USD
    # state and active from the very first physics step. This prevents arms from
    # falling freely under gravity during warm-up.
    _pre_drive_count = 0
    for _jp in stage.Traverse():
        _is_rev = _jp.IsA(UsdPhysics.RevoluteJoint)
        _is_pri = (not _is_rev) and _jp.IsA(UsdPhysics.PrismaticJoint)
        if not _is_rev and not _is_pri:
            continue
        _dt = "angular" if _is_rev else "linear"
        _da = UsdPhysics.DriveAPI.Apply(_jp, _dt)
        _da.CreateTypeAttr("force")
        _da.CreateStiffnessAttr().Set(1e6)
        _da.CreateDampingAttr().Set(1e5)
        _da.CreateMaxForceAttr().Set(1e8)
        _pre_drive_count += 1
    print(f"[RoboLab] Pre-reset: configured {_pre_drive_count} joint drives (force mode, Kp=1e6)")

    _robot_start_x = getattr(args, "robot_start_x", 0.8)
    try:
        tiago_xform = XFormPrim(prim_path=tiago_prim_path, name="tiago_root_pose")
        tiago_xform.set_world_pose(
            position=np.array([_robot_start_x, 0.0, 0.0], dtype=np.float32),
            orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        )
        print(f"[RoboLab] Applied startup pose: pos=({_robot_start_x}, 0.0, 0.0) facing +X toward table")
    except Exception as err:
        print(f"[RoboLab] WARN: failed to apply startup pose stabilization: {err}")

    world.reset()
    simulation_app.update()

    if tiago_articulation:
        try:
            tiago_articulation.initialize()
            print("[RoboLab] Tiago articulation initialized", flush=True)
        except Exception as err:
            print(f"[RoboLab] WARN: articulation initialize failed: {err}", flush=True)

    # Anchor the articulation physics body at the desired start position.
    # Retry set_world_pose until PhysX actually places the robot there.
    if tiago_articulation and _use_fixed_base:
        _INIT_POS = np.array([_robot_start_x, 0.0, 0.0], dtype=np.float32)
        _INIT_ORI = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        _anchor_ok = False
        for _anchor_attempt in range(5):
            try:
                tiago_articulation.set_world_pose(position=_INIT_POS, orientation=_INIT_ORI)
                _zero_vel = np.zeros(len(resolve_dof_names(tiago_articulation)), dtype=np.float32)
                tiago_articulation.set_joint_velocities(_zero_vel)
                for _ in range(20):
                    world.step(render=False)
                _art_pos, _art_ori = tiago_articulation.get_world_pose()
                if _art_pos is not None:
                    _anchor_drift = (abs(float(_art_pos[0]) - _robot_start_x) +
                                     abs(float(_art_pos[1])) +
                                     abs(float(_art_pos[2]) - 0.0))
                    print(f"[RoboLab] Anchor attempt {_anchor_attempt}: "
                          f"pos=({_art_pos[0]:.4f},{_art_pos[1]:.4f},{_art_pos[2]:.4f}) "
                          f"drift={_anchor_drift:.4f}", flush=True)
                    if _anchor_drift < 0.05:
                        _anchor_ok = True
                        break
            except Exception as err:
                print(f"[RoboLab] WARN: anchor attempt {_anchor_attempt} failed: {err}", flush=True)
        if not _anchor_ok:
            print(f"[RoboLab] WARN: could not anchor robot at ({_robot_start_x}, 0, 0.0) after 5 attempts", flush=True)

    # Log robot frame pose for diagnostics.
    # fixedBase=True should hold the articulation root in place.
    # If base drifts, it indicates a physics problem (invalid inertia, etc.).
    try:
        _diag_prim_xf = XFormPrim(prim_path=tiago_prim_path)
        _diag_prim_pos, _diag_prim_ori = _diag_prim_xf.get_world_pose()
        print(f"[RoboLab] Robot frame: /World/Tiago=({_diag_prim_pos[0]:.4f},{_diag_prim_pos[1]:.4f},{_diag_prim_pos[2]:.4f}) "
              f"ori=({_diag_prim_ori[0]:.4f},{_diag_prim_ori[1]:.4f},{_diag_prim_ori[2]:.4f},{_diag_prim_ori[3]:.4f})", flush=True)
    except Exception as _diag_err:
        print(f"[RoboLab] Frame check failed: {_diag_err}", flush=True)

    # Set initial joint position targets via ArticulationAction before warm-up.
    # Both arms go to a neutral "arms down" pose to avoid the default tucked/ear-scratch pose.
    _NEUTRAL_ARM_POSE = {
        "arm_right_1_joint": 0.20, "arm_right_2_joint": -0.35,
        "arm_right_3_joint": -0.20, "arm_right_4_joint": 1.90,
        "arm_right_5_joint": -1.57, "arm_right_6_joint": 1.20,
        "arm_right_7_joint": 0.0,
        "arm_left_1_joint": 0.20, "arm_left_2_joint": -0.35,
        "arm_left_3_joint": -0.20, "arm_left_4_joint": 1.90,
        "arm_left_5_joint": -1.57, "arm_left_6_joint": 1.20,
        "arm_left_7_joint": 0.0,
        "torso_lift_joint": 0.15,
        "head_1_joint": 0.0, "head_2_joint": 0.0,
    }
    if tiago_articulation:
        try:
            from omni.isaac.core.utils.types import ArticulationAction
            _dof_names_init = resolve_dof_names(tiago_articulation)
            _get_pos = getattr(tiago_articulation, "get_joint_positions", None) or getattr(
                tiago_articulation, "get_dof_positions", None
            )
            _set_vel = getattr(tiago_articulation, "set_joint_velocities", None) or getattr(
                tiago_articulation, "set_dof_velocities", None
            )
            _cur_pos = _as_list(_get_pos()) if _get_pos else []
            if _cur_pos and _dof_names_init:
                for _jn, _jv in _NEUTRAL_ARM_POSE.items():
                    if _jn in _dof_names_init:
                        _cur_pos[_dof_names_init.index(_jn)] = _jv
                # Teleport joints to neutral pose first (instant, no physics).
                _set_jp = getattr(tiago_articulation, "set_joint_positions", None)
                if _set_jp:
                    _set_jp(np.array(_cur_pos, dtype=np.float32))
                    print(f"[RoboLab] Teleported {len(_cur_pos)} joints to neutral pose")
                # Then set PD targets to the same pose.
                tiago_articulation.apply_action(
                    ArticulationAction(joint_positions=np.array(_cur_pos, dtype=np.float32))
                )
                print(f"[RoboLab] Set {len(_cur_pos)} initial joint targets (both arms neutral)")
            if _set_vel and _cur_pos:
                _set_vel([0.0] * len(_cur_pos))
                print(f"[RoboLab] Zeroed {len(_cur_pos)} initial joint velocities")
        except Exception as err:
            print(f"[RoboLab] WARN: failed to set initial joint targets: {err}")

    # Joint drive tuning: PD gains per joint. MUST BE DONE BEFORE WARMUP!
    # Drive type is "acceleration" — PhysX multiplies by joint inertia automatically
    if tiago_articulation:
        # (stiffness, damping, maxForce) — force mode
        # "acceleration" mode: stiffness in 1/s², damping in 1/s.
        # PhysX auto-compensates for link inertia, so gains are
        # independent of mass. maxForce in N·m (torque limit).
        _DRIVE_PARAMS = {
            "torso_lift_joint":                 (2000.0, 400.0, 20000.0),
            "arm_1_joint":                      (1500.0, 300.0, 5000.0),
            "arm_2_joint":                      (1500.0, 300.0, 5000.0),
            "arm_3_joint":                      (1500.0, 300.0, 4000.0),
            "arm_4_joint":                      (1200.0, 240.0, 3000.0),
            "arm_5_joint":                      (500.0, 100.0, 800.0),
            "arm_6_joint":                      (500.0, 100.0, 800.0),
            "arm_7_joint":                      (500.0, 100.0, 800.0),
            "head_1_joint":                     (400.0,  80.0,  200.0),
            "head_2_joint":                     (400.0,  80.0,  200.0),
            "gripper_right_left_finger_joint":  (2000.0, 400.0, 500.0),
            "gripper_right_right_finger_joint": (2000.0, 400.0, 500.0),
            "gripper_left_left_finger_joint":   (2000.0, 400.0, 500.0),
            "gripper_left_right_finger_joint":  (2000.0, 400.0, 500.0),
        }
        _DRIVE_MODE = "acceleration"
        _DEFAULT_DRIVE_PARAMS = (400.0, 80.0, 500.0)
        _drive_count = 0
        _stage_d = stage_utils.get_current_stage()
        for _jp in _stage_d.Traverse():
            if not _jp.GetPath().pathString.startswith(tiago_prim_path):
                continue
            _rev = UsdPhysics.RevoluteJoint(_jp) if _jp.IsA(UsdPhysics.RevoluteJoint) else None
            _pri = UsdPhysics.PrismaticJoint(_jp) if not _rev and _jp.IsA(UsdPhysics.PrismaticJoint) else None
            if not _rev and not _pri:
                continue
            _jname = _jp.GetName()
            _canonical = _jname
            if _jname.startswith("arm_right_") or _jname.startswith("arm_left_"):
                parts = _jname.split("_")
                if len(parts) >= 3 and parts[2].isdigit():
                    _canonical = f"arm_{parts[2]}_joint"
            _params = _DRIVE_PARAMS.get(_jname) or _DRIVE_PARAMS.get(_canonical, _DEFAULT_DRIVE_PARAMS)
            _stiff, _damp, _max_f = _params
            _drive_type = "angular" if _rev else "linear"
            _drive_api = UsdPhysics.DriveAPI.Apply(_jp, _drive_type)
            _drive_api.CreateTypeAttr(_DRIVE_MODE)
            _drive_api.CreateStiffnessAttr().Set(_stiff)
            _drive_api.CreateDampingAttr().Set(_damp)
            _drive_api.CreateMaxForceAttr().Set(_max_f)
            _drive_count += 1
        print(f"[RoboLab] Configured drives on {_drive_count} joints ({_DRIVE_MODE} PD, per-joint gains)")
        # Verify drives by reading back
        _verify_count = 0
        for _jp in stage.Traverse():
            if not _jp.IsA(UsdPhysics.RevoluteJoint) and not _jp.IsA(UsdPhysics.PrismaticJoint):
                continue
            _jn = _jp.GetName()
            if "arm_right_1" not in _jn:
                continue
            _dt = "angular" if _jp.IsA(UsdPhysics.RevoluteJoint) else "linear"
            _da = UsdPhysics.DriveAPI.Get(_jp, _dt)
            if _da:
                _s = _da.GetStiffnessAttr().Get() if _da.GetStiffnessAttr() else "N/A"
                _d = _da.GetDampingAttr().Get() if _da.GetDampingAttr() else "N/A"
                _m = _da.GetMaxForceAttr().Get() if _da.GetMaxForceAttr() else "N/A"
                _t = _da.GetTypeAttr().Get() if _da.GetTypeAttr() else "N/A"
                print(f"[RoboLab] Drive verify {_jn}: type={_t} stiff={_s} damp={_d} maxF={_m}")
                _verify_count += 1
        if _verify_count == 0:
            print("[RoboLab] WARN: Could not verify any drives!")

        # Also set gains via articulation API for runtime override.
        try:
            _warmup_dof = _as_list(getattr(tiago_articulation, "dof_names", None)) or []
            n = len(_warmup_dof)
            if n > 0:
                kps = np.zeros(n, dtype=np.float32)
                kds = np.zeros(n, dtype=np.float32)
                for i, dn in enumerate(_warmup_dof):
                    _cn = dn
                    if dn.startswith("arm_right_") or dn.startswith("arm_left_"):
                        parts = dn.split("_")
                        if len(parts) >= 3 and parts[2].isdigit():
                            _cn = f"arm_{parts[2]}_joint"
                    _p = _DRIVE_PARAMS.get(dn) or _DRIVE_PARAMS.get(_cn, _DEFAULT_DRIVE_PARAMS)
                    kps[i] = _p[0]
                    kds[i] = _p[1]
                _set_gains_fn = getattr(tiago_articulation, "set_gains", None)
                _ac = getattr(tiago_articulation, "get_articulation_controller", None)
                if _set_gains_fn:
                    _set_gains_fn(kps=kps, kds=kds)
                    print(f"[RoboLab] Runtime gains set via articulation.set_gains() on {n} DOFs")
                elif _ac:
                    _ctrl = _ac()
                    _ctrl_set = getattr(_ctrl, "set_gains", None)
                    if _ctrl_set:
                        _ctrl_set(kps=kps, kds=kds)
                        print(f"[RoboLab] Runtime gains set via controller.set_gains() on {n} DOFs")
                    else:
                        _avail = [m for m in dir(_ctrl) if not m.startswith("_")]
                        print(f"[RoboLab] controller has no set_gains. Methods: {_avail[:20]}")
                else:
                    _avail = [m for m in dir(tiago_articulation) if "gain" in m.lower() or "stiff" in m.lower() or "damp" in m.lower()]
                    print(f"[RoboLab] No gains API found. Related methods: {_avail}")
        except Exception as _gains_err:
            print(f"[RoboLab] WARN: set_gains failed: {_gains_err}")

    # Run physics warm-up steps so the robot, environment, and spawned objects
    # settle fully before data collection. 500 base steps + stability check.
    _WARMUP_BASE_STEPS = 500
    _WARMUP_MAX_EXTRA = 300
    _WARMUP_VELOCITY_THRESH = 0.01
    for _ in range(_WARMUP_BASE_STEPS):
        world.step(render=False)
    if _spawned_objects and tiago_articulation:
        _stable = False
        for _extra in range(_WARMUP_MAX_EXTRA):
            world.step(render=False)
            _max_vel = 0.0
            for _sp, _ in _spawned_objects:
                try:
                    _sxf = XFormPrim(_sp)
                    _spos, _ = _sxf.get_world_pose()
                    if _spos is not None and len(_spos) >= 3 and float(_spos[2]) < 0.01:
                        _sxf.set_world_pose(
                            position=np.array([float(_spos[0]), float(_spos[1]), 0.85], dtype=np.float32),
                            orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
                except Exception:
                    pass
            if _extra % 30 == 0 and _extra > 0:
                _all_settled = True
                for _sp, _ in _spawned_objects:
                    try:
                        _rb = UsdPhysics.RigidBodyAPI(stage.GetPrimAtPath(_sp))
                        _vel = _rb.GetVelocityAttr().Get()
                        if _vel is not None:
                            _v = sum(float(v)**2 for v in _vel) ** 0.5
                            if _v > _WARMUP_VELOCITY_THRESH:
                                _all_settled = False
                    except Exception:
                        pass
                if _all_settled:
                    _stable = True
                    print(f"[RoboLab] Objects settled after {_WARMUP_BASE_STEPS + _extra} warm-up steps")
                    break
        if not _stable:
            print(f"[RoboLab] Objects did not fully settle after {_WARMUP_BASE_STEPS + _WARMUP_MAX_EXTRA} steps")
    else:
        print(f"[RoboLab] Physics warm-up: {_WARMUP_BASE_STEPS} steps complete")

    # After warm-up, zero all velocities and re-lock position targets.
    if tiago_articulation:
        try:
            from omni.isaac.core.utils.types import ArticulationAction as _AA
            _get_pos2 = getattr(tiago_articulation, "get_joint_positions", None) or getattr(
                tiago_articulation, "get_dof_positions", None
            )
            _set_vel2 = getattr(tiago_articulation, "set_joint_velocities", None) or getattr(
                tiago_articulation, "set_dof_velocities", None
            )
            _settled_pos = _as_list(_get_pos2()) if _get_pos2 else []
            if _settled_pos:
                tiago_articulation.apply_action(
                    _AA(joint_positions=np.array(_settled_pos, dtype=np.float32))
                )
            if _set_vel2 and _settled_pos:
                _set_vel2([0.0] * len(_settled_pos))
                print(f"[RoboLab] Post-warmup: zeroed velocities and locked {len(_settled_pos)} joints")
                _warmup_dof_names = _as_list(getattr(tiago_articulation, "dof_names", None)) or []
                _arm_names = ["arm_right_1_joint", "arm_right_2_joint", "arm_right_3_joint",
                              "arm_right_4_joint", "arm_right_5_joint", "arm_right_6_joint", "arm_right_7_joint"]
                _idx_map = {n: i for i, n in enumerate(_warmup_dof_names)}
                _arm_diag = []
                for _an in _arm_names:
                    _ai = _idx_map.get(_an)
                    if _ai is not None and _ai < len(_settled_pos):
                        _arm_diag.append(f"{_an}={_settled_pos[_ai]:.4f}")
                _torso_idx = _idx_map.get("torso_lift_joint")
                if _torso_idx is not None and _torso_idx < len(_settled_pos):
                    print(f"[RoboLab] Post-warmup torso: actual={_settled_pos[_torso_idx]:.4f} target=0.1500")
                if _arm_diag:
                    print(f"[RoboLab] Post-warmup arm positions: {', '.join(_arm_diag)}")
                else:
                    print(f"[RoboLab] Post-warmup: could not read arm positions (dof_names={len(_warmup_dof_names)})")
        except Exception as err:
            print(f"[RoboLab] WARN: failed to zero startup articulation velocities: {err}")

    # Raycast-based object placement: reposition spawned objects onto actual surfaces.
    if _spawn_needs_raycast and _spawned_objects:
        _placed = 0
        _fell = 0
        try:
            from omni.physx import get_physx_scene_query_interface
            _pq = get_physx_scene_query_interface()

            for _ in range(10):
                world.step(render=False)

            for _obj_path, _obj_class in _spawned_objects:
                _obj_prim = stage.GetPrimAtPath(_obj_path)
                if not _obj_prim.IsValid():
                    continue
                _oxf = XFormPrim(_obj_path)
                _opos, _orot = _oxf.get_world_pose()
                if _opos is None:
                    continue
                _ox, _oy = float(_opos[0]), float(_opos[1])
                if args.single_object:
                    _ox, _oy = _get_single_object_xy()

                _hit_info = _pq.raycast_closest(
                    (_ox, _oy, 2.5), (0.0, 0.0, -1.0), 3.0
                )
                if _hit_info["hit"]:
                    _surface_z = float(_hit_info["position"][2])
                    if _surface_z > 0.3:
                        _spawn_z = _surface_z + 0.08
                        _oxf.set_world_pose(
                            position=np.array([_ox, _oy, _spawn_z], dtype=np.float32),
                            orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                        )
                        _placed += 1
                        continue

                _zones = _get_spawn_zones()
                _found_surface = False
                for _attempt in range(8):
                    if args.single_object:
                        _tx, _ty = _get_single_object_xy()
                    else:
                        _zone = _zones[_attempt % len(_zones)]
                        _tx = _rng.uniform(_zone[0], _zone[1])
                        _ty = _rng.uniform(_zone[2], _zone[3])
                    _hit2 = _pq.raycast_closest((_tx, _ty, 2.5), (0.0, 0.0, -1.0), 3.0)
                    if _hit2["hit"] and float(_hit2["position"][2]) > 0.3:
                        _sz = float(_hit2["position"][2]) + 0.08
                        _oxf.set_world_pose(
                            position=np.array([_tx, _ty, _sz], dtype=np.float32),
                            orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                        )
                        _placed += 1
                        _found_surface = True
                        break
                if not _found_surface:
                    _oxf.set_world_pose(
                        position=np.array([_ox, _oy, 0.85], dtype=np.float32),
                        orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                    )
                    _fell += 1

            print(f"[RoboLab] Raycast placement: {_placed} on surface, {_fell} fallback")
        except ImportError:
            print("[RoboLab] WARN: omni.physx not available, using fallback Z=0.85 for objects")
            for _obj_path, _ in _spawned_objects:
                try:
                    _oxf = XFormPrim(_obj_path)
                    _opos, _ = _oxf.get_world_pose()
                    if _opos is not None:
                        _oxf.set_world_pose(
                            position=np.array([float(_opos[0]), float(_opos[1]), 0.85], dtype=np.float32),
                            orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                        )
                except Exception:
                    pass
        except Exception as _re:
            print(f"[RoboLab] WARN: raycast placement failed: {_re}")

    # Post-warmup object position fix: ensure objects are on the table, not floating or on the floor.
    # Run multiple check-fix-settle cycles to handle objects that roll off.
    if _spawned_objects:
        _total_fixed = 0
        for _fix_round in range(3):
            _fixed_count = 0
            for _obj_path, _obj_class in _spawned_objects:
                try:
                    _oxf = XFormPrim(_obj_path)
                    _opos, _ = _oxf.get_world_pose()
                    if _opos is None:
                        continue
                    _oz = float(_opos[2])
                    if _oz < 0.5 or _oz > 1.2:
                        _zones = _get_spawn_zones()
                        _zone = _zones[0]
                        _cx = (_zone[0] + _zone[1]) / 2.0
                        _cy = (_zone[2] + _zone[3]) / 2.0
                        _oxf.set_world_pose(
                            position=np.array([_cx + _rng.uniform(-0.1, 0.1),
                                               _cy + _rng.uniform(-0.1, 0.1), 0.85],
                                              dtype=np.float32),
                            orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
                        _fixed_count += 1
                except Exception:
                    pass
            _total_fixed += _fixed_count
            if _fixed_count:
                for _ in range(80):
                    world.step(render=False)
            else:
                break
        if _total_fixed:
            print(f"[RoboLab] Fixed {_total_fixed} objects with bad Z over {_fix_round+1} rounds")

    if args.single_object and _spawned_objects:
        try:
            from omni.physx import get_physx_scene_query_interface
            _pq = get_physx_scene_query_interface()
            _sx, _sy = _get_single_object_xy()
            for _obj_path, _obj_class in _spawned_objects:
                _hit = _pq.raycast_closest((_sx, _sy, 2.5), (0.0, 0.0, -1.0), 3.0)
                _target_z = 0.85
                if _hit["hit"] and float(_hit["position"][2]) > 0.3:
                    _target_z = float(_hit["position"][2]) + 0.08
                _oxf = XFormPrim(_obj_path)
                _oxf.set_world_pose(
                    position=np.array([_sx, _sy, _target_z], dtype=np.float32),
                    orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
                )
            for _ in range(120):
                world.step(render=False)
            print(f"[RoboLab] Single-object reseat: reset {len(_spawned_objects)} object(s) to deterministic pose")
        except Exception as _single_reseat_err:
            print(f"[RoboLab] WARN: single-object reseat failed: {_single_reseat_err}")

    # Gripper startup diagnostic: verify the gripper responds to position commands.
    _diag_dof_names = resolve_dof_names(tiago_articulation) if tiago_articulation else []
    if tiago_articulation and _diag_dof_names:
        _gripper_test_joints = ["gripper_right_left_finger_joint", "gripper_right_right_finger_joint"]
        _gt_indices = []
        for _gtj in _gripper_test_joints:
            if _gtj in _diag_dof_names:
                _gt_indices.append(_diag_dof_names.index(_gtj))
        if _gt_indices:
            try:
                _get_jp = getattr(tiago_articulation, "get_joint_positions", None) or getattr(
                    tiago_articulation, "get_dof_positions", None)
                _before = [float(_as_list(_get_jp())[i]) for i in _gt_indices] if _get_jp else []
                _open_targets = list(_as_list(_get_jp()) if _get_jp else [0.0] * len(_diag_dof_names))
                for _gi in _gt_indices:
                    _open_targets[_gi] = 0.04
                tiago_articulation.apply_action(
                    ArticulationAction(joint_positions=np.array(_open_targets, dtype=np.float32)))
                for _ in range(60):
                    world.step(render=False)
                _after = [float(_as_list(_get_jp())[i]) for i in _gt_indices] if _get_jp else []
                if _before and _after:
                    _delta = max(abs(a - b) for a, b in zip(_before, _after))
                    print(f"[RoboLab] Gripper diagnostic: before={[round(v,4) for v in _before]} "
                          f"after={[round(v,4) for v in _after]} delta={_delta:.4f}")
                    if _delta < 0.005:
                        print("[RoboLab] WARNING: Gripper joints did not respond to open command! "
                              "Check USD drive stiffness or joint limits.")
                    else:
                        print("[RoboLab] Gripper responds to commands OK")
                _close_targets = list(_as_list(_get_jp()) if _get_jp else [0.0] * len(_diag_dof_names))
                for _gi in _gt_indices:
                    _close_targets[_gi] = 0.0
                tiago_articulation.apply_action(
                    ArticulationAction(joint_positions=np.array(_close_targets, dtype=np.float32)))
                for _ in range(30):
                    world.step(render=False)
            except Exception as _ge:
                print(f"[RoboLab] WARN: gripper diagnostic failed: {_ge}")
        else:
            print(f"[RoboLab] WARN: gripper joints {_gripper_test_joints} not in DOF list")

    # Contact sensors on gripper fingers for physical contact force measurement.
    _contact_sensor_left = None
    _contact_sensor_right = None
    _contact_sensor_interface = None
    _contact_sensor_left_reader = None
    _contact_sensor_right_reader = None
    _gripper_finger_left_path = None
    _gripper_finger_right_path = None
    if tiago_articulation:
        try:
            from pxr import PhysxSchema

            def _find_gripper_link(link_name):
                """Search for a gripper link prim across common Tiago USD structures."""
                _search_bases = [tiago_articulation_path, tiago_prim_path]
                for _base in _search_bases:
                    for _mid in _TIAGO_SEARCH_MIDS:
                        _path = _join_tiago_path(_base, _mid, link_name)
                        _pr = stage.GetPrimAtPath(_path)
                        if _pr.IsValid():
                            return _path, _pr
                for _p in stage.Traverse():
                    _pn = _p.GetPath().pathString
                    if _pn.startswith(tiago_prim_path) and _pn.endswith(f"/{link_name}"):
                        return _pn, _p
                return None, None

            _gripper_finger_left_path, _gfl_prim = _find_gripper_link("gripper_right_left_finger_link")
            _gripper_finger_right_path, _gfr_prim = _find_gripper_link("gripper_right_right_finger_link")

            if _gripper_finger_left_path:
                print(f"[RoboLab] Found right-arm left finger: {_gripper_finger_left_path}")
            if _gripper_finger_right_path:
                print(f"[RoboLab] Found right-arm right finger: {_gripper_finger_right_path}")

            if _gfl_prim is not None and _gfr_prim is not None:
                for _fp, _fn in [(_gripper_finger_left_path, "left_finger"), (_gripper_finger_right_path, "right_finger")]:
                    _fp_prim = stage.GetPrimAtPath(_fp)
                    if not _fp_prim.HasAPI(PhysxSchema.PhysxContactReportAPI):
                        PhysxSchema.PhysxContactReportAPI.Apply(_fp_prim)
                        PhysxSchema.PhysxContactReportAPI(_fp_prim).CreateThresholdAttr(0.0)
                    try:
                        _fcol = PhysxSchema.PhysxCollisionAPI.Apply(_fp_prim) if not _fp_prim.HasAPI(PhysxSchema.PhysxCollisionAPI) else PhysxSchema.PhysxCollisionAPI(_fp_prim)
                        _fcol.CreateContactOffsetAttr(0.003)
                        _fcol.CreateRestOffsetAttr(0.001)
                    except Exception:
                        pass

                _contact_sensor_left = f"{_gripper_finger_left_path}/Contact_Sensor"
                _contact_sensor_right = f"{_gripper_finger_right_path}/Contact_Sensor"

                from isaacsim.sensors.physics import _sensor, ContactSensor
                _contact_sensor_interface = _sensor.acquire_contact_sensor_interface()
                _contact_sensor_left_reader = ContactSensor(
                    prim_path=_contact_sensor_left,
                    name="RightFingerLeftContact",
                    frequency=60,
                    translation=np.array([0.0, 0.0, 0.0]),
                    min_threshold=0.0,
                    max_threshold=10000000.0,
                    radius=-1,
                )
                _contact_sensor_right_reader = ContactSensor(
                    prim_path=_contact_sensor_right,
                    name="RightFingerRightContact",
                    frequency=60,
                    translation=np.array([0.0, 0.0, 0.0]),
                    min_threshold=0.0,
                    max_threshold=10000000.0,
                    radius=-1,
                )

                print(f"[RoboLab] Contact sensors created on right-arm finger links: "
                      f"{_contact_sensor_left}, {_contact_sensor_right}")
            else:
                print("[RoboLab] WARN: right-arm finger links not found, contact sensors disabled")
        except Exception as err:
            print(f"[RoboLab] WARN: failed to create contact sensors: {err}")

    # Physics materials on gripper fingers for stable grasps (friction).
    if _gripper_finger_left_path and _gripper_finger_right_path:
        try:
            from pxr import UsdShade
            _grip_mat_path = "/World/Materials/GripperFrictionMaterial"
            _grip_mat_prim = stage.GetPrimAtPath(_grip_mat_path)
            if not _grip_mat_prim.IsValid():
                UsdShade.Material.Define(stage, _grip_mat_path)
                _grip_mat_prim = stage.GetPrimAtPath(_grip_mat_path)
            _phys_mat_api = UsdPhysics.MaterialAPI.Apply(_grip_mat_prim)
            _phys_mat_api.CreateStaticFrictionAttr(2.0)
            _phys_mat_api.CreateDynamicFrictionAttr(1.5)
            _phys_mat_api.CreateRestitutionAttr(0.0)
            _grip_mat = UsdShade.Material(_grip_mat_prim)
            for _finger_path in (_gripper_finger_left_path, _gripper_finger_right_path):
                _finger_prim = stage.GetPrimAtPath(_finger_path)
                if _finger_prim.IsValid():
                    UsdShade.MaterialBindingAPI.Apply(_finger_prim)
                    UsdShade.MaterialBindingAPI(_finger_prim).Bind(
                        _grip_mat, UsdShade.Tokens.weakerThanDescendants, "physics",
                    )
            print("[RoboLab] Applied friction physics material to gripper fingers "
                  "(staticFriction=1.0, dynamicFriction=0.8)")
        except Exception as _mat_err:
            print(f"[RoboLab] WARN: failed to apply gripper physics material: {_mat_err}")

    # Resolve DOF names from articulation (dof_names, dof_paths, or fallback).
    dof_names = []
    if tiago_articulation:
        dof_names = _as_list(getattr(tiago_articulation, "dof_names", None))
        if not dof_names:
            paths = _as_list(getattr(tiago_articulation, "dof_paths", None))
            dof_names = [str(p).split("/")[-1] if "/" in str(p) else str(p) for p in paths]
        if not dof_names:
            try:
                pos = tiago_articulation.get_joint_positions()
                if pos is None:
                    pos = tiago_articulation.get_dof_positions()
                if pos is not None:
                    dof_names = [f"joint_{i}" for i in range(len(pos))]
            except Exception:
                pass
    if not dof_names:
        dof_names = fallback_moveit_joint_names if args.moveit else fallback_joint_names

    def _build_moveit_joint_aliases(all_names: list[str]) -> dict:
        aliases = {}
        available = set(all_names)
        if "torso_lift_joint" in available:
            aliases["torso_lift_joint"] = "torso_lift_joint"
        for idx in range(1, 8):
            moveit_name = f"arm_{idx}_joint"
            for candidate in (f"arm_right_{idx}_joint", f"arm_left_{idx}_joint", moveit_name):
                if candidate in available:
                    aliases[moveit_name] = candidate
                    break
        for side in ("right", "left"):
            for finger in ("left_finger", "right_finger"):
                moveit_name = f"gripper_{side}_{finger}_joint"
                if moveit_name in available:
                    aliases[moveit_name] = moveit_name
        for hj in ("head_1_joint", "head_2_joint"):
            if hj in available:
                aliases[hj] = hj
        return aliases

    moveit_joint_aliases = _build_moveit_joint_aliases(dof_names)
    print(f"[RoboLab] DOF names ({len(dof_names)}): {dof_names[:20]}{'...' if len(dof_names) > 20 else ''}")
    print(f"[RoboLab] MoveIt joint aliases: {moveit_joint_aliases}")
    _arm_dofs = [n for n in dof_names if "arm" in n.lower()]
    print(f"[RoboLab] Arm DOFs found: {_arm_dofs}")
    if not moveit_joint_aliases:
        print("[RoboLab] WARNING: No MoveIt joint aliases resolved! Trajectories will NOT move the arm.")
    moveit_state_joint_names = fallback_moveit_joint_names + ["head_1_joint", "head_2_joint"]
    _default_joint_limits = {
        "torso_lift_joint": (0.0, 0.35),
        "arm_1_joint": (0.0, 2.68),
        "arm_2_joint": (-1.50, 1.02),
        "arm_3_joint": (-3.46, 1.57),
        "arm_4_joint": (-0.32, 2.27),
        "arm_5_joint": (-2.07, 2.07),
        "arm_6_joint": (-1.39, 1.39),
        "arm_7_joint": (-2.07, 2.07),
        "head_1_joint": (-1.4, 1.4),
        "head_2_joint": (-1.2, 0.9),
    }
    moveit_joint_limits = dict(_default_joint_limits)
    try:
        _limit_stage = stage_utils.get_current_stage()
        for _jp in _limit_stage.Traverse():
            if not _jp.GetPath().pathString.startswith(tiago_prim_path):
                continue
            _jname = _jp.GetName()
            _lo_attr = _jp.GetAttribute("physics:lowerLimit")
            _hi_attr = _jp.GetAttribute("physics:upperLimit")
            if _lo_attr and _lo_attr.Get() is not None and _hi_attr and _hi_attr.Get() is not None:
                _lo_val = float(_lo_attr.Get())
                _hi_val = float(_hi_attr.Get())
                if _jp.IsA(UsdPhysics.RevoluteJoint):
                    _lo_val = math.radians(_lo_val)
                    _hi_val = math.radians(_hi_val)
                _canonical = _jname
                if _jname.startswith("arm_right_"):
                    parts = _jname.split("_")
                    if len(parts) >= 3 and parts[2].isdigit():
                        _canonical = f"arm_{parts[2]}_joint"
                if _canonical in moveit_joint_limits:
                    _old = moveit_joint_limits[_canonical]
                    moveit_joint_limits[_canonical] = (max(_old[0], _lo_val), min(_old[1], _hi_val))
        _updated = {k: v for k, v in moveit_joint_limits.items() if v != _default_joint_limits.get(k)}
        if _updated:
            print(f"[RoboLab] Joint limits updated from USD: {_updated}")
    except Exception as _lim_exc:
        print(f"[RoboLab] WARN: Could not read USD joint limits: {_lim_exc}")
    print(f"[RoboLab] Joint limits: {moveit_joint_limits}")

    def _resolve_joint_name(name: str) -> str:
        if name in dof_names:
            return name
        return moveit_joint_aliases.get(name, name)

    def _normalize_joint_target(joint_name: str, value: float) -> float:
        if not math.isfinite(value):
            return 0.0
        canonical_name = joint_name
        if joint_name.startswith("arm_right_") or joint_name.startswith("arm_left_"):
            parts = joint_name.split("_")
            if len(parts) >= 3 and parts[2].isdigit():
                canonical_name = f"arm_{parts[2]}_joint"
        if canonical_name in moveit_joint_limits:
            lower, upper = moveit_joint_limits[canonical_name]
            return max(lower, min(upper, float(value)))
        wrapped = float(value)
        if wrapped > (2.0 * math.pi) or wrapped < (-2.0 * math.pi):
            wrapped = ((wrapped + math.pi) % (2.0 * math.pi)) - math.pi
        return wrapped

    # MoveIt bridge path: IPC with external ros2_fjt_proxy.py process via shared JSON files.
    # The proxy runs in conda Python (avoids DLL conflicts inside Isaac Sim).
    # Isaac Sim writes joint_state.json → proxy reads & publishes /joint_states.
    # Isaac Sim polls pending_{N}.json → executes trajectories via articulation.
    # Isaac Sim writes done_{N}.json → proxy returns FJT result to MoveGroup.
    FJT_PROXY_DIR = Path(os.environ.get("FJT_PROXY_DIR", r"C:\RoboLab_Data\fjt_proxy"))
    _proxy_ipc_enabled = args.moveit and FJT_PROXY_DIR.exists()
    if args.moveit:
        FJT_PROXY_DIR.mkdir(parents=True, exist_ok=True)
        _proxy_ipc_enabled = True
        print(f"[RoboLab] FJT proxy IPC dir: {FJT_PROXY_DIR}")

    # Keep the rclpy block for backwards compatibility / fallback, but don't depend on it.
    js_node = None
    js_pub = None
    js_msg_type = None
    ros_executor = None
    ros_executor_thread = None
    trajectory_servers = []
    latest_joint_snapshot = {}
    latest_joint_snapshot_lock = threading.Lock()
    trajectory_state_lock = threading.Lock()
    pending_trajectory_goals = deque()
    active_trajectory_goals = []
    rclpy_mod = None

    # IPC state for proxy communication.
    _seen_traj_ids: set = set()
    _ipc_write_counter = 0

    def _publish_joint_state_from_snapshot() -> None:
        if not (js_pub and js_node and js_msg_type):
            return
        with latest_joint_snapshot_lock:
            if not latest_joint_snapshot:
                return
            snapshot = {
                key: {"position": value["position"], "velocity": value["velocity"]}
                for key, value in latest_joint_snapshot.items()
            }
        try:
            js_msg = js_msg_type()
            # Use the wall-clock time explicitly so the timestamp is never 0.
            # rclpy on Windows with Isaac Sim may return time=0 from get_clock().now()
            # if no /clock topic is published, causing MoveGroup to reject joint states.
            _wall_ns = int(time.time() * 1_000_000_000)
            js_msg.header.stamp.sec = _wall_ns // 1_000_000_000
            js_msg.header.stamp.nanosec = _wall_ns % 1_000_000_000
            if args.moveit:
                js_msg.name = [j for j in moveit_state_joint_names if j in snapshot]
                if not js_msg.name:
                    js_msg.name = list(snapshot.keys())
            else:
                js_msg.name = list(snapshot.keys())
            js_msg.position = [_normalize_joint_target(n, float(snapshot[n]["position"])) for n in js_msg.name]
            js_msg.velocity = [float(snapshot[n]["velocity"]) for n in js_msg.name]
            js_pub.publish(js_msg)
        except Exception:
            pass

    # NOTE: In proxy IPC mode, rclpy is NOT imported inside Isaac Sim.
    # Importing rclpy inside Isaac Sim (bundled Python) causes a native DLL crash
    # on Windows due to version conflicts with conda ros2_humble DLLs.
    # The ros2_fjt_proxy.py process (running in conda Python) handles all ROS2 comms:
    #   - publishes /joint_states by reading joint_state.json from FJT_PROXY_DIR
    #   - hosts FJT action servers and writes pending_{N}.json for Isaac Sim
    # Isaac Sim reads pending trajectories and writes done_{N}.json.
    if args.moveit and not _proxy_ipc_enabled:
        # Legacy path (no proxy): attempt direct rclpy in Isaac Sim.
        # Only used when FJT_PROXY_DIR is not set. Likely to crash on Windows.
        try:
            import rclpy as rclpy_mod
            from sensor_msgs.msg import JointState
            from rclpy.executors import MultiThreadedExecutor

            if not rclpy_mod.ok():
                rclpy_mod.init(args=None)
            try:
                from rclpy.parameter import Parameter
                js_node = rclpy_mod.create_node(
                    "robolab_moveit_bridge",
                    parameter_overrides=[Parameter("use_sim_time", Parameter.Type.BOOL, False)],
                )
            except Exception:
                js_node = rclpy_mod.create_node("robolab_moveit_bridge")
            js_pub = js_node.create_publisher(JointState, "/joint_states", 10)
            js_msg_type = JointState
            js_node.create_timer(0.05, _publish_joint_state_from_snapshot)
            ros_executor = MultiThreadedExecutor(num_threads=4)
            ros_executor.add_node(js_node)
            ros_executor_thread = threading.Thread(target=ros_executor.spin, daemon=True)
            ros_executor_thread.start()
            print("[RoboLab] Direct /joint_states publisher enabled (MoveIt mode, legacy path).")
        except Exception as err:
            print(f"[RoboLab] WARN: direct /joint_states publisher unavailable: {err}")
    elif args.moveit and _proxy_ipc_enabled:
        print("[RoboLab] Proxy IPC mode: skipping rclpy inside Isaac Sim (ros2_fjt_proxy handles ROS2).")

    _apply_logged_once: set = set()

    def _apply_joint_positions(joint_values: dict) -> bool:
        """Apply joint targets via ArticulationAction (PD position drive).

        Only sets drive targets for joints in joint_values; other joints
        are left as NaN so Isaac Sim keeps their existing drive targets.
        This prevents re-setting all joint targets every frame, which
        was causing the gripper PD controller to fight itself.
        """
        if not tiago_articulation or not joint_values:
            return False
        try:
            from omni.isaac.core.utils.types import ArticulationAction
        except ImportError:
            pass
        try:
            n_dofs = len(dof_names)
            targets = [float('nan')] * n_dofs
            index_map = {n: i for i, n in enumerate(dof_names)}
            updated_any = False
            _resolved_joints = []
            _skipped_joints = []
            for name, value in joint_values.items():
                resolved_name = _resolve_joint_name(name)
                idx = index_map.get(resolved_name)
                if idx is None or idx >= n_dofs:
                    _skipped_joints.append(f"{name}->{resolved_name}")
                    continue
                normalized = _normalize_joint_target(resolved_name, float(value))
                targets[idx] = normalized
                updated_any = True
                _resolved_joints.append(f"{name}->{resolved_name}[{idx}]={normalized:.4f}")
            if _skipped_joints and "skipped" not in _apply_logged_once:
                _apply_logged_once.add("skipped")
                print(f"[RoboLab] WARN: joints skipped (not in DOF list): {_skipped_joints}")
            if _resolved_joints and "resolved" not in _apply_logged_once:
                _apply_logged_once.add("resolved")
                print(f"[RoboLab] Joint targets applied: {_resolved_joints}")
            if not updated_any:
                if "no_update" not in _apply_logged_once:
                    _apply_logged_once.add("no_update")
                    print(f"[RoboLab] WARN: _apply_joint_positions updated NO joints from {list(joint_values.keys())}")
                return False
            
            action = ArticulationAction(joint_positions=np.array(targets, dtype=np.float32))
            tiago_articulation.apply_action(action)
            return True
        except Exception as exc:
            print(f"[RoboLab] WARN: _apply_joint_positions failed: {exc}")
            return False

    _persistent_targets: dict = {
        "arm_left_1_joint": 0.20, "arm_left_2_joint": -0.35,
        "arm_left_3_joint": -0.20, "arm_left_4_joint": 1.90,
        "arm_left_5_joint": -1.57, "arm_left_6_joint": 1.20,
        "arm_left_7_joint": 0.0,
        "arm_right_1_joint": 0.20, "arm_right_2_joint": -0.35,
        "arm_right_3_joint": -0.20, "arm_right_4_joint": 1.90,
        "arm_right_5_joint": -1.57, "arm_right_6_joint": 1.20,
        "arm_right_7_joint": 0.0,
        "torso_lift_joint": 0.15,
        "head_1_joint": 0.0, "head_2_joint": 0.0,
        "gripper_right_left_finger_joint": 0.04,
        "gripper_right_right_finger_joint": 0.04,
        "gripper_left_left_finger_joint": 0.04,
        "gripper_left_right_finger_joint": 0.04,
    }

    def _process_trajectory_dispatcher() -> None:
        now = time.time()
        time_scale = max(1.0, float(args.trajectory_time_scale))
        with trajectory_state_lock:
            while pending_trajectory_goals:
                goal = pending_trajectory_goals.popleft()
                goal["start_wall"] = now
                goal["next_point_idx"] = 0
                goal["status"] = "running"
                active_trajectory_goals.append(goal)

            done_goals = []
            merged_targets = {}
            for goal in active_trajectory_goals:
                if goal.get("direct_set"):
                    _final_targets = None
                    if goal["points"]:
                        _final_targets = goal["points"][-1].get("targets")
                    if _final_targets:
                        merged_targets.update(_final_targets)
                        goal["status"] = "succeeded"
                        print(f"[RoboLab] direct_set goal -> PD targets only (no teleport)", flush=True)
                    else:
                        goal["status"] = "failed"
                        goal["error"] = "No targets in direct_set goal"
                    done_goals.append(goal)
                    continue
                points = goal["points"]
                next_idx = goal["next_point_idx"]
                start_wall = goal["start_wall"] or now
                elapsed_wall = now - start_wall

                # Advance next_idx to the first point whose scaled time
                # is still in the future, so we can interpolate.
                while next_idx < len(points) and (points[next_idx]["t"] / time_scale) <= elapsed_wall + 1e-4:
                    next_idx += 1

                # Linearly interpolate between the bracketing waypoints.
                latest_targets = None
                if next_idx >= len(points):
                    latest_targets = points[-1]["targets"]
                elif next_idx == 0:
                    latest_targets = points[0]["targets"]
                else:
                    prev_pt = points[next_idx - 1]
                    next_pt = points[next_idx]
                    t_prev = prev_pt["t"] / time_scale
                    t_next = next_pt["t"] / time_scale
                    dt = t_next - t_prev
                    alpha = (elapsed_wall - t_prev) / dt if dt > 1e-6 else 1.0
                    alpha = max(0.0, min(1.0, alpha))
                    latest_targets = {}
                    for jn in next_pt["targets"]:
                        v_prev = prev_pt["targets"].get(jn, next_pt["targets"][jn])
                        v_next = next_pt["targets"][jn]
                        latest_targets[jn] = v_prev + alpha * (v_next - v_prev)

                if latest_targets:
                    merged_targets.update(latest_targets)

                goal["next_point_idx"] = next_idx
                if next_idx >= len(points):
                    if not goal.get("_settle_start"):
                        goal["_settle_start"] = now
                        goal["_settle_targets"] = points[-1]["targets"] if points else {}
                    _settle_elapsed = now - goal["_settle_start"]
                    _settle_ok = False
                    _settle_timeout = 30.0
                    _max_arm_err = 0.0
                    if goal["_settle_targets"] and tiago_articulation:
                        try:
                            _cur_jp = tiago_articulation.get_joint_positions()
                            _idx_map = {n: i for i, n in enumerate(dof_names)}
                            for _sn, _sv in goal["_settle_targets"].items():
                                _rn = _resolve_joint_name(_sn)
                                _si = _idx_map.get(_rn)
                                if _si is not None and _si < len(_cur_jp) and "arm" in _sn.lower():
                                    _max_arm_err = max(_max_arm_err, abs(float(_cur_jp[_si]) - float(_sv)))
                            if _max_arm_err <= 0.05:
                                _settle_ok = True
                        except Exception:
                            pass
                    elif not goal["_settle_targets"]:
                        _settle_ok = True
                    if _settle_ok or _settle_elapsed >= _settle_timeout:
                        if _settle_ok:
                            print(f"[RoboLab] SETTLE converged goal={goal.get('traj_id','?')} max_arm_err={_max_arm_err:.4f} in {_settle_elapsed:.2f}s", flush=True)
                        elif _settle_elapsed >= _settle_timeout:
                            _per_joint_err = {}
                            try:
                                _cur_jp2 = tiago_articulation.get_joint_positions()
                                _idx_map2 = {n: i for i, n in enumerate(dof_names)}
                                for _sn2, _sv2 in goal["_settle_targets"].items():
                                    _rn2 = _resolve_joint_name(_sn2)
                                    _si2 = _idx_map2.get(_rn2)
                                    if _si2 is not None and _si2 < len(_cur_jp2):
                                        _per_joint_err[_sn2] = round(float(_cur_jp2[_si2]) - float(_sv2), 4)
                            except Exception:
                                pass
                            print(f"[RoboLab] SETTLE timeout goal={goal.get('traj_id','?')} max_arm_err={_max_arm_err:.4f}, per-joint: {_per_joint_err}", flush=True)
                        if _settle_ok or _max_arm_err <= 0.30:
                            goal["status"] = "succeeded"
                        else:
                            goal["status"] = "failed"
                            goal["error"] = f"Settle timeout: max_arm_err={_max_arm_err:.4f} exceeds 0.30 rad"
                            print(f"[RoboLab] SETTLE FAILED goal={goal.get('traj_id','?')} — arm error too large for success", flush=True)
                        done_goals.append(goal)

            if merged_targets:
                _persistent_targets.update(merged_targets)
                for _mk, _mv in merged_targets.items():
                    _resolved = _resolve_joint_name(_mk)
                    if _resolved != _mk and _resolved in _persistent_targets:
                        _persistent_targets[_resolved] = _mv
                _arm_merged = {k: round(v, 4) for k, v in merged_targets.items()
                               if "arm" in k and "left" not in k and "gripper" not in k}
                if _arm_merged:
                    _arm_persist = {k: round(v, 4) for k, v in _persistent_targets.items()
                                    if ("arm_right" in k or (k.startswith("arm_") and k[4].isdigit()))
                                    and "left" not in k and "gripper" not in k}
                    print(f"[RoboLab] TRAJ_ARM merged={_arm_merged} persist={_arm_persist}", flush=True)

            if _persistent_targets:
                ok = _apply_joint_positions(_persistent_targets)
                if not ok and "apply_fail" not in _apply_logged_once:
                    _apply_logged_once.add("apply_fail")
                    print(f"[RoboLab] WARN: _apply_joint_positions returned False for persistent targets!")
                if not ok and merged_targets:
                    for goal in active_trajectory_goals:
                        if goal not in done_goals:
                            goal["status"] = "failed"
                            goal["error"] = "Failed to apply articulation joint targets"
                            done_goals.append(goal)

            if active_trajectory_goals and tiago_articulation and not hasattr(_process_trajectory_dispatcher, '_vel_diag_ctr'):
                _process_trajectory_dispatcher._vel_diag_ctr = 0
            if active_trajectory_goals and tiago_articulation:
                _process_trajectory_dispatcher._vel_diag_ctr = getattr(_process_trajectory_dispatcher, '_vel_diag_ctr', 0) + 1
                if _process_trajectory_dispatcher._vel_diag_ctr % 30 == 0:
                    try:
                        _vels = tiago_articulation.get_joint_velocities()
                        _poss = tiago_articulation.get_joint_positions()
                        _arm_idx = {n: i for i, n in enumerate(dof_names) if "arm_right" in n}
                        _vel_items = []
                        for _an, _ai in sorted(_arm_idx.items()):
                            _tgt = _persistent_targets.get(_an, _persistent_targets.get(_an.replace("arm_right_", "arm_"), float('nan')))
                            _vel_items.append(f"{_an}:p={float(_poss[_ai]):.3f} t={float(_tgt):.3f} v={float(_vels[_ai]):.3f}")
                        print(f"[RoboLab] VEL_DIAG " + " | ".join(_vel_items), flush=True)
                    except Exception:
                        pass

            for goal in done_goals:
                if goal in active_trajectory_goals:
                    active_trajectory_goals.remove(goal)
                if goal.get("status") == "succeeded" and tiago_articulation:
                    try:
                        _cur_pos = tiago_articulation.get_joint_positions()
                        _final_tgt = goal["points"][-1]["targets"] if goal.get("points") else {}
                        _diag_lines = []
                        for _jn, _tv in _final_tgt.items():
                            _rn = _resolve_joint_name(_jn)
                            _idx = {n: i for i, n in enumerate(dof_names)}.get(_rn)
                            if _idx is not None and _idx < len(_cur_pos):
                                _actual = float(_cur_pos[_idx])
                                _err = abs(_actual - float(_tv))
                                if "arm" in _jn.lower() or "torso" in _jn.lower():
                                    _diag_lines.append(f"{_jn}->{_rn}[{_idx}] tgt={float(_tv):.4f} act={_actual:.4f} err={_err:.4f}")
                        if _diag_lines:
                            print(f"[RoboLab] TRAJ_DIAG goal={goal.get('traj_id','?')} " + " | ".join(_diag_lines), flush=True)
                    except Exception:
                        pass
                goal["done_event"].set()

    def _abort_all_trajectory_goals(reason: str) -> None:
        with trajectory_state_lock:
            to_abort = list(active_trajectory_goals) + list(pending_trajectory_goals)
            active_trajectory_goals.clear()
            pending_trajectory_goals.clear()
            for goal in to_abort:
                goal["status"] = "failed"
                goal["error"] = reason
                goal["done_event"].set()

    # FJT action servers inside Isaac Sim are only needed for the legacy (non-proxy) path.
    # In proxy IPC mode, ros2_fjt_proxy.py hosts the FJT servers externally.
    if args.moveit and tiago_articulation and js_node and not _proxy_ipc_enabled:
        try:
            from control_msgs.action import FollowJointTrajectory
            from rclpy.action import ActionServer
            from rclpy.action import GoalResponse, CancelResponse

            def _goal_cb(_goal_request):
                return GoalResponse.ACCEPT

            def _cancel_cb(_goal_handle):
                return CancelResponse.ACCEPT

            def _make_execute_cb(controller_name: str):
                def _execute_cb(goal_handle):
                    req = goal_handle.request
                    traj = req.trajectory
                    result = FollowJointTrajectory.Result()
                    if traj is None or not traj.points:
                        result.error_code = FollowJointTrajectory.Result.INVALID_GOAL
                        result.error_string = "Empty trajectory"
                        goal_handle.abort()
                        return result
                    joint_names_local = list(traj.joint_names)
                    index_map_local = {n: i for i, n in enumerate(dof_names)}
                    missing = [j for j in joint_names_local if _resolve_joint_name(j) not in index_map_local]
                    if missing:
                        result.error_code = FollowJointTrajectory.Result.INVALID_JOINTS
                        result.error_string = f"Unknown joints for articulation: {missing}"
                        goal_handle.abort()
                        return result

                    parsed_points = []
                    for point in traj.points:
                        point_positions = list(point.positions)
                        if len(point_positions) != len(joint_names_local):
                            continue
                        target_values = {name: point_positions[i] for i, name in enumerate(joint_names_local)}
                        t = float(point.time_from_start.sec) + float(point.time_from_start.nanosec) * 1e-9
                        parsed_points.append({"t": t, "targets": target_values})
                    if not parsed_points:
                        result.error_code = FollowJointTrajectory.Result.INVALID_GOAL
                        result.error_string = "Trajectory has no valid points"
                        goal_handle.abort()
                        return result

                    goal_state = {
                        "controller_name": controller_name,
                        "goal_handle": goal_handle,
                        "points": parsed_points,
                        "start_wall": None,
                        "next_point_idx": 0,
                        "status": "pending",
                        "error": "",
                        "done_event": threading.Event(),
                    }
                    with trajectory_state_lock:
                        pending_trajectory_goals.append(goal_state)

                    wait_started = time.time()
                    max_wait = max(30.0, float(args.duration) + 5.0)
                    while not goal_state["done_event"].wait(timeout=0.05):
                        if (time.time() - wait_started) > max_wait:
                            goal_state["status"] = "failed"
                            goal_state["error"] = "Trajectory execution timed out in dispatcher"
                            goal_state["done_event"].set()
                            break

                    t_end = time.time() - start_time
                    if goal_state["status"] == "succeeded":
                        result.error_code = FollowJointTrajectory.Result.SUCCESSFUL
                        result.error_string = ""
                        goal_handle.succeed()
                        print(f"[RoboLab] {controller_name} trajectory executed ({len(parsed_points)} pts, "
                              f"t_start={goal_state['start_wall'] - start_time:.2f}s t_end={t_end:.2f}s)")
                        dataset["joint_trajectories_executed"].append({
                            "controller": controller_name,
                            "joint_names": joint_names_local,
                            "num_points": len(parsed_points),
                            "t_start": goal_state["start_wall"] - start_time if goal_state["start_wall"] else t_end,
                            "t_end": t_end,
                            "status": "succeeded",
                        })
                        return result

                    result.error_code = FollowJointTrajectory.Result.PATH_TOLERANCE_VIOLATED
                    result.error_string = goal_state.get("error", "Trajectory execution failed")
                    goal_handle.abort()
                    dataset["joint_trajectories_executed"].append({
                        "controller": controller_name,
                        "joint_names": joint_names_local,
                        "num_points": len(parsed_points),
                        "t_end": t_end,
                        "status": "failed",
                        "error": result.error_string,
                    })
                    return result

                return _execute_cb

            trajectory_servers.append(
                ActionServer(
                    js_node,
                    FollowJointTrajectory,
                    "/arm_controller/follow_joint_trajectory",
                    execute_callback=_make_execute_cb("arm_controller"),
                    goal_callback=_goal_cb,
                    cancel_callback=_cancel_cb,
                )
            )
            trajectory_servers.append(
                ActionServer(
                    js_node,
                    FollowJointTrajectory,
                    "/torso_controller/follow_joint_trajectory",
                    execute_callback=_make_execute_cb("torso_controller"),
                    goal_callback=_goal_cb,
                    cancel_callback=_cancel_cb,
                )
            )
            print("[RoboLab] Direct FollowJointTrajectory servers enabled for arm/torso controllers.")
        except Exception as err:
            print(f"[RoboLab] WARN: could not start direct trajectory action servers: {err}")

    # Fallback only: add OmniGraph joint_states publisher when direct rclpy publisher is unavailable.
    # Skip in proxy IPC mode — proxy reads joint_state.json written by Isaac Sim.
    if args.moveit and tiago_articulation and not js_pub and not _proxy_ipc_enabled:
        try:
            import omni.graph.core as og

            # Node types vary by Isaac Sim version: isaacsim.ros2.bridge vs omni.isaac.ros2_bridge
            publish_node_type = "isaacsim.ros2.bridge.ROS2PublishJointState"
            try:
                og.Controller.edit(
                    {"graph_path": "/ActionGraph", "evaluator_name": "execution"},
                    {
                        og.Controller.Keys.CREATE_NODES: [
                            ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
                            ("PublishJointState", publish_node_type),
                            ("ReadSimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
                        ],
                        og.Controller.Keys.CONNECT: [
                            ("OnPlaybackTick.outputs:tick", "PublishJointState.inputs:execIn"),
                            ("ReadSimTime.outputs:simulationTime", "PublishJointState.inputs:timeStamp"),
                        ],
                        og.Controller.Keys.SET_VALUES: [
                            ("PublishJointState.inputs:targetPrim", tiago_articulation_path),
                        ],
                    },
                )
                print("[RoboLab] ROS2 joint_states publisher added via OmniGraph (MoveIt mode).")
            except Exception:
                publish_node_type = "omni.isaac.ros2_bridge.ROS2PublishJointState"
                og.Controller.edit(
                    {"graph_path": "/ActionGraph", "evaluator_name": "execution"},
                    {
                        og.Controller.Keys.CREATE_NODES: [
                            ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
                            ("PublishJointState", publish_node_type),
                            ("ReadSimTime", "omni.isaac.core_nodes.IsaacReadSimulationTime"),
                        ],
                        og.Controller.Keys.CONNECT: [
                            ("OnPlaybackTick.outputs:tick", "PublishJointState.inputs:execIn"),
                            ("ReadSimTime.outputs:simulationTime", "PublishJointState.inputs:timeStamp"),
                        ],
                        og.Controller.Keys.SET_VALUES: [
                            ("PublishJointState.inputs:targetPrim", tiago_articulation_path),
                        ],
                    },
                )
                print("[RoboLab] ROS2 joint_states publisher added via OmniGraph (MoveIt mode).")
        except Exception as err:
            print(f"[RoboLab] WARN: Could not add ROS2 joint_states publisher: {err}")
            print("[RoboLab] For MoveIt, enable joint_states in Isaac Sim: Tools > Robotics > ROS 2 OmniGraphs > JointStates.")

    _spawned_classes = sorted({str(cls).lower() for _, cls in _spawned_objects})

    def _class_to_category(name: str) -> str:
        _n = name.lower()
        if any(tok in _n for tok in ("mug", "cup", "glass")):
            return "mug_or_cup"
        if any(tok in _n for tok in ("bottle", "can", "jar", "carton")):
            return "bottle_or_container"
        if any(tok in _n for tok in ("apple", "banana", "orange", "fruit")):
            return "fruit"
        if any(tok in _n for tok in ("box", "container", "bowl", "plate", "dish")):
            return "container_or_dish"
        return "other"

    _category_counts = {}
    for _c in _spawned_classes:
        _cat = _class_to_category(_c)
        _category_counts[_cat] = _category_counts.get(_cat, 0) + 1

    dataset = {
        "metadata": {
            "robot": "tiago_omni_or_tiago_plus_plus",
            "environment_usd": env_usd,
            "tiago_usd": tiago_usd,
            "duration_sec": args.duration,
            "map_frame": "map",
            "ros2_topics": [
                "/joint_states",
                "/tf",
                "/tf_static",
                "/points",
                "/gt/object_poses",
            ],
            "sensors": ["rgb", "distance_to_camera", "pointcloud", "semantic_segmentation"],
            "replicator_subsample": _rep_subsample,
            "joint_source": "articulation_api" if tiago_articulation else "synthetic_fallback",
            "vr_teleop_enabled": bool(args.vr),
            "moveit_mode_enabled": bool(args.moveit),
            "robot_pov_camera_prim": camera_parent_prim,
            "cameras": {
                "camera_0": {"type": "head", "dir": "replicator_data", "video": "camera_0.mp4"},
                **({"camera_1_wrist": {"type": "wrist", "parent_link": "arm_tool_link", "dir": "replicator_wrist", "video": "camera_1_wrist.mp4"}} if _wrist_camera else {}),
                **({"camera_2_external": {"type": "external", "position": list(tuple(float(x) for x in args.external_camera_pos.split(","))), "dir": "replicator_external", "video": "camera_2_external.mp4"}} if _external_camera else {}),
            },
            "n_cameras": _n_cameras,
            "task_label": args.task_label if args.task_label else "unlabeled",
            "spawned_object_count": len(_spawned_objects),
            "spawned_object_classes": _spawned_classes,
            "spawned_object_category_counts": _category_counts,
        },
        "frames": [],
        # Per-frame joint states (positions + velocities) — continuous 20 Hz log.
        "joint_trajectories": [],
        # Each FJT trajectory execution event (start/end timestamps, joints, status).
        "joint_trajectories_executed": [],
    }

    telemetry_data = []
    _sim_frame_idx = 0
    start_time = time.time()

    # Grasp monitoring state.
    _grasp_events = []
    _prev_gripper_gap = None
    _prev_gripper_closing = False
    _gripped_object_path = None
    _gripped_object_class = None
    _grip_start_frame = -1
    _lift_start_z = None
    _grip_candidate_path = None
    _grip_candidate_class = None
    _grip_candidate_frames = 0
    _grip_release_frames = 0
    _GRIP_CONFIRM_FRAMES = 6
    _GRIP_RELEASE_FRAMES = 5
    _close_cycle_active = False

    _GRIPPER_JOINT_NAMES = (
        "gripper_right_left_finger_joint", "gripper_right_right_finger_joint",
    )
    _GRIPPER_GAP_EMPTY = 0.035
    _GRIPPER_GAP_GRASPED = 0.030
    _OBJECT_IN_GRIPPER_RADIUS = 0.15
    _OBJECT_IN_GRIPPER_CONFIRM_RADIUS = 0.08

    _graspable_prim_paths = [p for p, _ in _spawned_objects]
    _graspable_prim_classes = {p: c for p, c in _spawned_objects}

    _gripper_center_paths = [None, None]  # [left_finger, right_finger] or [tool_link, None]
    _tool_link_prim_path = None

    def _resolve_tool_link_path():
        _candidates = [
            f"{tiago_articulation_path}/arm_right_tool_link",
            f"{tiago_articulation_path}/arm_tool_link",
            f"{tiago_articulation_path}/arm_right_7_link",
            f"{tiago_articulation_path}/arm_7_link",
            f"{tiago_prim_path}/tiago_dual_functional_light/arm_right_tool_link",
            f"{tiago_prim_path}/tiago_dual_functional_light/arm_tool_link",
            f"{tiago_prim_path}/tiago_dual_functional_light/arm_right_7_link",
            f"{tiago_prim_path}/tiago_dual_functional/arm_right_tool_link",
            f"{tiago_prim_path}/tiago_dual_functional/arm_tool_link",
            f"{tiago_prim_path}/tiago_dual_functional/arm_right_7_link",
            f"{tiago_prim_path}/arm_right_tool_link",
            f"{tiago_prim_path}/arm_tool_link",
            f"{tiago_prim_path}/arm_right_7_link",
        ]
        for _cl in _candidates:
            try:
                if stage.GetPrimAtPath(_cl).IsValid():
                    return _cl
            except Exception:
                continue
        try:
            for _p in stage.Traverse():
                _pn = _p.GetPath().pathString
                if not _pn.startswith(tiago_prim_path):
                    continue
                _low = _pn.lower()
                if "left" in _low:
                    continue
                if "tool_link" in _low or _low.endswith("/arm_right_7_link") or _low.endswith("/arm_7_link"):
                    return _pn
        except Exception:
            pass
        return None

    def _init_gripper_center_paths():
        """Find gripper link paths for computing gripper center."""
        if _gripper_finger_left_path and _gripper_finger_right_path:
            _gripper_center_paths[0] = _gripper_finger_left_path
            _gripper_center_paths[1] = _gripper_finger_right_path
            print(f"[RoboLab] Gripper center: midpoint of right-arm finger links")
            return

        _candidates = [
            _resolve_tool_link_path(),
            f"{tiago_prim_path}/tiago_dual_functional_light/arm_7_link",
            f"{tiago_prim_path}/tiago_dual_functional/arm_7_link",
            f"{tiago_prim_path}/arm_7_link",
        ]
        for _cl in _candidates:
            try:
                if _cl and stage.GetPrimAtPath(_cl).IsValid():
                    _gripper_center_paths[0] = _cl
                    print(f"[RoboLab] Gripper center: single link {_cl}")
                    return
            except Exception:
                continue

        try:
            for _p in stage.Traverse():
                _pn = _p.GetPath().pathString
                if not _pn.startswith(tiago_prim_path):
                    continue
                if "arm" in _pn and ("tool_link" in _pn or "7_link" in _pn):
                    if "left" not in _pn.lower():
                        _gripper_center_paths[0] = _pn
                        print(f"[RoboLab] Gripper center: single link (search) {_pn}")
                        return
        except Exception:
            pass
        print("[RoboLab] WARNING: Could not find gripper center link")

    _init_gripper_center_paths()
    _tool_link_prim_path = _resolve_tool_link_path()
    if _tool_link_prim_path:
        print(f"[RoboLab] Tool link prim: {_tool_link_prim_path}")
    else:
        print("[RoboLab] WARN: tool link prim path not resolved")

    _physx_fk_fn = [None]
    _physx_tool_link_idx = [None]
    _physx_sim_view = [None]

    def _init_physx_fk():
        """Initialize PhysX tensor API for direct FK queries."""
        if _physx_tool_link_idx[0] is not None:
            return True
        try:
            from isaacsim.core.simulation_manager import SimulationManager

            sv = SimulationManager.get_physics_sim_view()
            if sv is None:
                print("[RoboLab] PhysX FK init: simulation view unavailable", flush=True)
                return False
            _physx_sim_view[0] = sv
            av = getattr(tiago_articulation, "_articulation_view", None)
            if av is None:
                print("[RoboLab] PhysX FK init: articulation view unavailable", flush=True)
                return False
            pv = getattr(av, "_physics_view", None)
            if pv is None:
                print("[RoboLab] PhysX FK init: articulation tensor physics view unavailable", flush=True)
                return False

            body_names = []
            try:
                body_names = list(getattr(av, "body_names", []) or [])
            except Exception:
                body_names = []
            if not body_names:
                try:
                    body_names = list(getattr(av, "link_names", []) or [])
                except Exception:
                    body_names = []
            if not body_names:
                try:
                    _meta = getattr(pv, "shared_metatype", None)
                    body_names = list(getattr(_meta, "link_names", []) or [])
                except Exception:
                    body_names = []

            tool_name = _tool_link_prim_path.rsplit("/", 1)[-1] if _tool_link_prim_path else "arm_right_tool_link"
            for i, bn in enumerate(body_names):
                if bn == tool_name:
                    _physx_tool_link_idx[0] = i
                    print(
                        f"[RoboLab] PhysX FK init: tool_link='{tool_name}' idx={i} total_links={len(body_names)}",
                        flush=True,
                    )
                    return True

            finger_l_name = _gripper_finger_left_path.rsplit("/", 1)[-1] if _gripper_finger_left_path else None
            finger_r_name = _gripper_finger_right_path.rsplit("/", 1)[-1] if _gripper_finger_right_path else None
            for i, bn in enumerate(body_names):
                if bn == finger_l_name or bn == finger_r_name:
                    _physx_tool_link_idx[0] = i
                    print(f"[RoboLab] PhysX FK init: using finger '{bn}' idx={i}", flush=True)
                    return True

            print(f"[RoboLab] PhysX FK init FAILED: tool link not found. body_names={body_names}", flush=True)
        except Exception as e:
            print(f"[RoboLab] PhysX FK init error: {e}", flush=True)
        return False

    def _physx_get_tool_pos():
        """Get tool link world position directly from PhysX tensor API."""
        if _physx_tool_link_idx[0] is None:
            return None
        try:
            av = getattr(tiago_articulation, "_articulation_view", None)
            pv = getattr(av, "_physics_view", None) if av is not None else None
            if pv is None:
                return None
            transforms = pv.get_link_transforms()
            _t_raw = transforms.numpy() if hasattr(transforms, "numpy") else np.asarray(transforms)
            t = np.asarray(_t_raw, dtype=np.float64).reshape(pv.count, pv.max_links, 7)
            pos = t[0, _physx_tool_link_idx[0], :3]
            return np.array(pos, dtype=np.float64)
        except Exception as e:
            print(f"[RoboLab] PhysX FK read error: {e}", flush=True)
            return None

    _physx_fk_fn[0] = _physx_get_tool_pos

    def _sim_fk_teleport(q_array, n_steps=6):
        """Teleport robot to joint config, update kinematics, return tool world pos.
        q_array: 8-element array [torso, arm1..arm7].
        Uses PhysX tensor API for ground-truth FK (no USD/Fabric staleness)."""
        full_pos = np.array(tiago_articulation.get_joint_positions(), dtype=np.float64)
        for i, idx in enumerate(_ik_all_indices):
            full_pos[idx] = float(q_array[i])
        tiago_articulation.set_joint_positions(full_pos.astype(np.float32))
        zero_vel = np.zeros(len(dof_names), dtype=np.float32)
        tiago_articulation.set_joint_velocities(zero_vel)
        try:
            if _physx_sim_view[0] is not None:
                _physx_sim_view[0].update_articulations_kinematic()
            else:
                pass # DO NOT call world.step() here, it mutates physics time iteratively and drifts!
        except Exception:
            pass
        
        # We disabled world.step() here because multiple IK perturbations advanced time significantly.
        # Ensure we always retrieve the freshest tensor values.
        result = _physx_get_tool_pos()
        
        # _sim_fk_teleport MUTATES joint state. Callers (_validate_physx_fk,
        # _solve_ik_sim) must save/restore the original state after use.
        zero_vel = np.zeros(len(dof_names), dtype=np.float32)
        tiago_articulation.set_joint_velocities(zero_vel)
        return result

    def _get_prim_world_pos_fabric(prim_path):
        """Read world position of a prim from Fabric (physics-updated transforms)."""
        try:
            from isaacsim.core.utils.xforms import get_world_pose as _xf_get_world_pose
            pos, _ = _xf_get_world_pose(prim_path, fabric=True)
            if pos is not None:
                return np.array([float(pos[0]), float(pos[1]), float(pos[2])], dtype=np.float64)
        except Exception:
            pass
        try:
            _xf = XFormPrim(prim_path)
            _p, _ = _xf.get_world_pose()
            if _p is not None:
                return np.array([float(_p[0]), float(_p[1]), float(_p[2])], dtype=np.float64)
        except Exception:
            pass
        return None

    def _get_sim_tool_world_pos():
        if _physx_fk_fn[0] is not None:
            p = _physx_fk_fn[0]()
            if p is not None:
                return p
        try:
            if _gripper_finger_left_path and _gripper_finger_right_path:
                _pl = _get_prim_world_pos_fabric(_gripper_finger_left_path)
                _pr = _get_prim_world_pos_fabric(_gripper_finger_right_path)
                if _pl is not None and _pr is not None:
                    return (_pl + _pr) * 0.5
        except Exception:
            pass
        try:
            if _tool_link_prim_path:
                return _get_prim_world_pos_fabric(_tool_link_prim_path)
        except Exception:
            pass
        return None

    # --- Native IK solver using analytical FK from USD kinematic chain ---
    _ik_arm_joint_names = [f"arm_right_{i}_joint" for i in range(1, 8)]
    _ik_all_names = ["torso_lift_joint"] + _ik_arm_joint_names
    _ik_all_indices = []
    for _jn in _ik_all_names:
        if _jn in dof_names:
            _ik_all_indices.append(dof_names.index(_jn))
        else:
            print(f"[RoboLab] IK WARNING: joint {_jn} not found in DOF list")
    _ik_moveit_names = ["torso_lift_joint"] + [f"arm_{i}_joint" for i in range(1, 8)]
    _ik_limits_lo = np.array([moveit_joint_limits.get(n, (-3.14, 3.14))[0] for n in _ik_moveit_names])
    _ik_limits_hi = np.array([moveit_joint_limits.get(n, (-3.14, 3.14))[1] for n in _ik_moveit_names])

    def _validate_physx_fk():
        """Quick sanity-check that tensor FK reacts to joint perturbations."""
        if not tiago_articulation or len(_ik_all_indices) != 8:
            print("[RoboLab] PhysX FK validation skipped: articulation not ready", flush=True)
            return False
        if not _init_physx_fk():
            print("[RoboLab] PhysX FK validation skipped: init failed", flush=True)
            return False

        saved_pos = np.array(tiago_articulation.get_joint_positions(), dtype=np.float64).copy()
        saved_vel = np.array(tiago_articulation.get_joint_velocities(), dtype=np.float64).copy()
        base_q = saved_pos[_ik_all_indices].copy()
        probes = [(0, 0.05), (1, 0.05), (2, 0.05), (4, 0.05), (7, 0.05)]
        moved = False
        try:
            base_pos = _sim_fk_teleport(base_q, n_steps=1)
            if base_pos is None:
                print("[RoboLab] PhysX FK validation failed: no base tool pose", flush=True)
                return False

            for joint_idx, delta in probes:
                probe_q = base_q.copy()
                probe_q[joint_idx] = np.clip(probe_q[joint_idx] + delta, _ik_limits_lo[joint_idx], _ik_limits_hi[joint_idx])
                probe_pos = _sim_fk_teleport(probe_q, n_steps=1)
                actual_pos = np.array(tiago_articulation.get_joint_positions(), dtype=np.float64)[_ik_all_indices]
                if probe_pos is None:
                    print(f"[RoboLab] PhysX FK validation joint[{joint_idx}] -> no pose", flush=True)
                    continue
                delta_pos = probe_pos - base_pos
                delta_norm = float(np.linalg.norm(delta_pos))
                max_q_err = float(np.max(np.abs(actual_pos - probe_q)))
                print(
                    f"[RoboLab] PhysX FK validation joint[{joint_idx}] dq={delta:.3f} "
                    f"dpos=({delta_pos[0]:.5f},{delta_pos[1]:.5f},{delta_pos[2]:.5f}) "
                    f"norm={delta_norm:.5f} q_err={max_q_err:.5f}",
                    flush=True,
                )
                if delta_norm > 1e-4:
                    moved = True
        finally:
            try:
                tiago_articulation.set_joint_positions(saved_pos.astype(np.float32))
                tiago_articulation.set_joint_velocities(saved_vel.astype(np.float32))
                if _physx_sim_view[0] is not None:
                    _physx_sim_view[0].update_articulations_kinematic()
                else:
                    world.step(render=False)
                # Re-apply PD targets so drives track the correct positions
                # after the teleport restore.
                _apply_joint_positions(_persistent_targets)
            except Exception as _restore_err:
                print(f"[RoboLab] PhysX FK validation restore failed: {_restore_err}", flush=True)

        print(f"[RoboLab] PhysX FK validation result: moved={moved}", flush=True)
        return moved

    def _quat_to_mat(w, x, y, z):
        """Quaternion (w,x,y,z) to 3x3 rotation matrix."""
        return np.array([
            [1 - 2*(y*y + z*z), 2*(x*y - w*z), 2*(x*z + w*y)],
            [2*(x*y + w*z), 1 - 2*(x*x + z*z), 2*(y*z - w*x)],
            [2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y)],
        ])

    def _rotx(angle):
        """Rotation matrix around X axis."""
        c, s = np.cos(angle), np.sin(angle)
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])

    def _make_T(R, t):
        """Build 4x4 homogeneous transform from 3x3 rotation and 3-vector."""
        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = t
        return T

    def _joint_frame_T(localPos0, localRot0, localPos1, localRot1):
        """Compute the fixed part of a joint transform:
        T = T(parent->joint_frame0) @ inv(T(child->joint_frame1))
        In PhysX: the joint connects body0 and body1, the joint frame is
        defined by localPos0/Rot0 in body0's frame and localPos1/Rot1 in body1's frame.
        The child body's origin in parent frame = parent->jf0 @ inv(child->jf1).
        """
        R0 = _quat_to_mat(*localRot0)
        R1 = _quat_to_mat(*localRot1)
        T0 = _make_T(R0, np.array(localPos0))
        T1 = _make_T(R1, np.array(localPos1))
        T1_inv = np.eye(4)
        T1_inv[:3, :3] = R1.T
        T1_inv[:3, 3] = -R1.T @ np.array(localPos1)
        return T0 @ T1_inv

    def _vec3_tuple(_value, _default=(0.0, 0.0, 0.0)):
        if _value is None:
            return _default
        try:
            return (float(_value[0]), float(_value[1]), float(_value[2]))
        except Exception:
            return _default

    def _quat_wxyz(_value, _default=(1.0, 0.0, 0.0, 0.0)):
        if _value is None:
            return _default
        try:
            _imag = _value.GetImaginary()
            return (
                float(_value.GetReal()),
                float(_imag[0]),
                float(_imag[1]),
                float(_imag[2]),
            )
        except Exception:
            try:
                return (float(_value[0]), float(_value[1]), float(_value[2]), float(_value[3]))
            except Exception:
                return _default

    _fallback_joint_frames = {
        "torso_fixed_joint": {
            "localPos0": (-0.062, 0.0, 0.216),
            "localRot0": (0.70710677, 0.0, 0.70710677, 0.0),
            "localPos1": (0.0, 0.0, 0.0),
            "localRot1": (0.70710677, 0.0, 0.70710677, 0.0),
            "axis": "X",
        },
        "torso_lift_joint": {
            "localPos0": (0.0, 0.0, 0.597),
            "localRot0": (0.70710677, 0.0, -0.70710677, 0.0),
            "localPos1": (0.0, 0.0, 0.0),
            "localRot1": (0.70710677, 0.0, -0.70710677, 0.0),
            "axis": "X",
        },
        "arm_right_1_joint": {
            "localPos0": (0.02556, -0.19, -0.171),
            "localRot0": (0.49999997, -0.49999997, -0.49999997, -0.49999997),
            "localPos1": (0.0, 0.0, 0.0),
            "localRot1": (0.70710677, 0.0, -0.70710677, 0.0),
            "axis": "X",
        },
        "arm_right_2_joint": {
            "localPos0": (0.125, -0.0195, -0.031),
            "localRot0": (0.49999997, -0.49999997, -0.49999997, 0.49999997),
            "localPos1": (0.0, 0.0, 0.0),
            "localRot1": (0.70710677, 0.0, -0.70710677, 0.0),
            "axis": "X",
        },
        "arm_right_3_joint": {
            "localPos0": (0.0895, 0.0, -0.0015),
            "localRot0": (0.0, 0.0, -0.7071067, 0.7071067),
            "localPos1": (0.0, 0.0, 0.0),
            "localRot1": (0.70710677, 0.0, -0.70710677, 0.0),
            "axis": "X",
        },
        "arm_right_4_joint": {
            "localPos0": (-0.02, -0.027, -0.222),
            "localRot0": (0.0, -0.7071067, -0.7071067, 0.0),
            "localPos1": (0.0, 0.0, 0.0),
            "localRot1": (0.70710677, 0.0, -0.70710677, 0.0),
            "axis": "X",
        },
        "arm_right_5_joint": {
            "localPos0": (-0.162, 0.02, 0.027),
            "localRot0": (0.0, 0.0, -0.9999999, 0.0),
            "localPos1": (0.0, 0.0, 0.0),
            "localRot1": (0.70710677, 0.0, -0.70710677, 0.0),
            "axis": "X",
        },
        "arm_right_6_joint": {
            "localPos0": (0.0, 0.0, 0.15),
            "localRot0": (0.0, -0.7071067, -0.7071067, 0.0),
            "localPos1": (0.0, 0.0, 0.0),
            "localRot1": (0.70710677, 0.0, -0.70710677, 0.0),
            "axis": "X",
        },
        "arm_right_7_joint": {
            "localPos0": (0.0, 0.0, 0.0),
            "localRot0": (0.7071067, 0.7071067, 0.0, 0.0),
            "localPos1": (0.0, 0.0, 0.0),
            "localRot1": (0.70710677, 0.0, -0.70710677, 0.0),
            "axis": "X",
        },
        "arm_right_tool_joint": {
            "localPos0": (0.0, 0.0, 0.0573),
            "localRot0": (-0.5, 0.49999994, 0.5, 0.49999994),
            "localPos1": (0.0, 0.0, 0.0),
            "localRot1": (1.0, 0.0, 0.0, 0.0),
            "axis": "X",
        },
    }

    def _extract_runtime_joint_frames():
        _joint_frames = {k: dict(v) for k, v in _fallback_joint_frames.items()}
        _target_names = set(_joint_frames.keys()) | {"arm_tool_joint"}
        try:
            for _jp in stage.Traverse():
                _jname = _jp.GetName()
                if _jname not in _target_names:
                    continue
                if not _jp.GetPath().pathString.startswith(tiago_prim_path):
                    continue
                _joint_frames[_jname] = {
                    "localPos0": _vec3_tuple(_jp.GetAttribute("physics:localPos0").Get(), _joint_frames.get(_jname, {}).get("localPos0", (0.0, 0.0, 0.0))),
                    "localRot0": _quat_wxyz(_jp.GetAttribute("physics:localRot0").Get(), _joint_frames.get(_jname, {}).get("localRot0", (1.0, 0.0, 0.0, 0.0))),
                    "localPos1": _vec3_tuple(_jp.GetAttribute("physics:localPos1").Get(), _joint_frames.get(_jname, {}).get("localPos1", (0.0, 0.0, 0.0))),
                    "localRot1": _quat_wxyz(_jp.GetAttribute("physics:localRot1").Get(), _joint_frames.get(_jname, {}).get("localRot1", (1.0, 0.0, 0.0, 0.0))),
                    "axis": str(_jp.GetAttribute("physics:axis").Get() or _joint_frames.get(_jname, {}).get("axis", "X")).upper(),
                }
            if "arm_tool_joint" in _joint_frames and "arm_right_tool_joint" not in _joint_frames:
                _joint_frames["arm_right_tool_joint"] = dict(_joint_frames["arm_tool_joint"])
        except Exception:
            pass
        return _joint_frames

    _runtime_joint_frames = _extract_runtime_joint_frames()

    def _generate_urdf_from_usd():
        """Generate a URDF file from the USD joint frames that matches the physics model.
        Converts PhysX localPos0/Rot0/localPos1/Rot1 to URDF <origin xyz rpy>."""
        import math as _m

        _chain = [
            ("base_footprint", "base_link", "base_footprint_joint", "fixed", None),
            ("base_link", "torso_lift_link", "torso_lift_joint", "prismatic", (0.0, 0.35)),
            ("torso_lift_link", "arm_right_1_link", "arm_right_1_joint", "revolute", (0.0, 2.68)),
            ("arm_right_1_link", "arm_right_2_link", "arm_right_2_joint", "revolute", (-1.50, 1.02)),
            ("arm_right_2_link", "arm_right_3_link", "arm_right_3_joint", "revolute", (-3.46, 1.57)),
            ("arm_right_3_link", "arm_right_4_link", "arm_right_4_joint", "revolute", (-0.32, 2.27)),
            ("arm_right_4_link", "arm_right_5_link", "arm_right_5_joint", "revolute", (-2.07, 2.07)),
            ("arm_right_5_link", "arm_right_6_link", "arm_right_6_joint", "revolute", (-1.39, 1.39)),
            ("arm_right_6_link", "arm_right_7_link", "arm_right_7_joint", "revolute", (-2.07, 2.07)),
            ("arm_right_7_link", "arm_right_tool_link", "arm_right_tool_joint", "fixed", None),
        ]

        def _rot_to_rpy(R):
            sy = _m.sqrt(R[0, 0]**2 + R[1, 0]**2)
            singular = sy < 1e-6
            if not singular:
                x = _m.atan2(R[2, 1], R[2, 2])
                y = _m.atan2(-R[2, 0], sy)
                z = _m.atan2(R[1, 0], R[0, 0])
            else:
                x = _m.atan2(-R[1, 2], R[1, 1])
                y = _m.atan2(-R[2, 0], sy)
                z = 0.0
            return (x, y, z)

        _jf_map = {
            "base_footprint_joint": {
                "localPos0": (0.0, 0.0, 0.0762),
                "localRot0": (1.0, 0.0, 0.0, 0.0),
                "localPos1": (0.0, 0.0, 0.0),
                "localRot1": (1.0, 0.0, 0.0, 0.0),
                "axis": "Z",
            },
        }
        _jf_map["torso_lift_joint"] = _runtime_joint_frames.get("torso_lift_joint", _fallback_joint_frames["torso_lift_joint"])
        _torso_fixed = _runtime_joint_frames.get("torso_fixed_joint", _fallback_joint_frames["torso_fixed_joint"])
        _tf_T = _joint_frame_T(
            _torso_fixed["localPos0"], _torso_fixed["localRot0"],
            _torso_fixed["localPos1"], _torso_fixed["localRot1"],
        )
        _tl = _runtime_joint_frames.get("torso_lift_joint", _fallback_joint_frames["torso_lift_joint"])
        _tl_T = _make_T(_quat_to_mat(*_tl["localRot0"]), np.array(_tl["localPos0"]))
        _combined_torso = _tf_T @ _tl_T
        _torso_xyz = _combined_torso[:3, 3]
        _torso_rpy = _rot_to_rpy(_combined_torso[:3, :3])
        _torso_axis = _tl.get("axis", "X").upper()

        lines = ['<?xml version="1.0"?>', '<robot name="tiago_right_arm">']
        all_links = set()
        for parent, child, jname, jtype, limits in _chain:
            all_links.add(parent)
            all_links.add(child)
        for lname in sorted(all_links):
            lines.append(f'  <link name="{lname}"/>')

        for parent, child, jname, jtype, limits in _chain:
            if jname == "base_footprint_joint":
                lines.append(f'  <joint name="{jname}" type="fixed">')
                lines.append(f'    <parent link="{parent}"/>')
                lines.append(f'    <child link="{child}"/>')
                lines.append(f'    <origin xyz="0 0 0.0762" rpy="0 0 0"/>')
                lines.append(f'  </joint>')
                continue

            if jname == "torso_lift_joint":
                _ax_str = "0 0 1" if _torso_axis == "Z" else ("0 1 0" if _torso_axis == "Y" else "1 0 0")
                lines.append(f'  <joint name="{jname}" type="{jtype}">')
                lines.append(f'    <parent link="{parent}"/>')
                lines.append(f'    <child link="{child}"/>')
                lines.append(f'    <origin xyz="{_torso_xyz[0]:.6f} {_torso_xyz[1]:.6f} {_torso_xyz[2]:.6f}" '
                             f'rpy="{_torso_rpy[0]:.6f} {_torso_rpy[1]:.6f} {_torso_rpy[2]:.6f}"/>')
                lines.append(f'    <axis xyz="{_ax_str}"/>')
                if limits:
                    lines.append(f'    <limit lower="{limits[0]}" upper="{limits[1]}" effort="2000" velocity="0.07"/>')
                lines.append(f'  </joint>')
                continue

            jf = _runtime_joint_frames.get(jname, _fallback_joint_frames.get(jname))
            if jf is None:
                continue

            T = _joint_frame_T(jf["localPos0"], jf["localRot0"], jf["localPos1"], jf["localRot1"])
            xyz = T[:3, 3]
            rpy = _rot_to_rpy(T[:3, :3])
            axis = jf.get("axis", "X").upper()
            _ax_str = "0 0 1" if axis == "Z" else ("0 1 0" if axis == "Y" else "1 0 0")

            lines.append(f'  <joint name="{jname}" type="{jtype}">')
            lines.append(f'    <parent link="{parent}"/>')
            lines.append(f'    <child link="{child}"/>')
            lines.append(f'    <origin xyz="{xyz[0]:.6f} {xyz[1]:.6f} {xyz[2]:.6f}" '
                         f'rpy="{rpy[0]:.6f} {rpy[1]:.6f} {rpy[2]:.6f}"/>')
            if jtype != "fixed":
                lines.append(f'    <axis xyz="{_ax_str}"/>')
                if limits:
                    lines.append(f'    <limit lower="{limits[0]}" upper="{limits[1]}" effort="50" velocity="2.0"/>')
            lines.append(f'  </joint>')

        lines.append('</robot>')
        urdf_text = "\n".join(lines)

        _urdf_path = Path(__file__).resolve().parent.parent / "config" / "tiago_right_arm.urdf"
        _urdf_path.write_text(urdf_text, encoding="utf-8")
        print(f"[RoboLab] Generated URDF from USD joint frames: {_urdf_path}", flush=True)
        return _urdf_path

    _generated_urdf_path = None
    try:
        from nvidia.srl.from_usd.to_urdf import UsdToUrdf as _UsdToUrdf
        _urdf_out = Path(__file__).resolve().parent.parent / "config" / "tiago_right_arm.urdf"
        _tiago_root_name = tiago_prim_path.rsplit("/", 1)[-1] if "/" in tiago_prim_path else "tiago_dual_functional"
        _usd_to_urdf = _UsdToUrdf(
            stage,
            root=_tiago_root_name,
            log_level="ERROR",
        )
        _usd_to_urdf.save_to_file(
            urdf_output_path=str(_urdf_out),
            quiet=True,
        )
        _generated_urdf_path = _urdf_out
        print(f"[RoboLab] Exported URDF from USD stage: {_urdf_out}", flush=True)
    except Exception as _urdf_exp_err:
        print(f"[RoboLab] USD->URDF export failed: {_urdf_exp_err}", flush=True)
        _generated_urdf_path = _generate_urdf_from_usd()

    def _axis_rot_T(axis_name: str, angle: float):
        _axis = (axis_name or "X").upper()
        if _axis == "Y":
            c = math.cos(angle)
            s = math.sin(angle)
            return _make_T(np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=np.float64), np.zeros(3))
        if _axis == "Z":
            c = math.cos(angle)
            s = math.sin(angle)
            return _make_T(np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64), np.zeros(3))
        return _make_T(_rotx(angle), np.zeros(3))

    def _axis_translate_T(axis_name: str, distance: float):
        _axis = (axis_name or "X").upper()
        _t = np.zeros(3, dtype=np.float64)
        if _axis == "Y":
            _t[1] = distance
        elif _axis == "Z":
            _t[2] = distance
        else:
            _t[0] = distance
        return _make_T(np.eye(3), _t)

    _fk_tip_local_offset = np.zeros(3, dtype=np.float64)

    _fk_robot_root_pos = np.array([_robot_start_x, 0.0, 0.0], dtype=np.float64)
    _fk_robot_root_quat = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64)  # w,x,y,z

    def _quat_to_rotmat(q):
        """Convert quaternion [w,x,y,z] to 3x3 rotation matrix."""
        w, x, y, z = q
        return np.array([
            [1 - 2*(y*y + z*z), 2*(x*y - w*z),     2*(x*z + w*y)],
            [2*(x*y + w*z),     1 - 2*(x*x + z*z), 2*(y*z - w*x)],
            [2*(x*z - w*y),     2*(y*z + w*x),     1 - 2*(x*x + y*y)],
        ], dtype=np.float64)

    def _update_fk_robot_root():
        """Refresh FK root from actual robot world pose (full orientation)."""
        try:
            _rxf = XFormPrim(prim_path=tiago_prim_path)
            _rp, _ro = _rxf.get_world_pose()
            _fk_robot_root_pos[0] = float(_rp[0])
            _fk_robot_root_pos[1] = float(_rp[1])
            _fk_robot_root_pos[2] = float(_rp[2])
            _fk_robot_root_quat[0] = float(_ro[0])
            _fk_robot_root_quat[1] = float(_ro[1])
            _fk_robot_root_quat[2] = float(_ro[2])
            _fk_robot_root_quat[3] = float(_ro[3])
        except Exception:
            pass

    def _fk_tool_transform(q):
        """Compute analytical tool-frame world transform from joint angles.
        Uses full quaternion orientation of the robot root."""
        _root_rot = _quat_to_rotmat(_fk_robot_root_quat)
        T = _make_T(_root_rot, _fk_robot_root_pos)

        # base_link: translate (0, 0, 0.0762), identity rotation
        T = T @ _make_T(np.eye(3), np.array([0.0, 0.0, 0.0762]))

        # torso_fixed_joint (fixed)
        _torso_fixed = _runtime_joint_frames["torso_fixed_joint"]
        T = T @ _joint_frame_T(
            _torso_fixed["localPos0"], _torso_fixed["localRot0"],
            _torso_fixed["localPos1"], _torso_fixed["localRot1"],
        )

        _torso_lift = _runtime_joint_frames["torso_lift_joint"]
        T = T @ _make_T(_quat_to_mat(*_torso_lift["localRot0"]), np.array(_torso_lift["localPos0"], dtype=np.float64))
        T = T @ _axis_translate_T(_torso_lift.get("axis", "X"), q[0])
        T = T @ _make_T(
            _quat_to_mat(*_torso_lift["localRot1"]).T,
            -_quat_to_mat(*_torso_lift["localRot1"]).T @ np.array(_torso_lift["localPos1"], dtype=np.float64),
        )

        for j in range(7):
            _joint_data = _runtime_joint_frames[f"arm_right_{j + 1}_joint"]
            T_jf0 = _make_T(
                _quat_to_mat(*_joint_data["localRot0"]),
                np.array(_joint_data["localPos0"], dtype=np.float64),
            )
            T_motion = _axis_rot_T(_joint_data.get("axis", "X"), q[1 + j])
            _R1 = _quat_to_mat(*_joint_data["localRot1"])
            T_jf1_inv = _make_T(
                _R1.T,
                -_R1.T @ np.array(_joint_data["localPos1"], dtype=np.float64),
            )
            T = T @ T_jf0 @ T_motion @ T_jf1_inv

        # arm_right_tool_joint (fixed)
        _tool_joint = _runtime_joint_frames["arm_right_tool_joint"]
        T = T @ _joint_frame_T(
            _tool_joint["localPos0"], _tool_joint["localRot0"],
            _tool_joint["localPos1"], _tool_joint["localRot1"],
        )

        return T

    def _fk_tool_pos(q):
        """Compute grasp-point world position from joint angles.
        q = [torso_lift, arm1..arm7] (8 values).
        Returns 3D world position of the calibrated grasp point.
        """
        T = _fk_tool_transform(q)
        if np.linalg.norm(_fk_tip_local_offset) > 1e-9:
            T = T @ _make_T(np.eye(3), _fk_tip_local_offset)
        return T[:3, 3]

    _sim_ik_ready = False
    _sim_ik_validation_error = None

    _update_fk_robot_root()

    try:
        if tiago_articulation and len(_ik_all_indices) == 8:
            _cur_q = np.array(tiago_articulation.get_joint_positions(), dtype=np.float64)
            _ik_seed = _cur_q[_ik_all_indices]
            _sim_tip_pos = _get_sim_tool_world_pos()
            if _sim_tip_pos is not None:
                _analytic_tool_T = _fk_tool_transform(_ik_seed)
                _sim_tip_h = np.ones(4, dtype=np.float64)
                _sim_tip_h[:3] = _sim_tip_pos
                _local_tip = np.linalg.inv(_analytic_tool_T) @ _sim_tip_h
                _fk_tip_local_offset = _local_tip[:3]
                print(
                    f"[RoboLab] FK tip local offset="
                    f"({_fk_tip_local_offset[0]:.4f},{_fk_tip_local_offset[1]:.4f},{_fk_tip_local_offset[2]:.4f})",
                    flush=True,
                )
    except Exception:
        pass

    # Validate FK against actual sim position at startup
    if tiago_articulation and len(_ik_all_indices) == 8:
        _cur_q = np.array(tiago_articulation.get_joint_positions(), dtype=np.float64)
        _ik_seed = _cur_q[_ik_all_indices]
        _fk_pos = _fk_tool_pos(_ik_seed)
        _sim_pos = _get_sim_tool_world_pos()
        if _sim_pos is not None:
            _err = np.linalg.norm(_fk_pos - _sim_pos)
            print(f"[RoboLab] FK validation: analytic=({_fk_pos[0]:.4f},{_fk_pos[1]:.4f},{_fk_pos[2]:.4f}) "
                  f"sim=({_sim_pos[0]:.4f},{_sim_pos[1]:.4f},{_sim_pos[2]:.4f}) err={_err:.4f}m", flush=True)
            _sim_ik_validation_error = float(_err)
            _sim_ik_ready = _err < 0.15
            if not _sim_ik_ready:
                print(f"[RoboLab] IK disabled: FK validation error too large ({_err:.4f}m)", flush=True)

    # --- Lula IK solver initialization ---
    _lula_ik_solver = None
    _lula_art_ik = None
    _lula_ik_ready = False

    try:
        from isaacsim.robot_motion.motion_generation import (
            LulaKinematicsSolver,
            ArticulationKinematicsSolver,
        )
        _lula_config_dir = Path(__file__).resolve().parent.parent / "config"
        _default_desc_path = _lula_config_dir / "tiago_right_arm_descriptor.yaml"
        _default_urdf_path = _lula_config_dir / "tiago_right_arm.urdf"
        _pal_desc_env = os.environ.get("TIAGO_PAL_DESCRIPTOR_PATH", "").strip()
        _pal_urdf_env = os.environ.get("TIAGO_PAL_URDF_PATH", "").strip()
        _pal_desc_local = _lula_config_dir / "tiago_pal_right_arm_descriptor.yaml"
        _pal_urdf_local = _lula_config_dir / "tiago_pal_right_arm.urdf"
        _lula_desc_path = Path(_pal_desc_env) if _pal_desc_env else (_pal_desc_local if _pal_desc_local.exists() else _default_desc_path)
        _lula_urdf_path = Path(_pal_urdf_env) if _pal_urdf_env else (_pal_urdf_local if _pal_urdf_local.exists() else _default_urdf_path)

        if _lula_desc_path.exists() and _lula_urdf_path.exists() and tiago_articulation:
            _lula_ik_solver = LulaKinematicsSolver(
                robot_description_path=str(_lula_desc_path),
                urdf_path=str(_lula_urdf_path),
            )
            _lula_art_ik = ArticulationKinematicsSolver(
                tiago_articulation,
                _lula_ik_solver,
                "arm_right_tool_link",
            )
            _lula_ik_ready = True
            print(
                f"[RoboLab] Lula IK solver initialized successfully "
                f"(descriptor={_lula_desc_path.name}, urdf={_lula_urdf_path.name})",
                flush=True,
            )
        else:
            _missing = []
            if not _lula_desc_path.exists():
                _missing.append(str(_lula_desc_path))
            if not _lula_urdf_path.exists():
                _missing.append(str(_lula_urdf_path))
            print(f"[RoboLab] Lula IK: missing files: {_missing}", flush=True)
    except ImportError as _lula_imp_err:
        print(f"[RoboLab] Lula IK import failed (expected in non-Isaac env): {_lula_imp_err}", flush=True)
    except Exception as _lula_init_err:
        print(f"[RoboLab] Lula IK init failed: {_lula_init_err}", flush=True)

    _physx_fk_valid = _validate_physx_fk()

    def _lula_fk(q_array):
        """Compute FK using Lula solver (reads URDF kinematics, not physics).
        q_array is [torso, arm1..arm7] (8 values). Returns world position."""
        if not _lula_ik_ready or _lula_ik_solver is None:
            return None
        try:
            _robot_xf = XFormPrim(prim_path=tiago_prim_path)
            _rp, _ro = _robot_xf.get_world_pose()
            _lula_ik_solver.set_robot_base_pose(
                robot_position=_rp, robot_orientation=_ro,
            )
            pos, rot = _lula_ik_solver.compute_forward_kinematics(
                "arm_right_tool_link",
                np.array(q_array, dtype=np.float64),
            )
            return np.array(pos, dtype=np.float64).flatten()
        except Exception as e:
            print(f"[RoboLab] _lula_fk error: {e}", flush=True)
            return None

    def _solve_ik_sim(target_world_pos, seed_joints=None, max_iter=200, tol=0.005):
        """Sim-based Jacobian IK: uses the physics engine as the FK oracle.
        Teleports the robot to candidate joint configs, steps physics, reads
        the actual tool position. Slower but guaranteed to match the simulation.
        Returns dict with 'success', 'joints' (MoveIt names), 'error_m'."""
        if not tiago_articulation or len(_ik_all_indices) != 8:
            return {"success": False, "error": "articulation not ready"}
        if not _physx_fk_valid:
            return {"success": False, "error": "physx tensor FK validation failed"}

        saved_pos = np.array(tiago_articulation.get_joint_positions(), dtype=np.float64).copy()
        cur_ik_q = saved_pos[_ik_all_indices].copy()

        ik_q = cur_ik_q.copy()
        if seed_joints:
            _name_to_idx = {}
            for i, mname in enumerate(_ik_moveit_names):
                _name_to_idx[mname] = i
                _name_to_idx[_ik_all_names[i]] = i
            for name, val in seed_joints.items():
                idx = _name_to_idx.get(name)
                if idx is not None:
                    ik_q[idx] = float(val)
        ik_q = np.clip(ik_q, _ik_limits_lo, _ik_limits_hi)

        target = np.array(target_world_pos, dtype=np.float64)

        cur_pos = _sim_fk_teleport(ik_q)
        if cur_pos is None:
            _sim_fk_teleport(cur_ik_q, n_steps=10)
            return {"success": False, "error": "sim FK query failed"}

        best_q = ik_q.copy()
        best_err = float(np.linalg.norm(target - cur_pos))
        best_pos = cur_pos.copy()
        print(f"[RoboLab] SimIK start: err={best_err:.4f}m target=({target[0]:.3f},{target[1]:.3f},{target[2]:.3f})", flush=True)

        delta = 0.05
        stall_count = 0
        n_iters = min(max_iter, 60)

        for iteration in range(n_iters):
            err_vec = target - cur_pos
            err_norm = float(np.linalg.norm(err_vec))
            if err_norm < tol:
                break

            base_pos = _sim_fk_teleport(ik_q, n_steps=8)
            if base_pos is None:
                break
            cur_pos = base_pos

            J = np.zeros((3, 8))
            for col in range(8):
                pq = ik_q.copy()
                actual_delta = delta
                if pq[col] + delta > _ik_limits_hi[col]:
                    actual_delta = -delta
                pq[col] += actual_delta
                pq = np.clip(pq, _ik_limits_lo, _ik_limits_hi)
                pp = _sim_fk_teleport(pq, n_steps=8)
                if pp is not None:
                    diff = pp - base_pos
                    J[:, col] = diff / actual_delta
                    if iteration == 0 and col < 3:
                        print(f"[RoboLab] SimIK J[{col}]: delta={actual_delta:.4f} "
                              f"base=({base_pos[0]:.4f},{base_pos[1]:.4f},{base_pos[2]:.4f}) "
                              f"pert=({pp[0]:.4f},{pp[1]:.4f},{pp[2]:.4f}) "
                              f"diff=({diff[0]:.6f},{diff[1]:.6f},{diff[2]:.6f})", flush=True)

            jn = np.linalg.norm(J)
            if jn < 1e-8:
                print(f"[RoboLab] SimIK iter {iteration}: Jacobian near zero (norm={jn:.2e}), stopping", flush=True)
                break

            lam = 0.01
            dq = J.T @ np.linalg.solve(J @ J.T + lam * np.eye(3), err_vec)
            step = float(np.max(np.abs(dq)))
            max_step = 0.15
            if step > max_step:
                dq *= max_step / step

            new_q = np.clip(ik_q + dq, _ik_limits_lo, _ik_limits_hi)
            new_pos = _sim_fk_teleport(new_q)
            if new_pos is None:
                break
            new_err = float(np.linalg.norm(target - new_pos))

            if new_err < best_err - 1e-5:
                best_err = new_err
                best_q = new_q.copy()
                best_pos = new_pos.copy()
                ik_q = new_q
                cur_pos = new_pos
                stall_count = 0
                if iteration % 5 == 0:
                    print(f"[RoboLab] SimIK iter {iteration}: err={new_err:.4f}m", flush=True)
            else:
                stall_count += 1
                _sim_fk_teleport(ik_q, n_steps=4)
                cur_pos_refresh = _get_sim_tool_world_pos()
                if cur_pos_refresh is not None:
                    cur_pos = cur_pos_refresh
                if stall_count >= 3:
                    break

        result_joints = {}
        for i, mn in enumerate(_ik_moveit_names):
            result_joints[mn] = round(float(best_q[i]), 4)

        _sim_fk_teleport(best_q, n_steps=10)
        _final_pos = _get_sim_tool_world_pos()
        _sim_err = float(np.linalg.norm(target - _final_pos)) if _final_pos is not None else 999.0

        _actual_str = f"actual=({_final_pos[0]:.3f},{_final_pos[1]:.3f},{_final_pos[2]:.3f})" if _final_pos is not None else "actual=unknown"
        print(f"[RoboLab] SimIK solved: sim_err={_sim_err:.4f}m "
              f"target=({target[0]:.3f},{target[1]:.3f},{target[2]:.3f}) {_actual_str}", flush=True)
        print(f"[RoboLab] SimIK joints: {result_joints}", flush=True)

        # CRITICAL: restore robot to pre-IK state so IK query doesn't
        # teleport the robot as a side effect.
        try:
            tiago_articulation.set_joint_positions(saved_pos.astype(np.float32))
            saved_vel = np.zeros(len(dof_names), dtype=np.float32)
            tiago_articulation.set_joint_velocities(saved_vel)
            if _physx_sim_view[0] is not None:
                _physx_sim_view[0].update_articulations_kinematic()
            else:
                world.step(render=False)
            # Re-apply persistent PD targets so drives continue from where they were.
            _apply_joint_positions(_persistent_targets)
            print(f"[RoboLab] SimIK: restored pre-IK joint state", flush=True)
        except Exception as _restore_err:
            print(f"[RoboLab] WARN: SimIK restore failed: {_restore_err}", flush=True)

        return {
            "success": _sim_err < 0.05,
            "joints": result_joints,
            "error_m": round(_sim_err, 4),
        }

    def _get_gripper_center():
        """Return approximate gripper center position."""
        if _gripper_center_paths[0] is None:
            return None
        try:
            if _gripper_center_paths[1] is not None:
                _pl = _get_prim_world_pos_fabric(_gripper_center_paths[0])
                _pr = _get_prim_world_pos_fabric(_gripper_center_paths[1])
                if _pl is not None and _pr is not None:
                    return [float((_pl[i] + _pr[i]) / 2.0) for i in range(3)]
            else:
                _pos = _get_prim_world_pos_fabric(_gripper_center_paths[0])
                return _pos.tolist() if _pos is not None else None
        except Exception:
            pass
        return None

    def _get_object_bounds_world(prim_path):
        """Return approximate world-space bounds center and size for a prim."""
        try:
            _prim = stage.GetPrimAtPath(prim_path)
            if not _prim.IsValid():
                return None, None
            _bbox_cache = UsdGeom.BBoxCache(
                Usd.TimeCode.Default(),
                includedPurposes=[UsdGeom.Tokens.default_],
                useExtentsHint=True,
            )
            _bbox = _bbox_cache.ComputeWorldBound(_prim)
            _abox = _bbox.ComputeAlignedBox()
            _mn = _abox.GetMin()
            _mx = _abox.GetMax()
            _center = [float((_mn[i] + _mx[i]) * 0.5) for i in range(3)]
            _size = [max(0.0, float(_mx[i] - _mn[i])) for i in range(3)]
            if not all(math.isfinite(_v) for _v in (_center + _size)):
                return None, None
            return _center, _size
        except Exception:
            return None, None

    def _compute_grasp_target_world(
        obj_world,
        obj_class,
        robot_yaw: float = 0.0,
        obj_center_world=None,
        obj_bounds_size=None,
    ):
        """Return a geometry-aware grasp anchor with class-offset fallback."""
        _anchor = obj_center_world if obj_center_world and len(obj_center_world) == 3 else obj_world
        if not _anchor or len(_anchor) != 3:
            return None

        _cls = str(obj_class or "").lower()
        _sx = float(obj_bounds_size[0]) if obj_bounds_size and len(obj_bounds_size) == 3 else 0.0
        _sy = float(obj_bounds_size[1]) if obj_bounds_size and len(obj_bounds_size) == 3 else 0.0
        _sz = float(obj_bounds_size[2]) if obj_bounds_size and len(obj_bounds_size) == 3 else 0.0

        def _clamp_mag(val: float, lo: float, hi: float) -> float:
            return max(lo, min(hi, val))

        _off_x = 0.0
        _off_y = 0.0
        _off_z = 0.0
        if any(_token in _cls for _token in ("mug", "cup", "can", "box", "carton")):
            _off_x = -_clamp_mag((_sx * 0.40) + 0.03, 0.05, 0.12)
            _off_y = _clamp_mag((_sy * 0.10) + 0.005, 0.005, 0.02)
            _off_z = _clamp_mag((_sz * 0.25) + 0.02, 0.04, 0.08)
        elif any(_token in _cls for _token in ("bottle", "juice", "milk")):
            _off_x = -_clamp_mag((_sx * 0.45) + 0.05, 0.07, 0.14)
            _off_y = _clamp_mag((_sy * 0.12) + 0.01, 0.01, 0.025)
            _off_z = _clamp_mag((_sz * 0.55) + 0.05, 0.11, 0.18)
        elif any(_token in _cls for _token in ("fruit", "apple", "orange", "banana", "pear", "lemon", "peach")):
            _off_x = -_clamp_mag((_sx * 0.30) + 0.03, 0.04, 0.10)
            _off_y = _clamp_mag((_sy * 0.08) + 0.005, 0.005, 0.02)
            _off_z = _clamp_mag((_sz * 0.35) + 0.02, 0.05, 0.10)
        elif abs(_sx) > 1e-4 or abs(_sz) > 1e-4:
            _off_x = -_clamp_mag((_sx * 0.40) + 0.03, 0.04, 0.10)
            _off_z = _clamp_mag((_sz * 0.35) + 0.02, 0.04, 0.10)

        if abs(_off_x) < 1e-6 and abs(_off_y) < 1e-6 and abs(_off_z) < 1e-6:
            return [float(v) for v in _anchor]

        _wx = _off_x * math.cos(robot_yaw) - _off_y * math.sin(robot_yaw)
        _wy = _off_x * math.sin(robot_yaw) + _off_y * math.cos(robot_yaw)
        return [
            float(_anchor[0]) + float(_wx),
            float(_anchor[1]) + float(_wy),
            float(_anchor[2]) + float(_off_z),
        ]

    _grip_debug_counter = [0]

    def _find_object_in_gripper(grip_center, gap):
        """Check if any graspable object center is within gripper reach."""
        if grip_center is None or gap > _GRIPPER_GAP_GRASPED:
            return None, None, None
        gx, gy, gz = grip_center
        best_dist = _OBJECT_IN_GRIPPER_RADIUS
        best_path = None
        _grip_debug_counter[0] += 1
        _do_log = (_grip_debug_counter[0] % 30 == 1)
        for _gp in _graspable_prim_paths:
            try:
                _xf = XFormPrim(_gp)
                _op, _ = _xf.get_world_pose()
                if _op is None:
                    continue
                ox, oy, oz = float(_op[0]), float(_op[1]), float(_op[2])
                dist = ((gx - ox)**2 + (gy - oy)**2 + (gz - oz)**2)**0.5
                if _do_log:
                    _cls = _graspable_prim_classes.get(_gp, "?")
                    print(f"[RoboLab] grip_center=({gx:.3f},{gy:.3f},{gz:.3f}) "
                          f"obj={_cls}@({ox:.3f},{oy:.3f},{oz:.3f}) dist={dist:.3f} gap={gap:.4f}")
                if dist < best_dist:
                    best_dist = dist
                    best_path = _gp
            except Exception:
                continue
        if best_path:
            return best_path, _graspable_prim_classes.get(best_path, "unknown"), float(best_dist)
        return None, None, None

    # Diagnostic: print arm joint positions just before main loop starts.
    if tiago_articulation:
        try:
            _pre_loop_pos = tiago_articulation.get_joint_positions()
            if _pre_loop_pos is not None:
                _idx_map_pre = {n: i for i, n in enumerate(dof_names)}
                _arm_pre = []
                for _an in ["arm_right_1_joint", "arm_right_2_joint", "arm_right_3_joint",
                            "arm_right_4_joint", "arm_right_5_joint", "arm_right_6_joint", "arm_right_7_joint"]:
                    _ai = _idx_map_pre.get(_an)
                    if _ai is not None:
                        _tgt = _persistent_targets.get(_an, float('nan'))
                        _act = float(_pre_loop_pos[_ai])
                        _arm_pre.append(f"{_an}: tgt={_tgt:.3f} act={_act:.3f} err={abs(_tgt-_act):.3f}")
                print(f"[RoboLab] PRE-LOOP arm state:")
                for _line in _arm_pre:
                    print(f"[RoboLab]   {_line}")
        except Exception:
            pass

    # Zero all joint velocities right before main loop to prevent residual
    # velocities from gripper diagnostic / FK validation from causing drift.
    if tiago_articulation:
        try:
            _zero_vel = np.zeros(len(dof_names), dtype=np.float32)
            tiago_articulation.set_joint_velocities(_zero_vel)
            _apply_joint_positions(_persistent_targets)
            print("[RoboLab] Pre-loop: zeroed velocities and re-applied targets")
        except Exception as _zv_err:
            print(f"[RoboLab] WARN: pre-loop velocity zero failed: {_zv_err}")

    if args.gui:
        import omni.timeline
        timeline = omni.timeline.get_timeline_interface()
        timeline.play()
        print("[RoboLab] GUI mode: timeline.play() called to start physics")

    print("[RoboLab] Starting simulation loop...")
    _grasp_events.clear()
    _prev_gripper_gap = None
    _prev_gripper_closing = False

    def _extract_contact_bodies(frame):
        bodies = []
        if not isinstance(frame, dict):
            return bodies
        contacts = frame.get("contacts")
        if isinstance(contacts, (list, tuple)):
            for contact in contacts:
                if isinstance(contact, dict):
                    for key in ("body0", "body1"):
                        value = contact.get(key)
                        if value is not None:
                            bodies.append(str(value))
                else:
                    for key in ("body0", "body1"):
                        try:
                            value = getattr(contact, key, None)
                        except Exception:
                            value = None
                        if value is not None:
                            bodies.append(str(value))
        else:
            for key in ("body0", "body1"):
                value = frame.get(key)
                if value is not None:
                    bodies.append(str(value))
        ordered = []
        seen = set()
        for body in bodies:
            if body not in seen:
                seen.add(body)
                ordered.append(body)
        return ordered

    while simulation_app.is_running():
        elapsed = time.time() - start_time
        if elapsed >= args.duration:
            break

        # Apply queued trajectory points from action callbacks in simulation thread.
        _process_trajectory_dispatcher()

        # One-time diagnostic: after first apply, read back joint positions and targets.
        if _sim_frame_idx == 1 and tiago_articulation:
            try:
                _pos1 = tiago_articulation.get_joint_positions()
                _vel1 = tiago_articulation.get_joint_velocities()
                _idx_map1 = {n: i for i, n in enumerate(dof_names)}
                _diag_joints = ["arm_right_1_joint", "arm_right_5_joint", "arm_right_6_joint"]
                for _dj in _diag_joints:
                    _di = _idx_map1.get(_dj)
                    if _di is not None:
                        _tgt = _persistent_targets.get(_dj, float('nan'))
                        _act = float(_pos1[_di]) if _pos1 is not None else float('nan')
                        _v = float(_vel1[_di]) if _vel1 is not None else float('nan')
                        print(f"[RoboLab] FRAME1 {_dj}: tgt={_tgt:.4f} act={_act:.4f} vel={_v:.4f} err={abs(_tgt-_act):.4f}")
            except Exception:
                pass

        # Monitor base drift but do NOT forcibly reset the XForm every frame.
        # fixedBase=True on the articulation should hold the base in place.
        # If it drifts, that indicates a physics problem that must be fixed
        # at the source, not masked by teleporting the visual root.
        if _use_fixed_base and _sim_frame_idx % 300 == 0:
            try:
                _base_xf = XFormPrim(prim_path=tiago_prim_path)
                _base_pos, _base_rot = _base_xf.get_world_pose()
                if _base_pos is not None:
                    _drift = abs(float(_base_pos[0]) - _robot_start_x) + abs(float(_base_pos[1])) + abs(float(_base_pos[2]) - 0.0)
                    if _drift > 0.05:
                        print(f"[RoboLab] WARN: base drift={_drift:.3f}m pos=({float(_base_pos[0]):.3f},{float(_base_pos[1]):.3f},{float(_base_pos[2]):.3f})", flush=True)
                if _base_rot is not None:
                    import math as _dm
                    _bw, _bx, _by, _bz = float(_base_rot[0]), float(_base_rot[1]), float(_base_rot[2]), float(_base_rot[3])
                    _pitch = _dm.asin(max(-1, min(1, 2.0*(_bw*_by - _bz*_bx))))
                    _roll = _dm.atan2(2.0*(_bw*_bx + _by*_bz), 1.0 - 2.0*(_bx*_bx + _by*_by))
                    _tilt_deg = _dm.degrees(max(abs(_pitch), abs(_roll)))
                    if _tilt_deg > 0.5:
                        print(f"[RoboLab] WARN: base tilt={_tilt_deg:.1f}deg pitch={_dm.degrees(_pitch):.1f} roll={_dm.degrees(_roll):.1f}", flush=True)
            except Exception:
                pass

        # Periodic coordinate monitor: log positions of robot, gripper, objects.
        if _sim_frame_idx % 600 == 0 and _sim_frame_idx > 0:
            try:
                _mon_parts = []
                # Robot base
                _mon_xf = XFormPrim(prim_path=tiago_prim_path)
                _mon_pos, _ = _mon_xf.get_world_pose()
                if _mon_pos is not None:
                    _mon_parts.append(f"base=({float(_mon_pos[0]):.3f},{float(_mon_pos[1]):.3f},{float(_mon_pos[2]):.3f})")
                # Gripper center (right) — midpoint of two finger links
                if _gripper_center_paths[0] and _gripper_center_paths[1]:
                    _gl = XFormPrim(prim_path=_gripper_center_paths[0]).get_world_pose()[0]
                    _gr = XFormPrim(prim_path=_gripper_center_paths[1]).get_world_pose()[0]
                    if _gl is not None and _gr is not None:
                        _gc = (_gl + _gr) / 2.0
                        _mon_parts.append(f"gripper=({float(_gc[0]):.3f},{float(_gc[1]):.3f},{float(_gc[2]):.3f})")
                elif _gripper_center_paths[0]:
                    _gc_pos, _ = XFormPrim(prim_path=_gripper_center_paths[0]).get_world_pose()
                    if _gc_pos is not None:
                        _mon_parts.append(f"gripper=({float(_gc_pos[0]):.3f},{float(_gc_pos[1]):.3f},{float(_gc_pos[2]):.3f})")
                # Graspable objects
                for _obj_path, _obj_label in _spawned_objects[:3]:
                    try:
                        _obj_xf = XFormPrim(prim_path=_obj_path)
                        _obj_pos, _ = _obj_xf.get_world_pose()
                        if _obj_pos is not None:
                            _short = _obj_path.split("/")[-1][:20]
                            _mon_parts.append(f"{_short}=({float(_obj_pos[0]):.3f},{float(_obj_pos[1]):.3f},{float(_obj_pos[2]):.3f})")
                    except Exception:
                        pass
                if _mon_parts:
                    print(f"[RoboLab] COORD_MON {' | '.join(_mon_parts)}", flush=True)
            except Exception:
                pass

        # IPC with ros2_fjt_proxy: poll for new pending trajectories from proxy,
        # write joint state snapshot, and write done markers after completion.
        if _proxy_ipc_enabled:
            # 1. Write current joint state snapshot for proxy to publish as /joint_states.
            _ipc_write_counter += 1
            if _ipc_write_counter % 3 == 0:  # ~20 Hz at 60 fps
                with latest_joint_snapshot_lock:
                    _snap = dict(latest_joint_snapshot)
                if _snap:
                    try:
                        _js_tmp = FJT_PROXY_DIR / "joint_state.tmp"
                        _js_tmp.write_text(json.dumps(_snap), encoding="utf-8")
                        _js_tmp.replace(FJT_PROXY_DIR / "joint_state.json")
                    except Exception:
                        pass

            # 2. Poll for pending trajectory files written by the proxy.
            try:
                for _pf in sorted(FJT_PROXY_DIR.glob("pending_*.json")):
                    try:
                        _traj_id = int(_pf.stem.split("_", 1)[1])
                    except (ValueError, IndexError):
                        continue
                    if _traj_id in _seen_traj_ids:
                        continue
                    try:
                        _payload = json.loads(_pf.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    _seen_traj_ids.add(_traj_id)
                    _joint_names_traj = _payload.get("joint_names", [])
                    _raw_points = _payload.get("points", [])
                    _parsed = []
                    for _pt in _raw_points:
                        _targets = {_joint_names_traj[i]: _pt["positions"][i]
                                    for i in range(len(_joint_names_traj))}
                        _parsed.append({"t": float(_pt["t"]), "targets": _targets})
                    if _parsed:
                        _goal_state = {
                            "controller_name": f"proxy_{_traj_id}",
                            "goal_handle": None,
                            "points": _parsed,
                            "start_wall": None,
                            "next_point_idx": 0,
                            "status": "pending",
                            "error": "",
                            "done_event": threading.Event(),
                            "traj_id": _traj_id,
                            "direct_set": bool(_payload.get("direct_set", False) and _payload.get("recovery_mode", False)),
                        }
                        with trajectory_state_lock:
                            pending_trajectory_goals.append(_goal_state)
                        print(f"[RoboLab] Queued proxy trajectory id={_traj_id} ({len(_parsed)} pts)")

                        # Background thread watches for completion and writes done file.
                        def _watch_done(_gs=_goal_state, _pid=_traj_id, _pf=_pf,
                                        _dur=args.duration, _jnames=_joint_names_traj,
                                        _npts=len(_parsed), _t0=time.time() - start_time):
                            _gs["done_event"].wait(timeout=_dur + 10.0)
                            _t_end = time.time() - start_time
                            _result = {
                                "traj_id": _pid,
                                "status": _gs["status"],
                                "error": _gs.get("error", ""),
                            }
                            try:
                                (FJT_PROXY_DIR / f"done_{_pid}.json").write_text(
                                    json.dumps(_result), encoding="utf-8"
                                )
                            except Exception:
                                pass
                            try:
                                _pf.unlink(missing_ok=True)
                            except Exception:
                                pass
                            # Record executed trajectory metadata in the dataset.
                            try:
                                dataset["joint_trajectories_executed"].append({
                                    "traj_id": _pid,
                                    "controller": f"proxy_{_pid}",
                                    "joint_names": _jnames,
                                    "num_points": _npts,
                                    "t_start": _t0,
                                    "t_end": _t_end,
                                    "status": _gs["status"],
                                    "error": _gs.get("error", ""),
                                })
                            except Exception:
                                pass

                        threading.Thread(target=_watch_done, daemon=True).start()
            except Exception as _ipc_err:
                pass  # non-fatal IPC errors

            # 3. Mobile base: read base_cmd.json, apply velocity only if fresh (< 500ms).
            #    Also write robot base pose to base_pose.json for diagnostics.
            if getattr(args, "mobile_base", False) and tiago_articulation:
                try:
                    from omni.isaac.core.prims import XFormPrim as _XFP
                    import math
                    import time as _time_mod
                    _root = _XFP(prim_path=tiago_prim_path)
                    _pos, _orient = _root.get_world_pose()
                    _qw, _qx, _qy, _qz = float(_orient[0]), float(_orient[1]), float(_orient[2]), float(_orient[3])
                    _yaw = math.atan2(2.0 * (_qw * _qz + _qx * _qy), 1.0 - 2.0 * (_qy * _qy + _qz * _qz))

                    if _sim_frame_idx % 30 == 0:
                        _pose_file = FJT_PROXY_DIR / "base_pose.json"
                        _pose_file.write_text(json.dumps({
                            "x": round(float(_pos[0]), 4),
                            "y": round(float(_pos[1]), 4),
                            "z": round(float(_pos[2]), 4),
                            "yaw_rad": round(_yaw, 4),
                            "yaw_deg": round(math.degrees(_yaw), 1),
                            "t": round(_time_mod.time(), 3),
                        }), encoding="utf-8")

                    _base_cmd_file = FJT_PROXY_DIR / "base_cmd.json"
                    if _base_cmd_file.exists():
                        _file_age = _time_mod.time() - _base_cmd_file.stat().st_mtime
                        if _file_age <= 0.5:
                            _bcmd = json.loads(_base_cmd_file.read_text(encoding="utf-8"))
                            _vx = float(_bcmd.get("vx", 0.0))
                            _vy = float(_bcmd.get("vy", 0.0))
                            _vyaw = float(_bcmd.get("vyaw", 0.0))
                            if abs(_vx) > 0.001 or abs(_vy) > 0.001 or abs(_vyaw) > 0.001:
                                _dt = 1.0 / 60.0
                                _dx = (_vx * math.cos(_yaw) - _vy * math.sin(_yaw)) * _dt
                                _dy = (_vx * math.sin(_yaw) + _vy * math.cos(_yaw)) * _dt
                                _dyaw = _vyaw * _dt
                                _new_pos = np.array([float(_pos[0]) + _dx, float(_pos[1]) + _dy, float(_pos[2])], dtype=np.float32)
                                _half = _dyaw / 2.0
                                _new_qw = _qw * math.cos(_half) - _qz * math.sin(_half)
                                _new_qz = _qw * math.sin(_half) + _qz * math.cos(_half)
                                _root.set_world_pose(position=_new_pos,
                                                     orientation=np.array([_new_qw, _qx, _qy, _new_qz], dtype=np.float32))
                except Exception:
                    pass

            # IPC: respond to object pose queries from intent bridge.
            try:
                _oq_file = FJT_PROXY_DIR / "query_object_pose.json"
                if _oq_file.exists():
                    _oq_req = {}
                    try:
                        _oq_req = json.loads(_oq_file.read_text(encoding="utf-8"))
                    except Exception:
                        _oq_req = {}
                    _oq_file.unlink()
                    _nearest = None
                    _nearest_dist = float("inf")
                    _object_entries = []
                    _gc = _get_gripper_center()
                    _pref_path = _oq_req.get("preferred_path")
                    _pref_class = _oq_req.get("preferred_class")
                    _ref_pos = _oq_req.get("reference_position")
                    _exclude_paths = set(str(p) for p in (_oq_req.get("exclude_paths") or []) if p)
                    _robot_pos = None
                    _robot_orient = None
                    _robot_yaw = 0.0
                    try:
                        _robot_xf = XFormPrim(prim_path=tiago_prim_path)
                        _rpos, _rorient = _robot_xf.get_world_pose()
                        if _rpos is not None and _rorient is not None:
                            _robot_pos = [float(v) for v in _rpos]
                            _robot_orient = [float(v) for v in _rorient]
                            _qw, _qx, _qy, _qz = _robot_orient
                            _robot_yaw = math.atan2(
                                2.0 * (_qw * _qz + _qx * _qy),
                                1.0 - 2.0 * (_qy * _qy + _qz * _qz),
                            )
                    except Exception:
                        pass
                    for _sp_path, _sp_class in _spawned_objects:
                        try:
                            if _sp_path in _exclude_paths:
                                continue
                            _sxf = XFormPrim(_sp_path)
                            _sp, _sorient = _sxf.get_world_pose()
                            if _sp is None:
                                continue
                            _spx = [float(_sp[0]), float(_sp[1]), float(_sp[2])]
                            _srot = [float(v) for v in _sorient] if _sorient is not None else None
                            _bounds_center, _bounds_size = _get_object_bounds_world(_sp_path)
                            _object_entries.append({
                                "path": _sp_path,
                                "class": _sp_class,
                                "position": _spx,
                                "orientation": _srot,
                                "bounds_center": _bounds_center,
                                "bounds_size": _bounds_size,
                            })
                            if _pref_path and _sp_path == _pref_path:
                                _nearest = {
                                    "path": _sp_path,
                                    "class": _sp_class,
                                    "position": [round(v, 4) for v in _spx],
                                    "orientation": [round(v, 4) for v in _srot] if _srot else None,
                                    "bounds_center": [round(v, 4) for v in _bounds_center] if _bounds_center else None,
                                    "bounds_size": [round(v, 4) for v in _bounds_size] if _bounds_size else None,
                                }
                                _nearest_dist = -1.0
                                break
                            if _pref_class and _sp_class != _pref_class:
                                continue
                            _d = float("inf")
                            if _ref_pos and len(_ref_pos) == 3:
                                _d = sum((float(_a) - float(_b))**2 for _a, _b in zip(_ref_pos, _spx))**0.5
                            elif _robot_pos is not None:
                                _dxw = _spx[0] - _robot_pos[0]
                                _dyw = _spx[1] - _robot_pos[1]
                                _local_x = _dxw * math.cos(_robot_yaw) + _dyw * math.sin(_robot_yaw)
                                _local_y = -_dxw * math.sin(_robot_yaw) + _dyw * math.cos(_robot_yaw)
                                _local_z = _spx[2] - _robot_pos[2]
                                _right_arm_ref = (0.33, -0.20, 0.84)
                                _reach_score = (
                                    (_local_x - _right_arm_ref[0]) ** 2
                                    + (_local_y - _right_arm_ref[1]) ** 2
                                    + ((_local_z - _right_arm_ref[2]) * 0.6) ** 2
                                ) ** 0.5
                                _right_side_penalty = 0.0 if _local_y <= -0.02 else 3.0 + abs(_local_y) * 8.0
                                if _local_y > 0.02:
                                    _right_side_penalty += 3.0 + (_local_y - 0.02) * 10.0
                                _lateral_penalty = 0.0 if -0.42 <= _local_y <= -0.12 else 1.2 + abs(_local_y + 0.20) * 3.0
                                _forward_penalty = 0.0 if 0.18 <= _local_x <= 0.48 else 1.2 + abs(_local_x - 0.34) * 2.8
                                _cross_penalty = 0.5 if (_local_x > 0.48 and abs(_local_y + 0.20) > 0.14) else 0.0
                                if _local_x > 0.58:
                                    _cross_penalty += 1.4 + (_local_x - 0.58) * 6.0
                                if _local_x > 0.48 and _local_y > -0.12:
                                    _cross_penalty += 1.4 + (_local_x - 0.48) * 5.0 + (_local_y + 0.12) * 6.0
                                _far_penalty = 0.0 if 0.15 <= _local_x <= 0.75 else 0.5
                                _height_penalty = 0.0 if 0.64 <= _local_z <= 0.82 else 1.0 + abs(_local_z - 0.73) * 2.8
                                if _local_z > 0.86:
                                    _height_penalty += 1.3 + (_local_z - 0.86) * 5.0
                                _d = (
                                    _reach_score
                                    + _right_side_penalty
                                    + _lateral_penalty
                                    + _forward_penalty
                                    + _cross_penalty
                                    + _far_penalty
                                    + _height_penalty
                                )
                                _class_name = str(_sp_class).lower()
                                if any(_token in _class_name for _token in ("fruit", "apple", "orange", "banana", "pear", "lemon", "peach")):
                                    _d += 1.4
                                if any(_token in _class_name for _token in ("plate", "bowl", "clamp", "pitcher")):
                                    _d += 1.8
                                if any(_token in _class_name for _token in ("bottle", "juice")):
                                    _d += 0.9
                                if any(_token in _class_name for _token in ("glass", "wineglass", "cup_glass")):
                                    _d += 1.1
                                if any(_token in _class_name for _token in ("mug", "cup", "box", "carton", "can")):
                                    _d -= 0.8
                            elif _gc:
                                _d = sum((_a - _b)**2 for _a, _b in zip(_gc, _spx))**0.5
                            if _d < _nearest_dist:
                                _nearest_dist = _d
                                _nearest = {
                                    "path": _sp_path,
                                    "class": _sp_class,
                                    "position": [round(v, 4) for v in _spx],
                                    "orientation": [round(v, 4) for v in _srot] if _srot else None,
                                    "bounds_center": [round(v, 4) for v in _bounds_center] if _bounds_center else None,
                                    "bounds_size": [round(v, 4) for v in _bounds_size] if _bounds_size else None,
                                }
                        except Exception:
                            continue
                    _resp = _nearest or {"path": None, "class": None, "position": None}
                    _grasp_target = None
                    if _nearest and _nearest.get("position"):
                        _grasp_target = _compute_grasp_target_world(
                            _nearest["position"],
                            _nearest.get("class"),
                            robot_yaw=_robot_yaw,
                            obj_center_world=_nearest.get("bounds_center"),
                            obj_bounds_size=_nearest.get("bounds_size"),
                        )

                    def _dist3(_a, _b):
                        return math.sqrt(sum((float(_x) - float(_y)) ** 2 for _x, _y in zip(_a, _b)))

                    def _segment_distance(_p, _a, _b):
                        _ab = [float(_b[i]) - float(_a[i]) for i in range(3)]
                        _ap = [float(_p[i]) - float(_a[i]) for i in range(3)]
                        _den = sum(_v * _v for _v in _ab)
                        if _den <= 1e-9:
                            return _dist3(_p, _a), 0.0
                        _t = max(0.0, min(1.0, sum(_ap[i] * _ab[i] for i in range(3)) / _den))
                        _proj = [float(_a[i]) + _t * _ab[i] for i in range(3)]
                        return _dist3(_p, _proj), _t

                    _blocking_objects = []
                    if _nearest and _nearest.get("position"):
                        _target_pos = [float(v) for v in (_grasp_target or _nearest["position"])]
                        for _entry in _object_entries:
                            if _entry["path"] == _nearest.get("path"):
                                continue
                            _ep = _entry["position"]
                            _dist_target = _dist3(_ep, _target_pos)
                            _dist_gripper = _dist3(_ep, _gc) if _gc else None
                            _segment_dist = None
                            _segment_t = None
                            if _gc:
                                _segment_dist, _segment_t = _segment_distance(_ep, _gc, _target_pos)
                            _height_delta = abs(float(_ep[2]) - float(_target_pos[2]))
                            _line_block = (
                                _gc is not None
                                and _segment_t is not None
                                and 0.08 <= _segment_t <= 0.98
                                and _segment_dist <= 0.14
                                and _height_delta <= 0.20
                            )
                            _near_target = _dist_target <= 0.18 and _height_delta <= 0.18
                            if not (_line_block or _near_target):
                                continue
                            _kind = []
                            if _line_block:
                                _kind.append("line")
                            if _near_target:
                                _kind.append("target")
                            _blocking_objects.append({
                                "path": _entry["path"],
                                "class": _entry["class"],
                                "position": [round(float(v), 4) for v in _ep],
                                "distance_to_target": round(float(_dist_target), 4),
                                "distance_to_gripper": round(float(_dist_gripper), 4) if _dist_gripper is not None else None,
                                "segment_distance": round(float(_segment_dist), 4) if _segment_dist is not None else None,
                                "segment_progress": round(float(_segment_t), 4) if _segment_t is not None else None,
                                "kind": "+".join(_kind) if _kind else "nearby",
                            })
                        _blocking_objects.sort(
                            key=lambda _item: (
                                0 if "line" in str(_item.get("kind", "")) else 1,
                                float(_item.get("segment_distance", 99.0) if _item.get("segment_distance") is not None else 99.0),
                                float(_item.get("distance_to_target", 99.0)),
                            )
                        )
                    _resp["blocking_objects"] = _blocking_objects[:5]
                    _resp["blocking_object_count"] = len(_blocking_objects)
                    _resp["gripper_center"] = [round(v, 4) for v in _gc] if _gc else None
                    _resp["grasp_target"] = [round(float(v), 4) for v in _grasp_target] if _grasp_target else None
                    try:
                        if _robot_pos is not None and _robot_orient is not None:
                            _resp["robot_position"] = [round(float(v), 4) for v in _robot_pos]
                            _resp["robot_orientation"] = [round(float(v), 4) for v in _robot_orient]
                    except Exception:
                        pass
                    if _nearest:
                        _resp["orientation"] = _nearest.get("orientation")
                        _resp["bounds_center"] = _nearest.get("bounds_center")
                        _resp["bounds_size"] = _nearest.get("bounds_size")
                    _oq_resp = FJT_PROXY_DIR / "object_pose_result.json"
                    _oq_resp.write_text(json.dumps(_resp), encoding="utf-8")
            except Exception:
                pass

            # IPC: publish current grasp result for intent bridge verification.
            try:
                _gr_file = FJT_PROXY_DIR / "grasp_result.json"
                _gr_data = {
                    "gripper_gap": round(_prev_gripper_gap, 5) if _prev_gripper_gap is not None else None,
                    "object_in_gripper": _gripped_object_class,
                    "object_in_gripper_path": _gripped_object_path,
                    "gripped_object_stable": _gripped_object_path is not None,
                    "hold_frames": max(0, _sim_frame_idx - _grip_start_frame) if _gripped_object_path else 0,
                    "candidate_frames": _grip_candidate_frames,
                    "object_distance_to_gripper": round(float(_obj_in_grip_dist), 4) if "_obj_in_grip_dist" in locals() and _obj_in_grip_dist is not None else None,
                    "left_finger_contact": _contact_left_in,
                    "right_finger_contact": _contact_right_in,
                    "contact_forces": round(
                        abs(_contact_left_force[0]) + abs(_contact_right_force[0]), 3
                    ) if (_contact_left_force and _contact_right_force) else 0.0,
                }
                _gr_file.write_text(json.dumps(_gr_data), encoding="utf-8")
            except Exception:
                pass

            # IPC: respond to IK queries from intent bridge using actual sim kinematics.
            try:
                _ik_query_file = FJT_PROXY_DIR / "query_ik.json"
                _ik_result_file = FJT_PROXY_DIR / "ik_result.json"
                if _ik_query_file.exists() and tiago_articulation:
                    try:
                        _ik_req = json.loads(_ik_query_file.read_text(encoding="utf-8"))
                        _ik_query_file.unlink()
                    except PermissionError:
                        _ik_req = None
                    if _ik_req is None:
                        raise PermissionError(f"IK query busy: {_ik_query_file}")
                    _ik_target_local = _ik_req.get("target_position")
                    if _ik_target_local and len(_ik_target_local) == 3:
                        # Target is in base_footprint frame; convert to world
                        # using full quaternion rotation (accounts for tilt).
                        try:
                            _robot_xf = XFormPrim(prim_path=tiago_prim_path)
                            _rp, _ro = _robot_xf.get_world_pose()
                            _rx, _ry, _rz = float(_rp[0]), float(_rp[1]), float(_rp[2])
                            _rw_q = float(_ro[0])
                            _rx_q, _ry_q, _rz_q = float(_ro[1]), float(_ro[2]), float(_ro[3])
                        except Exception:
                            _rx, _ry, _rz = _robot_start_x, 0.0, 0.0
                            _rw_q, _rx_q, _ry_q, _rz_q = 1.0, 0.0, 0.0, 0.0
                        _lx, _ly, _lz = float(_ik_target_local[0]), float(_ik_target_local[1]), float(_ik_target_local[2])
                        _q = np.array([_rw_q, _rx_q, _ry_q, _rz_q], dtype=np.float64)
                        _rot = _quat_to_rotmat(_q)
                        _local_vec = np.array([_lx, _ly, _lz], dtype=np.float64)
                        _world_vec = _rot @ _local_vec
                        _ik_target_world = np.array([
                            _world_vec[0] + _rx,
                            _world_vec[1] + _ry,
                            _world_vec[2] + _rz,
                        ], dtype=np.float64)
                        import math as _math_ik
                        _euler_pitch = _math_ik.asin(max(-1, min(1, 2.0*(_rw_q*_ry_q - _rz_q*_rx_q))))
                        print(f"[RoboLab] IK query: local=({_lx:.3f},{_ly:.3f},{_lz:.3f}) "
                              f"world=({_ik_target_world[0]:.3f},{_ik_target_world[1]:.3f},{_ik_target_world[2]:.3f}) "
                              f"robot=({_rx:.3f},{_ry:.3f},{_rz:.3f}) pitch={_math_ik.degrees(_euler_pitch):.1f}deg", flush=True)
                        _ik_result = _solve_ik_sim(
                            _ik_target_world,
                            _ik_req.get("seed_joints"),
                        )
                        _ik_result_tmp = _ik_result_file.with_suffix(".tmp")
                        _ik_result_tmp.write_text(json.dumps(_ik_result), encoding="utf-8")
                        _ik_result_tmp.replace(_ik_result_file)
                    else:
                        _ik_result_tmp = _ik_result_file.with_suffix(".tmp")
                        _ik_result_tmp.write_text(json.dumps({"success": False, "error": "invalid target"}), encoding="utf-8")
                        _ik_result_tmp.replace(_ik_result_file)
            except Exception as _ik_exc:
                print(f"[RoboLab] IK query error: {_ik_exc}", flush=True)

        world.step(render=True)
        if _rep_subsample <= 1 or (_sim_frame_idx % _rep_subsample) == 0:
            rep.orchestrator.step(rt_subframes=1)
        _sim_frame_idx += 1

        # Joint states + velocities.
        joint_snapshot = {}
        joint_positions = []
        joint_velocities = []
        if tiago_articulation:
            try:
                get_pos = getattr(tiago_articulation, "get_joint_positions", None) or getattr(
                    tiago_articulation, "get_dof_positions", lambda: None
                )
                get_vel = getattr(tiago_articulation, "get_joint_velocities", None) or getattr(
                    tiago_articulation, "get_dof_velocities", lambda: None
                )
                joint_positions = _as_list(get_pos())
                joint_velocities = _as_list(get_vel())
            except Exception as err:
                print(f"[RoboLab] WARN: joint extraction failed at t={elapsed:.2f}s: {err}")

        if not dof_names and joint_positions:
            dof_names = [f"joint_{i}" for i in range(len(joint_positions))]

        if dof_names:
            for index, name in enumerate(dof_names):
                position = float(joint_positions[index]) if index < len(joint_positions) else 0.0
                velocity = float(joint_velocities[index]) if index < len(joint_velocities) else 0.0
                joint_snapshot[name] = {"position": position, "velocity": velocity}
            # Mirror arm/torso joints to MoveIt naming if the articulation uses arm_left/right names.
            for moveit_name, sim_name in moveit_joint_aliases.items():
                if moveit_name not in joint_snapshot and sim_name in joint_snapshot:
                    joint_snapshot[moveit_name] = {
                        "position": joint_snapshot[sim_name]["position"],
                        "velocity": joint_snapshot[sim_name]["velocity"],
                    }
        else:
            # Synthetic fallback keeps the dataset contract valid when articulation assets are unavailable.
            for index, name in enumerate(dof_names):
                phase = elapsed + (index * 0.25)
                position = 0.2 * (index + 1) * math.sin(phase)
                velocity = 0.2 * (index + 1) * math.cos(phase)
                joint_snapshot[name] = {"position": float(position), "velocity": float(velocity)}

        with latest_joint_snapshot_lock:
            latest_joint_snapshot = {
                key: {"position": float(value["position"]), "velocity": float(value["velocity"])}
                for key, value in joint_snapshot.items()
            }

        # Robot base pose in map frame (read from articulation root, not static Xform).
        robot_pose = {"position": [], "orientation": []}
        try:
            robot_prim = XFormPrim(tiago_articulation_path)
            robot_pos, robot_rot = robot_prim.get_world_pose()
            robot_pose = {
                "position": robot_pos.tolist() if robot_pos is not None else [],
                "orientation": robot_rot.tolist() if robot_rot is not None else [],
            }
            if robot_pose["position"]:
                _telem_entry = {
                    "timestamp": elapsed,
                    "robot_position": {
                        "x": float(robot_pose["position"][0]),
                        "y": float(robot_pose["position"][1]),
                        "z": float(robot_pose["position"][2]),
                    },
                }
                if robot_pose["orientation"] and len(robot_pose["orientation"]) == 4:
                    import math as _tm
                    _tw, _tx, _ty, _tz = [float(v) for v in robot_pose["orientation"]]
                    _telem_entry["robot_orientation"] = {
                        "w": _tw, "x": _tx, "y": _ty, "z": _tz,
                        "pitch_deg": round(_tm.degrees(_tm.asin(max(-1, min(1, 2.0*(_tw*_ty - _tz*_tx))))), 2),
                        "roll_deg": round(_tm.degrees(_tm.atan2(2.0*(_tw*_tx + _ty*_tz), 1.0 - 2.0*(_tx*_tx + _ty*_ty))), 2),
                    }
                telemetry_data.append(_telem_entry)
        except Exception:
            pass

        # Semantic world poses.
        world_poses = {}
        for prim_path, semantic_class in tracked_prims:
            try:
                xform = XFormPrim(prim_path)
                pos, rot = xform.get_world_pose()
                world_poses[prim_path] = {
                    "class": semantic_class,
                    "position": pos.tolist() if pos is not None else [],
                    "orientation": rot.tolist() if rot is not None else [],
                }
            except Exception:
                continue

        # Ensure robot pose is always present in the world pose map.
        world_poses[tiago_prim_path] = {
            "class": "robot",
            "position": robot_pose.get("position", []),
            "orientation": robot_pose.get("orientation", []),
        }

        # Grasp state: gripper gap, object detection, event logging.
        _gripper_positions = []
        for _gn in _GRIPPER_JOINT_NAMES:
            _gj = joint_snapshot.get(_gn)
            if _gj:
                _gripper_positions.append(float(_gj["position"]))
        _gripper_gap = sum(_gripper_positions) / len(_gripper_positions) if _gripper_positions else 0.0
        _gap_delta = (_gripper_gap - _prev_gripper_gap) if _prev_gripper_gap is not None else 0.0
        _gripper_closing = _gap_delta < -0.002
        _gripper_opening = _gap_delta > 0.002

        _grip_center = _get_gripper_center()
        if _sim_frame_idx % 60 == 1:
            try:
                _tool_pos = _get_sim_tool_world_pos()
                _arm_joints_dbg = {}
                if tiago_articulation and dof_names:
                    _jpos = tiago_articulation.get_joint_positions()
                    if _jpos is not None:
                        for _ji, _jn in enumerate(dof_names):
                            if "arm_right" in _jn or _jn == "torso_lift_joint":
                                _arm_joints_dbg[_jn] = round(float(_jpos[_ji]), 4)
                _tp = _tool_pos.tolist() if _tool_pos is not None else None
                _base_pos_dbg = None
                try:
                    _base_xf = XFormPrim(prim_path=tiago_prim_path)
                    _bp, _ = _base_xf.get_world_pose()
                    _base_pos_dbg = _bp.tolist() if _bp is not None else None
                except Exception:
                    pass
                if _tp:
                    _base_str = ""
                    if _base_pos_dbg:
                        _base_str = f" base=({_base_pos_dbg[0]:.3f},{_base_pos_dbg[1]:.3f},{_base_pos_dbg[2]:.3f})"
                    print(f"[RoboLab] TOOL_LINK world=({_tp[0]:.3f},{_tp[1]:.3f},{_tp[2]:.3f}){_base_str} "
                          f"joints={_arm_joints_dbg}", flush=True)
            except Exception as _e:
                pass
        _obj_in_grip_path, _obj_in_grip_class, _obj_in_grip_dist = _find_object_in_gripper(
            _grip_center, _gripper_gap
        )
        _obj_z = None
        if _obj_in_grip_path:
            _owp = world_poses.get(_obj_in_grip_path, {})
            _opos = _owp.get("position", [])
            _obj_z = float(_opos[2]) if len(_opos) > 2 else None

        _candidate_close_enough = (
            _obj_in_grip_dist is not None and _obj_in_grip_dist <= _OBJECT_IN_GRIPPER_CONFIRM_RADIUS
        )

        # Contact sensor readings from the official current-frame API, with
        # legacy interface fallback for force/in_contact when raw contacts are absent.
        _contact_left_force = [0.0, 0.0, 0.0]
        _contact_right_force = [0.0, 0.0, 0.0]
        _contact_left_in = False
        _contact_right_in = False
        _contact_left_count = 0
        _contact_right_count = 0
        _contact_left_bodies = []
        _contact_right_bodies = []
        if _contact_sensor_left_reader is not None:
            try:
                _frame_left = _contact_sensor_left_reader.get_current_frame()
                if isinstance(_frame_left, dict):
                    _contact_left_in = bool(_frame_left.get("in_contact", False))
                    _contact_left_count = int(_frame_left.get("number_of_contacts", 0) or 0)
                    _contact_left_bodies = _extract_contact_bodies(_frame_left)
                    _lf = _frame_left.get("force", 0.0) or 0.0
                    _contact_left_force = [round(float(_lf), 3), 0.0, 0.0]
            except Exception:
                pass
        if _contact_sensor_right_reader is not None:
            try:
                _frame_right = _contact_sensor_right_reader.get_current_frame()
                if isinstance(_frame_right, dict):
                    _contact_right_in = bool(_frame_right.get("in_contact", False))
                    _contact_right_count = int(_frame_right.get("number_of_contacts", 0) or 0)
                    _contact_right_bodies = _extract_contact_bodies(_frame_right)
                    _rf = _frame_right.get("force", 0.0) or 0.0
                    _contact_right_force = [round(float(_rf), 3), 0.0, 0.0]
            except Exception:
                pass
        if _contact_sensor_interface and _contact_sensor_left:
            try:
                if not _contact_left_in:
                    _cl = _contact_sensor_interface.get_sensor_reading(
                        _contact_sensor_left, use_latest_data=True)
                    if _cl.is_valid:
                        _contact_left_in = bool(_cl.in_contact)
                        if _contact_left_force[0] == 0.0:
                            _contact_left_force = [round(float(_cl.value), 3), 0.0, 0.0]
                if not _contact_right_in:
                    _cr = _contact_sensor_interface.get_sensor_reading(
                        _contact_sensor_right, use_latest_data=True)
                    if _cr.is_valid:
                        _contact_right_in = bool(_cr.in_contact)
                        if _contact_right_force[0] == 0.0:
                            _contact_right_force = [round(float(_cr.value), 3), 0.0, 0.0]
            except Exception:
                pass

        _has_finger_contact = (
            _contact_left_in or _contact_right_in or _contact_left_count > 0 or _contact_right_count > 0
        )

        _stable = False
        if (
            _obj_in_grip_path
            and _obj_z is not None
            and _lift_start_z is not None
            and _candidate_close_enough
            and _has_finger_contact
        ):
            _stable = _obj_z >= _lift_start_z - 0.02

        grasp_state = {
            "gripper_gap": round(_gripper_gap, 5),
            "gripper_closing": _gripper_closing,
            "object_in_gripper": _obj_in_grip_class,
            "object_in_gripper_path": _obj_in_grip_path,
            "gripped_object_stable": _stable,
            "hold_frames": max(0, _sim_frame_idx - _grip_start_frame) if _gripped_object_path else 0,
            "candidate_frames": _grip_candidate_frames,
            "object_distance_to_gripper": round(float(_obj_in_grip_dist), 4) if _obj_in_grip_dist is not None else None,
            "contact_forces": {
                "left_finger": _contact_left_force,
                "right_finger": _contact_right_force,
            },
            "left_finger_contact": _contact_left_in,
            "right_finger_contact": _contact_right_in,
            "left_finger_contact_count": _contact_left_count,
            "right_finger_contact_count": _contact_right_count,
            "left_finger_contact_bodies": _contact_left_bodies[:8],
            "right_finger_contact_bodies": _contact_right_bodies[:8],
        }
        if _grip_center:
            grasp_state["gripper_center"] = [round(c, 4) for c in _grip_center]

        # Event detection with debounce to avoid spam from gap oscillation.
        _last_close_frame = max((e["frame"] for e in _grasp_events if e.get("event") == "gripper_close_start"), default=-999)
        if _gripper_closing and not _close_cycle_active and (_sim_frame_idx - _last_close_frame) > 30:
            _grasp_events.append({"frame": _sim_frame_idx, "time": round(elapsed, 3),
                                  "event": "gripper_close_start"})
            _close_cycle_active = True
        _last_open_frame = max((e["frame"] for e in _grasp_events if e.get("event") == "gripper_open_start"), default=-999)
        if _gripper_opening and _close_cycle_active and _gripper_gap >= 0.02 and (_sim_frame_idx - _last_open_frame) > 30:
            _grasp_events.append({"frame": _sim_frame_idx, "time": round(elapsed, 3),
                                  "event": "gripper_open_start"})
            _close_cycle_active = False

        if (_contact_left_in and _contact_right_in) and _gripper_closing and not any(
            e.get("event") == "contact_detected" and e.get("frame", 0) > _sim_frame_idx - 30
            for e in _grasp_events
        ):
            _contact_force_mag = abs(_contact_left_force[0]) + abs(_contact_right_force[0])
            _grasp_events.append({"frame": _sim_frame_idx, "time": round(elapsed, 3),
                                  "event": "contact_detected",
                                  "object": _obj_in_grip_class or "unknown",
                                  "force": round(_contact_force_mag, 2)})

        if _obj_in_grip_path and _candidate_close_enough and _has_finger_contact:
            if _obj_in_grip_path == _grip_candidate_path:
                _grip_candidate_frames += 1
            else:
                _grip_candidate_path = _obj_in_grip_path
                _grip_candidate_class = _obj_in_grip_class
                _grip_candidate_frames = 1
            _grip_release_frames = 0
        else:
            _grip_candidate_path = None
            _grip_candidate_class = None
            _grip_candidate_frames = 0
            if _gripped_object_path:
                _grip_release_frames += 1

        if (_gripped_object_path is None and _grip_candidate_path and
                _grip_candidate_frames >= _GRIP_CONFIRM_FRAMES):
            _gripped_object_path = _grip_candidate_path
            _gripped_object_class = _grip_candidate_class
            _grip_start_frame = _sim_frame_idx
            _lift_start_z = _obj_z
            _grasp_events.append({"frame": _sim_frame_idx, "time": round(elapsed, 3),
                                  "event": "grasp_confirmed", "object": _gripped_object_class,
                                  "gap": round(_gripper_gap, 4), "confirm_frames": _grip_candidate_frames,
                                  "distance": round(float(_obj_in_grip_dist), 4) if _obj_in_grip_dist is not None else None})

        if _gripped_object_path and _obj_z is not None and _lift_start_z is not None:
            if _obj_z > _lift_start_z + 0.05 and not any(
                e.get("event") == "lift_detected" and e.get("object") == _gripped_object_class
                for e in _grasp_events
            ):
                _grasp_events.append({"frame": _sim_frame_idx, "time": round(elapsed, 3),
                                      "event": "lift_detected", "object": _gripped_object_class,
                                      "z": round(_obj_z, 3)})

        if _gripped_object_path and _grip_release_frames >= _GRIP_RELEASE_FRAMES:
            if _obj_z is None:
                _dropped_z = None
                _dwp = world_poses.get(_gripped_object_path, {})
                _dp = _dwp.get("position", [])
                if len(_dp) > 2:
                    _dropped_z = round(float(_dp[2]), 3)
            else:
                _dropped_z = round(_obj_z, 3)
            _grasp_events.append({"frame": _sim_frame_idx, "time": round(elapsed, 3),
                                  "event": "object_released", "object": _gripped_object_class,
                                  "z": _dropped_z, "release_frames": _grip_release_frames})
            _gripped_object_path = None
            _gripped_object_class = None
            _lift_start_z = None
            _grip_start_frame = -1
            _grip_release_frames = 0
            _close_cycle_active = False

        _prev_gripper_gap = _gripper_gap
        _prev_gripper_closing = _gripper_closing

        frame_record = {
            "timestamp": elapsed,
            "map_frame": "map",
            "robot_pose": robot_pose,
            "robot_joints": joint_snapshot,
            "world_poses": world_poses,
            "grasp_state": grasp_state,
        }
        dataset["frames"].append(frame_record)
        dataset["joint_trajectories"].append({
            "timestamp": elapsed,
            "joints": joint_snapshot,
        })

    _abort_all_trajectory_goals("Simulation loop ended before trajectory completion")

    # Finalize replicator writes and shutdown timeline gracefully.
    try:
        import omni.timeline

        omni.timeline.get_timeline_interface().stop()
        rep.orchestrator.wait_until_complete()
    except Exception as err:
        print(f"[RoboLab] WARN: replicator finalization warning: {err}")

    # Save structured dataset.
    dataset_path = os.path.join(args.output_dir, "dataset.json")
    with open(dataset_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    telemetry_path = os.path.join(args.output_dir, "telemetry.json")
    with open(telemetry_path, "w", encoding="utf-8") as f:
        json.dump({"episode_duration": args.duration, "trajectory": telemetry_data}, f, indent=2)

    grasp_events_path = os.path.join(args.output_dir, "grasp_events.json")
    with open(grasp_events_path, "w", encoding="utf-8") as f:
        json.dump(_grasp_events, f, indent=2)
    print(f"[RoboLab] Grasp events saved: {grasp_events_path} ({len(_grasp_events)} events)")

    video_path = os.path.join(args.output_dir, "camera_0.mp4")
    encode_video_from_rgb(replicator_dir, video_path)

    if _wrist_replicator_dir and os.path.isdir(_wrist_replicator_dir):
        _wrist_video = os.path.join(args.output_dir, "camera_1_wrist.mp4")
        encode_video_from_rgb(_wrist_replicator_dir, _wrist_video)
        print(f"[RoboLab] Wrist video saved: {_wrist_video}")

    if _external_replicator_dir and os.path.isdir(_external_replicator_dir):
        _ext_video = os.path.join(args.output_dir, "camera_2_external.mp4")
        encode_video_from_rgb(_external_replicator_dir, _ext_video)
        print(f"[RoboLab] External video saved: {_ext_video}")

    manifest_path = os.path.join(args.output_dir, "dataset_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(build_output_manifest(args.output_dir), f, indent=2)

    print(f"[RoboLab] Dataset saved: {dataset_path}")
    print(f"[RoboLab] Telemetry saved: {telemetry_path}")
    print(f"[RoboLab] Video saved: {video_path}")
    print(f"[RoboLab] Manifest saved: {manifest_path}")

except Exception as _top_err:
    import traceback
    print(f"[RoboLab] FATAL ERROR: {_top_err}")
    traceback.print_exc()
    sys.exit(1)

finally:
    try:
        if "trajectory_servers" in locals():
            for srv in trajectory_servers:
                try:
                    srv.destroy()
                except Exception:
                    pass
        if "ros_executor" in locals() and ros_executor is not None:
            try:
                ros_executor.shutdown()
            except Exception:
                pass
        if "ros_executor_thread" in locals() and ros_executor_thread is not None:
            try:
                ros_executor_thread.join(timeout=1.0)
            except Exception:
                pass
        if "js_node" in locals() and js_node is not None:
            js_node.destroy_node()
        if "rclpy_mod" in locals() and rclpy_mod is not None and rclpy_mod.ok():
            rclpy_mod.shutdown()
    except Exception:
        pass
    simulation_app.update()
    simulation_app.close()
    sys.exit(0)
