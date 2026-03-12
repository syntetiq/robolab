"""
Clean Robot Test Bench
======================
Standalone Isaac Sim script for testing TIAGo robot models in a minimal scene.
No MoveIt, no ROS2, no bridge -- pure Isaac Sim + PhysX.

Usage:
    python.bat scripts/test_robot_bench.py --all-models --output C:\\RoboLab_Data\\bench
    python.bat scripts/test_robot_bench.py --model heavy --output C:\\RoboLab_Data\\bench
    python.bat scripts/test_robot_bench.py --model light --no-video --output C:\\RoboLab_Data\\bench
"""

import argparse
import glob
import json
import math
import os
import sys
import time

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Clean Robot Test Bench")
parser.add_argument("--model", type=str, default="heavy",
                    choices=["heavy", "light", "urdf"],
                    help="Robot model to test (default: heavy)")
parser.add_argument("--all-models", action="store_true",
                    help="Test all 3 models sequentially")
parser.add_argument("--output", type=str, default=r"C:\RoboLab_Data\bench",
                    help="Output directory for logs and videos")
parser.add_argument("--no-video", action="store_true",
                    help="Skip video recording (faster)")
parser.add_argument("--headless", action="store_true", default=True,
                    help="Run headless (default: True)")
parser.add_argument("--duration", type=float, default=25.0,
                    help="Total test duration in seconds")
parser.add_argument("--tiago-dir", type=str,
                    default=r"C:\RoboLab_Data\data\tiago_isaac",
                    help="Directory containing TIAGo USD files")
parser.add_argument("--width", type=int, default=640)
parser.add_argument("--height", type=int, default=480)
parser.add_argument("--drive-base", action="store_true",
                    help="Enable base driving (unfixes base, uses wheel velocity control)")
parser.add_argument("--drive-distance", type=float, default=1.0,
                    help="Distance to drive forward/backward in meters (default: 1.0)")
parser.add_argument("--drive-speed", type=float, default=0.3,
                    help="Base drive speed in m/s (default: 0.3, PAL max=1.0)")
parser.add_argument("--choreo", action="store_true",
                    help="Run choreography sequence (implies --drive-base)")
args, _unknown = parser.parse_known_args()

if args.choreo:
    args.drive_base = True

MODEL_FILES = {
    "heavy": "tiago_dual_functional.usd",
    "light": "tiago_dual_functional_light.usd",
    "urdf":  "tiago_dual_urdf_imported.usd",
}

MODELS_TO_TEST = list(MODEL_FILES.keys()) if args.all_models else [args.model]

# ---------------------------------------------------------------------------
# Isaac Sim bootstrap
# ---------------------------------------------------------------------------
from isaacsim import SimulationApp

simulation_app = SimulationApp({
    "headless": args.headless,
    "width": args.width,
    "height": args.height,
})

try:
    import omni.kit.app
    ext_mgr = omni.kit.app.get_app().get_extension_manager()
    ext_mgr.set_extension_enabled_immediate("omni.replicator.core", True)
    ext_mgr.set_extension_enabled_immediate("omni.replicator.isaac", True)
except Exception as e:
    print(f"[Bench] WARN: extension enable failed: {e}")

simulation_app.update()

import numpy as np
import omni.replicator.core as rep
import omni.isaac.core.utils.stage as stage_utils
from omni.isaac.core import World
from omni.isaac.core.articulations import Articulation
from omni.isaac.core.prims import XFormPrim
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade

try:
    from pxr import PhysxSchema
except ImportError:
    PhysxSchema = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def quat_to_euler(w, x, y, z):
    """Quaternion (w,x,y,z) -> (roll, pitch, yaw) in degrees."""
    sinr_cosp = 2.0 * (w * x + y * z)
    cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.asin(sinp)

    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def encode_video(replicator_dir, output_path):
    """Encode RGB PNGs from replicator output into MP4."""
    rgb_files = sorted(
        glob.glob(os.path.join(replicator_dir, "**", "rgb_*.png"), recursive=True),
        key=lambda f: int("".join(c for c in os.path.basename(f) if c.isdigit()) or "0"),
    )
    if not rgb_files:
        print(f"[Bench] No RGB frames in {replicator_dir}")
        return False
    try:
        import imageio.v2 as imageio
        print(f"[Bench] Encoding {len(rgb_files)} frames -> {output_path}")
        with imageio.get_writer(output_path, fps=30) as writer:
            for fp in rgb_files:
                writer.append_data(imageio.imread(fp))
        return True
    except Exception as e:
        print(f"[Bench] WARN: video encode failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Scene builder
# ---------------------------------------------------------------------------
def build_clean_scene():
    """Build a minimal 5x5m test scene with floor, lights, and coordinate axes."""
    stage = stage_utils.get_current_stage()

    # -- Visible floor, top at z=0 --
    floor_size = 10.0 if args.drive_base else 5.0
    floor_path = "/World/Floor"
    if not stage.GetPrimAtPath(floor_path).IsValid():
        floor = UsdGeom.Cube.Define(stage, floor_path)
        floor.CreateSizeAttr(1.0)
        floor.AddScaleOp().Set(Gf.Vec3f(floor_size, floor_size, 0.02))
        floor.AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.01))
        floor.CreateDisplayColorAttr([(0.35, 0.35, 0.38)])
        UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(floor_path))
        if PhysxSchema:
            PhysxSchema.PhysxCollisionAPI.Apply(stage.GetPrimAtPath(floor_path))
        # Add friction material for wheel traction
        mat_path = "/World/FloorMaterial"
        if not stage.GetPrimAtPath(mat_path).IsValid():
            UsdShade.Material.Define(stage, mat_path)
            mat_prim = stage.GetPrimAtPath(mat_path)
            UsdPhysics.MaterialAPI.Apply(mat_prim)
            mat_prim.CreateAttribute("physics:staticFriction", Sdf.ValueTypeNames.Float).Set(0.8)
            mat_prim.CreateAttribute("physics:dynamicFriction", Sdf.ValueTypeNames.Float).Set(0.6)
            mat_prim.CreateAttribute("physics:restitution", Sdf.ValueTypeNames.Float).Set(0.01)
        floor_prim = stage.GetPrimAtPath(floor_path)
        if not floor_prim.HasRelationship("material:binding"):
            UsdShade.MaterialBindingAPI.Apply(floor_prim).Bind(
                UsdShade.Material(stage.GetPrimAtPath(mat_path)))
        print(f"[Bench] Floor: {floor_size}x{floor_size}m visible gray, collision + friction enabled")

    # -- Dome light --
    dome_path = "/World/DomeLight"
    if not stage.GetPrimAtPath(dome_path).IsValid():
        dome = UsdLux.DomeLight.Define(stage, dome_path)
        dome.CreateIntensityAttr(1000.0)

    # -- Distant light from above --
    dist_path = "/World/DistantLight"
    if not stage.GetPrimAtPath(dist_path).IsValid():
        dist = UsdLux.DistantLight.Define(stage, dist_path)
        dist.CreateIntensityAttr(500.0)
        dist.CreateAngleAttr(0.53)
        xf = UsdGeom.Xformable(dist.GetPrim())
        xf.AddRotateXYZOp().Set(Gf.Vec3f(-45, 30, 0))

    # -- Coordinate axes (thin cylinders, 1m each) --
    axis_defs = [
        ("AxisX", (0.5, 0, 0), (0, 90, 0), (0.9, 0.1, 0.1)),
        ("AxisY", (0, 0.5, 0), (90, 0, 0), (0.1, 0.9, 0.1)),
        ("AxisZ", (0, 0, 0.5), (0, 0, 0),  (0.1, 0.1, 0.9)),
    ]
    for name, pos, rot, color in axis_defs:
        ax_path = f"/World/{name}"
        if not stage.GetPrimAtPath(ax_path).IsValid():
            cyl = UsdGeom.Cylinder.Define(stage, ax_path)
            cyl.CreateRadiusAttr(0.005)
            cyl.CreateHeightAttr(1.0)
            cyl.CreateDisplayColorAttr([color])
            xf = UsdGeom.Xformable(cyl.GetPrim())
            xf.AddTranslateOp().Set(Gf.Vec3d(*pos))
            xf.AddRotateXYZOp().Set(Gf.Vec3f(*rot))

    # -- Physics scene --
    phys_path = "/World/PhysicsScene"
    if not stage.GetPrimAtPath(phys_path).IsValid():
        UsdPhysics.Scene.Define(stage, phys_path)
    phys_prim = stage.GetPrimAtPath(phys_path)
    phys_api = UsdPhysics.Scene(phys_prim)
    phys_api.CreateGravityDirectionAttr(Gf.Vec3f(0, 0, -1))
    phys_api.CreateGravityMagnitudeAttr(9.81)
    if PhysxSchema:
        px = PhysxSchema.PhysxSceneAPI.Apply(phys_prim)
        px.CreateSolverTypeAttr("TGS")
        px.CreateMinPositionIterationCountAttr(64)
        px.CreateMinVelocityIterationCountAttr(4)
        px.CreateEnableStabilizationAttr(True)
        try:
            px.CreateSleepThresholdAttr(0.00005)
            px.CreateStabilizationThresholdAttr(0.00001)
        except AttributeError:
            pass

    print("[Bench] Scene built: floor, lights, axes, physics")


# ---------------------------------------------------------------------------
# Camera setup
# ---------------------------------------------------------------------------
def setup_cameras(output_dir, width, height):
    """Create 3 cameras: front, side, top. Returns list of (name, render_product, writer, rep_dir)."""
    if args.choreo:
        # Choreography: robot goes fwd 1m, then right 2m. Center at (0.5, -1.0)
        cx, cy = 0.5, -1.0
        cam_defs = {
            "front": ((cx, cy - 5.0, 2.0), (cx, cy, 0.7)),
            "side":  ((cx + 5.0, cy, 2.0),  (cx, cy, 0.7)),
            "top":   ((cx, cy, 6.0),        (cx, cy, 0.0)),
        }
    elif args.drive_base:
        cx = args.drive_distance / 2.0
        cam_defs = {
            "front": ((cx, -3.5, 1.2), (cx, 0.0, 0.7)),
            "side":  ((cx + 3.0, 0.0, 1.2), (cx, 0.0, 0.7)),
            "top":   ((cx, 0.0, 4.5),       (cx, 0.0, 0.0)),
        }
    else:
        cam_defs = {
            "front": ((2.5, 0.0, 1.2), (0.0, 0.0, 0.7)),
            "side":  ((0.0, 2.5, 1.2), (0.0, 0.0, 0.7)),
            "top":   ((0.0, 0.0, 3.5), (0.0, 0.0, 0.0)),
        }
    cameras = []
    for name, (pos, target) in cam_defs.items():
        cam = rep.create.camera(position=pos, look_at=target)
        rp = rep.create.render_product(cam, (width, height))
        rep_dir = os.path.join(output_dir, f"replicator_{name}")
        w = rep.WriterRegistry.get("BasicWriter")
        w.initialize(output_dir=rep_dir, rgb=True)
        w.attach([rp])
        cameras.append((name, rp, w, rep_dir))
        print(f"[Bench] Camera '{name}': pos={pos} target={target}")
    return cameras


# ---------------------------------------------------------------------------
# Robot loader
# ---------------------------------------------------------------------------
def load_robot(model_name, tiago_dir):
    """Load a TIAGo USD model into the scene. Returns (articulation, dof_names, prim_path) or raises."""
    usd_file = MODEL_FILES[model_name]
    usd_path = os.path.join(tiago_dir, usd_file)
    if not os.path.isfile(usd_path):
        raise FileNotFoundError(f"Robot USD not found: {usd_path}")

    prim_path = "/World/Robot"
    stage = stage_utils.get_current_stage()

    # Remove previous robot if exists
    old = stage.GetPrimAtPath(prim_path)
    if old and old.IsValid():
        stage.RemovePrim(prim_path)
        print(f"[Bench] Removed previous robot at {prim_path}")

    stage_utils.add_reference_to_stage(usd_path=usd_path, prim_path=prim_path)
    print(f"[Bench] Loaded {model_name}: {usd_file} ({os.path.getsize(usd_path)} bytes)")

    # Find articulation root
    art_root_path = None
    for prim in Usd.PrimRange(stage.GetPrimAtPath(prim_path)):
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            art_root_path = str(prim.GetPath())
            break

    if not art_root_path:
        print(f"[Bench] WARN: no ArticulationRootAPI found, using {prim_path}")
        art_root_path = prim_path

    # Configure articulation
    art_prim = stage.GetPrimAtPath(art_root_path)
    fixed = not args.drive_base
    art_prim.CreateAttribute("physxArticulation:fixedBase", Sdf.ValueTypeNames.Bool).Set(fixed)
    art_prim.CreateAttribute("physxArticulation:enabledSelfCollisions", Sdf.ValueTypeNames.Bool).Set(False)
    print(f"[Bench] Articulation root: {art_root_path} (fixedBase={fixed})")

    return art_root_path, prim_path


def resolve_dof_names(articulation):
    """Get DOF names from articulation."""
    names = articulation.dof_names
    if names is None:
        names = []
    if hasattr(names, "tolist"):
        names = names.tolist()
    return list(names)


# ---------------------------------------------------------------------------
# Drive configuration
# ---------------------------------------------------------------------------
DRIVE_PARAMS = {
    "torso_lift_joint":  (3000.0, 600.0, 25000.0),
    "arm_1_joint":       (1500.0, 300.0, 5000.0),
    "arm_2_joint":       (1500.0, 300.0, 5000.0),
    "arm_3_joint":       (1500.0, 300.0, 4000.0),
    "arm_4_joint":       (1000.0, 200.0, 2000.0),
    "arm_5_joint":       (500.0, 100.0, 800.0),
    "arm_6_joint":       (500.0, 100.0, 800.0),
    "arm_7_joint":       (500.0, 100.0, 800.0),
    "head_1_joint":      (400.0, 80.0, 500.0),
    "head_2_joint":      (400.0, 80.0, 500.0),
    "gripper_left_left_finger_joint":   (2000.0, 400.0, 500.0),
    "gripper_left_right_finger_joint":  (2000.0, 400.0, 500.0),
    "gripper_right_left_finger_joint":  (2000.0, 400.0, 500.0),
    "gripper_right_right_finger_joint": (2000.0, 400.0, 500.0),
}
DEFAULT_DRIVE = (400.0, 80.0, 500.0)


def configure_drives(prim_path):
    """Configure PD drives on all joints under prim_path."""
    stage = stage_utils.get_current_stage()
    count = 0
    wheel_set = set(WHEEL_NAMES)
    roller_count = 0
    for jp in stage.Traverse():
        if not jp.GetPath().pathString.startswith(prim_path):
            continue
        is_rev = jp.IsA(UsdPhysics.RevoluteJoint)
        is_pri = (not is_rev) and jp.IsA(UsdPhysics.PrismaticJoint)
        if not (is_rev or is_pri):
            continue
        jname = jp.GetName()

        # Roller joints on omni wheels — low friction, free spin
        if "roller" in jname:
            drive_type = "angular" if is_rev else "linear"
            drive_api = UsdPhysics.DriveAPI.Apply(jp, drive_type)
            drive_api.CreateTypeAttr("acceleration")
            drive_api.CreateStiffnessAttr(0.0)
            drive_api.CreateDampingAttr(5.0)
            drive_api.CreateMaxForceAttr(100.0)
            roller_count += 1
            count += 1
            continue

        # Wheel joints — velocity mode for driving
        if jname in wheel_set and args.drive_base:
            drive_type = "angular" if is_rev else "linear"
            drive_api = UsdPhysics.DriveAPI.Apply(jp, drive_type)
            drive_api.CreateTypeAttr("acceleration")
            drive_api.CreateStiffnessAttr(0.0)
            drive_api.CreateDampingAttr(500.0)
            drive_api.CreateMaxForceAttr(50000.0)
            count += 1
            continue

        canonical = jname
        parts = jname.split("_")
        if len(parts) >= 3 and parts[0] in ("arm", "gripper") and ("right" in jname or "left" in jname):
            for p in parts:
                if p.isdigit():
                    canonical = f"{parts[0]}_{p}_joint"
                    break
        params = DRIVE_PARAMS.get(jname) or DRIVE_PARAMS.get(canonical, DEFAULT_DRIVE)
        stiff, damp, max_f = params
        drive_type = "angular" if is_rev else "linear"
        drive_api = UsdPhysics.DriveAPI.Apply(jp, drive_type)
        drive_api.CreateTypeAttr("acceleration")
        drive_api.CreateStiffnessAttr(stiff)
        drive_api.CreateDampingAttr(damp)
        drive_api.CreateMaxForceAttr(max_f)
        count += 1
    print(f"[Bench] Configured {count} joint drives ({roller_count} rollers, acceleration mode)")
    return count


# ---------------------------------------------------------------------------
# PAL Robotics TIAGo home/tuck pose
# Arms folded close to body, torso at minimum, head centered.
# Based on PAL standard tuck configuration for safe navigation.
# ---------------------------------------------------------------------------
HOME_JOINTS = {
    "torso_lift_joint": 0.0,
    "arm_right_1_joint": 0.07, "arm_right_2_joint": -1.0,
    "arm_right_3_joint": -0.20, "arm_right_4_joint": 1.50,
    "arm_right_5_joint": -1.57, "arm_right_6_joint": 0.10,
    "arm_right_7_joint": 0.0,
    "arm_left_1_joint": 0.07, "arm_left_2_joint": -1.0,
    "arm_left_3_joint": -0.20, "arm_left_4_joint": 1.50,
    "arm_left_5_joint": -1.57, "arm_left_6_joint": 0.10,
    "arm_left_7_joint": 0.0,
    "head_1_joint": 0.0, "head_2_joint": -0.20,
}

TORSO_SPEED = 0.05  # m/s — PAL spec max is 0.07 m/s, use safe 0.05

# TIAGo omni-base wheel parameters
WHEEL_RADIUS = 0.0985  # meters
WHEEL_SEPARATION_X = 0.222  # front-to-rear half-distance (meters)
WHEEL_SEPARATION_Y = 0.222  # left-to-right half-distance (meters)
WHEEL_NAMES = [
    "wheel_front_left_joint", "wheel_front_right_joint",
    "wheel_rear_left_joint", "wheel_rear_right_joint",
]


def omni_wheel_velocities(vx, vy, omega_z):
    """Mecanum inverse kinematics: (vx, vy, omega_z) -> (FL, FR, RL, RR) rad/s.
    vx = forward (m/s), vy = left (m/s), omega_z = CCW rotation (rad/s).
    For TIAGo omni with 45-degree rollers."""
    L = WHEEL_SEPARATION_X + WHEEL_SEPARATION_Y
    fl = (vx - vy - L * omega_z) / WHEEL_RADIUS
    fr = (vx + vy + L * omega_z) / WHEEL_RADIUS
    rl = (vx + vy - L * omega_z) / WHEEL_RADIUS
    rr = (vx - vy + L * omega_z) / WHEEL_RADIUS
    return (fl, fr, rl, rr)


# ---------------------------------------------------------------------------
# Arm poses (within joint limits)
# Joint order: 1=shoulder_lift, 2=shoulder_roll, 3=elbow_rot, 4=elbow_flex,
#              5=wrist_rot, 6=wrist_flex, 7=wrist_rot2
# Limits: 1[-1.18,1.57] 2[-1.18,1.57] 3[-0.79,3.93] 4[-0.39,2.36]
#         5[-2.09,2.09] 6[-1.41,1.41] 7[-2.09,2.09]
# ---------------------------------------------------------------------------
ARM_POSES = {
    "home": {
        "R": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0],
        "L": [0.07, -1.0, -0.20, 1.50, -1.57, 0.10, 0.0],
    },
    "forward": {
        "R": [1.50, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "L": [1.50, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    },
    "down": {
        "R": [0.0, 0.20, -0.20, 0.0, 0.0, 0.0, 0.0],
        "L": [0.0, 0.20, -0.20, 0.0, 0.0, 0.0, 0.0],
    },
    "Y_shape": {
        "R": [0.20, -1.10, -0.20, 0.0, 0.0, 0.0, 0.0],
        "L": [0.20, -1.10, -0.20, 0.0, 0.0, 0.0, 0.0],
    },
    "heart": {
        "R": [1.40, -0.30, 2.50, 2.20, -1.00, -1.00, 0.0],
        "L": [1.40, -0.30, 2.50, 2.20, 1.00, 1.00, 0.0],
    },
}

ARM_JOINT_NAMES_R = [f"arm_right_{i}_joint" for i in range(1, 8)]
ARM_JOINT_NAMES_L = [f"arm_left_{i}_joint" for i in range(1, 8)]


def arm_pose_to_dict(pose_name):
    """Convert named arm pose to joint target dict."""
    pose = ARM_POSES[pose_name]
    d = {}
    for i, val in enumerate(pose["R"]):
        d[ARM_JOINT_NAMES_R[i]] = val
    for i, val in enumerate(pose["L"]):
        d[ARM_JOINT_NAMES_L[i]] = val
    return d


# ---------------------------------------------------------------------------
# Physics logger
# ---------------------------------------------------------------------------
class PhysicsLogger:
    def __init__(self, model_name, dof_names, articulation, prim_path):
        self.model_name = model_name
        self.dof_names = dof_names
        self.articulation = articulation
        self.prim_path = prim_path
        self.frames = []
        self.init_pos = None
        self.init_ori = None
        self._link_paths = self._discover_links()

    def _discover_links(self):
        """Find key link prims for frame logging."""
        stage = stage_utils.get_current_stage()
        key_names = [
            "base_footprint", "base_link", "torso_lift_link",
            "arm_right_1_link", "arm_right_2_link", "arm_right_3_link",
            "arm_right_4_link", "arm_right_5_link", "arm_right_6_link",
            "arm_right_7_link", "arm_right_tool_link",
            "arm_left_1_link", "arm_left_2_link", "arm_left_3_link",
            "arm_left_4_link", "arm_left_5_link", "arm_left_6_link",
            "arm_left_7_link", "arm_left_tool_link",
            "head_1_link", "head_2_link",
        ]
        found = {}
        for prim in Usd.PrimRange(stage.GetPrimAtPath(self.prim_path)):
            name = prim.GetName()
            if name in key_names:
                found[name] = str(prim.GetPath())
        print(f"[Bench] Discovered {len(found)} key links for frame logging")
        return found

    def log_scene_info(self):
        """Log static physics scene parameters (called once)."""
        stage = stage_utils.get_current_stage()
        info = {}
        phys_prim = stage.GetPrimAtPath("/World/PhysicsScene")
        if phys_prim.IsValid():
            ps = UsdPhysics.Scene(phys_prim)
            gdir = ps.GetGravityDirectionAttr().Get()
            gmag = ps.GetGravityMagnitudeAttr().Get()
            info["gravity"] = {"direction": list(gdir) if gdir else [0, 0, -1],
                               "magnitude": float(gmag) if gmag else 9.81}
            if PhysxSchema:
                try:
                    px = PhysxSchema.PhysxSceneAPI(phys_prim)
                    info["solver"] = px.GetSolverTypeAttr().Get()
                    info["pos_iterations"] = px.GetMinPositionIterationCountAttr().Get()
                    info["vel_iterations"] = px.GetMinVelocityIterationCountAttr().Get()
                    info["stabilization"] = px.GetEnableStabilizationAttr().Get()
                except Exception:
                    pass
        info["physics_dt"] = 1.0 / 120.0
        info["rendering_dt"] = 1.0 / 60.0
        info["model"] = self.model_name
        info["dof_count"] = len(self.dof_names)
        info["dof_names"] = self.dof_names
        info["links_tracked"] = list(self._link_paths.keys())
        return info

    def log_frame(self, sim_time, step_idx, targets):
        """Log one physics frame."""
        frame = {
            "sim_time": round(sim_time, 4),
            "step": step_idx,
        }

        # -- Base pose --
        try:
            art_pos, art_ori = self.articulation.get_world_pose()
            if art_pos is not None:
                px, py, pz = float(art_pos[0]), float(art_pos[1]), float(art_pos[2])
                frame["base_position"] = {"x": round(px, 5), "y": round(py, 5), "z": round(pz, 5)}
                if self.init_pos is None:
                    self.init_pos = (px, py, pz)
                drift = math.sqrt(
                    (px - self.init_pos[0])**2 +
                    (py - self.init_pos[1])**2 +
                    (pz - self.init_pos[2])**2
                )
                frame["base_drift_m"] = round(drift, 5)
            if art_ori is not None:
                w, x, y, z = float(art_ori[0]), float(art_ori[1]), float(art_ori[2]), float(art_ori[3])
                frame["base_orientation_quat"] = {"w": round(w, 5), "x": round(x, 5),
                                                   "y": round(y, 5), "z": round(z, 5)}
                roll, pitch, yaw = quat_to_euler(w, x, y, z)
                frame["base_euler_deg"] = {"roll": round(roll, 3), "pitch": round(pitch, 3),
                                           "yaw": round(yaw, 3)}
                if self.init_ori is None:
                    self.init_ori = (w, x, y, z)
                tilt = max(abs(roll), abs(pitch))
                frame["base_tilt_deg"] = round(tilt, 3)
        except Exception:
            pass

        # -- Joint states --
        try:
            positions = self.articulation.get_joint_positions()
            velocities = self.articulation.get_joint_velocities()
            if positions is not None:
                positions = np.array(positions, dtype=np.float64)
            if velocities is not None:
                velocities = np.array(velocities, dtype=np.float64)

            joints = {}
            for i, name in enumerate(self.dof_names):
                jdata = {}
                if positions is not None and i < len(positions):
                    jdata["position_rad"] = round(float(positions[i]), 5)
                if velocities is not None and i < len(velocities):
                    jdata["velocity_rads"] = round(float(velocities[i]), 5)
                if name in targets:
                    jdata["target_rad"] = round(float(targets[name]), 5)
                    if "position_rad" in jdata:
                        jdata["error_rad"] = round(jdata["target_rad"] - jdata["position_rad"], 5)
                joints[name] = jdata
            frame["joints"] = joints
        except Exception as e:
            frame["joints_error"] = str(e)

        # -- Link world frames --
        link_frames = {}
        for link_name, link_path in self._link_paths.items():
            try:
                xf = XFormPrim(prim_path=link_path)
                lp, lo = xf.get_world_pose()
                if lp is not None:
                    entry = {
                        "position": {"x": round(float(lp[0]), 5),
                                     "y": round(float(lp[1]), 5),
                                     "z": round(float(lp[2]), 5)},
                    }
                    if lo is not None:
                        w, x, y, z = float(lo[0]), float(lo[1]), float(lo[2]), float(lo[3])
                        entry["orientation_quat"] = {"w": round(w, 5), "x": round(x, 5),
                                                     "y": round(y, 5), "z": round(z, 5)}
                        r, p, ya = quat_to_euler(w, x, y, z)
                        entry["euler_deg"] = {"roll": round(r, 3), "pitch": round(p, 3),
                                              "yaw": round(ya, 3)}
                    link_frames[link_name] = entry
            except Exception:
                pass
        if link_frames:
            frame["link_frames"] = link_frames

        self.frames.append(frame)
        return frame

    def console_summary(self, frame):
        """Print a one-line summary to console."""
        t = frame.get("sim_time", 0)
        drift = frame.get("base_drift_m", 0)
        tilt = frame.get("base_tilt_deg", 0)
        bp = frame.get("base_position", {})
        joints = frame.get("joints", {})
        torso = joints.get("torso_lift_joint", {})
        torso_pos = torso.get("position_rad", "?")
        torso_err = torso.get("error_rad", "?")
        max_err = 0.0
        max_vel = 0.0
        for jn, jd in joints.items():
            e = abs(jd.get("error_rad", 0))
            v = abs(jd.get("velocity_rads", 0))
            if e > max_err:
                max_err = e
            if v > max_vel:
                max_vel = v
        base_str = (f"base=({bp.get('x', 0):+.5f},{bp.get('y', 0):+.5f},{bp.get('z', 0):+.5f})")
        print(f"[Bench] t={t:6.2f}s | "
              f"{base_str} "
              f"drift={drift:.5f}m tilt={tilt:.2f}deg | "
              f"torso={torso_pos} err={torso_err} | "
              f"max_err={max_err:.4f} max_vel={max_vel:.3f}")

    def generate_report(self):
        """Generate summary statistics."""
        if not self.frames:
            return {"error": "no frames logged"}
        max_drift = max(f.get("base_drift_m", 0) for f in self.frames)
        max_tilt = max(f.get("base_tilt_deg", 0) for f in self.frames)
        max_joint_err = 0.0
        max_joint_vel = 0.0
        for f in self.frames:
            for jn, jd in f.get("joints", {}).items():
                e = abs(jd.get("error_rad", 0))
                v = abs(jd.get("velocity_rads", 0))
                if e > max_joint_err:
                    max_joint_err = e
                if v > max_joint_vel:
                    max_joint_vel = v
        final_base = self.frames[-1].get("base_position", {})
        if args.drive_base:
            stable = max_tilt < 5.0
            verdict = "PASS (driving)" if stable else "FAIL (tilt during drive)"
        else:
            stable = max_drift < 0.01 and max_tilt < 1.0
            verdict = "PASS" if stable else "FAIL (unstable base)"
        report = {
            "model": self.model_name,
            "total_frames": len(self.frames),
            "duration_s": self.frames[-1].get("sim_time", 0),
            "max_drift_m": round(max_drift, 5),
            "max_tilt_deg": round(max_tilt, 3),
            "max_joint_error_rad": round(max_joint_err, 5),
            "max_joint_velocity_rads": round(max_joint_vel, 4),
            "final_base_position": final_base,
            "stable": stable,
            "verdict": verdict,
        }
        if args.drive_base:
            report["drive_mode"] = True
            report["drive_distance_m"] = args.drive_distance
            report["drive_speed_ms"] = args.drive_speed
        return report


# ---------------------------------------------------------------------------
# Action sequence
# ---------------------------------------------------------------------------
# Each action is a dict for clarity:
#   t: trigger time, desc: label,
#   torso: target, torso_speed: m/s or None,
#   wheels: (FL,FR,RL,RR) rad/s or None (keep),
#   arm_pose: name from ARM_POSES or None (keep)
# ---------------------------------------------------------------------------
def _act(t, desc, torso=None, torso_speed=None, wheels=None, arm_pose=None):
    return {"t": t, "desc": desc, "torso": torso, "torso_speed": torso_speed,
            "wheels": wheels, "arm_pose": arm_pose}


def _stop_wheels():
    return (0.0, 0.0, 0.0, 0.0)


def build_action_sequence():
    """Returns (actions_list, total_duration)."""
    spd = args.drive_speed
    dist = args.drive_distance

    if args.choreo:
        drive_t = dist / spd
        # Rotation: 90 deg CW = -pi/2 rad. omega = angle/time.
        rot_speed = 0.3  # rad/s
        rot_angle = math.pi / 2.0
        rot_time = rot_angle / rot_speed

        t = 0.0
        actions = []
        # -- Settle in home --
        actions.append(_act(t, "home_settle", torso=0.15, arm_pose="home", wheels=_stop_wheels())); t += 3.0

        # 1) Drive forward 1m, arms forward
        actions.append(_act(t, "arms_forward", arm_pose="forward")); t += 2.0
        actions.append(_act(t, "drive_fwd_1m",
                            wheels=omni_wheel_velocities(spd, 0, 0))); t += drive_t
        actions.append(_act(t, "stop_1", wheels=_stop_wheels())); t += 1.5

        # 2) Drive right 1m, arms down
        actions.append(_act(t, "arms_down", arm_pose="down")); t += 2.0
        actions.append(_act(t, "drive_right_1m",
                            wheels=omni_wheel_velocities(0, -spd, 0))); t += drive_t
        actions.append(_act(t, "stop_2", wheels=_stop_wheels())); t += 1.5

        # 3) Drive right 1m, arms Y-shape
        actions.append(_act(t, "arms_Y", arm_pose="Y_shape")); t += 2.0
        actions.append(_act(t, "drive_right_1m_2",
                            wheels=omni_wheel_velocities(0, -spd, 0))); t += drive_t
        actions.append(_act(t, "stop_3", wheels=_stop_wheels())); t += 1.5

        # 4) Rotate 90 CW, arms heart
        actions.append(_act(t, "arms_heart", arm_pose="heart")); t += 2.5
        actions.append(_act(t, "rotate_90cw",
                            wheels=omni_wheel_velocities(0, 0, -rot_speed))); t += rot_time
        actions.append(_act(t, "stop_4", wheels=_stop_wheels())); t += 3.0

        # -- Return to home --
        actions.append(_act(t, "arms_home_final", arm_pose="home")); t += 3.0
        return actions, t

    elif args.drive_base:
        drive_t = dist / spd
        w_fwd = omni_wheel_velocities(spd, 0, 0)
        w_back = omni_wheel_velocities(-spd, 0, 0)

        t = 0.0
        actions = []
        actions.append(_act(t, "home_settle", torso=0.0, wheels=_stop_wheels())); t += 3.0
        actions.append(_act(t, "torso_up", torso=0.35, torso_speed=TORSO_SPEED)); t += 0.35 / TORSO_SPEED
        actions.append(_act(t, "hold_up", torso=0.35)); t += 2.0
        actions.append(_act(t, "drive_forward", wheels=w_fwd)); t += drive_t
        actions.append(_act(t, "stop_forward", wheels=_stop_wheels())); t += 2.0
        actions.append(_act(t, "drive_backward", wheels=w_back)); t += drive_t
        actions.append(_act(t, "stop_backward", wheels=_stop_wheels())); t += 2.0
        actions.append(_act(t, "torso_down", torso=0.0, torso_speed=TORSO_SPEED)); t += 0.35 / TORSO_SPEED
        actions.append(_act(t, "hold_final", torso=0.0)); t += 3.0
        return actions, t

    else:
        t_up_start = 3.0
        t_up_end = t_up_start + 0.35 / TORSO_SPEED
        t_hold = t_up_end + 3.0
        t_down_end = t_hold + 0.35 / TORSO_SPEED
        t_final = t_down_end + 3.0
        return [
            _act(0.0,         "home_settle",  torso=0.0),
            _act(t_up_start,  "torso_up",     torso=0.35, torso_speed=TORSO_SPEED),
            _act(t_up_end,    "hold_up",      torso=0.35),
            _act(t_hold,      "torso_down",   torso=0.0,  torso_speed=TORSO_SPEED),
            _act(t_down_end,  "hold_down",    torso=0.0),
        ], t_final


# ---------------------------------------------------------------------------
# Main test loop for one model
# ---------------------------------------------------------------------------
def run_test(model_name, world, output_dir, record_video):
    print(f"\n{'='*70}")
    print(f"[Bench] TESTING MODEL: {model_name}")
    print(f"{'='*70}")

    model_dir = os.path.join(output_dir, model_name)
    os.makedirs(model_dir, exist_ok=True)

    # Load robot
    art_root_path, prim_path = load_robot(model_name, args.tiago_dir)
    configure_drives(prim_path)

    # Position robot at origin
    try:
        xf = XFormPrim(prim_path=prim_path, name="robot_pose")
        xf.set_world_pose(
            position=np.array([0.0, 0.0, 0.08], dtype=np.float32),
            orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        )
        print(f"[Bench] Robot placed at (0, 0, 0.08)")
    except Exception as e:
        print(f"[Bench] WARN: set_world_pose failed: {e}")

    # Reset world
    world.reset()
    simulation_app.update()

    # Initialize articulation
    articulation = Articulation(prim_path=art_root_path, name="tiago_bench")
    world.scene.add(articulation)
    world.reset()
    simulation_app.update()

    try:
        articulation.initialize()
    except Exception as e:
        print(f"[Bench] WARN: articulation.initialize() failed: {e}")

    dof_names = resolve_dof_names(articulation)
    print(f"[Bench] DOFs ({len(dof_names)}): {dof_names}")

    # Anchor robot at origin after reset
    for attempt in range(5):
        try:
            articulation.set_world_pose(
                position=np.array([0.0, 0.0, 0.08], dtype=np.float32),
                orientation=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
            )
            zero_vel = np.zeros(len(dof_names), dtype=np.float32)
            articulation.set_joint_velocities(zero_vel)
            for _ in range(20):
                world.step(render=False)
            art_pos, _ = articulation.get_world_pose()
            if art_pos is not None:
                drift = abs(float(art_pos[0])) + abs(float(art_pos[1])) + abs(float(art_pos[2]) - 0.08)
                print(f"[Bench] Anchor attempt {attempt}: pos=({art_pos[0]:.4f},{art_pos[1]:.4f},{art_pos[2]:.4f}) drift={drift:.4f}")
                if drift < 0.05:
                    break
        except Exception as e:
            print(f"[Bench] Anchor attempt {attempt} failed: {e}")

    # Setup cameras
    cameras = []
    if record_video:
        cameras = setup_cameras(model_dir, args.width, args.height)

    # Logger
    logger = PhysicsLogger(model_name, dof_names, articulation, prim_path)
    scene_info = logger.log_scene_info()
    print(f"[Bench] Scene info: {json.dumps(scene_info, indent=2)}")

    # Joint limits discovery
    joint_limits = {}
    stage = stage_utils.get_current_stage()
    for jp in stage.Traverse():
        if not jp.GetPath().pathString.startswith(prim_path):
            continue
        is_rev = jp.IsA(UsdPhysics.RevoluteJoint)
        is_pri = (not is_rev) and jp.IsA(UsdPhysics.PrismaticJoint)
        if not (is_rev or is_pri):
            continue
        jname = jp.GetName()
        lo = hi = None
        if is_rev:
            rev = UsdPhysics.RevoluteJoint(jp)
            lo_attr = rev.GetLowerLimitAttr()
            hi_attr = rev.GetUpperLimitAttr()
        else:
            pri = UsdPhysics.PrismaticJoint(jp)
            lo_attr = pri.GetLowerLimitAttr()
            hi_attr = pri.GetUpperLimitAttr()
        if lo_attr:
            lo = lo_attr.Get()
        if hi_attr:
            hi = hi_attr.Get()
        if lo is not None and hi is not None:
            if is_rev:
                lo = math.radians(float(lo))
                hi = math.radians(float(hi))
            joint_limits[jname] = (round(lo, 5), round(hi, 5))
    print(f"[Bench] Joint limits ({len(joint_limits)}):")
    for jn, (lo, hi) in sorted(joint_limits.items()):
        print(f"  {jn}: [{lo:.4f}, {hi:.4f}]")
    scene_info["joint_limits"] = {k: list(v) for k, v in joint_limits.items()}

    # Set initial home pose (PAL tuck)
    targets = dict(HOME_JOINTS)
    _apply_targets(articulation, dof_names, targets)
    for _ in range(120):
        world.step(render=False)
    print("[Bench] Home pose applied (PAL tuck), settling...")

    # Action sequence
    actions, total_duration = build_action_sequence()
    if args.duration < total_duration:
        args.duration = total_duration
        print(f"[Bench] Duration auto-extended to {total_duration:.1f}s for full action sequence")

    physics_dt = 1.0 / 120.0
    total_steps = int(args.duration / physics_dt)
    log_every = 6  # 20Hz logging
    console_every = 60  # 0.5s console
    render_every = 2  # 60Hz render

    current_targets = dict(targets)
    action_idx = 0
    _torso_interp_start_time = 0.0
    _torso_interp_start_val = 0.0
    _torso_interp_end_val = 0.0
    _torso_interp_speed = None
    _current_wheel_vels = (0.0, 0.0, 0.0, 0.0)  # FL, FR, RL, RR

    # Resolve wheel DOF indices (FL, FR, RL, RR order)
    wheel_dof_indices = []
    for wn in WHEEL_NAMES:
        if wn in dof_names:
            wheel_dof_indices.append(dof_names.index(wn))
    if args.drive_base:
        print(f"[Bench] Wheel DOFs: {len(wheel_dof_indices)} "
              f"({[dof_names[i] for i in wheel_dof_indices]})")

    # Print sequence summary
    print(f"[Bench] Starting simulation: {total_steps} steps ({args.duration}s)")
    print(f"[Bench] Actions: {len(actions)}")
    for a in actions:
        print(f"  t={a['t']:6.1f}s: {a['desc']}"
              + (f" torso={a['torso']}" if a.get('torso') is not None else "")
              + (f" arm={a['arm_pose']}" if a.get('arm_pose') else "")
              + (f" wheels={a['wheels']}" if a.get('wheels') else ""))

    start_wall = time.time()
    for step in range(total_steps):
        sim_time = step * physics_dt

        # Check action triggers
        while action_idx < len(actions) and sim_time >= actions[action_idx]["t"]:
            act = actions[action_idx]
            desc = act["desc"]

            # Torso
            if act.get("torso") is not None:
                _torso_interp_start_time = act["t"]
                _torso_interp_start_val = current_targets.get("torso_lift_joint", 0.0)
                _torso_interp_end_val = act["torso"]
                _torso_interp_speed = act.get("torso_speed")

            # Wheels
            if act.get("wheels") is not None:
                _current_wheel_vels = act["wheels"]

            # Arm pose
            if act.get("arm_pose"):
                arm_joints = arm_pose_to_dict(act["arm_pose"])
                current_targets.update(arm_joints)
                _apply_targets(articulation, dof_names, current_targets)

            print(f"[Bench] ACTION t={sim_time:.2f}s: {desc}")
            action_idx += 1

        # Smooth torso interpolation
        if _torso_interp_speed and _torso_interp_speed > 0:
            elapsed = sim_time - _torso_interp_start_time
            distance = abs(_torso_interp_end_val - _torso_interp_start_val)
            if distance > 1e-6:
                duration = distance / _torso_interp_speed
                alpha = min(1.0, elapsed / duration)
                torso_now = _torso_interp_start_val + alpha * (_torso_interp_end_val - _torso_interp_start_val)
                current_targets["torso_lift_joint"] = torso_now
                _apply_targets(articulation, dof_names, current_targets)
                if alpha >= 1.0:
                    _torso_interp_speed = None
        elif _torso_interp_speed is None and "torso_lift_joint" in current_targets:
            current_targets["torso_lift_joint"] = _torso_interp_end_val
            _apply_targets(articulation, dof_names, current_targets)

        # Wheel velocity control via ArticulationAction (per-wheel)
        if args.drive_base and wheel_dof_indices:
            from omni.isaac.core.utils.types import ArticulationAction
            vel_array = np.zeros(len(dof_names), dtype=np.float32)
            for i, wi in enumerate(wheel_dof_indices):
                if i < len(_current_wheel_vels):
                    vel_array[wi] = _current_wheel_vels[i]
            try:
                articulation.apply_action(ArticulationAction(
                    joint_velocities=vel_array))
            except Exception:
                pass

        do_render = (step % render_every == 0)
        world.step(render=do_render)

        if step % log_every == 0:
            frame = logger.log_frame(sim_time, step, current_targets)
            if step % console_every == 0:
                logger.console_summary(frame)

    wall_elapsed = time.time() - start_wall
    print(f"[Bench] Simulation complete: {total_steps} steps in {wall_elapsed:.1f}s "
          f"(realtime factor: {args.duration/wall_elapsed:.2f}x)")

    # Report
    report = logger.generate_report()
    report["wall_time_s"] = round(wall_elapsed, 2)
    report["scene_info"] = scene_info

    print(f"\n[Bench] === REPORT: {model_name} ===")
    for k, v in report.items():
        if k not in ("scene_info",):
            print(f"  {k}: {v}")

    # Save logs
    log_path = os.path.join(model_dir, "physics_log.json")
    with open(log_path, "w") as f:
        json.dump({"scene_info": scene_info, "frames": logger.frames, "report": report}, f, indent=1)
    print(f"[Bench] Log saved: {log_path} ({len(logger.frames)} frames)")

    summary_path = os.path.join(model_dir, "summary.txt")
    with open(summary_path, "w") as f:
        f.write(f"Robot Test Bench - {model_name}\n")
        f.write(f"{'='*50}\n\n")
        for k, v in report.items():
            f.write(f"{k}: {v}\n")
        f.write(f"\nJoint limits:\n")
        for jn, (lo, hi) in sorted(joint_limits.items()):
            f.write(f"  {jn}: [{lo:.4f}, {hi:.4f}]\n")
    print(f"[Bench] Summary saved: {summary_path}")

    # Encode videos
    if record_video:
        for cam_name, rp, w, rep_dir in cameras:
            video_path = os.path.join(model_dir, f"{cam_name}.mp4")
            encode_video(rep_dir, video_path)

    # Cleanup: remove articulation from scene before next model
    try:
        world.scene.remove_object("tiago_bench")
    except Exception:
        pass

    return report


def _apply_targets(articulation, dof_names, targets):
    """Apply joint position targets via ArticulationAction.
    Skips wheel/roller joints when driving to avoid fighting velocity control."""
    from omni.isaac.core.utils.types import ArticulationAction
    pos_array = np.zeros(len(dof_names), dtype=np.float32)
    current = articulation.get_joint_positions()
    if current is not None:
        pos_array[:] = np.array(current, dtype=np.float32)
    for jname, val in targets.items():
        if args.drive_base and ("wheel" in jname or "roller" in jname):
            continue
        if jname in dof_names:
            idx = dof_names.index(jname)
            pos_array[idx] = float(val)
        else:
            for alias in [jname.replace("arm_right_", "arm_"),
                          jname.replace("arm_left_", "arm_"),
                          jname.replace("arm_", "arm_right_"),
                          jname.replace("arm_", "arm_left_")]:
                if alias in dof_names:
                    idx = dof_names.index(alias)
                    pos_array[idx] = float(val)
    articulation.apply_action(ArticulationAction(joint_positions=pos_array))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
try:
    os.makedirs(args.output, exist_ok=True)
    world = World(physics_dt=1.0 / 120.0, rendering_dt=1.0 / 60.0)
    build_clean_scene()
    simulation_app.update()

    all_reports = {}
    for model_name in MODELS_TO_TEST:
        report = run_test(model_name, world, args.output, record_video=not args.no_video)
        all_reports[model_name] = report

    # Comparison summary
    if len(all_reports) > 1:
        print(f"\n{'='*70}")
        print("[Bench] MODEL COMPARISON")
        print(f"{'='*70}")
        header = f"{'Model':<10} {'Drift(m)':<12} {'Tilt(deg)':<12} {'MaxJErr(rad)':<14} {'Stable':<8} {'Verdict'}"
        print(header)
        print("-" * len(header))
        for mn, r in all_reports.items():
            print(f"{mn:<10} {r['max_drift_m']:<12.5f} {r['max_tilt_deg']:<12.3f} "
                  f"{r['max_joint_error_rad']:<14.5f} {str(r['stable']):<8} {r['verdict']}")

        comp_path = os.path.join(args.output, "comparison.json")
        with open(comp_path, "w") as f:
            json.dump(all_reports, f, indent=2)
        print(f"\n[Bench] Comparison saved: {comp_path}")

    print("\n[Bench] ALL TESTS COMPLETE")

except Exception as e:
    import traceback
    print(f"[Bench] FATAL: {e}")
    traceback.print_exc()
finally:
    simulation_app.close()
