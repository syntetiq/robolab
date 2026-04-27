# Kitchen Raw Mesh Package

This folder currently stores source meshes for a kitchen environment:

- `uploads_files_6048305_Kitchen+Modern.obj`
- `uploads_files_6048305_Kitchen+Modern.dae`
- `uploads_files_6048305_Kitchen+Modern.mtl`

These files are **not task-ready** for RoboLab pipelines yet. The current
pipelines expect a USD/USDA stage with physics support and deterministic robot
spawn settings.

## Conversion path (safe, additive)

1. Convert OBJ/DAE to USD in Isaac Sim importer (or DCC pipeline).
2. Generate a Tiago-compatible wrapper using:

```powershell
python scripts/build_kitchen_scene_wrapper.py --source-usd "C:\RoboLab_Data\scenes\Kitchen_Modern.usd"
```

3. Register the wrapper path in web scenes and run scene-specific smoke gates.
4. Keep existing `kitchen_fixed` scene untouched as regression baseline.
