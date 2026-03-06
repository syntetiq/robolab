import argparse
import os
import random
from pathlib import Path

OBJECT_LIBRARY = [
    {"name": "mug_blue", "size": (0.08, 0.08, 0.10), "color": (0.15, 0.35, 0.90), "semantic": "mug"},
    {"name": "mug_red", "size": (0.08, 0.08, 0.10), "color": (0.85, 0.20, 0.20), "semantic": "mug"},
    {"name": "bottle_green", "size": (0.06, 0.06, 0.25), "color": (0.20, 0.70, 0.30), "semantic": "bottle"},
    {"name": "bottle_clear", "size": (0.06, 0.06, 0.22), "color": (0.65, 0.80, 0.90), "semantic": "bottle"},
    {"name": "apple_red", "size": (0.07, 0.07, 0.07), "color": (0.85, 0.15, 0.10), "semantic": "fruit"},
    {"name": "apple_green", "size": (0.07, 0.07, 0.07), "color": (0.25, 0.70, 0.20), "semantic": "fruit"},
    {"name": "container_gray", "size": (0.15, 0.15, 0.10), "color": (0.55, 0.55, 0.55), "semantic": "container"},
    {"name": "container_white", "size": (0.14, 0.14, 0.09), "color": (0.85, 0.85, 0.85), "semantic": "container"},
]


def add_box(stage, path, size, position, color):
    from pxr import UsdGeom, UsdPhysics

    xform = UsdGeom.Xform.Define(stage, path)
    xform.AddTranslateOp().Set(position)

    cube = UsdGeom.Cube.Define(stage, f"{path}/Mesh")
    cube.GetSizeAttr().Set(1.0)
    cube.AddScaleOp().Set(size)

    UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
    cube.GetDisplayColorAttr().Set([color])
    return xform.GetPrim()


def add_semantic_label(prim, label):
    from omni.isaac.core.utils.semantics import add_update_semantics

    add_update_semantics(prim, label)


def create_articulated_door(stage, parent_path, name, door_size, door_pos, joint_axis="Y", hinge_pos=None):
    from pxr import UsdPhysics

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
        joint.CreateLocalPos1Attr().Set((-door_size[0] / 2, 0, 0))

    joint.CreateAxisAttr().Set(joint_axis)
    joint.CreateLowerLimitAttr().Set(0)
    joint.CreateUpperLimitAttr().Set(120 if joint_axis == "Z" else -120)

    drive = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "angular")
    drive.CreateTypeAttr().Set("force")
    drive.CreateDampingAttr().Set(10.0)
    drive.CreateStiffnessAttr().Set(0.0)

    add_semantic_label(door, f"{name.lower()}_door")
    return door


def build_fridge(stage, root_path, position):
    from pxr import UsdPhysics

    fridge_path = f"{root_path}/Fridge"
    body = add_box(stage, fridge_path, (0.8, 0.8, 2.0), position, (0.9, 0.9, 0.9))
    UsdPhysics.RigidBodyAPI.Apply(body)
    UsdPhysics.ArticulationRootAPI.Apply(body)

    create_articulated_door(
        stage,
        fridge_path,
        "FreezerDoor",
        (0.05, 0.78, 0.8),
        (0.42, 0, 0.5),
        "Z",
        (0.4, -0.4, 0.5),
    )
    create_articulated_door(
        stage,
        fridge_path,
        "FridgeDoor",
        (0.05, 0.78, 1.1),
        (0.42, 0, -0.45),
        "Z",
        (0.4, -0.4, -0.45),
    )
    add_semantic_label(body, "fridge")


def build_dishwasher(stage, root_path, position):
    from pxr import UsdPhysics

    dishwasher_path = f"{root_path}/Dishwasher"
    body = add_box(stage, dishwasher_path, (0.6, 0.6, 0.8), position, (0.2, 0.2, 0.2))
    UsdPhysics.RigidBodyAPI.Apply(body)
    UsdPhysics.ArticulationRootAPI.Apply(body)

    create_articulated_door(
        stage,
        dishwasher_path,
        "Door",
        (0.05, 0.58, 0.78),
        (0.32, 0, 0),
        "Y",
        (0.3, 0, -0.4),
    )
    add_semantic_label(body, "dishwasher")


def spawn_objects(stage, root_path, support_pos, rng, count=8):
    from pxr import UsdPhysics

    object_root = f"{root_path}/Objects"
    add_box(stage, f"{root_path}/ObjectSpawnerProxy", (0.01, 0.01, 0.01), (-100, -100, -100), (0.0, 0.0, 0.0))
    base_x, base_y, base_z = support_pos
    base_z += 0.5

    chosen = rng.sample(OBJECT_LIBRARY, min(count, len(OBJECT_LIBRARY)))
    for idx, template in enumerate(chosen):
        x = base_x + rng.uniform(-0.32, 0.32)
        y = base_y + rng.uniform(-0.32, 0.32)
        path = f"{object_root}/{template['name']}_{idx}"
        prim = add_box(stage, path, template["size"], (x, y, base_z), template["color"])

        UsdPhysics.RigidBodyAPI.Apply(prim)
        mass = UsdPhysics.MassAPI.Apply(prim)
        mass.GetMassAttr().Set(0.35)

        add_semantic_label(prim, template["semantic"])


def init_stage(stage):
    from pxr import UsdGeom

    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    UsdGeom.Xform.Define(stage, "/World/Environment")


def build_small_house(stage, seed):
    rng = random.Random(seed)
    root_path = "/World/Environment"

    add_box(stage, f"{root_path}/Floor", (10.0, 10.0, 0.1), (0, 0, -0.05), (0.2, 0.2, 0.2))
    table_pos = (1.5, 0.0, 0.4)
    table = add_box(stage, f"{root_path}/Table", (1.0, 1.0, 0.8), table_pos, (0.6, 0.4, 0.2))
    sink = add_box(stage, f"{root_path}/Sink", (0.8, 0.6, 0.8), (1.5, 1.2, 0.4), (0.9, 0.9, 0.95))
    add_semantic_label(table, "table")
    add_semantic_label(sink, "sink")

    build_fridge(stage, root_path, (0.0, 1.5, 1.0))
    build_dishwasher(stage, root_path, (1.5, -1.0, 0.4))
    spawn_objects(stage, root_path, table_pos, rng, count=8)


def build_office(stage, seed):
    rng = random.Random(seed + 1000)
    root_path = "/World/Environment"

    add_box(stage, f"{root_path}/Floor", (10.0, 10.0, 0.1), (0, 0, -0.05), (0.2, 0.2, 0.2))
    desk_pos = (1.5, 0.0, 0.4)
    desk = add_box(stage, f"{root_path}/Desk", (1.2, 0.6, 0.8), desk_pos, (0.2, 0.2, 0.2))
    cabinet = add_box(stage, f"{root_path}/Cabinet", (0.5, 0.8, 1.2), (0.0, 1.5, 0.6), (0.7, 0.7, 0.7))
    add_semantic_label(desk, "desk")
    add_semantic_label(cabinet, "cabinet")

    # Office environment keeps a sink + dishwasher for cross-domain task transfer.
    sink = add_box(stage, f"{root_path}/Sink", (0.8, 0.6, 0.8), (2.0, 1.2, 0.4), (0.9, 0.9, 0.95))
    add_semantic_label(sink, "sink")
    build_dishwasher(stage, root_path, (2.0, -1.0, 0.4))
    spawn_objects(stage, root_path, desk_pos, rng, count=8)


def save_stage(stage, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stage.GetRootLayer().Export(str(output_path))
    print(f"[RoboLab] Saved: {output_path}")


def generate_scene(scene_name, output_path, seed):
    import omni.isaac.core.utils.stage as stage_utils
    import omni.usd

    stage_utils.clear_stage()
    stage_utils.create_new_stage()
    stage = omni.usd.get_context().get_stage()
    init_stage(stage)

    if scene_name == "office":
        build_office(stage, seed)
    else:
        build_small_house(stage, seed)

    save_stage(stage, output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate interactive RoboLab scenes.")
    parser.add_argument(
        "--scene",
        type=str,
        choices=["small_house", "office", "all"],
        default="all",
        help="Which scene to generate.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="C:\\RoboLab_Data\\scenes",
        help="Directory for generated USD scenes.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic randomization seed for object layout.",
    )
    args = parser.parse_args()

    from isaacsim import SimulationApp

    simulation_app = SimulationApp({"headless": True})
    out_dir = Path(args.output_dir)

    try:
        if args.scene in ("small_house", "all"):
            generate_scene("small_house", out_dir / "Small_House_Interactive.usd", args.seed)
        if args.scene in ("office", "all"):
            generate_scene("office", out_dir / "Office_Interactive.usd", args.seed)
        print("[RoboLab] Scene generation complete.")
    finally:
        simulation_app.close()


