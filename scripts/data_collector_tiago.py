# scripts/data_collector_tiago.py
# Usage: python.bat scripts/data_collector_tiago.py --env data/scenes/Small_House.usd --output_dir data/collection_01

import argparse
import sys
import os
import json
import numpy as np

parser = argparse.ArgumentParser(description="Tiago Data Collection Script")
parser.add_argument("--env", type=str, required=True, help="Path to environment USD")
parser.add_argument("--output_dir", type=str, required=True, help="Directory for dataset")
parser.add_argument("--duration", type=int, default=120, help="Recording duration in seconds")
parser.add_argument("--headless", action="store_true", help="Run without UI")
parser.add_argument("--vr", action="store_true", help="Enable SteamVR/OpenXR Teleoperation")
parser.add_argument("--webrtc", action="store_true", help="Enable WebRTC stream on Port 8211")
args, _ = parser.parse_known_args()

os.makedirs(args.output_dir, exist_ok=True)
print("[RoboLab] Starting Tiago Data Collector...")

from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": args.headless, "livestream": 2 if args.webrtc else 0})

from omni.isaac.core.utils.extensions import enable_extension
enable_extension("omni.isaac.core_nodes")
enable_extension("omni.isaac.ros2_bridge")
enable_extension("omni.replicator.core")

if args.vr:
    print("[RoboLab] Enabling VR Teleoperation Mode (OpenXR)...")
    enable_extension("omni.kit.xr.profile.vr")

if args.webrtc:
    import carb
    print("[RoboLab] Applying standard WebRTC Livestream port...")
    carb.settings.get_settings().set("/exts/omni.kit.livestream.webrtc/port", 8211)

simulation_app.update()

import omni.isaac.core.utils.stage as stage_utils
from omni.isaac.core import World
from omni.isaac.core.articulations import Articulation
from omni.isaac.core.prims import XFormPrim
from omni.isaac.core.utils.semantics import get_semantics
import omni.replicator.core as rep
import omni.graph.core as og
from pxr import UsdGeom

# 1. Load Environment
world = World()
stage_utils.add_reference_to_stage(usd_path=os.path.abspath(args.env), prim_path="/World/Environment")

# 2. Spawn Tiago
tiago_usd_path = "C:/RoboLab_Data/tiago_isaac/tiago_dual_functional.usd"
tiago_prim_path = "/World/Tiago"
stage_utils.add_reference_to_stage(usd_path=tiago_usd_path, prim_path=tiago_prim_path)

# tiago_articulation = Articulation(tiago_prim_path, name="tiago")
# world.scene.add(tiago_articulation)

# Setup Semantic Label for Tiago for Replicator segmentation
from omni.isaac.core.utils.semantics import add_update_semantics
add_update_semantics(stage_utils.get_current_stage().GetPrimAtPath(tiago_prim_path), "Tiago")

# 3. ROS 2 Bridge Action Graphs disabled for pure Headless WebRTC Teleop
print("[RoboLab] Skipping ROS 2 Action Graphs to prevent WebRTC initialization conflicts...")


# 4. Setup Replicator for Point Cloud & Camera Data
# Head camera transform relative to Tiago
camera_prim_path = "/World/Tiago" 
# Create camera and parent it to the head link
head_camera = rep.create.camera(position=(0,0,0), parent=camera_prim_path)

if args.vr:
    import omni.kit.viewport.utility
    viewport = omni.kit.viewport.utility.get_active_viewport()
    if viewport:
        viewport.camera_path = str(head_camera.node.get_attribute("primPath").get())
        print(f"[RoboLab] Attached VR Viewport to Tiago Head Camera: {viewport.camera_path}")

render_product = rep.create.render_product(head_camera, (640, 480))
writer = rep.WriterRegistry.get("BasicWriter")
writer.initialize(
    output_dir=os.path.join(args.output_dir, "replicator_data"),
    rgb=True,
    distance_to_camera=True,
    pointcloud=True,
    semantic_segmentation=True
)
writer.attach([render_product])


# Search for interactive props to track poses
stage = stage_utils.get_current_stage()
tracked_prims = []
for prim in stage.Traverse():
    if prim.HasAPI(UsdGeom.Xformable):
        # Only track props with semantic labels (e.g. Mug, Fridge)
        sem = get_semantics(prim)
        if sem and "class" in sem and sem["class"] != "class":
            tracked_prims.append((str(prim.GetPath()), sem["class"]))
            
print(f"[RoboLab] Tracking {len(tracked_prims)} objects for world poses.")

world.reset()

dataset = {
    "duration": args.duration,
    "frames": []
}

import time
start_time = time.time()
print("\n[RoboLab] Starting Data Collection Simulation loop...")

while simulation_app.is_running():
    elapsed = time.time() - start_time
    if elapsed > args.duration:
        break
        
    world.step(render=False)
    rep.orchestrator.step(rt_subframes=1)
    
    # Collect World Poses
    poses = {}
    for prim_path, cls_name in tracked_prims:
        xform = XFormPrim(prim_path)
        pos, rot = xform.get_world_pose()
        poses[cls_name] = {
            "position": pos.tolist() if pos is not None else [],
            "orientation": rot.tolist() if rot is not None else []
        }
        
    # Collect Joint States (Disabled temporarily for WebRTC stability)
    joints = {}
        
    dataset["frames"].append({
        "timestamp": elapsed,
        "robot_joints": joints,
        "world_poses": poses
    })

# Save structured dataset
output_json = os.path.join(args.output_dir, "dataset.json")
with open(output_json, "w") as f:
    json.dump(dataset, f, indent=2)

print(f"\n[RoboLab] Data collection complete! Dataset saved to {output_json}")
print(f"[RoboLab] Replicator PointClouds/Images saved to {os.path.join(args.output_dir, 'replicator_data')}")

try:
    import omni.timeline
    omni.timeline.get_timeline_interface().stop()
    rep.orchestrator.wait_until_complete()
except Exception as e:
    print(f"[RoboLab] Ignored error during shutdown sync: {e}")

simulation_app.update()
simulation_app.close()
sys.exit(0)
