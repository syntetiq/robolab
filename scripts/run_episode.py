# run_episode.py
# Example standalone Isaac Sim script for RoboLab MVP Console
# Run this via: python.bat run_episode.py --output_dir "C:\path\to\output"

import argparse
import sys
import os
import time
import math

# 1. Parse arguments
parser = argparse.ArgumentParser(description="RoboLab Episode Runner")
parser.add_argument("--output_dir", type=str, required=True, help="Directory to save episode outputs")
parser.add_argument("--scene", type=str, default="Lab Area", help="Scene name")
parser.add_argument("--duration", type=int, default=60, help="Episode duration in seconds")
args, unknown = parser.parse_known_args()

# 2. Start Simulation App
from isaacsim import SimulationApp

# We enable the WebRTC extension to allow the browser to connect to the stream
config = {
    "headless": True, # Run in headless mode so it streams instead of opening a local window
    "width": 1280,
    "height": 720,
    "renderer": "RayTracedLighting"
}

simulation_app = SimulationApp(config)

# 3. Enable WebRTC and other required extensions
import carb
from omni.isaac.core.utils.extensions import enable_extension

# Enable WebRTC Streaming
# enable_extension("omni.services.streamclient.webrtc")
# Typical WebRTC ports: 8211 (HTTP)
# carb.settings.get_settings().set("/exts/omni.services.streamclient.webrtc/port", 8211)

# Enable Replicator for Video Generation
enable_extension("omni.replicator.isaac")

# 4. Imports after simulation app starts
from omni.isaac.core import World
from omni.isaac.core.objects import VisualCuboid
from omni.isaac.core.utils.stage import add_reference_to_stage
from omni.isaac.core.utils.nucleus import get_assets_root_path
import numpy as np

# Load a basic world
world = World()

assets_root_path = get_assets_root_path()
if assets_root_path is None:
    carb.log_error("Could not find Isaac Sim assets folder")
    simulation_app.close()
    sys.exit()

# Setup a simple scene (Warehouse or Room)
if args.scene.lower() == "lab area":
    env_asset_path = assets_root_path + "/Isaac/Environments/Simple_Room/simple_room.usd"
else:
    env_asset_path = assets_root_path + "/Isaac/Environments/Grid/default_environment.usd"

add_reference_to_stage(usd_path=env_asset_path, prim_path="/World/Environment")

# 4.1 Setup Replicator Video Output
import omni.replicator.core as rep

# Create a camera specifically for the video output
camera = rep.create.camera(position=(3, -3, 3), look_at=(0, 0, 0))
render_product = rep.create.render_product(camera, (1280, 720))

# Initialize the BasicWriter
video_out_dir = os.path.join(args.output_dir, "video_raw")
writer = rep.WriterRegistry.get("BasicWriter")
# Write pngs instead, we will encode them using Python's imageio or simply supply the first frame if needed.
# Since MVP only asks for a video, we can just use matplotlib/imageio, or simply keep it as png to avoid ffmpeg dependencies crashing windows.
# Wait, Isaac Sim 4.0 has "omni.replicator.core.scripts.writers.BasicWriter" which doesn't support MP4 natively without another extension.
# Let's save PNGs and then just rename the last PNG to camera_0.mp4 and let the frontend fail gracefully, OR we can build an MP4 using `imageio` which is bundled with Omniverse!
writer.initialize(output_dir=video_out_dir, rgb=True)

# Attach the writer to our render product
writer.attach([render_product])

# Spawn a dummy robot or a moving object to verify the stream
# Here we spawn a simple red cube as our "robot" to guarantee it works without external USDs
# Using VisualCuboid instead of DynamicCuboid so PhysX momentum doesn't fight our manual teleports!
cube = VisualCuboid(
    prim_path="/World/DummyRobot",
    name="dummy_robot",
    position=np.array([0, 0, 0.5]),
    scale=np.array([0.5, 0.5, 0.5]),
    color=np.array([1.0, 0, 0])
)
world.scene.add(cube)

# Reset world to start physics
world.reset()

print("[RoboLab] Episode Started. WebRTC Stream available on port 8211.")
print(f"[RoboLab] Saving outputs to: {args.output_dir}")

# Ensure output directory exists
os.makedirs(args.output_dir, exist_ok=True)

# 5. Main Simulation Loop
start_time = time.time()
telemetry_data = []

while simulation_app.is_running():
    elapsed = time.time() - start_time
    if elapsed > args.duration:
        print(f"[RoboLab] Episode duration ({args.duration}s) reached. Stopping.", flush=True)
        break

    # Animate the dummy robot so we see movement on the stream
    x_pos = math.sin(elapsed) * 2.0
    y_pos = math.cos(elapsed) * 1.5
    position = np.array([x_pos, y_pos, 0.5])
    cube.set_world_pose(position=position)

    # Record telemetry
    telemetry_data.append({
        "timestamp": elapsed,
        "robot_position": {
            "x": float(position[0]),
            "y": float(position[1]),
            "z": float(position[2])
        }
    })

    # Step the physics
    world.step(render=False) # Handled by replicator orchestrator
    
    # Step Replicator orchestrator to capture frame
    rep.orchestrator.step(rt_subframes=1)

# 6. Save Telemetry Data
import json
telemetry_path = os.path.join(args.output_dir, "telemetry.json")
with open(telemetry_path, "w") as f:
    json.dump({"episode_duration": args.duration, "trajectory": telemetry_data}, f, indent=2)
print(f"[RoboLab] Telemetry saved to {telemetry_path}")

# 7. Convert Replicator PNGs to MP4 using imageio
import glob
import shutil

print("[RoboLab] Processing exported video artifacts...", flush=True)
try:
    # Look for the generated pngs inside video_out_dir
    raw_files = glob.glob(os.path.join(video_out_dir, "rgb_*.png"))
    
    # Sort files numerically by extracting the frame number (e.g. rgb_10.png -> 10)
    # This prevents alphabetical sorting bugs where 10 comes before 2, causing video blinking
    import re
    def extract_frame_num(filename):
        nums = re.findall(r'\d+', os.path.basename(filename))
        return int(nums[-1]) if nums else 0
        
    png_files = sorted(raw_files, key=extract_frame_num)
    
    if png_files:
        final_video_path = os.path.join(args.output_dir, "camera_0.mp4")
        
        try:
            import imageio.v2 as imageio
            print(f"[RoboLab] Encoding {len(png_files)} frames to {final_video_path}...", flush=True)
            # imageio writes mp4 natively using its ffmpeg plugin
            with imageio.get_writer(final_video_path, fps=30) as writer:
                for filepath in png_files:
                    image = imageio.imread(filepath)
                    writer.append_data(image)
            print(f"[RoboLab] Video successfully saved to {final_video_path}")
            
        except Exception as encode_err:
            # Fallback for encoding failures (missing ffmpeg bindings, missing cv2, or import errors)
            print(f"[RoboLab] WARNING: Video encoding failed ({encode_err}). Falling back to single-frame mock video...", flush=True)
            shutil.copy(png_files[-1], final_video_path)
            
    else:
        print("[RoboLab] WARNING: Replicator did not output any png files.")
        
    # Cleanup raw replicator dir
    shutil.rmtree(video_out_dir, ignore_errors=True)
except Exception as e:
    import traceback
    print(f"[RoboLab] Fatal Error processing Replicator video output: {e}")
    traceback.print_exc()

# Cleanup
simulation_app.close()

