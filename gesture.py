"""
gesture.py
----------
MediaPipe two-hand gesture detection and classification.

Exposes:
    GestureDetector.detect(frame)  — returns GestureState dataclass
    GestureState                   — dataclass with left/right gesture + landmarks

Gesture vocabulary:
    TURN_30  — index finger only extended
    TURN_60  — index + middle extended (peace sign)
    TURN_90  — index + middle + ring extended (three fingers)
    FORWARD  — thumb up (thumb extended, all fingers curled)
    REVERSE  — thumb down (inverted thumbs up — detected via wrist orientation)
    HOLD     — open palm (all five extended)
    STOP     — fist (all curled)
    NONE     — no hand detected or unrecognized pose
"""

from dataclasses import dataclass, field
from typing import Optional, List
from collections import deque
import mediapipe as mp
import numpy as np
import cv2
from config import GESTURE_HOLD_FRAMES


# ── Landmark index constants ──────────────────────────────────────────────────
WRIST       = 0
THUMB_CMC   = 1; THUMB_MCP = 2; THUMB_IP  = 3; THUMB_TIP  = 4
INDEX_MCP   = 5; INDEX_PIP = 6; INDEX_DIP = 7; INDEX_TIP  = 8
MIDDLE_MCP  = 9; MIDDLE_PIP= 10;MIDDLE_DIP= 11;MIDDLE_TIP = 12
RING_MCP    = 13;RING_PIP  = 14;RING_DIP  = 15;RING_TIP   = 16
PINKY_MCP   = 17;PINKY_PIP = 18;PINKY_DIP = 19;PINKY_TIP  = 20

# Valid gesture string constants
GESTURE_TURN_30 = "TURN_30"
GESTURE_TURN_60 = "TURN_60"
GESTURE_TURN_90 = "TURN_90"
GESTURE_FORWARD = "FORWARD"
GESTURE_REVERSE = "REVERSE"
GESTURE_HOLD    = "HOLD"
GESTURE_STOP    = "STOP"
GESTURE_NONE    = "NONE"


@dataclass
class GestureState:
    """
    Result of a single frame of gesture detection.

    Attributes:
        left_gesture:   Gesture string for the left hand, or GESTURE_NONE
        right_gesture:  Gesture string for the right hand, or GESTURE_NONE
        left_landmarks: MediaPipe NormalizedLandmarkList for left hand, or None
        right_landmarks:MediaPipe NormalizedLandmarkList for right hand, or None
    """
    left_gesture:    str   = GESTURE_NONE
    right_gesture:   str   = GESTURE_NONE
    left_landmarks:  object = None
    right_landmarks: object = None


class GestureDetector:
    """
    Wraps MediaPipe Hands for two-hand gesture detection.

    Applies temporal smoothing: a gesture must persist for GESTURE_HOLD_FRAMES
    consecutive frames before it is emitted. This prevents flicker from
    transient landmark noise.
    """

    def __init__(self):
        self.mp_hands   = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils

        # max_num_hands=2 to track both hands simultaneously
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,   # video mode — faster, uses tracking
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5
        )

        # Temporal smoothing buffers — one deque per hand
        # Each deque holds the last GESTURE_HOLD_FRAMES raw gesture strings
        self._left_buffer  = deque(maxlen=GESTURE_HOLD_FRAMES)
        self._right_buffer = deque(maxlen=GESTURE_HOLD_FRAMES)

        # Last confirmed (smoothed) gesture per hand
        self._left_confirmed  = GESTURE_NONE
        self._right_confirmed = GESTURE_NONE

        self._frame_count = 0
        self._last_state  = GestureState()

    def detect(self, bgr_frame: np.ndarray) -> GestureState:
        """
        Run MediaPipe on a single BGR frame and return GestureState.

        Args:
            bgr_frame: OpenCV BGR image from webcam, any resolution.

        Returns:
            GestureState with smoothed gesture strings and raw landmarks.
        """
        self._frame_count += 1
        if self._frame_count % 3 != 0:
            return self._last_state

        # MediaPipe requires RGB
        rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False  # performance optimization
        results = self.hands.process(rgb_frame)
        rgb_frame.flags.writeable = True

        state = GestureState()

        if not results.multi_hand_landmarks:
            # No hands detected — push NONE to both buffers
            self._left_buffer.append(GESTURE_NONE)
            self._right_buffer.append(GESTURE_NONE)
            state.left_gesture  = self._smooth(self._left_buffer,  self._left_confirmed)
            state.right_gesture = self._smooth(self._right_buffer, self._right_confirmed)
            self._left_confirmed  = state.left_gesture
            self._right_confirmed = state.right_gesture
            self._last_state = state
            return state

        # Process each detected hand
        for i, hand_landmarks in enumerate(results.multi_hand_landmarks):
            label = results.multi_handedness[i].classification[0].label  # "Left" or "Right"
            gesture = self._classify(hand_landmarks, label)

            if label == "Left":
                self._left_buffer.append(gesture)
                state.left_landmarks = hand_landmarks
            else:
                self._right_buffer.append(gesture)
                state.right_landmarks = hand_landmarks

        # Hands not seen this frame get NONE pushed
        labels_seen = {
            results.multi_handedness[i].classification[0].label
            for i in range(len(results.multi_hand_landmarks))
        }
        if "Left"  not in labels_seen: self._left_buffer.append(GESTURE_NONE)
        if "Right" not in labels_seen: self._right_buffer.append(GESTURE_NONE)

        # Apply temporal smoothing
        state.left_gesture  = self._smooth(self._left_buffer,  self._left_confirmed)
        state.right_gesture = self._smooth(self._right_buffer, self._right_confirmed)
        self._left_confirmed  = state.left_gesture
        self._right_confirmed = state.right_gesture

        self._last_state = state
        return state

    def _smooth(self, buffer: deque, current: str) -> str:
        """
        Return the gesture only if it has been consistent for GESTURE_HOLD_FRAMES frames.
        Otherwise return the current confirmed gesture (hold last known good).

        Args:
            buffer:  deque of recent raw gesture strings
            current: currently confirmed gesture string

        Returns:
            New confirmed gesture string
        """
        if len(buffer) < GESTURE_HOLD_FRAMES:
            return current
        # All entries in the buffer must be the same gesture
        if len(set(buffer)) == 1:
            return buffer[-1]
        return current

    def _classify(self, landmarks, handedness: str) -> str:
        """
        Classify a single hand's gesture from its 21 landmarks.

        Uses geometric rules on normalized landmark coordinates:
        - Finger extension: tip.y < pip.y in normalized image coords
        - Thumb extension: tip.x comparison adjusted for handedness
        - Thumb direction (up/down): tip.y vs wrist.y

        Args:
            landmarks:   MediaPipe NormalizedLandmarkList (21 points)
            handedness:  "Left" or "Right" — MediaPipe's chirality label

        Returns:
            One of the GESTURE_* string constants
        """
        lm = landmarks.landmark  # list of NormalizedLandmark objects with .x, .y, .z

        # ── Finger extension detection ─────────────────────────────────────────
        # Index: tip.y < pip.y → extended (y=0 is top of image)
        index_extended  = lm[INDEX_TIP].y  < lm[INDEX_PIP].y
        middle_extended = lm[MIDDLE_TIP].y < lm[MIDDLE_PIP].y
        ring_extended   = lm[RING_TIP].y   < lm[RING_PIP].y
        pinky_extended  = lm[PINKY_TIP].y  < lm[PINKY_PIP].y

        # Thumb extension: x-axis comparison, direction depends on handedness
        # For "Right" hand (camera-left): thumb tip to the right of IP = extended
        # For "Left"  hand (camera-right): thumb tip to the left of IP = extended
        if handedness == "Right":
            thumb_extended = lm[THUMB_TIP].x > lm[THUMB_IP].x
            thumb_up       = lm[THUMB_TIP].y < lm[WRIST].y   # tip above wrist
        else:
            thumb_extended = lm[THUMB_TIP].x < lm[THUMB_IP].x
            thumb_up       = lm[THUMB_TIP].y < lm[WRIST].y

        fingers_extended = [index_extended, middle_extended, ring_extended, pinky_extended]
        num_extended     = sum(fingers_extended)

        # ── Classification rules (evaluated in priority order) ─────────────────

        # STOP: fist — nothing extended
        if not any(fingers_extended) and not thumb_extended:
            return GESTURE_STOP

        # HOLD: open palm — all five extended
        if all(fingers_extended) and thumb_extended:
            return GESTURE_HOLD

        # FORWARD: thumbs up — thumb extended and up, no fingers extended
        if thumb_extended and thumb_up and not any(fingers_extended):
            return GESTURE_FORWARD

        # REVERSE: thumbs down — thumb extended and down, no fingers extended
        if thumb_extended and not thumb_up and not any(fingers_extended):
            return GESTURE_REVERSE

        # TURN_30: index only
        if index_extended and not middle_extended and not ring_extended and not pinky_extended:
            return GESTURE_TURN_30

        # TURN_60: index + middle (peace sign)
        if index_extended and middle_extended and not ring_extended and not pinky_extended:
            return GESTURE_TURN_60

        # TURN_90: index + middle + ring
        if index_extended and middle_extended and ring_extended and not pinky_extended:
            return GESTURE_TURN_90

        return GESTURE_NONE

    def draw_landmarks(self, frame: np.ndarray, state: GestureState) -> np.ndarray:
        """
        Draw MediaPipe hand skeleton overlays onto a frame copy.

        Args:
            frame: BGR image to draw on (modified in place on a copy)
            state: GestureState with landmark objects

        Returns:
            BGR image with landmarks drawn
        """
        annotated = frame.copy()
        draw_spec_point = self.mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=3)
        draw_spec_line  = self.mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=2)

        for lm in [state.left_landmarks, state.right_landmarks]:
            if lm is not None:
                self.mp_drawing.draw_landmarks(
                    annotated,
                    lm,
                    self.mp_hands.HAND_CONNECTIONS,
                    draw_spec_point,
                    draw_spec_line
                )
        return annotated

    def close(self):
        """Release MediaPipe resources."""
        self.hands.close()
