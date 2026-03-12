import argparse
import sys
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument("--usd", type=str, default=r"C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional_light.usd")
args = parser.parse_args()

from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": False})

from omni.isaac.core import World
from omni.isaac.core.robots import Robot
from omni.isaac.core.utils.stage import add_reference_to_stage
from omni.isaac.core.utils.types import ArticulationAction
from pxr import UsdPhysics

world = World()
world.scene.add_default_ground_plane()

robot_prim_path = "/World/Tiago"
add_reference_to_stage(args.usd, robot_prim_path)

robot = Robot(prim_path=robot_prim_path, name="tiago")
world.scene.add(robot)

print("Configuring drives...")
stage = world.stage
for jp in stage.Traverse():
    if not jp.IsA(UsdPhysics.RevoluteJoint) and not jp.IsA(UsdPhysics.PrismaticJoint):
        continue
    dt = "angular" if jp.IsA(UsdPhysics.RevoluteJoint) else "linear"
    da = UsdPhysics.DriveAPI.Apply(jp, dt)
    da.CreateTypeAttr("force")
    da.CreateStiffnessAttr().Set(1e6)
    da.CreateDampingAttr().Set(1e5)
    da.CreateMaxForceAttr().Set(1e8)

world.reset()

print("Warming up...")
for _ in range(100):
    world.step(render=True)

dof_names = robot.dof_names
print(f"Robot DOFs: {dof_names}")

target_pos = np.zeros(len(dof_names), dtype=np.float32)
if "arm_right_1_joint" in dof_names:
    idx = dof_names.index("arm_right_1_joint")
    target_pos[idx] = 1.0
    print(f"Setting arm_right_1_joint to 1.0 (idx {idx})")
if "torso_lift_joint" in dof_names:
    idx = dof_names.index("torso_lift_joint")
    target_pos[idx] = 0.3
    print(f"Setting torso_lift_joint to 0.3 (idx {idx})")

print("Applying action...")
robot.apply_action(ArticulationAction(joint_positions=target_pos))

print("Simulating...")
for iter in range(200):
    world.step(render=True)
    if iter % 50 == 0:
        pos = robot.get_joint_positions()
        print(f"Step {iter} arm_right_1_joint=", pos[dof_names.index("arm_right_1_joint")])

print("Done.")
simulation_app.close()
