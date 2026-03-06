import os
import random

def add_box(stage, path, size, position, color, name="box"):
    from pxr import UsdGeom, UsdPhysics
    xform = UsdGeom.Xform.Define(stage, path)
    xform.AddTranslateOp().Set(position)
    
    cube = UsdGeom.Cube.Define(stage, f"{path}/Mesh")
    cube.GetSizeAttr().Set(1.0)
    cube.AddScaleOp().Set(size)
    
    UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
    if color:
        cube.GetDisplayColorAttr().Set([color])
    return xform.GetPrim()

def create_articulated_door(stage, parent_path, name, door_size, door_pos, joint_axis="Y", hinge_pos=None):
    from pxr import UsdPhysics
    from omni.isaac.core.utils.semantics import add_update_semantics
    
    door_path = f"{parent_path}/{name}"
    door = add_box(stage, door_path, door_size, door_pos, (0.8, 0.8, 0.8))
    
    UsdPhysics.RigidBodyAPI.Apply(door)
    mass_api = UsdPhysics.MassAPI.Apply(door)
    mass_api.GetMassAttr().Set(2.0)
    
    joint_path = f"{door_path}/Hinge"
    joint = UsdPhysics.RevoluteJoint.Define(stage, joint_path)
    joint.CreateBody0Rel().SetTargets([parent_path])
    joint.CreateBody1Rel().SetTargets([door_path])
    
    if hinge_pos:
        joint.CreateLocalPos0Attr().Set(hinge_pos)
        joint.CreateLocalPos1Attr().Set((-door_size[0]/2, 0, 0))
    
    joint.CreateAxisAttr().Set(joint_axis)
    joint.CreateLowerLimitAttr().Set(0)
    joint.CreateUpperLimitAttr().Set(120 if joint_axis == "Z" else -120) 
    
    drive = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "angular")
    drive.CreateTypeAttr().Set("force")
    drive.CreateDampingAttr().Set(10.0)
    drive.CreateStiffnessAttr().Set(0.0)
    
    add_update_semantics(door, name)
    return door

def build_fridge(stage, root_path, position):
    from pxr import UsdPhysics
    from omni.isaac.core.utils.semantics import add_update_semantics
    
    fridge_path = f"{root_path}/Fridge"
    body = add_box(stage, fridge_path, (0.8, 0.8, 2.0), position, (0.9, 0.9, 0.9))
    UsdPhysics.RigidBodyAPI.Apply(body)
    UsdPhysics.ArticulationRootAPI.Apply(body)
    
    create_articulated_door(stage, fridge_path, "FreezerDoor", (0.05, 0.78, 0.8), (0.42, 0, 0.5), "Z", (0.4, -0.4, 0.5))
    create_articulated_door(stage, fridge_path, "FridgeDoor", (0.05, 0.78, 1.1), (0.42, 0, -0.45), "Z", (0.4, -0.4, -0.45))
    add_update_semantics(body, "Fridge")

def build_dishwasher(stage, root_path, position):
    from pxr import UsdPhysics
    from omni.isaac.core.utils.semantics import add_update_semantics
    
    dw_path = f"{root_path}/Dishwasher"
    body = add_box(stage, dw_path, (0.6, 0.6, 0.8), position, (0.2, 0.2, 0.2))
    UsdPhysics.RigidBodyAPI.Apply(body)
    UsdPhysics.ArticulationRootAPI.Apply(body)

    create_articulated_door(stage, dw_path, "Door", (0.05, 0.58, 0.78), (0.32, 0, 0), "Y", (0.3, 0, -0.4))
    add_update_semantics(body, "Dishwasher")

def spawn_objects(stage, root_path, table_pos):
    from pxr import UsdPhysics
    from omni.isaac.core.utils.semantics import add_update_semantics
    
    objects = [
        {"name": "Mug_Blue", "size": (0.08, 0.08, 0.1), "color": (0, 0, 1)},
        {"name": "Mug_Red", "size": (0.08, 0.08, 0.1), "color": (1, 0, 0)},
        {"name": "Bottle", "size": (0.06, 0.06, 0.25), "color": (0, 1, 0)},
        {"name": "Apple", "size": (0.07, 0.07, 0.07), "color": (0.8, 0.1, 0.1)},
        {"name": "Container", "size": (0.15, 0.15, 0.1), "color": (0.5, 0.5, 0.5)},
    ]
    
    base_x, base_y, base_z = table_pos
    base_z += 0.5 
    
    for obj in objects:
        x = base_x + random.uniform(-0.3, 0.3)
        y = base_y + random.uniform(-0.3, 0.3)
        
        path = f"{root_path}/{obj['name']}"
        prim = add_box(stage, path, obj["size"], (x, y, base_z), obj["color"])
        
        UsdPhysics.RigidBodyAPI.Apply(prim)
        mass = UsdPhysics.MassAPI.Apply(prim)
        mass.GetMassAttr().Set(0.5)
        
        add_update_semantics(prim, obj["name"])

def generate_small_house(output_path):
    import omni.isaac.core.utils.stage as stage_utils
    from omni.isaac.core.utils.semantics import add_update_semantics
    from pxr import UsdGeom
    import omni.usd
    
    print(f"Generating Small House Interactive at {output_path}...")
    stage_utils.clear_stage()
    stage_utils.create_new_stage()
    stage = omni.usd.get_context().get_stage()
    
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    
    root_path = "/World/Environment"
    UsdGeom.Xform.Define(stage, root_path)
    
    floor = add_box(stage, f"{root_path}/Floor", (10.0, 10.0, 0.1), (0, 0, -0.05), (0.2, 0.2, 0.2))
    
    table_pos = (1.5, 0.0, 0.4)
    table = add_box(stage, f"{root_path}/Table", (1.0, 1.0, 0.8), table_pos, (0.6, 0.4, 0.2))
    add_update_semantics(table, "Table")
    
    sink = add_box(stage, f"{root_path}/Sink", (0.8, 0.6, 0.8), (1.5, 1.2, 0.4), (0.9, 0.9, 0.95))
    add_update_semantics(sink, "Sink")
    
    build_fridge(stage, root_path, (0.0, 1.5, 1.0))
    build_dishwasher(stage, root_path, (1.5, -1.0, 0.4))
    
    spawn_objects(stage, root_path, table_pos)
    
    stage.Save(output_path)
    print("Saved Small House.")

def generate_office(output_path):
    import omni.isaac.core.utils.stage as stage_utils
    from omni.isaac.core.utils.semantics import add_update_semantics
    from pxr import UsdGeom
    import omni.usd
    
    print(f"Generating Office Data at {output_path}...")
    stage_utils.clear_stage()
    stage_utils.create_new_stage()
    stage = omni.usd.get_context().get_stage()
    
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    
    root_path = "/World/Environment"
    UsdGeom.Xform.Define(stage, root_path)
    
    floor = add_box(stage, f"{root_path}/Floor", (10.0, 10.0, 0.1), (0, 0, -0.05), (0.2, 0.2, 0.2))
    
    desk_pos = (1.5, 0.0, 0.4)
    desk = add_box(stage, f"{root_path}/Desk", (1.2, 0.6, 0.8), desk_pos, (0.2, 0.2, 0.2))
    add_update_semantics(desk, "Desk")
    
    cabinet = add_box(stage, f"{root_path}/Cabinet", (0.5, 0.8, 1.2), (0.0, 1.5, 0.6), (0.7, 0.7, 0.7))
    add_update_semantics(cabinet, "Cabinet")
    
    spawn_objects(stage, root_path, desk_pos)
    
    stage.Save(output_path)
    print("Saved Office.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=str, required=True)
    args = parser.parse_args()
    
    from isaacsim import SimulationApp
    simulation_app = SimulationApp({"headless": True})
    
    from omni.isaac.core import SimulationContext
    sim = SimulationContext()
    
    if "Office" in args.out:
        generate_office(args.out)
    else:
        generate_small_house(args.out)
    
    simulation_app.close()


