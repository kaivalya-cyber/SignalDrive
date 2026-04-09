"""
config.py
---------
Single source of truth for all tunable parameters.
No magic numbers anywhere else in the codebase — all constants imported from here.
"""

import cv2

# ── Render Mode ────────────────────────────────────────────────────────────────
RENDER_MODE = "2D"  # Switch to "3D" for PyBullet follow camera

# ── Display ────────────────────────────────────────────────────────────────────
CAMERA_WIDTH  = 1280
CAMERA_HEIGHT = 720
HUD_FONT      = cv2.FONT_HERSHEY_DUPLEX
TARGET_FPS    = 30

# ── Gesture ────────────────────────────────────────────────────────────────────
# Number of consecutive frames a gesture must be held before it is accepted.
# Prevents flickering commands from transient hand poses.
GESTURE_HOLD_FRAMES = 5

# ── Steering ───────────────────────────────────────────────────────────────────
# Discrete steering angles in degrees applied to front wheels.
# PyBullet uses radians internally — conversion happens in car_sim.py.
STEERING_ANGLES = [30, 60, 90]  # degrees

# Maximum steering angle the racecar URDF physically supports.
# The racecar.urdf joint limit is ±0.5 radians (≈28.6°) for steering joints.
MAX_STEERING_RAD = 0.5  # radians — matches racecar.urdf joint limits

# ── Speed ─────────────────────────────────────────────────────────────────────
FORWARD_VELOCITY  = 20.0   # wheel velocity (rad/s) for forward motion
REVERSE_VELOCITY  = -10.0  # wheel velocity (rad/s) for reverse
BRAKE_VELOCITY    =   0.0  # wheel velocity (rad/s) for hold/stop

# ── PID (steering smoothing) ───────────────────────────────────────────────────
PID_KP = 0.8
PID_KI = 0.01
PID_KD = 0.1

# ── HUD ───────────────────────────────────────────────────────────────────────
GRAPH_BUFFER_SIZE = 200    # number of historical data points in rolling graphs
MAP_SIZE          = 220    # minimap pixel dimensions (square)
MAP_SCALE         = 0.05   # world units per minimap pixel (tune based on arena size)
PIP_WIDTH         = 320    # webcam picture-in-picture width
PIP_HEIGHT        = 240    # webcam picture-in-picture height

# ── Colors (BGR for OpenCV) ───────────────────────────────────────────────────
COLOR_CYAN    = (255, 255,   0)   # telemetry values
COLOR_WHITE   = (255, 255, 255)   # labels
COLOR_YELLOW  = (  0, 255, 255)   # gesture display border
COLOR_GREEN   = (  0, 255,   0)   # forward indicator, map dot
COLOR_RED     = (  0,   0, 255)   # reverse indicator
COLOR_OVERLAY = (  0,   0,   0)   # semi-transparent panel background (applied with alpha)
ALPHA_OVERLAY = 0.6               # opacity of dark HUD panels

# ── PyBullet Camera ───────────────────────────────────────────────────────────
CAM_DISTANCE      = 4.0    # meters behind car
CAM_PITCH         = -20.0  # degrees (negative = looking down)
CAM_FOV           = 60.0   # field of view in degrees
CAM_NEAR          = 0.1    # near clipping plane
CAM_FAR           = 100.0  # far clipping plane
