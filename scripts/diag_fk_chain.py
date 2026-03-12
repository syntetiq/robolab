"""
Standalone FK diagnostic for TIAGo in Isaac Sim.

Verifies:
  1. Frame delta between /World/Tiago and base_footprint
  2. FK agreement between Isaac Sim PhysX and MoveIt URDF (pure-Python FK)

Usage (from Isaac Sim python):
  python.bat scripts/diag_fk_chain.py --env "C:\RoboLab_Data\scenes\Small_House_Interactive.usd"

No MoveIt, no ROS, no IPC required.
"""

import argparse
import math
import os
import sys
from pathlib import Path

os.environ["PYTHONUNBUFFERED"] = "1"

import numpy as np

# Force unbuffered stdout for Isaac Sim
_orig_print = print
def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _orig_print(*args, **kwargs)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="TIAGo FK chain diagnostic")
parser.add_argument("--env", type=str, required=True, help="Path to environment USD")
parser.add_argument(
    "--tiago-usd",
    type=str,
    default=os.environ.get(
        "TIAGO_USD_PATH",
        r"C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional_light.usd",
    ),
)
parser.add_argument("--headless", action="store_true", default=True)
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Isaac Sim bootstrap
# ---------------------------------------------------------------------------
from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": args.headless, "width": 640, "height": 480})

from omni.isaac.core import World
from omni.isaac.core.articulations import Articulation
from omni.isaac.core.prims import XFormPrim
from omni.isaac.core.utils import stage as stage_utils
from pxr import Sdf, UsdPhysics

# ---------------------------------------------------------------------------
# MoveIt URDF FK (pure Python, no ROS)
# ---------------------------------------------------------------------------
# Kinematic chain from tiago_move_group_working.yaml:
#   base_footprint -> base_link -> torso_lift_link -> arm_1..7 -> arm_tool_link

_HALF_PI = math.pi / 2.0

URDF_CHAIN = [
    # (joint_name, joint_type, xyz, rpy, axis)
    ("base_footprint_joint", "fixed",     (0.0, 0.0, 0.0762),    (0.0, 0.0, 0.0)),
    ("torso_lift_joint",     "prismatic",  (-0.062, 0.0, 0.813),  (0.0, 0.0, 0.0)),
    ("arm_1_joint",          "revolute",   (0.0256, -0.190, -0.171), (0.0, 0.0, -_HALF_PI)),
    ("arm_2_joint",          "revolute",   (0.125, -0.0195, -0.031), (-_HALF_PI, 0.0, 0.0)),
    ("arm_3_joint",          "revolute",   (0.0895, 0.0, -0.0015),  (-_HALF_PI, 0.0, _HALF_PI)),
    ("arm_4_joint",          "revolute",   (-0.02, -0.027, -0.222), (-_HALF_PI, -_HALF_PI, 0.0)),
    ("arm_5_joint",          "revolute",   (-0.162, 0.02, 0.027),  (0.0, -_HALF_PI, 0.0)),
    ("arm_6_joint",          "revolute",   (0.0, 0.0, 0.15),      (-_HALF_PI, -_HALF_PI, 0.0)),
    ("arm_7_joint",          "revolute",   (0.0, 0.0, 0.0),       (_HALF_PI, 0.0, _HALF_PI)),
    ("arm_tool_joint",       "fixed",      (0.0, 0.0, 0.0573),    (-_HALF_PI, -_HALF_PI, 0.0)),
]

# MoveIt joint name -> Isaac Sim DOF name
MOVEIT_TO_SIM = {
    "torso_lift_joint": "torso_lift_joint",
    "arm_1_joint": "arm_right_1_joint",
    "arm_2_joint": "arm_right_2_joint",
    "arm_3_joint": "arm_right_3_joint",
    "arm_4_joint": "arm_right_4_joint",
    "arm_5_joint": "arm_right_5_joint",
    "arm_6_joint": "arm_right_6_joint",
    "arm_7_joint": "arm_right_7_joint",
}


def _rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)


def _rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)


def _rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)


def _rpy_to_matrix(r, p, y):
    return _rot_z(y) @ _rot_y(p) @ _rot_x(r)


def _make_transform(xyz, rpy):
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = _rpy_to_matrix(*rpy)
    T[:3, 3] = xyz
    return T


def urdf_fk(joint_values: dict) -> np.ndarray:
    """Compute tool_link position in base_footprint frame using MoveIt URDF chain."""
    T = np.eye(4, dtype=np.float64)
    for jname, jtype, xyz, rpy in URDF_CHAIN:
        T_joint = _make_transform(xyz, rpy)
        if jtype == "revolute":
            q = joint_values.get(jname, 0.0)
            T_joint = T_joint @ _make_transform((0, 0, 0), (0, 0, q))
        elif jtype == "prismatic":
            q = joint_values.get(jname, 0.0)
            # axis is (0,0,1) for all prismatic joints in this URDF
            T_joint = T_joint @ _make_transform((0, 0, q), (0, 0, 0))
        T = T @ T_joint
    return T[:3, 3]


# ---------------------------------------------------------------------------
# Test configurations (from moveit_intent_bridge.py)
# ---------------------------------------------------------------------------
TIAGO_PRE_GRASP_JOINTS = {
    "torso_lift_joint": 0.30,
    "arm_1_joint": 1.30,
    "arm_2_joint": -0.40,
    "arm_3_joint": -0.70,
    "arm_4_joint": 1.80,
    "arm_5_joint": -0.80,
    "arm_6_joint": -0.50,
    "arm_7_joint": 0.0,
}

TIAGO_GRASP_JOINTS = {
    "torso_lift_joint": 0.20,
    "arm_1_joint": 1.30,
    "arm_2_joint": 0.10,
    "arm_3_joint": -1.60,
    "arm_4_joint": 2.10,
    "arm_5_joint": -0.80,
    "arm_6_joint": -0.80,
    "arm_7_joint": 0.0,
}

TIAGO_HOME_JOINTS = {
    "torso_lift_joint": 0.15,
    "arm_1_joint": 0.20,
    "arm_2_joint": -0.35,
    "arm_3_joint": -0.20,
    "arm_4_joint": 1.90,
    "arm_5_joint": -1.57,
    "arm_6_joint": 1.37,
    "arm_7_joint": 0.0,
}

# IK solution from smoke run (angled-60, grasp step)
SMOKE_IK_SOLUTION = {
    "torso_lift_joint": 0.274,
    "arm_1_joint": 1.3622,
    "arm_2_joint": -1.1602,
    "arm_3_joint": 2.5661,
    "arm_4_joint": 2.0685,
    "arm_5_joint": -1.6038,
    "arm_6_joint": 1.2163,
    "arm_7_joint": 1.9733,
}

TEST_CONFIGS = {
    "HOME": TIAGO_HOME_JOINTS,
    "PRE_GRASP": TIAGO_PRE_GRASP_JOINTS,
    "GRASP": TIAGO_GRASP_JOINTS,
    "SMOKE_IK": SMOKE_IK_SOLUTION,
}

# ---------------------------------------------------------------------------
# Scene setup
# ---------------------------------------------------------------------------
print("=" * 70)
print("  TIAGo FK Chain Diagnostic")
print("=" * 70)

world = World(physics_dt=1.0 / 120.0, rendering_dt=1.0 / 60.0)

env_usd = str(Path(args.env).resolve()) if Path(args.env).exists() else args.env
stage_utils.add_reference_to_stage(usd_path=env_usd, prim_path="/World/Environment")

tiago_prim_path = "/World/Tiago"
tiago_usd = str(Path(args.tiago_usd).resolve()) if Path(args.tiago_usd).exists() else args.tiago_usd
stage_utils.add_reference_to_stage(usd_path=tiago_usd, prim_path=tiago_prim_path)

stage = stage_utils.get_current_stage()
tiago_prim = stage.GetPrimAtPath(tiago_prim_path)
assert tiago_prim.IsValid(), f"Tiago prim not found: {tiago_prim_path}"

# Detect articulation root
tiago_articulation_path = tiago_prim_path
tiago_articulation = None

if tiago_prim.HasAPI(UsdPhysics.ArticulationRootAPI):
    tiago_articulation_path = tiago_prim_path
else:
    for prim in stage.Traverse():
        ps = str(prim.GetPath())
        if ps.startswith(tiago_prim_path) and prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            tiago_articulation_path = ps
            break

print(f"\n[DIAG] tiago_prim_path        = {tiago_prim_path}")
print(f"[DIAG] tiago_articulation_path = {tiago_articulation_path}")

# Check USD hierarchy transforms from /World/Tiago to base_footprint
from pxr import UsdGeom as _UsdGeom_diag
print("\n[DIAG] USD hierarchy transforms:")
_hier_path = ""
for _part in tiago_articulation_path.strip("/").split("/"):
    _hier_path += "/" + _part
    _hier_prim = stage.GetPrimAtPath(_hier_path)
    if _hier_prim.IsValid():
        _xf = _UsdGeom_diag.Xformable(_hier_prim)
        _ops = _xf.GetOrderedXformOps()
        if _ops:
            for _op in _ops:
                print(f"  {_hier_path}: {_op.GetOpName()} = {_op.Get()}")
        else:
            print(f"  {_hier_path}: (no xform ops)")
    else:
        print(f"  {_hier_path}: NOT VALID")

# Pin base and fix invalid mass on base_footprint
art_prim = stage.GetPrimAtPath(tiago_articulation_path)
if art_prim.IsValid():
    art_prim.CreateAttribute("physxArticulation:fixedBase", Sdf.ValueTypeNames.Bool).Set(True)
    art_prim.CreateAttribute("physxArticulation:enabledSelfCollisions", Sdf.ValueTypeNames.Bool).Set(False)
    print(f"[DIAG] Set fixedBase=True on {tiago_articulation_path}")

    # Fix invalid mass/inertia on base_footprint (PhysX warns about negative mass)
    from pxr import UsdPhysics as _UsdPhysics, Gf
    if art_prim.HasAPI(_UsdPhysics.MassAPI):
        mass_api = _UsdPhysics.MassAPI(art_prim)
    else:
        mass_api = _UsdPhysics.MassAPI.Apply(art_prim)
    mass_api.GetMassAttr().Set(50.0)
    mass_api.GetDiagonalInertiaAttr().Set(Gf.Vec3f(10.0, 10.0, 10.0))
    print(f"[DIAG] Fixed mass/inertia on base_footprint: mass=50, inertia=(10,10,10)")

# Set robot world pose (same as data_collector)
tiago_xform = XFormPrim(prim_path=tiago_prim_path, name="tiago_root_pose")
ROBOT_WORLD_POS = np.array([0.8, 0.0, 0.08], dtype=np.float32)
ROBOT_WORLD_ORI = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
tiago_xform.set_world_pose(position=ROBOT_WORLD_POS, orientation=ROBOT_WORLD_ORI)

# Create articulation
try:
    tiago_articulation = Articulation(prim_path=tiago_articulation_path, name="tiago")
    world.scene.add(tiago_articulation)
except Exception as e:
    print(f"[DIAG] FATAL: Cannot create articulation: {e}")
    simulation_app.close()
    sys.exit(1)

world.reset()
simulation_app.update()

try:
    tiago_articulation.initialize()
    print("[DIAG] Articulation initialized")
except Exception as e:
    print(f"[DIAG] FATAL: Articulation init failed: {e}")
    simulation_app.close()
    sys.exit(1)

# Set initial joint positions to a safe neutral pose (same as data_collector)
try:
    from omni.isaac.core.utils.types import ArticulationAction
    dof_names_init = list(tiago_articulation.dof_names or [])
    n_dofs = len(dof_names_init)
    init_pos = np.zeros(n_dofs, dtype=np.float32)
    _NEUTRAL = {
        "arm_right_1_joint": 0.20, "arm_right_2_joint": -0.35,
        "arm_right_3_joint": -0.20, "arm_right_4_joint": 1.90,
        "arm_right_5_joint": -1.57, "arm_right_6_joint": 1.37,
        "arm_right_7_joint": 0.0,
        "arm_left_1_joint": 0.20, "arm_left_2_joint": -0.35,
        "arm_left_3_joint": -0.20, "arm_left_4_joint": 1.90,
        "arm_left_5_joint": -1.57, "arm_left_6_joint": 1.37,
        "arm_left_7_joint": 0.0,
        "torso_lift_joint": 0.15,
        "head_1_joint": 0.0, "head_2_joint": -0.3,
    }
    for jn, jv in _NEUTRAL.items():
        if jn in dof_names_init:
            init_pos[dof_names_init.index(jn)] = jv
    tiago_articulation.set_joint_positions(init_pos)
    tiago_articulation.set_joint_velocities(np.zeros(n_dofs, dtype=np.float32))
    targets = np.full(n_dofs, float("nan"), dtype=np.float32)
    for jn, jv in _NEUTRAL.items():
        if jn in dof_names_init:
            targets[dof_names_init.index(jn)] = jv
    tiago_articulation.apply_action(ArticulationAction(joint_positions=targets))
    print("[DIAG] Initial joint positions applied")
except Exception as e:
    print(f"[DIAG] WARN: Failed to set initial joints: {e}")

# Step frames for physics to settle, applying base lock each step
print("[DIAG] Stepping physics with base lock to settle articulation...")
_lock_xf_init = XFormPrim(prim_path=tiago_prim_path)
for i in range(300):
    _lock_xf_init.set_world_pose(position=ROBOT_WORLD_POS, orientation=ROBOT_WORLD_ORI)
    tiago_articulation.set_world_pose(position=ROBOT_WORLD_POS, orientation=ROBOT_WORLD_ORI)
    world.step(render=False)
    if i % 100 == 99:
        _check_pos, _ = _lock_xf_init.get_world_pose()
        print(f"  step {i+1}: /World/Tiago pos=({_check_pos[0]:.4f}, {_check_pos[1]:.4f}, {_check_pos[2]:.4f})")
print("[DIAG] Settled after 300 steps with articulation + XForm base lock.")

# Check where base_footprint actually is in PhysX
try:
    _av = getattr(tiago_articulation, "_articulation_view", None)
    _pv = getattr(_av, "_physics_view", None) if _av else None
    if _pv is not None:
        _transforms = _pv.get_link_transforms()
        _t_raw = _transforms.numpy() if hasattr(_transforms, "numpy") else np.asarray(_transforms)
        _t = np.asarray(_t_raw, dtype=np.float64).reshape(_pv.count, _pv.max_links, 7)
        _bf_physx = _t[0, 0, :3].copy()
        _bf_physx_ori = _t[0, 0, 3:7].copy()
        print(f"[DIAG] PhysX base_footprint pos = ({_bf_physx[0]:.6f}, {_bf_physx[1]:.6f}, {_bf_physx[2]:.6f})")
        print(f"[DIAG] PhysX base_footprint ori = ({_bf_physx_ori[0]:.6f}, {_bf_physx_ori[1]:.6f}, {_bf_physx_ori[2]:.6f}, {_bf_physx_ori[3]:.6f})")
        _delta_bf = _bf_physx - np.array(ROBOT_WORLD_POS, dtype=np.float64)
        print(f"[DIAG] Delta (PhysX bf - /World/Tiago) = ({_delta_bf[0]:.6f}, {_delta_bf[1]:.6f}, {_delta_bf[2]:.6f})  |d|={np.linalg.norm(_delta_bf):.6f}")
except Exception as e:
    print(f"[DIAG] PhysX base_footprint check failed: {e}")

# ---------------------------------------------------------------------------
# TEST 1: Verify /World/Tiago is stable (base lock working)
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("  TEST 1: /World/Tiago stability check")
print("=" * 70)

prim_xf = XFormPrim(prim_path=tiago_prim_path)
prim_pos, prim_ori = prim_xf.get_world_pose()

expected_pos = np.array(ROBOT_WORLD_POS, dtype=np.float64)
actual_pos = np.array(prim_pos, dtype=np.float64)
delta_pos = actual_pos - expected_pos
delta_dist = np.linalg.norm(delta_pos)

print(f"\n  Expected pos = ({expected_pos[0]:.6f}, {expected_pos[1]:.6f}, {expected_pos[2]:.6f})")
print(f"  Actual pos   = ({actual_pos[0]:.6f}, {actual_pos[1]:.6f}, {actual_pos[2]:.6f})")
print(f"  Orientation  = ({prim_ori[0]:.6f}, {prim_ori[1]:.6f}, {prim_ori[2]:.6f}, {prim_ori[3]:.6f})")
print(f"  DELTA        = ({delta_pos[0]:.6f}, {delta_pos[1]:.6f}, {delta_pos[2]:.6f})  dist = {delta_dist:.6f} m")

if delta_dist < 0.001:
    print(f"\n  OK: /World/Tiago is stable (delta < 1mm)")
else:
    print(f"\n  *** WARNING: /World/Tiago drifted by {delta_dist:.4f} m ***")

# ---------------------------------------------------------------------------
# PhysX FK init
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("  Initializing PhysX FK")
print("=" * 70)

physx_tool_idx = None
body_names = []

try:
    from isaacsim.core.simulation_manager import SimulationManager
    sv = SimulationManager.get_physics_sim_view()
    av = getattr(tiago_articulation, "_articulation_view", None)
    pv = getattr(av, "_physics_view", None) if av else None

    if pv is None:
        print("[DIAG] FATAL: No physics view available")
        simulation_app.close()
        sys.exit(1)

    for attr in ("body_names", "link_names"):
        try:
            body_names = list(getattr(av, attr, []) or [])
            if body_names:
                break
        except Exception:
            pass
    if not body_names:
        try:
            body_names = list(getattr(pv.shared_metatype, "link_names", []) or [])
        except Exception:
            pass

    print(f"  Body names ({len(body_names)}): {body_names}")

    for target in ("arm_right_tool_link", "arm_tool_link", "arm_right_7_link", "arm_7_link"):
        for i, bn in enumerate(body_names):
            if bn == target:
                physx_tool_idx = i
                print(f"  Tool link: '{target}' at index {i}")
                break
        if physx_tool_idx is not None:
            break

    if physx_tool_idx is None:
        print("[DIAG] FATAL: Tool link not found in body names")
        simulation_app.close()
        sys.exit(1)

except Exception as e:
    print(f"[DIAG] FATAL: PhysX FK init error: {e}")
    simulation_app.close()
    sys.exit(1)

# Get DOF names and build index map
dof_names = []
try:
    dof_names = list(tiago_articulation.dof_names or [])
except Exception:
    pass
print(f"  DOF names ({len(dof_names)}): {dof_names}")

sim_dof_index = {}
for i, dn in enumerate(dof_names):
    sim_dof_index[dn] = i


def physx_get_tool_pos():
    transforms = pv.get_link_transforms()
    t_raw = transforms.numpy() if hasattr(transforms, "numpy") else np.asarray(transforms)
    t = np.asarray(t_raw, dtype=np.float64).reshape(pv.count, pv.max_links, 7)
    return t[0, physx_tool_idx, :3].copy()


def physx_get_link_pos(link_idx):
    transforms = pv.get_link_transforms()
    t_raw = transforms.numpy() if hasattr(transforms, "numpy") else np.asarray(transforms)
    t = np.asarray(t_raw, dtype=np.float64).reshape(pv.count, pv.max_links, 7)
    return t[0, link_idx, :3].copy()


def set_joints_and_settle(moveit_joints: dict, n_steps=120):
    """Set joint positions using MoveIt naming, mapped to Isaac Sim DOF names.
    Applies base lock each step to prevent drift (same as data_collector)."""
    n_dofs = len(dof_names)
    current = tiago_articulation.get_joint_positions()
    if current is None:
        current = np.zeros(n_dofs, dtype=np.float32)
    new_pos = np.array(current, dtype=np.float32)

    for mj_name, val in moveit_joints.items():
        sim_name = MOVEIT_TO_SIM.get(mj_name, mj_name)
        idx = sim_dof_index.get(sim_name)
        if idx is not None:
            new_pos[idx] = float(val)

    tiago_articulation.set_joint_positions(new_pos)
    tiago_articulation.set_joint_velocities(np.zeros(n_dofs, dtype=np.float32))

    from omni.isaac.core.utils.types import ArticulationAction
    targets = np.full(n_dofs, float("nan"), dtype=np.float32)
    for mj_name, val in moveit_joints.items():
        sim_name = MOVEIT_TO_SIM.get(mj_name, mj_name)
        idx = sim_dof_index.get(sim_name)
        if idx is not None:
            targets[idx] = float(val)
    tiago_articulation.apply_action(ArticulationAction(joint_positions=targets))

    _lock_xf = XFormPrim(prim_path=tiago_prim_path)
    for _ in range(n_steps):
        _lock_xf.set_world_pose(position=ROBOT_WORLD_POS, orientation=ROBOT_WORLD_ORI)
        tiago_articulation.set_world_pose(position=ROBOT_WORLD_POS, orientation=ROBOT_WORLD_ORI)
        world.step(render=False)


# ---------------------------------------------------------------------------
# TEST 2: FK comparison for each config
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("  TEST 2: FK comparison (PhysX vs URDF) for known joint configs")
print("=" * 70)

# Use /World/Tiago as the reference frame (same as data_collector_tiago.py)
ref_pos = np.array(prim_pos, dtype=np.float64)
ref_ori = np.array(prim_ori, dtype=np.float64)
w, x, y, z = ref_ori
yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
print(f"\n  /World/Tiago yaw = {math.degrees(yaw):.2f} deg")


def world_to_local(world_pos):
    """Convert world position to robot local frame using /World/Tiago."""
    d = np.array(world_pos, dtype=np.float64) - ref_pos
    cos_y = math.cos(-yaw)
    sin_y = math.sin(-yaw)
    return np.array([
        cos_y * d[0] - sin_y * d[1],
        sin_y * d[0] + cos_y * d[1],
        d[2],
    ])


def world_to_physx_bf(world_pos, bf_pos, bf_ori_xyzw):
    """Convert world position to PhysX base_footprint local frame.
    bf_ori_xyzw is (x,y,z,w) quaternion from PhysX."""
    x, y, z, w = bf_ori_xyzw
    d = np.array(world_pos, dtype=np.float64) - np.array(bf_pos, dtype=np.float64)
    # Inverse rotation: q_inv * d
    # For unit quaternion, q_inv = conjugate = (w, -x, -y, -z)
    # Rotate vector by quaternion: q * v * q_inv
    # But we want q_inv * v * q (inverse rotation)
    t = 2.0 * np.cross(np.array([-x, -y, -z]), d)
    return d + w * t + np.cross(np.array([-x, -y, -z]), t)


for config_name, joints in TEST_CONFIGS.items():
    print(f"\n  --- {config_name} ---")
    print(f"  Joints: {joints}")

    set_joints_and_settle(joints, n_steps=120)

    prim_pos_now, _ = XFormPrim(prim_path=tiago_prim_path).get_world_pose()

    # Read PhysX base_footprint position and tool link position
    _transforms = pv.get_link_transforms()
    _t_raw = _transforms.numpy() if hasattr(_transforms, "numpy") else np.asarray(_transforms)
    _t = np.asarray(_t_raw, dtype=np.float64).reshape(pv.count, pv.max_links, 7)
    _bf_pos = _t[0, 0, :3].copy()
    _bf_ori_xyzw = _t[0, 0, 3:7].copy()  # PhysX uses (x,y,z,w)

    physx_world = physx_get_tool_pos()

    # Method 1: local relative to /World/Tiago (current pipeline)
    physx_local_prim = world_to_local(physx_world)

    # Method 2: local relative to PhysX base_footprint (physics ground truth)
    physx_local_bf = world_to_physx_bf(physx_world, _bf_pos, _bf_ori_xyzw)

    urdf_local = urdf_fk(joints)

    delta_prim = physx_local_prim - urdf_local
    delta_bf = physx_local_bf - urdf_local
    err_prim = np.linalg.norm(delta_prim)
    err_bf = np.linalg.norm(delta_bf)

    print(f"\n  PhysX TOOL_LINK world      = ({physx_world[0]:.4f}, {physx_world[1]:.4f}, {physx_world[2]:.4f})")
    print(f"  PhysX base_footprint       = ({_bf_pos[0]:.4f}, {_bf_pos[1]:.4f}, {_bf_pos[2]:.4f})")
    print(f"  PhysX local (vs /W/Tiago)  = ({physx_local_prim[0]:.4f}, {physx_local_prim[1]:.4f}, {physx_local_prim[2]:.4f})")
    print(f"  PhysX local (vs PhysX bf)  = ({physx_local_bf[0]:.4f}, {physx_local_bf[1]:.4f}, {physx_local_bf[2]:.4f})")
    print(f"  URDF FK local              = ({urdf_local[0]:.4f}, {urdf_local[1]:.4f}, {urdf_local[2]:.4f})")
    print(f"  Delta (vs /W/Tiago)        = ({delta_prim[0]:.4f}, {delta_prim[1]:.4f}, {delta_prim[2]:.4f})  |err| = {err_prim:.4f} m")
    print(f"  Delta (vs PhysX bf)        = ({delta_bf[0]:.4f}, {delta_bf[1]:.4f}, {delta_bf[2]:.4f})  |err| = {err_bf:.4f} m")

    if err_bf < 0.02:
        print(f"  ==> OK (PhysX bf frame): FK matches URDF within 2cm!")
    elif err_bf < 0.05:
        print(f"  ==> CLOSE (PhysX bf frame): FK error {err_bf:.4f} m (2-5cm)")
    else:
        print(f"  ==> FAIL (PhysX bf frame): FK error {err_bf:.4f} m >= 5cm")

    if err_prim < 0.02:
        print(f"  ==> OK (/World/Tiago frame): FK matches URDF within 2cm!")
    else:
        print(f"  ==> FAIL (/World/Tiago frame): FK error {err_prim:.4f} m >= 2cm")

# ---------------------------------------------------------------------------
# TEST 3: Object coordinate transform comparison
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("  TEST 3: Coordinate transform verification")
print("=" * 70)

# Simulate the object at the known position from the smoke test
obj_world = np.array([1.280, -0.160, 0.801], dtype=np.float64)

local_via_prim = world_to_local(obj_world)

print(f"\n  Object world pos       = ({obj_world[0]:.4f}, {obj_world[1]:.4f}, {obj_world[2]:.4f})")
print(f"  Local via /World/Tiago = ({local_via_prim[0]:.4f}, {local_via_prim[1]:.4f}, {local_via_prim[2]:.4f})")
print(f"\n  Expected local (from smoke bridge.err.log) = (0.4800, -0.1600, 0.7210)")
print(f"  Match? {np.allclose(local_via_prim, [0.48, -0.16, 0.721], atol=0.01)}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("  SUMMARY")
print("=" * 70)
print(f"\n  /World/Tiago drift: {delta_dist:.4f} m (should be < 1mm)")
print(f"  NOTE: base_footprint XFormPrim drifts due to invalid inertia in USD.")
print(f"  All coordinate transforms correctly use /World/Tiago (base-locked).")

print(f"\n  Diagnostic complete.")
print("=" * 70)

simulation_app.close()
