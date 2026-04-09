"""
renderer.py
-----------
Pure OpenCV 2D top-down renderer for the gesture car.
PyBullet still runs physics headlessly. This renderer reads telemetry
and draws everything with OpenCV onto a NumPy array.

Exposes:
    TopDownRenderer.render(telemetry, trail)  — returns 1280×720 BGR NumPy image
"""

import math
import numpy as np
import cv2
from config import CAMERA_WIDTH, CAMERA_HEIGHT


# ── Constants ─────────────────────────────────────────────────────────────────
_SCALE    = 40        # pixels per world meter
_CX       = CAMERA_WIDTH  // 2   # screen center X (640)
_CY       = CAMERA_HEIGHT // 2   # screen center Y (360)
_GRID_GAP = 80        # pixels between grid lines
_BG_COLOR = (15, 15, 20)
_GRID_CLR = (35, 35, 50)
_OBS_FILL = (30, 30, 200)
_OBS_BORD = (60, 80, 255)
_CAR_BODY = (200, 200, 210)
_CAR_ACCENT = (0, 200, 255)
_SPEED_LINE = (80, 80, 90)


def world_to_screen(wx: float, wy: float, car_x: float, car_y: float,
                    scale: int = _SCALE) -> tuple:
    """Convert world coordinates to screen coordinates centred on the car."""
    sx = int(_CX + (wx - car_x) * scale)
    sy = int(_CY - (wy - car_y) * scale)          # invert Y
    return sx, sy


class TopDownRenderer:
    """Full 2D top-down scene renderer using only OpenCV primitives."""

    def __init__(self, obstacle_positions: list):
        """
        Args:
            obstacle_positions: list of (x, y) world coordinates of obstacles.
        """
        self.obstacle_positions = obstacle_positions

        # Pre-build vignette mask once (dark circle at edges)
        self._vignette = np.zeros((CAMERA_HEIGHT, CAMERA_WIDTH, 3), dtype=np.uint8)
        cv2.circle(self._vignette, (_CX, _CY), 800, (255, 255, 255), -1)
        # Invert: bright at center, dark at edges → used as subtractive overlay
        self._vignette = cv2.GaussianBlur(self._vignette, (201, 201), 0)
        self._vignette_inv = 255 - self._vignette

    # ── public API ────────────────────────────────────────────────────────────

    def render(self, telemetry: dict, trail: list) -> np.ndarray:
        """Draw full 2D scene. Returns 1280×720 BGR NumPy array."""
        car_x = telemetry["position"][0]
        car_y = telemetry["position"][1]
        heading = telemetry["heading"]         # degrees
        speed   = telemetry["speed"]

        frame = np.full((CAMERA_HEIGHT, CAMERA_WIDTH, 3), _BG_COLOR, dtype=np.uint8)

        self._draw_grid(frame, car_x, car_y)
        self._draw_trail(frame, trail, car_x, car_y)
        self._draw_obstacles(frame, car_x, car_y)
        self._draw_speed_lines(frame, heading, speed)
        self._draw_car(frame, heading)
        self._apply_vignette(frame)

        return frame

    # ── internals ─────────────────────────────────────────────────────────────

    def _draw_grid(self, frame, car_x, car_y):
        """Scrolling grid that moves with the car."""
        offset_x = int((car_x * _SCALE) % _GRID_GAP)
        offset_y = int((car_y * _SCALE) % _GRID_GAP)
        for x in range(-_GRID_GAP, CAMERA_WIDTH + _GRID_GAP, _GRID_GAP):
            cv2.line(frame, (x - offset_x, 0), (x - offset_x, CAMERA_HEIGHT), _GRID_CLR, 1)
        for y in range(-_GRID_GAP, CAMERA_HEIGHT + _GRID_GAP, _GRID_GAP):
            cv2.line(frame, (0, y + offset_y), (CAMERA_WIDTH, y + offset_y), _GRID_CLR, 1)

    def _draw_trail(self, frame, trail, car_x, car_y):
        """Fading polyline of the car's position history."""
        if len(trail) < 2:
            return
        n = len(trail)
        for i in range(1, n):
            t = i / max(n - 1, 1)
            r = int(0 + t * 0)
            g = int(80 + t * (255 - 80))
            b = int(60 + t * (200 - 60))
            color = (r, g, b)
            sx1, sy1 = world_to_screen(trail[i-1][0], trail[i-1][1], car_x, car_y)
            sx2, sy2 = world_to_screen(trail[i][0], trail[i][1], car_x, car_y)
            cv2.line(frame, (sx1, sy1), (sx2, sy2), color, 2)

    def _draw_obstacles(self, frame, car_x, car_y):
        """Red filled rectangles for each obstacle."""
        half = 40  # 80px / 2
        for (ox, oy) in self.obstacle_positions:
            sx, sy = world_to_screen(ox, oy, car_x, car_y)
            x1, y1 = sx - half, sy - half
            x2, y2 = sx + half, sy + half
            if x2 < 0 or x1 > CAMERA_WIDTH or y2 < 0 or y1 > CAMERA_HEIGHT:
                continue
            cv2.rectangle(frame, (x1, y1), (x2, y2), _OBS_FILL, -1)
            cv2.rectangle(frame, (x1, y1), (x2, y2), _OBS_BORD, 2)

    def _draw_car(self, frame, heading_deg):
        """
        Draw rotated car body at screen centre with cyan accent and direction arrow.
        Uses warpAffine on a temporary canvas, composited via mask.
        """
        car_w, car_h = 36, 18  # length × width in pixels
        accent_h = 6
        tmp_size = 80
        tmp = np.zeros((tmp_size, tmp_size, 3), dtype=np.uint8)
        cx, cy = tmp_size // 2, tmp_size // 2

        # Body rectangle centred on tmp
        x1 = cx - car_w // 2
        y1 = cy - car_h // 2
        x2 = cx + car_w // 2
        y2 = cy + car_h // 2
        cv2.rectangle(tmp, (x1, y1), (x2, y2), _CAR_BODY, -1)

        # Front accent bar (right side = front in 0° heading)
        cv2.rectangle(tmp, (x2 - accent_h, y1), (x2, y2), _CAR_ACCENT, -1)

        # Direction arrow extending from front
        arrow_start = (x2, cy)
        arrow_end   = (x2 + 20, cy)
        cv2.arrowedLine(tmp, arrow_start, arrow_end, (255, 255, 255), 2, tipLength=0.5)

        # Rotate by heading (PyBullet heading: 0=+X, CCW positive)
        # Screen rotation: negative because screen Y is inverted
        M = cv2.getRotationMatrix2D((cx, cy), heading_deg, 1.0)
        rotated = cv2.warpAffine(tmp, M, (tmp_size, tmp_size))

        # Create mask from rotated car
        mask = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)

        # Composite onto main frame at screen centre
        dst_x = _CX - cx
        dst_y = _CY - cy
        # Clamp to frame bounds
        src_x1 = max(0, -dst_x)
        src_y1 = max(0, -dst_y)
        src_x2 = min(tmp_size, CAMERA_WIDTH - dst_x)
        src_y2 = min(tmp_size, CAMERA_HEIGHT - dst_y)
        fx1 = max(0, dst_x)
        fy1 = max(0, dst_y)
        fx2 = fx1 + (src_x2 - src_x1)
        fy2 = fy1 + (src_y2 - src_y1)

        roi = frame[fy1:fy2, fx1:fx2]
        car_crop = rotated[src_y1:src_y2, src_x1:src_x2]
        mask_crop = mask[src_y1:src_y2, src_x1:src_x2]
        inv_mask = cv2.bitwise_not(mask_crop)
        bg = cv2.bitwise_and(roi, roi, mask=inv_mask)
        fg = cv2.bitwise_and(car_crop, car_crop, mask=mask_crop)
        frame[fy1:fy2, fx1:fx2] = cv2.add(bg, fg)

    def _draw_speed_lines(self, frame, heading_deg, speed):
        """Radiating lines behind the car when moving."""
        if speed <= 0.002:
            return
        heading_rad = math.radians(heading_deg)
        num_lines = 8
        spread = math.radians(40)
        for i in range(num_lines):
            frac = (i / (num_lines - 1)) - 0.5          # -0.5 → +0.5
            angle = heading_rad + math.pi + frac * 2 * spread  # behind car
            line_len = int(15 + min(speed * 800, 20))    # 15-35px
            ex = int(_CX + math.cos(angle) * line_len)
            ey = int(_CY - math.sin(angle) * line_len)
            sx = int(_CX + math.cos(angle) * 22)        # start a bit away from centre
            sy = int(_CY - math.sin(angle) * 22)
            cv2.line(frame, (sx, sy), (ex, ey), _SPEED_LINE, 1)

    def _apply_vignette(self, frame):
        """Darken edges with pre-computed vignette."""
        cv2.subtract(frame, (self._vignette_inv * 0.25).astype(np.uint8), frame)
