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
        default="2.5,-2.0,2.0",
        help="External camera position as x,y,z (default: 2.5,-2.0,2.0).",
    )
    parser.add_argument(
        "--external-camera-target",
        type=str,
        default="0.0,0.0,0.8",
        help="External camera look-at target as x,y,z (default: 0.0,0.0,0.8).",
    )
    parser.add_argument(
        "--task-label",
        type=str,
        default="",
        help="Task label/intent name for this episode (e.g. pick_from_table).",
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

    # Per-scene spawn zones: table bounding boxes in world coordinates.
    # Each zone is (x_min, x_max, y_min, y_max). Objects are scattered
    # within these bounds and raycasted downward to find the table surface.
    _SCENE_SPAWN_ZONES = {
        "Kitchen":        [(0.4, 1.2, -1.0, -0.4)],
        "L_Kitchen":      [(0.4, 1.2, -1.0, -0.4)],
        "Modern_Kitchen": [(0.4, 1.2, -1.0, -0.4)],
        "Small_House":    [(0.3, 1.0, -1.2, -0.5)],
    }
    _DEFAULT_SPAWN_ZONE = [(0.4, 1.2, -1.0, -0.4)]

    def _get_spawn_zones():
        """Pick spawn zones based on the scene USD path."""
        _scene_path = str(getattr(args, "env_usd", "") or "")
        for _key, _zones in _SCENE_SPAWN_ZONES.items():
            if _key.lower() in _scene_path.lower():
                return _zones
        return _DEFAULT_SPAWN_ZONE

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
        if not _all_usds:
            _builtin_shapes = ["Cube", "Cylinder", "Sphere", "Cone"]
            print(f"[RoboLab] No object USDs found, spawning built-in shapes as graspable objects")
            _spawn_zones = _get_spawn_zones()
            for _si, _shape in enumerate(_builtin_shapes):
                _obj_path = f"/World/GraspableObjects/{_shape}_{_si}"
                _zone = _spawn_zones[_si % len(_spawn_zones)]
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
                add_update_semantics(_obj_prim, _shape.lower())
                _spawned_objects.append((_obj_path, _shape.lower()))
                print(f"[RoboLab]   spawned built-in: {_obj_path}")
        else:
            _rng.shuffle(_all_usds)
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
                    _xoff = _rng.uniform(_zone[0], _zone[1])
                    _yoff = _rng.uniform(_zone[2], _zone[3])
                    _xf.AddTranslateOp().Set(Gf.Vec3d(_xoff, _yoff, 3.0))
                    if not _obj_prim.HasAPI(UsdPhysics.RigidBodyAPI):
                        UsdPhysics.RigidBodyAPI.Apply(_obj_prim)
                    if not _obj_prim.HasAPI(UsdPhysics.CollisionAPI):
                        UsdPhysics.CollisionAPI.Apply(_obj_prim)
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
            for _mid in ["/tiago_dual_functional", ""]:
                for _name in _wrist_candidates:
                    _cand = f"{_base}{_mid}/{_name}"
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
        _ext_pos = tuple(float(x) for x in args.external_camera_pos.split(","))
        _ext_tgt = tuple(float(x) for x in args.external_camera_target.split(","))
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
    try:
        from pxr import Sdf
        _art_prim = stage.GetPrimAtPath(tiago_articulation_path)
        if _art_prim.IsValid():
            _fb_attr = _art_prim.GetAttribute("physxArticulation:fixedBase")
            if _fb_attr and _fb_attr.IsValid():
                _fb_attr.Set(_use_fixed_base)
            else:
                _art_prim.CreateAttribute("physxArticulation:fixedBase", Sdf.ValueTypeNames.Bool).Set(_use_fixed_base)
            print(f"[RoboLab] Set articulation fixedBase={_use_fixed_base} at {tiago_articulation_path}")
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
            "arm_right_1_joint": (2000.0, 400.0),
            "arm_right_2_joint": (2000.0, 400.0),
            "arm_right_3_joint": (2000.0, 400.0),
            "arm_right_4_joint": (2000.0, 400.0),
            "arm_right_5_joint": (1000.0, 200.0),
            "arm_right_6_joint": (1000.0, 200.0),
            "arm_right_7_joint": (1000.0, 200.0),
            "arm_left_1_joint": (2000.0, 400.0),
            "arm_left_2_joint": (2000.0, 400.0),
            "arm_left_3_joint": (2000.0, 400.0),
            "arm_left_4_joint": (2000.0, 400.0),
            "arm_left_5_joint": (1000.0, 200.0),
            "arm_left_6_joint": (1000.0, 200.0),
            "arm_left_7_joint": (1000.0, 200.0),
            "head_1_joint": (500.0, 100.0),
            "head_2_joint": (500.0, 100.0),
            "gripper_right_left_finger_joint": (5000.0, 800.0),
            "gripper_right_right_finger_joint": (5000.0, 800.0),
            "gripper_left_left_finger_joint": (5000.0, 800.0),
            "gripper_left_right_finger_joint": (5000.0, 800.0),
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
            _drive_type = "angular" if _rev else "linear"
            _drive_api = UsdPhysics.DriveAPI.Apply(_jp, _drive_type)
            _drive_api.CreateTypeAttr("force")
            _drive_api.CreateStiffnessAttr().Set(_stiff)
            _drive_api.CreateDampingAttr().Set(_damp)
            _drive_api.CreateMaxForceAttr().Set(1000.0)
            _drive_count += 1
        print(f"[RoboLab] Configured drives on {_drive_count} joints (stiffness+damping+maxForce)")

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
    _gripper_left_prim_path = None
    _gripper_right_prim_path = None
    if tiago_articulation:
        try:
            from pxr import PhysxSchema

            def _find_gripper_link(link_name):
                """Search for a gripper link prim across common Tiago USD structures."""
                _search_bases = [tiago_articulation_path, tiago_prim_path]
                _search_mids = ["", "/tiago_dual_functional"]
                for _base in _search_bases:
                    for _mid in _search_mids:
                        _path = f"{_base}{_mid}/{link_name}"
                        _pr = stage.GetPrimAtPath(_path)
                        if _pr.IsValid():
                            return _path, _pr
                for _p in stage.Traverse():
                    _pn = _p.GetPath().pathString
                    if _pn.startswith(tiago_prim_path) and _pn.endswith(f"/{link_name}"):
                        return _pn, _p
                return None, None

            _gripper_left_prim_path, _gl_prim = _find_gripper_link("gripper_left_link")
            _gripper_right_prim_path, _gr_prim = _find_gripper_link("gripper_right_link")

            if _gripper_left_prim_path:
                print(f"[RoboLab] Found gripper_left_link: {_gripper_left_prim_path}")
            if _gripper_right_prim_path:
                print(f"[RoboLab] Found gripper_right_link: {_gripper_right_prim_path}")

            if _gl_prim is not None and _gr_prim is not None:
                for _fp, _fn in [(_gripper_left_prim_path, "left"), (_gripper_right_prim_path, "right")]:
                    _fp_prim = stage.GetPrimAtPath(_fp)
                    if not _fp_prim.HasAPI(PhysxSchema.PhysxContactReportAPI):
                        PhysxSchema.PhysxContactReportAPI.Apply(_fp_prim)
                        PhysxSchema.PhysxContactReportAPI(_fp_prim).CreateThresholdAttr(0.0)

                import omni.kit.commands
                from pxr import Gf

                omni.kit.commands.execute(
                    "IsaacSensorCreateContactSensor",
                    path="Contact_Sensor",
                    parent=_gripper_left_prim_path,
                    sensor_period=0,
                    min_threshold=0.0,
                    max_threshold=100000.0,
                    translation=Gf.Vec3d(0, 0, 0),
                )
                omni.kit.commands.execute(
                    "IsaacSensorCreateContactSensor",
                    path="Contact_Sensor",
                    parent=_gripper_right_prim_path,
                    sensor_period=0,
                    min_threshold=0.0,
                    max_threshold=100000.0,
                    translation=Gf.Vec3d(0, 0, 0),
                )

                _contact_sensor_left = f"{_gripper_left_prim_path}/Contact_Sensor"
                _contact_sensor_right = f"{_gripper_right_prim_path}/Contact_Sensor"

                from isaacsim.sensors.physics import _sensor
                _contact_sensor_interface = _sensor.acquire_contact_sensor_interface()

                print(f"[RoboLab] Contact sensors created on gripper fingers: "
                      f"{_contact_sensor_left}, {_contact_sensor_right}")
            else:
                print("[RoboLab] WARN: gripper finger links not found, contact sensors disabled")
        except Exception as err:
            print(f"[RoboLab] WARN: failed to create contact sensors: {err}")

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

    _apply_logged_once: set = set()

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
            _resolved_joints = []
            _skipped_joints = []
            for name, value in joint_values.items():
                resolved_name = _resolve_joint_name(name)
                idx = index_map.get(resolved_name)
                if idx is None or idx >= len(targets):
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

    _persistent_targets: dict = {}

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
                _persistent_targets.update(merged_targets)

            if _persistent_targets:
                ok = _apply_joint_positions(_persistent_targets)
                if not ok and merged_targets:
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
            "cameras": {
                "camera_0": {"type": "head", "dir": "replicator_data", "video": "camera_0.mp4"},
                **({"camera_1_wrist": {"type": "wrist", "parent_link": "arm_tool_link", "dir": "replicator_wrist", "video": "camera_1_wrist.mp4"}} if _wrist_camera else {}),
                **({"camera_2_external": {"type": "external", "position": list(tuple(float(x) for x in args.external_camera_pos.split(","))), "dir": "replicator_external", "video": "camera_2_external.mp4"}} if _external_camera else {}),
            },
            "n_cameras": _n_cameras,
            "task_label": args.task_label if args.task_label else "unlabeled",
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

    _GRIPPER_JOINT_NAMES = (
        "gripper_right_left_finger_joint", "gripper_right_right_finger_joint",
    )
    _GRIPPER_GAP_EMPTY = 0.015
    _GRIPPER_GAP_GRASPED = 0.012
    _OBJECT_IN_GRIPPER_RADIUS = 0.25

    _graspable_prim_paths = [p for p, _ in _spawned_objects]
    _graspable_prim_classes = {p: c for p, c in _spawned_objects}

    _gripper_center_paths = [None, None]  # [left_link, right_link] or [tool_link, None]

    def _init_gripper_center_paths():
        """Find gripper link paths for computing gripper center."""
        if _gripper_left_prim_path and _gripper_right_prim_path:
            _gripper_center_paths[0] = _gripper_left_prim_path
            _gripper_center_paths[1] = _gripper_right_prim_path
            print(f"[RoboLab] Gripper center: midpoint of finger links")
            return

        _candidates = [
            f"{tiago_articulation_path}/arm_right_tool_link",
            f"{tiago_articulation_path}/arm_tool_link",
            f"{tiago_articulation_path}/arm_right_7_link",
            f"{tiago_articulation_path}/arm_7_link",
            f"{tiago_prim_path}/tiago_dual_functional/arm_tool_link",
            f"{tiago_prim_path}/tiago_dual_functional/arm_7_link",
            f"{tiago_prim_path}/tiago_dual_functional/arm_right_tool_link",
            f"{tiago_prim_path}/tiago_dual_functional/arm_right_7_link",
            f"{tiago_prim_path}/arm_tool_link",
            f"{tiago_prim_path}/arm_right_tool_link",
            f"{tiago_prim_path}/arm_7_link",
            f"{tiago_prim_path}/arm_right_7_link",
        ]
        for _cl in _candidates:
            try:
                if stage.GetPrimAtPath(_cl).IsValid():
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

    def _get_gripper_center():
        """Return approximate gripper center position."""
        if _gripper_center_paths[0] is None:
            return None
        try:
            if _gripper_center_paths[1] is not None:
                _xf_l = XFormPrim(_gripper_center_paths[0])
                _xf_r = XFormPrim(_gripper_center_paths[1])
                _pl, _ = _xf_l.get_world_pose()
                _pr, _ = _xf_r.get_world_pose()
                if _pl is not None and _pr is not None:
                    return [float((_pl[i] + _pr[i]) / 2.0) for i in range(3)]
            else:
                _xf = XFormPrim(_gripper_center_paths[0])
                _pos, _ = _xf.get_world_pose()
                return _pos.tolist() if _pos is not None else None
        except Exception:
            pass
        return None

    def _find_object_in_gripper(grip_center, gap):
        """Check if any graspable object center is within gripper reach."""
        if grip_center is None or gap > _GRIPPER_GAP_GRASPED:
            return None, None
        gx, gy, gz = grip_center
        best_dist = _OBJECT_IN_GRIPPER_RADIUS
        best_path = None
        for _gp in _graspable_prim_paths:
            try:
                _xf = XFormPrim(_gp)
                _op, _ = _xf.get_world_pose()
                if _op is None:
                    continue
                ox, oy, oz = float(_op[0]), float(_op[1]), float(_op[2])
                dist = ((gx - ox)**2 + (gy - oy)**2 + (gz - oz)**2)**0.5
                if dist < best_dist:
                    best_dist = dist
                    best_path = _gp
            except Exception:
                continue
        if best_path:
            return best_path, _graspable_prim_classes.get(best_path, "unknown")
        return None, None

    print("[RoboLab] Starting simulation loop...")
    _grasp_events.clear()
    _prev_gripper_gap = None
    _prev_gripper_closing = False

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

            # 3. Mobile base: read base_cmd.json and apply velocity to root body.
            if getattr(args, "mobile_base", False) and tiago_articulation:
                try:
                    _base_cmd_file = FJT_PROXY_DIR / "base_cmd.json"
                    if _base_cmd_file.exists():
                        _bcmd = json.loads(_base_cmd_file.read_text(encoding="utf-8"))
                        _vx = float(_bcmd.get("vx", 0.0))
                        _vy = float(_bcmd.get("vy", 0.0))
                        _vyaw = float(_bcmd.get("vyaw", 0.0))
                        if abs(_vx) > 0.001 or abs(_vy) > 0.001 or abs(_vyaw) > 0.001:
                            from omni.isaac.core.prims import XFormPrim as _XFP
                            _root = _XFP(prim_path=tiago_prim_path)
                            _pos, _orient = _root.get_world_pose()
                            import math
                            _qw, _qx, _qy, _qz = float(_orient[0]), float(_orient[1]), float(_orient[2]), float(_orient[3])
                            _yaw = math.atan2(2.0 * (_qw * _qz + _qx * _qy), 1.0 - 2.0 * (_qy * _qy + _qz * _qz))
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
                    _oq_file.unlink()
                    _nearest = None
                    _nearest_dist = float("inf")
                    _gc = _get_gripper_center()
                    for _sp_path, _sp_class in _spawned_objects:
                        try:
                            _sxf = XFormPrim(_sp_path)
                            _sp, _ = _sxf.get_world_pose()
                            if _sp is None:
                                continue
                            _spx = [float(_sp[0]), float(_sp[1]), float(_sp[2])]
                            _d = float("inf")
                            if _gc:
                                _d = sum((_a - _b)**2 for _a, _b in zip(_gc, _spx))**0.5
                            if _d < _nearest_dist:
                                _nearest_dist = _d
                                _nearest = {"path": _sp_path, "class": _sp_class,
                                            "position": [round(v, 4) for v in _spx]}
                        except Exception:
                            continue
                    _resp = _nearest or {"path": None, "class": None, "position": None}
                    _resp["gripper_center"] = [round(v, 4) for v in _gc] if _gc else None
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
                    "gripped_object_stable": _gripped_object_path is not None,
                    "left_finger_contact": _contact_left_in,
                    "right_finger_contact": _contact_right_in,
                    "contact_forces": round(
                        abs(_contact_left_force[0]) + abs(_contact_right_force[0]), 3
                    ) if (_contact_left_force and _contact_right_force) else 0.0,
                }
                _gr_file.write_text(json.dumps(_gr_data), encoding="utf-8")
            except Exception:
                pass

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

        # Grasp state: gripper gap, object detection, event logging.
        _gripper_positions = []
        for _gn in _GRIPPER_JOINT_NAMES:
            _gj = joint_snapshot.get(_gn)
            if _gj:
                _gripper_positions.append(float(_gj["position"]))
        _gripper_gap = sum(_gripper_positions) / len(_gripper_positions) if _gripper_positions else 0.0
        _gap_delta = (_gripper_gap - _prev_gripper_gap) if _prev_gripper_gap is not None else 0.0
        _gripper_closing = _gap_delta < -0.00002
        _gripper_opening = _gap_delta > 0.00002

        _grip_center = _get_gripper_center()
        _obj_in_grip_path, _obj_in_grip_class = _find_object_in_gripper(
            _grip_center, _gripper_gap
        )
        _obj_z = None
        if _obj_in_grip_path:
            _owp = world_poses.get(_obj_in_grip_path, {})
            _opos = _owp.get("position", [])
            _obj_z = float(_opos[2]) if len(_opos) > 2 else None

        _stable = False
        if _obj_in_grip_path and _obj_z is not None and _lift_start_z is not None:
            _stable = _obj_z >= _lift_start_z - 0.02

        # Contact sensor force readings.
        _contact_left_force = [0.0, 0.0, 0.0]
        _contact_right_force = [0.0, 0.0, 0.0]
        _contact_left_in = False
        _contact_right_in = False
        if _contact_sensor_interface and _contact_sensor_left:
            try:
                _cl = _contact_sensor_interface.get_sensor_reading(
                    _contact_sensor_left, use_latest_data=True)
                if _cl.is_valid:
                    _contact_left_in = _cl.in_contact
                    _contact_left_force = [round(float(_cl.value), 3), 0.0, 0.0]
                _cr = _contact_sensor_interface.get_sensor_reading(
                    _contact_sensor_right, use_latest_data=True)
                if _cr.is_valid:
                    _contact_right_in = _cr.in_contact
                    _contact_right_force = [round(float(_cr.value), 3), 0.0, 0.0]
            except Exception:
                pass

        grasp_state = {
            "gripper_gap": round(_gripper_gap, 5),
            "gripper_closing": _gripper_closing,
            "object_in_gripper": _obj_in_grip_class,
            "object_in_gripper_path": _obj_in_grip_path,
            "gripped_object_stable": _stable,
            "contact_forces": {
                "left_finger": _contact_left_force,
                "right_finger": _contact_right_force,
            },
            "left_finger_contact": _contact_left_in,
            "right_finger_contact": _contact_right_in,
        }
        if _grip_center:
            grasp_state["gripper_center"] = [round(c, 4) for c in _grip_center]

        # Event detection.
        if _gripper_closing and not _prev_gripper_closing:
            _grasp_events.append({"frame": _sim_frame_idx, "time": round(elapsed, 3),
                                  "event": "gripper_close_start"})
        if _gripper_opening and _prev_gripper_closing:
            _grasp_events.append({"frame": _sim_frame_idx, "time": round(elapsed, 3),
                                  "event": "gripper_open_start"})

        if (_contact_left_in and _contact_right_in) and _gripper_closing and not any(
            e.get("event") == "contact_detected" and e.get("frame", 0) > _sim_frame_idx - 30
            for e in _grasp_events
        ):
            _contact_force_mag = abs(_contact_left_force[0]) + abs(_contact_right_force[0])
            _grasp_events.append({"frame": _sim_frame_idx, "time": round(elapsed, 3),
                                  "event": "contact_detected",
                                  "object": _obj_in_grip_class or "unknown",
                                  "force": round(_contact_force_mag, 2)})

        if _obj_in_grip_path and _gripped_object_path is None:
            _gripped_object_path = _obj_in_grip_path
            _gripped_object_class = _obj_in_grip_class
            _grip_start_frame = _sim_frame_idx
            _lift_start_z = _obj_z
            _grasp_events.append({"frame": _sim_frame_idx, "time": round(elapsed, 3),
                                  "event": "grasp_confirmed", "object": _obj_in_grip_class,
                                  "gap": round(_gripper_gap, 4)})

        if _gripped_object_path and _obj_z is not None and _lift_start_z is not None:
            if _obj_z > _lift_start_z + 0.05 and not any(
                e.get("event") == "lift_detected" and e.get("object") == _gripped_object_class
                for e in _grasp_events
            ):
                _grasp_events.append({"frame": _sim_frame_idx, "time": round(elapsed, 3),
                                      "event": "lift_detected", "object": _gripped_object_class,
                                      "z": round(_obj_z, 3)})

        if _gripped_object_path and _obj_in_grip_path is None:
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
                                  "z": _dropped_z})
            _gripped_object_path = None
            _gripped_object_class = None
            _lift_start_z = None

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
