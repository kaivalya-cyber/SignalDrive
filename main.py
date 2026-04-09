"""
main.py
-------
Entry point. Orchestrates car sim, gesture detection, 2D/3D rendering, and HUD.

Run with: python main.py
Quit with: press 'q' in the OpenCV window, or Ctrl+C in terminal.
"""

import time
import cv2
import numpy as np

from config import (
    TARGET_FPS, CAMERA_WIDTH, CAMERA_HEIGHT,
    FORWARD_VELOCITY, REVERSE_VELOCITY, BRAKE_VELOCITY,
    STEERING_ANGLES, RENDER_MODE
)
from car_sim   import CarSim
from renderer  import TopDownRenderer
from gesture   import (GestureDetector, GESTURE_TURN_30, GESTURE_TURN_60, GESTURE_TURN_90,
                       GESTURE_FORWARD, GESTURE_REVERSE, GESTURE_HOLD, GESTURE_STOP, GESTURE_NONE)
from hud       import HUD


def gesture_to_action(gesture_state) -> dict:
    """
    Convert a GestureState into a car action dict.

    Priority order:
        1. STOP (either hand)     → brake=True, speed=0
        2. HOLD (either hand)     → brake=True, speed=0 (gradual stop)
        3. FORWARD/REVERSE        → set speed, steering from other hand
        4. Turn gestures          → set steering angle, speed=FORWARD_VELOCITY

    Steering:
        Left hand turn gesture  → negative steering (left)
        Right hand turn gesture → positive steering (right)
        If both hands show a turn, right hand takes priority.

    Args:
        gesture_state: GestureState dataclass

    Returns:
        dict with keys: steering_angle (float, degrees), speed (float), brake (bool), command (str)
    """
    lg = gesture_state.left_gesture
    rg = gesture_state.right_gesture

    TURN_MAP = {
        GESTURE_TURN_30: STEERING_ANGLES[0],
        GESTURE_TURN_60: STEERING_ANGLES[1],
        GESTURE_TURN_90: STEERING_ANGLES[2],
    }

    # Priority 1: STOP
    if GESTURE_STOP in (lg, rg):
        return {"steering_angle": 0.0, "speed": BRAKE_VELOCITY, "brake": True, "command": "STOP"}

    # Priority 2: HOLD
    if GESTURE_HOLD in (lg, rg):
        return {"steering_angle": 0.0, "speed": BRAKE_VELOCITY, "brake": True, "command": "HOLD"}

    # Determine steering from turn gestures
    steering = 0.0
    if rg in TURN_MAP:
        steering = TURN_MAP[rg]           # positive = right
    elif lg in TURN_MAP:
        steering = -TURN_MAP[lg]          # negative = left

    # Priority 3: FORWARD
    if GESTURE_FORWARD in (lg, rg):
        return {"steering_angle": steering, "speed": FORWARD_VELOCITY, "brake": False,
                "command": f"FORWARD steer={steering:.0f}\u00b0"}

    # Priority 4: REVERSE
    if GESTURE_REVERSE in (lg, rg):
        return {"steering_angle": -steering, "speed": REVERSE_VELOCITY, "brake": False,
                "command": f"REVERSE steer={-steering:.0f}\u00b0"}

    # Turn only (no throttle gesture) — coast forward slowly
    if steering != 0.0:
        return {"steering_angle": steering, "speed": FORWARD_VELOCITY * 0.5, "brake": False,
                "command": f"COAST steer={steering:.0f}\u00b0"}

    # No recognized gesture — maintain last state (brake softly)
    return {"steering_angle": 0.0, "speed": BRAKE_VELOCITY, "brake": False, "command": "IDLE"}


def main():
    """Main loop. Runs until 'q' is pressed or KeyboardInterrupt."""

    print(f"[main] Render mode: {RENDER_MODE}")
    print("[main] Initializing PyBullet car simulation...")
    sim = CarSim(gui=False)

    # Get obstacle positions for 2D renderer
    obstacle_positions = sim.get_obstacle_positions()
    renderer = TopDownRenderer(obstacle_positions)
    print(f"[main] 2D renderer ready ({len(obstacle_positions)} obstacles)")

    print("[main] Initializing webcam...")
    cap = None
    for cam_idx in range(3):
        print(f"[main] Trying device index {cam_idx}...")
        c = cv2.VideoCapture(cam_idx)
        if c.isOpened():
            ret, _ = c.read()
            if ret:
                cap = c
                print(f"[main] Successfully opened webcam at device {cam_idx}")
                break
        c.release()

    if cap is None:
        raise RuntimeError("Could not open webcam at device index 0, 1, or 2. "
                           "Please ensure camera permissions are fully granted in macOS System Settings.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print("[main] Initializing gesture detector...")
    detector = GestureDetector()

    print("[main] Initializing HUD...")
    hud = HUD()

    fps_counter = 0
    fps_timer   = time.time()
    actual_fps  = 0.0

    print("[main] Running. Press 'q' in the OpenCV window to quit.\n")

    try:
        while True:
            loop_start = time.time()

            # 1. Read webcam frame
            ret, webcam_frame = cap.read()
            if not ret:
                print("[main] Warning: failed to read webcam frame, skipping.")
                continue

            # 2. Detect gestures
            gesture_state = detector.detect(webcam_frame)

            # 3. Resolve action from gesture state
            action = gesture_to_action(gesture_state)

            # 4. Step simulation
            sim._last_command = action["command"]
            sim.step(action)

            # 5. Get telemetry (needed by both renderers and HUD)
            telemetry = sim.get_telemetry()

            # 6. Get base frame — 2D or 3D depending on RENDER_MODE
            if RENDER_MODE == "2D":
                base_frame = renderer.render(telemetry, list(hud.map_trail))
            else:
                base_frame = sim.get_camera_frame()

            # 7. Draw landmarks on webcam frame for PiP
            annotated_webcam = detector.draw_landmarks(webcam_frame, gesture_state)

            # 8. Composite HUD
            final_frame = hud.draw(base_frame, telemetry, gesture_state, annotated_webcam)

            # 9. Display FPS overlay
            cv2.putText(final_frame, f"FPS: {actual_fps:.1f}",
                        (CAMERA_WIDTH - 120, CAMERA_HEIGHT - 45),
                        cv2.FONT_HERSHEY_DUPLEX, 0.45, (0, 255, 0), 1)

            # 10. Show frame
            cv2.imshow("Gesture Car", final_frame)

            # 11. FPS tracking
            fps_counter += 1
            if time.time() - fps_timer >= 1.0:
                actual_fps  = fps_counter / (time.time() - fps_timer)
                fps_counter = 0
                fps_timer   = time.time()
                print(f"[main] FPS: {actual_fps:.1f} | CMD: {action['command']}")

            # 12. Quit on 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("[main] Quit requested.")
                break

    except KeyboardInterrupt:
        print("\n[main] KeyboardInterrupt received.")

    finally:
        print("[main] Shutting down...")
        cap.release()
        cv2.destroyAllWindows()
        detector.close()
        sim.close()
        print("[main] Done.")


if __name__ == "__main__":
    main()
