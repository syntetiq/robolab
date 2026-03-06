# scripts/build_data_collection_scenes.py
# Run this script using the Isaac Sim Python interpreter on the host machine using:
# python.bat scripts/build_data_collection_scenes.py

import sys
import os
import argparse
from pathlib import Path

# Parse arguments
parser = argparse.ArgumentParser(description="Environment Builder for Tiago Data Collection")
parser.add_argument("--output_path", type=str, default="data/scenes", help="Directory to save USD scenes")
args, _ = parser.parse_known_args()

print("[RoboLab] Starting Isaac Sim Environment Builder...")

from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": True})

import omni.client
import omni.usd
from omni.isaac.core.utils.nucleus import get_assets_root_path
from pxr import Usd, UsdGeom, Sdf

assets_root_path = get_assets_root_path()
if assets_root_path is None:
    print("[Error] Could not find Isaac Sim assets folder on Nucleus.")
    simulation_app.close()
    sys.exit(1)

# Ensure output directory exists
os.makedirs(args.output_path, exist_ok=True)
out_dir = os.path.abspath(args.output_path)

def create_environment(name, base_usd, props=[]):
    stage_path = os.path.join(out_dir, f"{name}.usd")
    print(f"\n[RoboLab] Building {name} at {stage_path}...")
    
    # Create new stage
    omni.usd.get_context().new_stage()
    stage = omni.usd.get_context().get_stage()

    # Define root
    UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    stage.SetUpAxis(UsdGeom.Tokens.z)
    
    # Add base environment
    env_prim_path = "/World/Environment"
    env_prim = stage.DefinePrim(env_prim_path, "Xform")
    env_prim.GetReferences().AddReference(base_usd)
    print(f"  -> Added Base Environment: {base_usd}")

    # Add props
    prop_root = "/World/Props"
    stage.DefinePrim(prop_root, "Xform")
    
    for i, prop in enumerate(props):
        prop_name, prop_usd, position, scale = prop
        prim_path = f"{prop_root}/{prop_name}_{i}"
        prim = stage.DefinePrim(prim_path, "Xform")
        prim.GetReferences().AddReference(prop_usd)
        
        # Set transform
        xform = UsdGeom.Xformable(prim)
        xform.AddTranslateOp().Set(position)
        if scale:
            xform.AddScaleOp().Set(scale)
            
        print(f"  -> Added Prop: {prop_name} at {position}")
        
        # Assign semantic label based on name
        from omni.isaac.core.utils.semantics import add_update_semantics
        add_update_semantics(prim, prop_name)

    # Save
    omni.usd.get_context().save_as_stage(stage_path)
    print(f"[RoboLab] Saved {name} successfully.")


# 1. Build Small House
small_house_base = f"{assets_root_path}/Isaac/Environments/Hospital/hospital.usd" # Hospital has good kitchen counter setups
small_house_props = [
    # (Name, Nucleus_USD_Path, Position(x,y,z), Scale(x,y,z))
    # We use common Isaac Sim assets. If they don't explicitly exist, Isaac Sim will just show a missing reference, 
    # but these are standard paths in 2023.1.1+
    ("Table", f"{assets_root_path}/Isaac/Environments/Simple_Room/Props/table.usd", (1.0, 0.0, 0.0), (1, 1, 1)),
    # Add random YCB objects for diversity
    ("CrackerBox", f"{assets_root_path}/Isaac/Props/YCB/Axis_Aligned/003_cracker_box.usd", (1.0, 0.1, 0.8), None),
    ("SoupCan", f"{assets_root_path}/Isaac/Props/YCB/Axis_Aligned/005_tomato_soup_can.usd", (1.0, -0.1, 0.8), None),
    ("Mustard", f"{assets_root_path}/Isaac/Props/YCB/Axis_Aligned/006_mustard_bottle.usd", (0.8, 0.0, 0.8), None),
]
create_environment("Small_House", small_house_base, small_house_props)

# 2. Build Office
office_base = f"{assets_root_path}/Isaac/Environments/Office/office.usd"
office_props = [
    ("Mug", f"{assets_root_path}/Isaac/Props/YCB/Axis_Aligned/025_mug.usd", (0.0, 0.0, 0.8), None),
]
create_environment("Office", office_base, office_props)

print("\n[RoboLab] All environments built successfully.")
simulation_app.close()
sys.exit(0)
