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
        default=os.environ.get("TIAGO_USD_PATH", "C:/RoboLab_Data/data/tiago_isaac/tiago_dual_functional.usd"),
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
        default=1.5,
        help="Execution speed multiplier for FollowJointTrajectory playback in Isaac.",
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


def _resolve_dof_names(articulation) -> list:
    """Resolve joint/DOF names from articulation. Tries dof_names, dof_paths, then fallback."""
    if not articulation:
        return []
    # 1. dof_names (omni.isaac.core Articulation)
    names = getattr(articulation, "dof_names", None)
    if names and len(names) > 0:
        return list(names)
    # 2. dof_paths: extract last path component (e.g. /World/Tiago/arm_1_joint -> arm_1_joint)
    paths = getattr(articulation, "dof_paths", None)
    if paths and len(paths) > 0:
        return [str(p).split("/")[-1] if p else f"joint_{i}" for i, p in enumerate(paths)]
    # 3. num_dofs for length; names filled in later from positions
    return []


def setup_joint_state_publisher_omnigraph(robot_prim_path: str) -> bool:
    """Add ROS2 Publish Joint State node via OmniGraph when --moveit. Returns True if setup succeeded."""
    try:
        import omni.graph.core as og

        # Node types vary by Isaac Sim version
        publish_node_types = [
            "isaacsim.ros2.bridge.ROS2PublishJointState",
            "omni.isaac.ros2_bridge.ROS2PublishJointState",
        ]
        publish_type = None
        for nt in publish_node_types:
            try:
                og.Controller.edit(
                    {"graph_path": "/ActionGraph", "evaluator_name": "execution"},
                    {
                        og.Controller.Keys.CREATE_NODES: [
                            ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
                            ("PublishJointState", nt),
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
                publish_type = nt
                break
            except Exception:
                continue
        if publish_type:
            print(f"[RoboLab] Joint state publisher added via OmniGraph (target={robot_prim_path})")
            return True
        return False
    except Exception as err:
        print(f"[RoboLab] WARN: OmniGraph joint state setup failed: {err}")
        return False


def resolve_dof_names(articulation) -> list:
    """Resolve joint/DOF names from articulation. Tries dof_names, dof_paths, then fallback."""
    if not articulation:
        return []
    # Try dof_names (omni.isaac.core)
    names = getattr(articulation, "dof_names", None)
    if names and len(names) > 0:
        return list(names)
    # Try dof_paths and extract last path component (e.g. /World/Tiago/arm_1_joint -> arm_1_joint)
    paths = getattr(articulation, "dof_paths", None)
    if paths and len(paths) > 0:
        return [str(p).split("/")[-1] if p else f"joint_{i}" for i, p in enumerate(paths)]
    # Fallback: use joint count from positions
    try:
        pos = articulation.get_joint_positions()
        if pos is not None and len(pos) > 0:
            return [f"joint_{i}" for i in range(len(pos))]
    except Exception:
        try:
            pos = getattr(articulation, "get_dof_positions", lambda: None)()
            if pos is not None and len(pos) > 0:
                return [f"joint_{i}" for i in range(len(pos))]
        except Exception:
            pass
    return []


def _resolve_dof_names(articulation):
    """Resolve joint/DOF names from articulation. Tries dof_names, dof_paths, then fallback."""
    if not articulation:
        return []
    names = getattr(articulation, "dof_names", None)
    if names and len(names) > 0:
        return list(names)
    paths = getattr(articulation, "dof_paths", None)
    if paths and len(paths) > 0:
        return [str(p).split("/")[-1] if "/" in str(p) else str(p) for p in paths]
    return []


def _setup_joint_state_publisher(robot_prim_path: str) -> bool:
    """Add OmniGraph ROS2 Publish Joint State node for /joint_states when --moveit."""
    try:
        import omni.graph.core as og

        # Node types vary by Isaac Sim version
        publish_node_types = [
            "isaacsim.ros2.bridge.ROS2PublishJointState",
            "omni.isaac.ros2_bridge.ROS2PublishJointState",
        ]
        publish_type = None
        for nt in publish_node_types:
            try:
                og.Controller.edit(
                    {"graph_path": "/ActionGraph", "evaluator_name": "execution"},
                    {og.Controller.Keys.CREATE_NODES: [("_TestNode", nt)]},
                )
                og.Controller.edit(
                    {"graph_path": "/ActionGraph", "evaluator_name": "execution"},
                    {og.Controller.Keys.DELETE_NODES: ["_TestNode"]},
                )
                publish_type = nt
                break
            except Exception:
                continue
        if not publish_type:
            print("[RoboLab] WARN: ROS2PublishJointState node type not found, skipping joint_states publisher.")
            return False

        og.Controller.edit(
            {"graph_path": "/ActionGraph", "evaluator_name": "execution"},
            {
                og.Controller.Keys.CREATE_NODES: [
                    ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
                    ("PublishJointState", publish_type),
                    ("ReadSimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
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
        print(f"[RoboLab] Joint state publisher added for {robot_prim_path} -> /joint_states")
        return True
    except Exception as err:
        print(f"[RoboLab] WARN: Failed to add joint state publisher: {err}")
        return False


def setup_joint_state_publisher_omnigraph(robot_prim_path: str) -> bool:
    """Add ROS2 Publish Joint State node via OmniGraph when --moveit. Returns True if successful."""
    try:
        import omni.graph.core as og

        # Node types may vary by Isaac Sim version
        publish_node_types = [
            "isaacsim.ros2.bridge.ROS2PublishJointState",
            "omni.isaac.ros2_bridge.ROS2PublishJointState",
        ]
        publish_type = None
        for nt in publish_node_types:
            try:
                og.Controller.edit(
                    {"graph_path": "/ActionGraph", "evaluator_name": "execution"},
                    {
                        og.Controller.Keys.CREATE_NODES: [
                            ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
                            ("PublishJointState", nt),
                            ("ReadSimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
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
                publish_type = nt
                break
            except Exception:
                continue
        if publish_type:
            print(f"[RoboLab] Joint state publisher added (target={robot_prim_path})")
            return True
        return False
    except Exception as err:
        print(f"[RoboLab] WARN: Could not add joint state publisher via OmniGraph: {err}")
        return False


def setup_joint_state_publisher_omnigraph(robot_prim_path: str) -> bool:
    """Add ROS2 Joint State publisher via OmniGraph when --moveit. Returns True if successful."""
    try:
        import omni.graph.core as og

        # Node types vary by Isaac Sim version
        publish_node_types = [
            "isaacsim.ros2.bridge.ROS2PublishJointState",
            "omni.isaac.ros2_bridge.ROS2PublishJointState",
        ]
        publish_type = None
        for nt in publish_node_types:
            try:
                og.Controller.edit(
                    {"graph_path": "/ActionGraph", "evaluator_name": "execution"},
                    {og.Controller.Keys.CREATE_NODES: [("PublishJointState", nt)]},
                )
                publish_type = nt
                break
            except Exception:
                continue
        if not publish_type:
            print("[RoboLab] WARN: ROS2PublishJointState node type not found. Joint states will not be published.")
            return False

        og.Controller.edit(
            {"graph_path": "/ActionGraph", "evaluator_name": "execution"},
            {
                og.Controller.Keys.CREATE_NODES: [
                    ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
                    ("ReadSimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
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
        print(f"[RoboLab] Joint state publisher configured for {robot_prim_path} on /joint_states")
        return True
    except Exception as err:
        print(f"[RoboLab] WARN: Failed to setup joint state publisher: {err}")
        return False


def setup_joint_state_publisher_omnigraph(robot_prim_path: str) -> bool:
    """Add ROS2 Publish Joint State node via OmniGraph when --moveit. Returns True if successful."""
    try:
        import omni.graph.core as og

        # Node types vary by Isaac Sim version
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
                        ("PublishJointState.inputs:targetPrim", robot_prim_path),
                    ],
                },
            )
            print(f"[RoboLab] Joint state publisher added for {robot_prim_path} on /joint_states")
            return True
        except Exception as e1:
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
                        ("PublishJointState.inputs:targetPrim", robot_prim_path),
                    ],
                },
            )
            print(f"[RoboLab] Joint state publisher added for {robot_prim_path} on /joint_states")
            return True
    except Exception as err:
        print(f"[RoboLab] WARN: Could not add joint state publisher ({err}). Run Isaac Sim with ROS2 bridge and add Joint State publisher manually.")
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


def setup_joint_state_publisher(robot_prim_path: str) -> bool:
    """Add OmniGraph ROS2 Publish Joint State node for MoveIt integration.
    Returns True if setup succeeded."""
    try:
        import omni.graph.core as og
        # Node types vary by Isaac Sim version
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
            except Exception as e:
                continue
        print("[RoboLab] WARN: Could not create ROS2 joint state publisher (no compatible node type)")
        return False
    except Exception as err:
        print(f"[RoboLab] WARN: Joint state publisher setup failed: {err}")
        return False


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
    "headless": args.headless or (not args.vr and not args.webrtc),
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
    from pxr import Gf, UsdGeom, UsdPhysics, UsdLux
    try:
        from pxr import PhysxSchema
    except ImportError:
        PhysxSchema = None

    # Prepare stage and world — use 120 Hz physics for stable articulated contacts.
    world = World(physics_dt=1.0 / 120.0, rendering_dt=1.0 / 60.0)
    env_usd = resolve_usd_path(args.env)
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
            _px.CreateMinPositionIterationCountAttr(16)
            _px.CreateMinVelocityIterationCountAttr(4)
            _px.CreateEnableStabilizationAttr(True)
            print("[RoboLab] PhysX scene: TGS solver, posIter=16, velIter=4, stabilization=ON")
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

    # Anchor environment objects (fridge, dishwasher, etc.) as kinematic so
    # they don't fall through the floor under gravity.
    _env_root = _stage_tmp.GetPrimAtPath("/World/Environment")
    _anchored = 0
    if _env_root and _env_root.IsValid():
        _anchor_stack = list(_env_root.GetChildren())
        while _anchor_stack:
            _ap = _anchor_stack.pop()
            _ap_path = str(_ap.GetPath())
            if _ap.HasAPI(UsdPhysics.RigidBodyAPI):
                _rb = UsdPhysics.RigidBodyAPI(_ap)
                _rb.CreateKinematicEnabledAttr(True)
                _anchored += 1
            else:
                _name_low = _ap.GetName().lower()
                _needs_anchor = any(kw in _name_low for kw in (
                    "fridge", "refrigerator", "dishwasher", "sink", "counter",
                    "table", "shelf", "cabinet", "oven", "microwave", "wall",
                    "floor", "ceiling", "door",
                ))
                if _needs_anchor:
                    UsdPhysics.RigidBodyAPI.Apply(_ap)
                    UsdPhysics.RigidBodyAPI(_ap).CreateKinematicEnabledAttr(True)
                    _anchored += 1
                else:
                    _anchor_stack.extend(_ap.GetChildren())
    print(f"[RoboLab] Anchored {_anchored} environment prims as kinematic")

    # Spawn diverse graspable objects on table surfaces when --spawn-objects is set.
    _spawned_objects = []
    if args.spawn_objects:
        import random as _rng
        _obj_dir = Path(args.objects_dir)
        _obj_usds = []
        if _obj_dir.exists():
            for _ext in ("*.usd", "*.usdc", "*.usdz"):
                _obj_usds.extend(_obj_dir.glob(_ext))
        if not _obj_usds:
            _builtin_shapes = ["Cube", "Cylinder", "Sphere", "Cone"]
            print(f"[RoboLab] No object USDs in {_obj_dir}, spawning built-in shapes as graspable objects")
            for _si, _shape in enumerate(_builtin_shapes):
                _obj_path = f"/World/GraspableObjects/{_shape}_{_si}"
                _xoff = 0.8 + _si * 0.15
                _yoff = -0.7 + (_si % 2) * 0.15
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
                _xf.AddTranslateOp().Set(Gf.Vec3d(_xoff, _yoff, 0.85))
                _xf.AddScaleOp().Set(Gf.Vec3f(_scale, _scale, _scale))
                UsdPhysics.RigidBodyAPI.Apply(_obj_prim)
                UsdPhysics.CollisionAPI.Apply(_obj_prim)
                UsdPhysics.MassAPI.Apply(_obj_prim).CreateMassAttr(0.2)
                add_update_semantics(_obj_prim, _shape.lower())
                _spawned_objects.append((_obj_path, _shape.lower()))
                print(f"[RoboLab]   spawned built-in: {_obj_path}")
        else:
            _rng.shuffle(_obj_usds)
            _to_spawn = _obj_usds[:6]
            for _si, _obj_usd in enumerate(_to_spawn):
                _obj_name = _obj_usd.stem
                _obj_path = f"/World/GraspableObjects/{_obj_name}_{_si}"
                stage_utils.add_reference_to_stage(
                    usd_path=str(_obj_usd), prim_path=_obj_path,
                )
                _obj_prim = _stage_tmp.GetPrimAtPath(_obj_path)
                if _obj_prim.IsValid():
                    _xf = UsdGeom.Xformable(_obj_prim)
                    _xoff = 0.7 + _si * 0.12
                    _yoff = -0.7 + (_si % 3) * 0.12
                    _xf.AddTranslateOp().Set(Gf.Vec3d(_xoff, _yoff, 0.85))
                    if not _obj_prim.HasAPI(UsdPhysics.RigidBodyAPI):
                        UsdPhysics.RigidBodyAPI.Apply(_obj_prim)
                    if not _obj_prim.HasAPI(UsdPhysics.CollisionAPI):
                        UsdPhysics.CollisionAPI.Apply(_obj_prim)
                    add_update_semantics(_obj_prim, _obj_name)
                    _spawned_objects.append((_obj_path, _obj_name))
                    print(f"[RoboLab]   spawned: {_obj_path} from {_obj_usd.name}")
        print(f"[RoboLab] Spawned {len(_spawned_objects)} graspable objects")

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

    # Stabilize known problematic Tiago rigid-body mass/inertia values that can
    # cause immediate toppling in PhysX.
    mass_overrides = {
        f"{tiago_prim_path}/tiago_dual_functional/base_footprint": (45.0, Gf.Vec3f(2.5, 2.5, 2.5)),
        f"{tiago_prim_path}/tiago_dual_functional/gemini2_link": (0.5, Gf.Vec3f(0.01, 0.01, 0.01)),
        f"{tiago_prim_path}/tiago_dual_functional/wheel_front_left_link/mecanum_wheel_fl/wheel_link": (
            1.0,
            Gf.Vec3f(0.01, 0.01, 0.01),
        ),
        f"{tiago_prim_path}/tiago_dual_functional/wheel_front_right_link/mecanum_wheel_fr/wheel_link": (
            1.0,
            Gf.Vec3f(0.01, 0.01, 0.01),
        ),
        f"{tiago_prim_path}/tiago_dual_functional/wheel_rear_left_link/mecanum_wheel_rl/wheel_link": (
            1.0,
            Gf.Vec3f(0.01, 0.01, 0.01),
        ),
        f"{tiago_prim_path}/tiago_dual_functional/wheel_rear_right_link/mecanum_wheel_rr/wheel_link": (
            1.0,
            Gf.Vec3f(0.01, 0.01, 0.01),
        ),
    }
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

    # Replicator streams for rgb/depth/pointcloud/semantics.
    replicator_dir = os.path.join(args.output_dir, "replicator_data")
    camera_parent_prim = args.robot_pov_camera_prim or tiago_prim_path
    if not stage.GetPrimAtPath(camera_parent_prim).IsValid():
        print(f"[RoboLab] WARN: POV parent prim '{camera_parent_prim}' not found, falling back to {tiago_prim_path}")
        camera_parent_prim = tiago_prim_path

    # Camera setup: VR mode mounts camera at robot head for operator POV.
    # Non-VR mode uses a world-fixed overview camera for recording.
    if args.vr:
        head_link = f"{tiago_prim_path}/tiago_dual_functional/head_2_link"
        if not stage.GetPrimAtPath(head_link).IsValid():
            head_link = camera_parent_prim
        head_camera = rep.create.camera(
            position=(0.05, 0, 0.05), look_at=(1, 0, 0), parent=head_link
        )
        camera_parent_prim = head_link
        print(f"[RoboLab] VR head camera mounted at {head_link}")
    elif camera_parent_prim == tiago_prim_path:
        head_camera = rep.create.camera(position=(3.0, -3.0, 2.0), look_at=(0.0, 0.0, 1.0))
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
    writer.attach([render_product])
    print(f"[RoboLab] Replicator subsample={_rep_subsample} (capture every {_rep_subsample} frames, with pointcloud)")

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

    # Pin the articulation root as a fixed base BEFORE world.reset() so PhysX
    # builds the articulation tree with the root body locked to the world frame.
    try:
        from pxr import Sdf
        _art_prim = stage.GetPrimAtPath(tiago_articulation_path)
        if _art_prim.IsValid():
            _fb_attr = _art_prim.GetAttribute("physxArticulation:fixedBase")
            if _fb_attr and _fb_attr.IsValid():
                _fb_attr.Set(True)
            else:
                _art_prim.CreateAttribute("physxArticulation:fixedBase", Sdf.ValueTypeNames.Bool).Set(True)
            print(f"[RoboLab] Set articulation fixedBase=True at {tiago_articulation_path}")
    except Exception as err:
        print(f"[RoboLab] WARN: failed to set fixedBase: {err}")

    # Force a stable startup pose BEFORE world.reset().
    try:
        tiago_xform = XFormPrim(prim_path=tiago_prim_path, name="tiago_root_pose")
        tiago_xform.set_world_pose(
            position=np.array([1.0, -1.0, 0.08], dtype=np.float32),
            orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        )
        print("[RoboLab] Applied startup pose: pos=(1.0, -1.0, 0.08) orientation=identity")
    except Exception as err:
        print(f"[RoboLab] WARN: failed to apply startup pose stabilization: {err}")

    world.reset()
    simulation_app.update()

    # Set initial joint position targets via ArticulationAction before warm-up.
    # This makes PD drives actively hold the robot in its startup configuration.
    if tiago_articulation:
        try:
            from omni.isaac.core.utils.types import ArticulationAction
            _get_pos = getattr(tiago_articulation, "get_joint_positions", None) or getattr(
                tiago_articulation, "get_dof_positions", None
            )
            _set_vel = getattr(tiago_articulation, "set_joint_velocities", None) or getattr(
                tiago_articulation, "set_dof_velocities", None
            )
            _cur_pos = _as_list(_get_pos()) if _get_pos else []
            if _cur_pos:
                tiago_articulation.apply_action(
                    ArticulationAction(joint_positions=np.array(_cur_pos, dtype=np.float32))
                )
                print(f"[RoboLab] Set {len(_cur_pos)} initial joint position targets")
            if _set_vel and _cur_pos:
                _set_vel([0.0] * len(_cur_pos))
                print(f"[RoboLab] Zeroed {len(_cur_pos)} initial joint velocities")
        except Exception as err:
            print(f"[RoboLab] WARN: failed to set initial joint targets: {err}")

    # Run physics warm-up steps so the robot and environment settle fully
    # before data collection. 200 steps at 1/120s ≈ 1.67s of simulated time.
    for _ in range(200):
        world.step(render=False)

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
        except Exception as err:
            print(f"[RoboLab] WARN: failed to zero startup articulation velocities: {err}")

    # Joint drive tuning: set stiffness/damping on each revolute/prismatic drive
    # to prevent oscillation and overshooting during trajectory playback.
    if tiago_articulation:
        _DRIVE_CONFIG = {
            "torso_lift_joint": (5000.0, 1000.0),
            "arm_1_joint": (2000.0, 400.0),
            "arm_2_joint": (2000.0, 400.0),
            "arm_3_joint": (2000.0, 400.0),
            "arm_4_joint": (2000.0, 400.0),
            "arm_5_joint": (1000.0, 200.0),
            "arm_6_joint": (1000.0, 200.0),
            "arm_7_joint": (1000.0, 200.0),
            "head_1_joint": (500.0, 100.0),
            "head_2_joint": (500.0, 100.0),
            "gripper_left_joint": (500.0, 100.0),
            "gripper_right_joint": (500.0, 100.0),
        }
        _DEFAULT_DRIVE = (1000.0, 200.0)
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
            _stiff, _damp = _DRIVE_CONFIG.get(_jname, _DEFAULT_DRIVE)
            _drive_api = UsdPhysics.DriveAPI.Apply(_jp, "angular" if _rev else "linear")
            _drive_api.CreateStiffnessAttr(_stiff)
            _drive_api.CreateDampingAttr(_damp)
            _drive_count += 1
        print(f"[RoboLab] Configured drives on {_drive_count} joints (stiffness+damping)")

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
        return aliases

    moveit_joint_aliases = _build_moveit_joint_aliases(dof_names)
    moveit_state_joint_names = fallback_moveit_joint_names + ["head_1_joint", "head_2_joint"]
    moveit_joint_limits = {
        "torso_lift_joint": (0.0, 0.35),
        "arm_1_joint": (-2.9, 2.9),
        "arm_2_joint": (-2.0, 2.0),
        "arm_3_joint": (-3.6, 1.8),
        "arm_4_joint": (-0.8, 2.5),
        "arm_5_joint": (-2.2, 2.2),
        "arm_6_joint": (-1.5, 1.5),
        "arm_7_joint": (-2.2, 2.2),
        "head_1_joint": (-1.4, 1.4),
        "head_2_joint": (-1.2, 0.9),
    }

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

    def _apply_joint_positions(joint_values: dict) -> bool:
        """Apply joint targets via ArticulationAction (PD position drive).

        This sets drive targets instead of teleporting joints, so the physics
        engine smoothly tracks the desired configuration without creating
        reaction forces that destabilise the base.
        """
        if not tiago_articulation or not joint_values:
            return False
        try:
            from omni.isaac.core.utils.types import ArticulationAction
        except ImportError:
            pass
        try:
            get_pos = getattr(tiago_articulation, "get_joint_positions", None) or getattr(
                tiago_articulation, "get_dof_positions", None
            )
            if not get_pos:
                return False
            current = _as_list(get_pos())
            if not current:
                return False
            targets = list(current)
            index_map = {n: i for i, n in enumerate(dof_names)}
            updated_any = False
            for name, value in joint_values.items():
                resolved_name = _resolve_joint_name(name)
                idx = index_map.get(resolved_name)
                if idx is None or idx >= len(targets):
                    continue
                normalized = _normalize_joint_target(resolved_name, float(value))
                targets[idx] = normalized
                updated_any = True
            if not updated_any:
                return False
            for i, joint_name in enumerate(dof_names):
                if i >= len(targets):
                    continue
                targets[i] = _normalize_joint_target(joint_name, float(targets[i]))
            action = ArticulationAction(joint_positions=np.array(targets, dtype=np.float32))
            tiago_articulation.apply_action(action)
            return True
        except Exception as exc:
            print(f"[RoboLab] WARN: _apply_joint_positions failed: {exc}")
            return False

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
                points = goal["points"]
                next_idx = goal["next_point_idx"]
                start_wall = goal["start_wall"] or now
                elapsed_wall = now - start_wall

                latest_targets = None
                while next_idx < len(points) and (points[next_idx]["t"] / time_scale) <= elapsed_wall + 1e-4:
                    latest_targets = points[next_idx]["targets"]
                    next_idx += 1

                if latest_targets:
                    merged_targets.update(latest_targets)

                goal["next_point_idx"] = next_idx
                if next_idx >= len(points):
                    goal["status"] = "succeeded"
                    done_goals.append(goal)

            if merged_targets:
                ok = _apply_joint_positions(merged_targets)
                if not ok:
                    for goal in active_trajectory_goals:
                        if goal not in done_goals:
                            goal["status"] = "failed"
                            goal["error"] = "Failed to apply articulation joint targets"
                            done_goals.append(goal)

            for goal in done_goals:
                if goal in active_trajectory_goals:
                    active_trajectory_goals.remove(goal)
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
    print("[RoboLab] Starting simulation loop...")

    while simulation_app.is_running():
        elapsed = time.time() - start_time
        if elapsed >= args.duration:
            break

        # Apply queued trajectory points from action callbacks in simulation thread.
        _process_trajectory_dispatcher()

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
                telemetry_data.append({
                    "timestamp": elapsed,
                    "robot_position": {
                        "x": float(robot_pose["position"][0]),
                        "y": float(robot_pose["position"][1]),
                        "z": float(robot_pose["position"][2]),
                    },
                })
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

        frame_record = {
            "timestamp": elapsed,
            "map_frame": "map",
            "robot_pose": robot_pose,
            "robot_joints": joint_snapshot,
            "world_poses": world_poses,
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

    video_path = os.path.join(args.output_dir, "camera_0.mp4")
    encode_video_from_rgb(replicator_dir, video_path)

    manifest_path = os.path.join(args.output_dir, "dataset_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(build_output_manifest(args.output_dir), f, indent=2)

    print(f"[RoboLab] Dataset saved: {dataset_path}")
    print(f"[RoboLab] Telemetry saved: {telemetry_path}")
    print(f"[RoboLab] Video saved: {video_path}")
    print(f"[RoboLab] Manifest saved: {manifest_path}")

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
