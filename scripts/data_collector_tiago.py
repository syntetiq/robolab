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
        default=8.0,
        help="Execution speed multiplier for FollowJointTrajectory playback in Isaac.",
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
    except Exception as err:
        print(f"[RoboLab] WARN: Failed to enable extension {name}: {err}")


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
    "headless": args.headless or (not args.vr),
    "livestream": 2 if args.webrtc else 0,
    "width": args.capture_width,
    "height": args.capture_height,
})

try:
    safe_enable_extension("omni.isaac.core_nodes")
    safe_enable_extension("omni.isaac.ros2_bridge")
    safe_enable_extension("omni.replicator.core")
    safe_enable_extension("omni.replicator.isaac")

    if args.vr:
        safe_enable_extension("omni.kit.xr.profile.vr")
    if args.webrtc:
        import carb

        carb.settings.get_settings().set("/exts/omni.kit.livestream.webrtc/port", 8211)
        print("[RoboLab] WebRTC stream configured on port 8211.")

    simulation_app.update()

    import omni.replicator.core as rep
    import omni.isaac.core.utils.stage as stage_utils
    from omni.isaac.core import World
    from omni.isaac.core.articulations import Articulation
    from omni.isaac.core.prims import XFormPrim
    from omni.isaac.core.utils.semantics import add_update_semantics, get_semantics
    from pxr import UsdGeom, UsdPhysics

    # Prepare stage and world.
    world = World()
    env_usd = resolve_usd_path(args.env)
    stage_utils.add_reference_to_stage(usd_path=env_usd, prim_path="/World/Environment")

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
    head_camera = rep.create.camera(position=(0, 0, 1.35), look_at=(1, 0, 1.15), parent=camera_parent_prim)
    render_product = rep.create.render_product(head_camera, (args.capture_width, args.capture_height))
    writer = rep.WriterRegistry.get("BasicWriter")
    writer.initialize(
        output_dir=replicator_dir,
        rgb=True,
        distance_to_camera=True,
        pointcloud=True,
        semantic_segmentation=True,
    )
    writer.attach([render_product])

    tracked_prims = []
    for prim in stage.Traverse():
        if not prim.HasAPI(UsdGeom.Xformable):
            continue
        semantic = get_semantics(prim)
        if semantic and semantic.get("class") and semantic["class"] != "class":
            tracked_prims.append((str(prim.GetPath()), semantic["class"]))
    print(f"[RoboLab] Tracking {len(tracked_prims)} semantic objects.")

    world.reset()
    simulation_app.update()

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

    # MoveIt bridge path: publish /joint_states directly and host trajectory actions.
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
            js_msg.header.stamp = js_node.get_clock().now().to_msg()
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

    if args.moveit:
        try:
            import rclpy as rclpy_mod
            from sensor_msgs.msg import JointState
            from rclpy.executors import MultiThreadedExecutor

            if not rclpy_mod.ok():
                rclpy_mod.init(args=None)
            js_node = rclpy_mod.create_node("robolab_moveit_bridge")
            js_pub = js_node.create_publisher(JointState, "/joint_states", 10)
            js_msg_type = JointState
            js_node.create_timer(0.05, _publish_joint_state_from_snapshot)
            ros_executor = MultiThreadedExecutor(num_threads=4)
            ros_executor.add_node(js_node)
            ros_executor_thread = threading.Thread(target=ros_executor.spin, daemon=True)
            ros_executor_thread.start()
            print("[RoboLab] Direct /joint_states publisher enabled (MoveIt mode).")
        except Exception as err:
            print(f"[RoboLab] WARN: direct /joint_states publisher unavailable: {err}")

    def _apply_joint_positions(joint_values: dict) -> bool:
        if not tiago_articulation or not joint_values:
            return False
        try:
            get_pos = getattr(tiago_articulation, "get_joint_positions", None) or getattr(
                tiago_articulation, "get_dof_positions", None
            )
            set_pos = getattr(tiago_articulation, "set_joint_positions", None) or getattr(
                tiago_articulation, "set_dof_positions", None
            )
            if not get_pos or not set_pos:
                return False
            current = _as_list(get_pos())
            if not current:
                return False
            index_map = {n: i for i, n in enumerate(dof_names)}
            update_indices = []
            update_values = []
            for name, value in joint_values.items():
                resolved_name = _resolve_joint_name(name)
                idx = index_map.get(resolved_name)
                if idx is None or idx >= len(current):
                    continue
                normalized = _normalize_joint_target(resolved_name, float(value))
                update_indices.append(idx)
                update_values.append(normalized)
            if not update_indices:
                return False
            for idx, value in zip(update_indices, update_values):
                current[idx] = value
            # PhysX revolute drive targets must stay within [-2pi, 2pi].
            for i, joint_name in enumerate(dof_names):
                if i >= len(current):
                    continue
                current[i] = _normalize_joint_target(joint_name, float(current[i]))
            set_pos(current)
            return True
        except Exception:
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
                    ok = _apply_joint_positions(latest_targets)
                    if not ok:
                        goal["status"] = "failed"
                        goal["error"] = "Failed to apply articulation joint targets"
                        done_goals.append(goal)
                        continue

                goal["next_point_idx"] = next_idx
                if next_idx >= len(points):
                    goal["status"] = "succeeded"
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

    if args.moveit and tiago_articulation and js_node:
        try:
            try:
                from control_msgs.action import FollowJointTrajectory
            except Exception:
                ros2_dll_dir = Path(args.ros2_dll_dir)
                if os.name == "nt" and ros2_dll_dir.exists():
                    try:
                        os.add_dll_directory(str(ros2_dll_dir))
                    except Exception:
                        pass
                    if str(ros2_dll_dir) not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = f"{ros2_dll_dir};{os.environ.get('PATH', '')}"
                ros2_site = Path(args.ros2_site_packages)
                if ros2_site.exists():
                    ros2_site_str = str(ros2_site)
                    if ros2_site_str not in sys.path:
                        sys.path.append(ros2_site_str)
                    from control_msgs.action import FollowJointTrajectory
                else:
                    raise
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

                    if goal_state["status"] == "succeeded":
                        result.error_code = FollowJointTrajectory.Result.SUCCESSFUL
                        result.error_string = ""
                        goal_handle.succeed()
                        print(f"[RoboLab] {controller_name} trajectory executed ({len(parsed_points)} points)")
                        return result

                    result.error_code = FollowJointTrajectory.Result.PATH_TOLERANCE_VIOLATED
                    result.error_string = goal_state.get("error", "Trajectory execution failed")
                    goal_handle.abort()
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
    if args.moveit and tiago_articulation and not js_pub:
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
            "joint_source": "articulation_api" if tiago_articulation else "synthetic_fallback",
            "vr_teleop_enabled": bool(args.vr),
            "moveit_mode_enabled": bool(args.moveit),
            "robot_pov_camera_prim": camera_parent_prim,
        },
        "frames": [],
        "joint_trajectories": [],
    }

    telemetry_data = []
    start_time = time.time()
    print("[RoboLab] Starting simulation loop...")

    while simulation_app.is_running():
        elapsed = time.time() - start_time
        if elapsed >= args.duration:
            break

        # Apply queued trajectory points from action callbacks in simulation thread.
        _process_trajectory_dispatcher()
        world.step(render=False)
        rep.orchestrator.step(rt_subframes=1)

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

        # Robot base pose in map frame.
        robot_pose = {"position": [], "orientation": []}
        try:
            robot_prim = XFormPrim(tiago_prim_path)
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
