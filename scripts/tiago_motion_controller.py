"""TIAGo motion controller wrapper.

Provides a unified interface for controlling TIAGo's right arm using either:
1. RMPFlow (when Lula robot descriptor + URDF are available)
2. Direct trajectory interpolation (fallback)

Usage in data_collector_tiago.py:
    from tiago_motion_controller import TiagoMotionController
    controller = TiagoMotionController(robot_articulation, config_dir)
    actions = controller.compute_approach(target_position, target_orientation)
    robot_articulation.apply_action(actions)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np

_RMPFLOW_AVAILABLE = False
_LULA_AVAILABLE = False

try:
    from isaacsim.robot_motion.motion_generation import (
        ArticulationMotionPolicy,
        LulaKinematicsSolver,
        ArticulationKinematicsSolver,
    )
    from isaacsim.robot_motion.motion_generation.lula.motion_policies import RmpFlow
    _RMPFLOW_AVAILABLE = True
    _LULA_AVAILABLE = True
except ImportError:
    pass


class TiagoMotionController:
    """Unified motion controller for TIAGo right arm."""

    def __init__(
        self,
        robot_articulation,
        config_dir: str | Path = "config",
        physics_dt: float = 1.0 / 120.0,
        end_effector_frame: str = "arm_right_tool_link",
    ):
        self._articulation = robot_articulation
        self._config_dir = Path(config_dir)
        self._physics_dt = physics_dt
        self._ee_frame = end_effector_frame

        self._rmpflow = None
        self._ik_solver = None
        self._art_ik = None
        self._art_motion = None
        self._mode = "direct"

        self._try_init_lula()

    def _try_init_lula(self):
        """Attempt to initialize Lula IK and RMPFlow from config files."""
        if not _LULA_AVAILABLE:
            print("[TiagoMotion] Lula not available, using direct mode")
            return

        desc_path = self._config_dir / "tiago_right_arm_descriptor.yaml"
        rmpflow_path = self._config_dir / "tiago_rmpflow_config.yaml"
        urdf_path = self._config_dir / "tiago_right_arm.urdf"

        if not desc_path.exists():
            print(f"[TiagoMotion] Robot descriptor not found: {desc_path}")
            print("[TiagoMotion] Generate it using Isaac Sim Robot Description Editor")
            return

        if not urdf_path.exists():
            print(f"[TiagoMotion] URDF not found: {urdf_path}")
            print("[TiagoMotion] Export URDF from TIAGo USD using Isaac Sim")
            return

        try:
            self._ik_solver = LulaKinematicsSolver(
                robot_description_path=str(desc_path),
                urdf_path=str(urdf_path),
            )
            self._art_ik = ArticulationKinematicsSolver(
                self._articulation, self._ik_solver, self._ee_frame,
            )
            self._mode = "lula_ik"
            print("[TiagoMotion] Lula IK solver initialized")
        except Exception as e:
            print(f"[TiagoMotion] Failed to init Lula IK: {e}")

        if _RMPFLOW_AVAILABLE and rmpflow_path.exists() and urdf_path.exists():
            try:
                self._rmpflow = RmpFlow(
                    robot_description_path=str(desc_path),
                    rmpflow_config_path=str(rmpflow_path),
                    urdf_path=str(urdf_path),
                    end_effector_frame_name=self._ee_frame,
                    maximum_substep_size=0.00334,
                )
                self._art_motion = ArticulationMotionPolicy(
                    self._articulation, self._rmpflow, self._physics_dt,
                )
                base_pos, base_orient = self._articulation.get_world_pose()
                self._rmpflow.set_robot_base_pose(
                    robot_position=base_pos, robot_orientation=base_orient,
                )
                self._mode = "rmpflow"
                print("[TiagoMotion] RMPFlow controller initialized")
            except Exception as e:
                print(f"[TiagoMotion] Failed to init RMPFlow: {e}")

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def has_rmpflow(self) -> bool:
        return self._rmpflow is not None

    @property
    def has_lula_ik(self) -> bool:
        return self._ik_solver is not None

    def compute_ik(
        self,
        target_position: np.ndarray,
        target_orientation: Optional[np.ndarray] = None,
    ):
        """Compute IK using Lula solver. Returns ArticulationAction or None."""
        if not self._art_ik:
            return None
        try:
            actions, success = self._art_ik.compute_inverse_kinematics(
                target_position=target_position,
                target_orientation=target_orientation,
            )
            if success:
                return actions
        except Exception as e:
            print(f"[TiagoMotion] Lula IK failed: {e}")
        return None

    def compute_approach(
        self,
        target_position: np.ndarray,
        target_orientation: Optional[np.ndarray] = None,
    ):
        """Compute approach motion using RMPFlow. Returns ArticulationAction or None."""
        if not self._art_motion or not self._rmpflow:
            return None
        try:
            from isaacsim.robot_motion.motion_generation import MotionPolicyController
            actions = MotionPolicyController.forward(
                self._art_motion,
                target_end_effector_position=target_position,
                target_end_effector_orientation=target_orientation,
            )
            return actions
        except Exception as e:
            print(f"[TiagoMotion] RMPFlow approach failed: {e}")
        return None

    def reset(self):
        """Reset controller state."""
        if self._rmpflow:
            try:
                base_pos, base_orient = self._articulation.get_world_pose()
                self._rmpflow.set_robot_base_pose(
                    robot_position=base_pos, robot_orientation=base_orient,
                )
            except Exception:
                pass
