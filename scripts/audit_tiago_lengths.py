import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from pxr import Usd, UsdGeom, Gf

USD_PATH = Path(r"C:\RoboLab_Data\data\tiago_isaac\tiago_dual_functional.usd")
URDF_PATH = Path(r"C:\Users\max\Documents\Cursor\robolab\config\tiago_right_arm.urdf")


def find_prim_paths(stage, suffix):
    out = []
    for prim in stage.Traverse():
        if prim.GetPath().pathString.endswith(suffix):
            out.append(prim.GetPath().pathString)
    return out


def transform_point_to_tool(tool_T, p_world):
    inv = tool_T.GetInverse()
    return inv.Transform(Gf.Vec3d(float(p_world[0]), float(p_world[1]), float(p_world[2])))


def bbox_corners_world(range3d):
    mn = range3d.GetMin()
    mx = range3d.GetMax()
    corners = []
    for x in (mn[0], mx[0]):
        for y in (mn[1], mx[1]):
            for z in (mn[2], mx[2]):
                corners.append((x, y, z))
    return corners


def collect_descendant_imageables(prim, skip_prefixes=()):
    out = []
    root = prim.GetPath().pathString
    for p in prim.GetStage().Traverse():
        ps = p.GetPath().pathString
        if not ps.startswith(root):
            continue
        if any(ps.startswith(pref) for pref in skip_prefixes):
            continue
        if p.IsA(UsdGeom.Imageable):
            out.append(p)
    return out


def project_extents_tool_frame(tool_T, imageable_prims):
    if not imageable_prims:
        return None
    bbox_cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render, UsdGeom.Tokens.proxy])
    pts_tool = []
    for p in imageable_prims:
        try:
            wb = bbox_cache.ComputeWorldBound(p)
            r = wb.ComputeAlignedRange()
            if r.IsEmpty():
                continue
            for c in bbox_corners_world(r):
                t = transform_point_to_tool(tool_T, c)
                pts_tool.append((float(t[0]), float(t[1]), float(t[2])))
        except Exception:
            pass
    if not pts_tool:
        return None
    xs = [p[0] for p in pts_tool]
    ys = [p[1] for p in pts_tool]
    zs = [p[2] for p in pts_tool]
    return {
        "min": [min(xs), min(ys), min(zs)],
        "max": [max(xs), max(ys), max(zs)],
        "centroid": [sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs)],
        "points_count": len(pts_tool),
    }


def main():
    stage = Usd.Stage.Open(str(USD_PATH))
    if not stage:
        raise RuntimeError(f"Cannot open USD: {USD_PATH}")

    tool_paths = find_prim_paths(stage, "/arm_right_tool_link")
    lf_paths = find_prim_paths(stage, "/gripper_right_left_finger_link")
    rf_paths = find_prim_paths(stage, "/gripper_right_right_finger_link")

    if not tool_paths:
        raise RuntimeError("arm_right_tool_link not found")
    if not lf_paths or not rf_paths:
        raise RuntimeError("finger links not found")

    tool = stage.GetPrimAtPath(tool_paths[0])
    lf = stage.GetPrimAtPath(lf_paths[0])
    rf = stage.GetPrimAtPath(rf_paths[0])

    tool_T = UsdGeom.Xformable(tool).ComputeLocalToWorldTransform(Usd.TimeCode.Default())

    finger_imgs = collect_descendant_imageables(lf) + collect_descendant_imageables(rf)
    finger_ext = project_extents_tool_frame(tool_T, finger_imgs)

    skip = (lf.GetPath().pathString, rf.GetPath().pathString)
    palm_imgs = collect_descendant_imageables(tool, skip_prefixes=skip)
    palm_ext = project_extents_tool_frame(tool_T, palm_imgs)

    full_imgs = collect_descendant_imageables(tool)
    full_ext = project_extents_tool_frame(tool_T, full_imgs)

    axes = ["x", "y", "z"]
    c = finger_ext["centroid"] if finger_ext else [0, 0, 1]
    axis_idx = max(range(3), key=lambda i: abs(c[i]))
    axis_name = axes[axis_idx]
    sign = 1.0 if c[axis_idx] >= 0 else -1.0

    def forward_extent(ext):
        if not ext:
            return None
        return sign * ext["max"][axis_idx] if sign > 0 else -sign * ext["min"][axis_idx]

    root = ET.parse(URDF_PATH).getroot()
    joints = {j.attrib.get("name"): j for j in root.findall("joint")}
    chain = ["arm_right_2_joint", "arm_right_3_joint", "arm_right_4_joint", "arm_right_5_joint", "arm_right_6_joint", "arm_right_tool_joint"]
    urdf_segments = []
    for n in chain:
        j = joints.get(n)
        if j is None:
            continue
        o = j.find("origin")
        xyz = [float(v) for v in o.attrib.get("xyz", "0 0 0").split()]
        urdf_segments.append({"joint": n, "xyz": xyz, "norm_m": math.sqrt(sum(v * v for v in xyz))})

    out = {
        "usd_model": str(USD_PATH),
        "tool_link": tool.GetPath().pathString,
        "left_finger_link": lf.GetPath().pathString,
        "right_finger_link": rf.GetPath().pathString,
        "approach_axis_in_tool_frame": {"axis": axis_name, "sign": "+" if sign > 0 else "-"},
        "forward_extents_m_from_tool_origin": {
            "fingers_only": forward_extent(finger_ext),
            "palm_or_holder_block_only": forward_extent(palm_ext),
            "full_gripper_block_with_fingers": forward_extent(full_ext),
        },
        "raw_tool_frame_extents": {
            "fingers": finger_ext,
            "palm_block": palm_ext,
            "full": full_ext,
        },
        "urdf_chain_segments": urdf_segments,
        "urdf_chain_sum_m": sum(s["norm_m"] for s in urdf_segments),
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
