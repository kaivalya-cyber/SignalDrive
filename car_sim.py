"""
car_sim.py
----------
PyBullet 3D racecar simulation.

Exposes:
    CarSim.step(action)          — apply action dict, advance physics
    CarSim.get_telemetry()       — return current state as dict
    CarSim.get_camera_frame()    — return BGR NumPy image from follow camera
    CarSim.reset()               — reset car to spawn position
    CarSim.close()               — disconnect PyBullet
"""

import math
import numpy as np
import pybullet as p
import pybullet_data
import os
import cv2
from config import (
    CAMERA_WIDTH, CAMERA_HEIGHT,
    CAM_DISTANCE, CAM_PITCH, CAM_FOV, CAM_NEAR, CAM_FAR,
    MAX_STEERING_RAD, FORWARD_VELOCITY, REVERSE_VELOCITY, BRAKE_VELOCITY
)


# Joint indices — updated via runtime verification
# Steering: left_steering_hinge_joint (4), right_steering_hinge_joint (6)
# Drive: front_left (5), front_right (7), rear_left (2), rear_right (3)
_STEER_JOINTS = [4, 6]
_DRIVE_JOINTS = [5, 7, 2, 3]  # Arranged so _DRIVE_JOINTS[2:] gets rear wheels


class CarSim:
    """
    Wraps a PyBullet racecar simulation.

    Physics runs at 240 Hz internally (PyBullet default).
    Each call to step() advances the simulation by one physics step
    and applies the given action.
    """

    def __init__(self, gui: bool = True):
        """
        Initialize PyBullet, load ground plane and racecar URDF.

        Args:
            gui: If True, open PyBullet's OpenGL window. Set False for headless.
                 In this project we use gui=True for the PyBullet debug window,
                 but rendering is done via get_camera_frame() not the GUI window.
        """
        # Connect to PyBullet
        self.client = p.connect(p.GUI if gui else p.DIRECT)

        # Set data path so PyBullet can find built-in URDFs
        p.setAdditionalSearchPath(pybullet_data.getDataPath())

        # Gravity — standard Earth gravity on Z axis
        p.setGravity(0, 0, -9.81)

        # Load ground plane
        self.plane_id = p.loadURDF("plane.urdf")

        # Load racecar at origin, slightly above ground to prevent z-fighting
        spawn_pos    = [0, 0, 0.1]
        spawn_orient = p.getQuaternionFromEuler([0, 0, 0])
        self.car_id  = p.loadURDF("racecar/racecar.urdf", spawn_pos, spawn_orient)

        # Load static obstacle boxes for visual interest
        self._spawn_obstacles()

        # Verify joint indices at runtime — prints to stdout, does not crash
        self._verify_joints()

        # Internal state for telemetry history
        self._prev_pos      = np.array([0.0, 0.0, 0.1])
        self._prev_time     = 0.0
        self._speed_history = []

    def _spawn_obstacles(self):
        """
        Spawn 6 static box obstacles at fixed positions around the arena.
        Uses PyBullet's createCollisionShape + createMultiBody (no URDF needed).
        Boxes are 1m × 1m × 0.5m, placed at least 3m from origin.
        """
        obstacle_positions = [
            [5, 0, 0.25], [-5, 0, 0.25],
            [0, 5, 0.25], [0, -5, 0.25],
            [4, 4, 0.25], [-4, -4, 0.25],
        ]
        box_half_extents = [0.5, 0.5, 0.25]

        col_shape = p.createCollisionShape(
            p.GEOM_BOX,
            halfExtents=box_half_extents
        )
        vis_shape = p.createVisualShape(
            p.GEOM_BOX,
            halfExtents=box_half_extents,
            rgbaColor=[0.8, 0.2, 0.2, 1.0]  # red boxes
        )

        self.obstacle_ids = []
        for pos in obstacle_positions:
            body_id = p.createMultiBody(
                baseMass=0,  # 0 mass = static (immovable)
                baseCollisionShapeIndex=col_shape,
                baseVisualShapeIndex=vis_shape,
                basePosition=pos
            )
            self.obstacle_ids.append(body_id)

    def _verify_joints(self):
        """
        Print all joint names and indices to stdout.
        Called once at init so the operator can verify joint mapping.
        Does not raise — verification is informational only.
        """
        print("\n[CarSim] Joint verification:")
        for i in range(p.getNumJoints(self.car_id)):
            info = p.getJointInfo(self.car_id, i)
            joint_name = info[1].decode("utf-8")
            joint_type = info[2]
            lower_lim  = info[8]
            upper_lim  = info[9]
            print(f"  Joint {i}: {joint_name} | type={joint_type} | limits=[{lower_lim:.3f}, {upper_lim:.3f}]")
        print()

    def step(self, action: dict):
        """
        Apply action to the car and advance physics by one step.

        Args:
            action: dict with keys:
                - steering_angle (float): target steering angle in DEGREES.
                                          Positive = right, Negative = left.
                                          Will be clamped to ±MAX_STEERING_RAD after conversion.
                - speed (float): wheel velocity in rad/s.
                                 Use FORWARD_VELOCITY, REVERSE_VELOCITY, or BRAKE_VELOCITY from config.
                - brake (bool): if True, override speed with 0 and apply max damping.
        """
        steering_deg = action.get("steering_angle", 0.0)
        speed        = action.get("speed", 0.0)
        brake        = action.get("brake", False)

        if brake:
            speed = BRAKE_VELOCITY

        # Convert steering from degrees to radians and clamp to joint limits
        steering_rad = math.radians(steering_deg)
        steering_rad = max(-MAX_STEERING_RAD, min(MAX_STEERING_RAD, steering_rad))

        # Apply steering to front joints using POSITION_CONTROL
        for joint in _STEER_JOINTS:
            p.setJointMotorControl2(
                bodyUniqueId=self.car_id,
                jointIndex=joint,
                controlMode=p.POSITION_CONTROL,
                targetPosition=steering_rad,
                force=10.0  # N·m — sufficient for racecar steering joints
            )

        # Apply velocity to all drive joints using VELOCITY_CONTROL
        for joint in _DRIVE_JOINTS:
            p.setJointMotorControl2(
                bodyUniqueId=self.car_id,
                jointIndex=joint,
                controlMode=p.VELOCITY_CONTROL,
                targetVelocity=speed,
                force=20.0 if not brake else 100.0  # higher force when braking
            )

        # Advance simulation by one step
        p.stepSimulation()

    def get_telemetry(self) -> dict:
        """
        Return current car state as a dict.

        Returns:
            dict with keys:
                position    (list[float]): [x, y, z] world position in meters
                heading     (float):       yaw in degrees (0=+X axis, CCW positive)
                speed       (float):       estimated speed in m/s (finite diff of position)
                steering    (float):       current front steering joint angle in degrees
                wheel_rpm   (float):       average rear wheel RPM
                command     (str):         last applied command string (set externally by main.py)
        """
        # Position and orientation
        pos, orient = p.getBasePositionAndOrientation(self.car_id)
        euler        = p.getEulerFromQuaternion(orient)
        heading_deg  = math.degrees(euler[2])  # yaw

        # Estimated speed from position delta
        pos_array = np.array(pos)
        delta_pos  = np.linalg.norm(pos_array - self._prev_pos)
        # Note: speed estimation is in units/step, not units/second
        # For display purposes this is acceptable; multiply by TARGET_FPS for m/s estimate
        self._prev_pos = pos_array

        # Steering angle from joint state
        # getJointState returns (position, velocity, reactionForces, appliedMotorTorque)
        steer_state  = p.getJointState(self.car_id, _STEER_JOINTS[0])
        steering_deg = math.degrees(steer_state[0])

        # Wheel RPM from drive joint velocities (average of rear wheels)
        rear_velocities = [p.getJointState(self.car_id, j)[1] for j in _DRIVE_JOINTS[2:]]
        avg_rad_per_sec = sum(rear_velocities) / len(rear_velocities)
        wheel_rpm       = (avg_rad_per_sec * 60.0) / (2 * math.pi)

        return {
            "position":   list(pos),
            "heading":    heading_deg,
            "speed":      delta_pos,
            "steering":   steering_deg,
            "wheel_rpm":  wheel_rpm,
            "command":    getattr(self, "_last_command", "NONE"),
        }

    def get_camera_frame(self) -> np.ndarray:
        """
        Render a third-person follow camera frame from PyBullet.

        The camera follows the car from behind and above, always pointing at the car.
        Uses PyBullet's getCameraImage with ER_TINY_RENDERER for speed.

        Returns:
            np.ndarray: BGR image of shape (CAMERA_HEIGHT, CAMERA_WIDTH, 3), dtype=uint8
        """
        # Get car position and yaw for camera positioning
        pos, orient = p.getBasePositionAndOrientation(self.car_id)
        euler        = p.getEulerFromQuaternion(orient)
        yaw          = euler[2]  # radians

        # Compute camera position: behind and above the car
        cam_x = pos[0] - CAM_DISTANCE * math.cos(yaw)
        cam_y = pos[1] - CAM_DISTANCE * math.sin(yaw)
        cam_z = pos[2] + CAM_DISTANCE * math.tan(math.radians(-CAM_PITCH))

        cam_eye    = [cam_x, cam_y, cam_z]
        cam_target = list(pos)
        cam_up     = [0, 0, 1]

        view_matrix = p.computeViewMatrix(
            cameraEyePosition=cam_eye,
            cameraTargetPosition=cam_target,
            cameraUpVector=cam_up
        )

        proj_matrix = p.computeProjectionMatrixFOV(
            fov=CAM_FOV,
            aspect=CAMERA_WIDTH / CAMERA_HEIGHT,
            nearVal=CAM_NEAR,
            farVal=CAM_FAR
        )

        # Render — returns (width, height, rgbPixels, depthPixels, segmentationMaskBuffer)
        _, _, rgb_pixels, _, _ = p.getCameraImage(
            width=640,
            height=480,
            viewMatrix=view_matrix,
            projectionMatrix=proj_matrix,
            renderer=p.ER_TINY_RENDERER  # faster than OpenGL renderer for this use case
        )

        # rgb_pixels is a flat list of RGBA values — reshape and convert to BGR
        rgba_image = np.array(rgb_pixels, dtype=np.uint8).reshape(480, 640, 4)
        bgr_image  = cv2.cvtColor(rgba_image, cv2.COLOR_RGBA2BGR)
        bgr_image  = cv2.resize(bgr_image, (CAMERA_WIDTH, CAMERA_HEIGHT))  # upscale after

        return bgr_image

    def reset(self):
        """Reset car to spawn position and zero velocity."""
        spawn_pos    = [0, 0, 0.1]
        spawn_orient = p.getQuaternionFromEuler([0, 0, 0])
        p.resetBasePositionAndOrientation(self.car_id, spawn_pos, spawn_orient)
        p.resetBaseVelocity(self.car_id, [0, 0, 0], [0, 0, 0])

    def get_obstacle_positions(self) -> list:
        """Return list of (x, y) world positions of all obstacles."""
        positions = []
        for obs_id in self.obstacle_ids:
            pos, _ = p.getBasePositionAndOrientation(obs_id)
            positions.append((pos[0], pos[1]))
        return positions

    def close(self):
        """Disconnect from PyBullet. Must be called on shutdown."""
        p.disconnect(self.client)
