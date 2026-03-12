## TIAGo PAL Lula Migration

This repo currently falls back to `config/tiago_right_arm_descriptor.yaml` and
`config/tiago_right_arm.urdf` for Lula initialization.

To switch to a PAL-derived canonical source without further code changes, place
the following files in `config/` or point the environment variables to them:

- `tiago_pal_right_arm_descriptor.yaml`
- `tiago_pal_right_arm.urdf`

Optional environment variables:

- `TIAGO_PAL_DESCRIPTOR_PATH`
- `TIAGO_PAL_URDF_PATH`

Current lookup order in `scripts/data_collector_tiago.py`:

1. `TIAGO_PAL_DESCRIPTOR_PATH` / `TIAGO_PAL_URDF_PATH`
2. `config/tiago_pal_right_arm_descriptor.yaml` / `config/tiago_pal_right_arm.urdf`
3. existing repo defaults:
   - `config/tiago_right_arm_descriptor.yaml`
   - `config/tiago_right_arm.urdf`

Expected PAL-derived content:

- active joints: `torso_lift_joint`, `arm_right_1_joint` .. `arm_right_7_joint`
- end-effector frame aligned with the right tool/finger grasp frame
- limits and naming kept consistent with Isaac Sim articulation DOF names
