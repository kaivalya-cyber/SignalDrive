"""
hud.py
------
F1 pit-wall telemetry HUD compositing over any base frame (2D or 3D).

Design language: F1 telemetry meets military drone HUD.
All drawing uses OpenCV primitives only — no PIL, no matplotlib.

Panels:
    - Top-left:      Telemetry panel (300×230px) with speed bar + blinking dot
    - Top-right:     Gesture panel (340×130px) with gesture icons
    - Right side:    Minimap (220×220px) with compass rose + heading triangle
    - Bottom strip:  Three graphs with filled area, axis ticks, current value
    - Bottom-left:   Webcam PiP (320×240px) labelled OPERATOR, blinking REC
    - Bottom bar:    Full-width status bar with CMD, steering indicator, speed arc
"""

import math
from collections import deque
import numpy as np
import cv2
from config import (
    CAMERA_WIDTH, CAMERA_HEIGHT, HUD_FONT,
    GRAPH_BUFFER_SIZE, MAP_SIZE, MAP_SCALE,
    PIP_WIDTH, PIP_HEIGHT
)

# ── F1 colour palette (all BGR) ──────────────────────────────────────────────
_PANEL_BG    = (8, 8, 12)
_PANEL_ALPHA = 0.75
_TEAL        = (110, 160, 0)       # panel borders + accents
_LABEL       = (100, 90, 90)       # dim grey labels
_VALUE       = (180, 255, 0)       # mint green values
_CYAN        = (255, 220, 0)       # electric cyan — active gesture
_RED_ORANGE  = (255, 60, 0)        # reverse / warning
_BLINK_ON    = (100, 255, 0)       # blinking dot ON
_BLINK_OFF   = (30, 60, 30)        # blinking dot OFF
_SEPARATOR   = (40, 30, 30)
_BAR_EMPTY   = (40, 30, 30)
_REC_RED     = (0, 0, 255)
_DIM         = (60, 50, 50)
_ARC_EMPTY   = (40, 30, 30)

_STATUS_H    = 30                  # bottom status bar height


class HUD:
    """Stateful F1-style HUD renderer."""

    def __init__(self):
        # Rolling data buffers for real-time graphs
        self.speed_buf    = deque([0.0] * GRAPH_BUFFER_SIZE, maxlen=GRAPH_BUFFER_SIZE)
        self.steering_buf = deque([0.0] * GRAPH_BUFFER_SIZE, maxlen=GRAPH_BUFFER_SIZE)
        self.throttle_buf = deque([0.0] * GRAPH_BUFFER_SIZE, maxlen=GRAPH_BUFFER_SIZE)

        # Minimap trail — world (x, y) positions, last 100 points
        self.map_trail = deque(maxlen=100)
        self._frame_idx = 0   # frame counter for blink effects

    # ── public API ────────────────────────────────────────────────────────────

    def draw(
        self,
        base_frame:   np.ndarray,
        telemetry:    dict,
        gesture_state,
        webcam_frame: np.ndarray,
    ) -> np.ndarray:
        """Composite all HUD elements onto base_frame (1280×720 BGR)."""
        frame = base_frame.copy()
        self._frame_idx += 1

        # Update rolling buffers
        self.speed_buf.append(telemetry["speed"])
        self.steering_buf.append(telemetry["steering"])
        throttle_val = 1.0 if "FORWARD" in telemetry.get("command", "") else \
                      -1.0 if "REVERSE" in telemetry.get("command", "") else 0.0
        self.throttle_buf.append(throttle_val)

        pos = telemetry["position"]
        self.map_trail.append((pos[0], pos[1]))

        frame = self._draw_telemetry(frame, telemetry)
        frame = self._draw_gesture(frame, gesture_state)
        frame = self._draw_minimap(frame, telemetry)
        frame = self._draw_graphs(frame)
        frame = self._draw_pip(frame, webcam_frame)
        frame = self._draw_status_bar(frame, telemetry)

        return frame

    # ── helpers ───────────────────────────────────────────────────────────────

    def _panel(self, frame, x, y, w, h):
        """Semi-transparent dark panel with teal border + 2px top accent."""
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + w, y + h), _PANEL_BG, -1)
        frame = cv2.addWeighted(overlay, _PANEL_ALPHA, frame, 1 - _PANEL_ALPHA, 0)
        cv2.rectangle(frame, (x, y), (x + w, y + h), _TEAL, 1)
        cv2.line(frame, (x, y), (x + w, y), _TEAL, 2)       # top accent
        return frame

    # ── telemetry panel ───────────────────────────────────────────────────────

    def _draw_telemetry(self, frame, telemetry):
        px, py, pw, ph = 10, 10, 300, 230
        frame = self._panel(frame, px, py, pw, ph)

        # Header + blink dot
        cv2.putText(frame, "CAR TELEMETRY", (px + 10, py + 20), HUD_FONT, 0.45, _LABEL, 1)
        dot_color = _BLINK_ON if self._frame_idx % 2 == 0 else _BLINK_OFF
        cv2.circle(frame, (px + pw - 20, py + 15), 5, dot_color, -1)

        # Separator
        cv2.line(frame, (px + 8, py + 28), (px + pw - 8, py + 28), _SEPARATOR, 1)

        rows = [
            ("X",       f"{telemetry['position'][0]:+.2f} m"),
            ("Y",       f"{telemetry['position'][1]:+.2f} m"),
            ("Z",       f"{telemetry['position'][2]:+.2f} m"),
            ("SPEED",   f"{telemetry['speed']:.3f} m/s"),
            ("HEADING", f"{telemetry['heading']:.1f}°"),
            ("STEER",   f"{telemetry['steering']:.1f}°"),
            ("RPM",     f"{telemetry['wheel_rpm']:.0f}"),
            ("CMD",     telemetry["command"]),
        ]
        ty = py + 46
        for label, value in rows:
            cv2.putText(frame, label, (px + 12, ty), HUD_FONT, 0.38, _LABEL, 1)
            # Right-align value
            (tw, _), _ = cv2.getTextSize(value, HUD_FONT, 0.38, 1)
            cv2.putText(frame, value, (px + pw - 12 - tw, ty), HUD_FONT, 0.38, _VALUE, 1)
            ty += 20

        # Speed bar at bottom of panel
        bar_x, bar_y = px + 12, py + ph - 18
        bar_w, bar_h = pw - 24, 10
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), _BAR_EMPTY, -1)
        fill = max(0, min(1.0, telemetry["speed"] / 0.03))  # normalise (display delta)
        fill_w = int(bar_w * fill)
        if fill_w > 0:
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), _VALUE, -1)

        return frame

    # ── gesture panel ─────────────────────────────────────────────────────────

    def _draw_gesture(self, frame, gs):
        pw, ph = 340, 130
        px = CAMERA_WIDTH - pw - 10
        py = 10
        frame = self._panel(frame, px, py, pw, ph)
        # cyan border override
        cv2.rectangle(frame, (px, py), (px + pw, py + ph), _CYAN, 2)

        cv2.putText(frame, "GESTURE", (px + 10, py + 20), HUD_FONT, 0.40, _LABEL, 1)

        # Left
        cv2.putText(frame, f"L: {gs.left_gesture}", (px + 12, py + 60), HUD_FONT, 0.75, _CYAN, 2)
        self._draw_gesture_icon(frame, gs.left_gesture, px + pw - 55, py + 48)

        # Right
        cv2.putText(frame, f"R: {gs.right_gesture}", (px + 12, py + 100), HUD_FONT, 0.75, _CYAN, 2)
        self._draw_gesture_icon(frame, gs.right_gesture, px + pw - 55, py + 88)

        return frame

    def _draw_gesture_icon(self, frame, gesture, cx, cy):
        """Draw a small procedural icon for the gesture at (cx, cy)."""
        c = _CYAN
        s = 14  # icon half-size
        if gesture == "FORWARD":
            cv2.line(frame, (cx, cy + s), (cx, cy - s), c, 2)
            cv2.line(frame, (cx, cy - s), (cx - 6, cy - s + 8), c, 2)
            cv2.line(frame, (cx, cy - s), (cx + 6, cy - s + 8), c, 2)
        elif gesture == "REVERSE":
            cv2.line(frame, (cx, cy - s), (cx, cy + s), c, 2)
            cv2.line(frame, (cx, cy + s), (cx - 6, cy + s - 8), c, 2)
            cv2.line(frame, (cx, cy + s), (cx + 6, cy + s - 8), c, 2)
        elif gesture == "TURN_30":
            pts = [(cx - 6, cy + 4), (cx, cy - 4), (cx + 6, cy)]
            for i in range(len(pts) - 1):
                cv2.line(frame, pts[i], pts[i + 1], c, 2)
        elif gesture == "TURN_60":
            pts = [(cx - 8, cy + 6), (cx - 4, cy), (cx, cy - 6), (cx + 4, cy - 2), (cx + 8, cy + 4)]
            for i in range(len(pts) - 1):
                cv2.line(frame, pts[i], pts[i + 1], c, 2)
        elif gesture == "TURN_90":
            r = 12
            pts = []
            for a in range(7):
                angle = math.radians(180 + a * (90 / 6))
                pts.append((int(cx + r * math.cos(angle)), int(cy + r * math.sin(angle))))
            for i in range(len(pts) - 1):
                cv2.line(frame, pts[i], pts[i + 1], c, 2)
        elif gesture == "HOLD":
            cv2.line(frame, (cx - s, cy + 4), (cx + s, cy + 4), c, 2)
            for dx in range(-s + 3, s, 7):
                cv2.line(frame, (cx + dx, cy + 4), (cx + dx, cy - 8), c, 1)
        elif gesture == "STOP":
            cv2.line(frame, (cx - s, cy - s), (cx + s, cy + s), c, 2)
            cv2.line(frame, (cx + s, cy - s), (cx - s, cy + s), c, 2)
        else:  # NONE
            cv2.line(frame, (cx - 8, cy), (cx + 8, cy), c, 2)

    # ── minimap ───────────────────────────────────────────────────────────────

    def _draw_minimap(self, frame, telemetry):
        ms = MAP_SIZE   # 220
        mx = CAMERA_WIDTH - ms - 10
        my = CAMERA_HEIGHT // 2 - ms // 2
        frame = self._panel(frame, mx, my, ms, ms)

        # Compass labels
        cv2.putText(frame, "N", (mx + ms // 2 - 5, my + 16), HUD_FONT, 0.35, _LABEL, 1)
        cv2.putText(frame, "S", (mx + ms // 2 - 5, my + ms - 6), HUD_FONT, 0.35, _LABEL, 1)
        cv2.putText(frame, "E", (mx + ms - 16, my + ms // 2 + 4), HUD_FONT, 0.35, _LABEL, 1)
        cv2.putText(frame, "W", (mx + 5, my + ms // 2 + 4), HUD_FONT, 0.35, _LABEL, 1)

        ccx, ccy = mx + ms // 2, my + ms // 2  # centre of minimap

        # Trail
        trail = list(self.map_trail)
        n = len(trail)
        for i, (wx, wy) in enumerate(trail):
            px = int(ccx + wx / MAP_SCALE)
            py = int(ccy - wy / MAP_SCALE)
            if mx <= px < mx + ms and my <= py < my + ms:
                t = i / max(n - 1, 1)
                clr = (int(110 * t), int(160 * t), 0)
                cv2.circle(frame, (px, py), 1, clr, -1)

        # Car triangle rotated by heading
        pos = telemetry["position"]
        heading_rad = math.radians(telemetry["heading"])
        cpx = int(ccx + pos[0] / MAP_SCALE)
        cpy = int(ccy - pos[1] / MAP_SCALE)
        cpx = max(mx + 4, min(mx + ms - 4, cpx))
        cpy = max(my + 4, min(my + ms - 4, cpy))
        ts = 7  # triangle size
        pts = []
        for a_offset in [0, 2.4, -2.4]:  # front, back-left, back-right
            a = heading_rad + a_offset
            px = int(cpx + ts * math.cos(a))
            py = int(cpy - ts * math.sin(a))
            pts.append([px, py])
        pts_arr = np.array(pts, np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(frame, [pts_arr], _VALUE)

        # Position text below minimap
        cv2.putText(frame, f"X:{pos[0]:.1f} Y:{pos[1]:.1f}",
                    (mx + 5, my + ms + 16), HUD_FONT, 0.35, _LABEL, 1)

        return frame

    # ── graphs ────────────────────────────────────────────────────────────────

    def _draw_graphs(self, frame):
        graph_h = 100
        graph_y = CAMERA_HEIGHT - _STATUS_H - graph_h - 10
        graph_w = (CAMERA_WIDTH - PIP_WIDTH - 50) // 3
        graph_start = PIP_WIDTH + 20

        cfgs = [
            ("SPEED (m/s)", self.speed_buf,    _VALUE),
            ("STEER (deg)", self.steering_buf,  _CYAN),
            ("THROTTLE",    self.throttle_buf, (0, 255, 0)),
        ]

        for i, (label, buf, color) in enumerate(cfgs):
            gx = graph_start + i * (graph_w + 10)
            gy = graph_y
            frame = self._panel(frame, gx, gy, graph_w, graph_h)

            cv2.putText(frame, label, (gx + 5, gy + 14), HUD_FONT, 0.33, _LABEL, 1)

            data = list(buf)
            if len(data) < 2:
                continue

            dmin, dmax = min(data), max(data)
            if abs(dmax - dmin) < 1e-6:
                dmin -= 1.0; dmax += 1.0

            def to_py(val):
                norm = (val - dmin) / (dmax - dmin)
                return int(gy + graph_h - 20 - norm * (graph_h - 30))

            # Zero line
            if dmin < 0 < dmax:
                zy = to_py(0)
                cv2.line(frame, (gx, zy), (gx + graph_w, zy), _SEPARATOR, 1)

            # Build polyline
            pts = []
            for j, v in enumerate(data):
                px = int(gx + j * graph_w / GRAPH_BUFFER_SIZE)
                py = to_py(v)
                pts.append((px, py))

            # Filled area under curve
            fill_pts = list(pts) + [(pts[-1][0], gy + graph_h - 20), (pts[0][0], gy + graph_h - 20)]
            fill_arr = np.array(fill_pts, np.int32).reshape((-1, 1, 2))
            fill_overlay = frame.copy()
            cv2.fillPoly(fill_overlay, [fill_arr], color)
            frame = cv2.addWeighted(fill_overlay, 0.3, frame, 0.7, 0)

            # Line
            for j in range(1, len(pts)):
                cv2.line(frame, pts[j - 1], pts[j], color, 1)

            # Current value top-right
            cur_str = f"{data[-1]:.2f}"
            (tw, _), _ = cv2.getTextSize(cur_str, HUD_FONT, 0.33, 1)
            cv2.putText(frame, cur_str, (gx + graph_w - tw - 5, gy + 14), HUD_FONT, 0.33, _VALUE, 1)

            # Axis ticks (4 on left edge)
            for tick in range(1, 5):
                ty = int(gy + graph_h - 20 - tick * (graph_h - 30) / 4)
                cv2.line(frame, (gx, ty), (gx + 5, ty), _LABEL, 1)

        return frame

    # ── webcam PiP ────────────────────────────────────────────────────────────

    def _draw_pip(self, frame, webcam_frame):
        pip = cv2.resize(webcam_frame, (PIP_WIDTH, PIP_HEIGHT))
        px = 10
        py = CAMERA_HEIGHT - _STATUS_H - PIP_HEIGHT - 10

        frame[py:py + PIP_HEIGHT, px:px + PIP_WIDTH] = pip
        cv2.rectangle(frame, (px, py), (px + PIP_WIDTH, py + PIP_HEIGHT), _CYAN, 1)
        cv2.putText(frame, "OPERATOR", (px + 5, py + 14), HUD_FONT, 0.35, _LABEL, 1)

        # Blinking REC
        if self._frame_idx % 2 == 0:
            rx = px + PIP_WIDTH - 60
            ry = py + 14
            cv2.circle(frame, (rx, ry - 4), 5, _REC_RED, -1)
            cv2.putText(frame, "REC", (rx + 8, ry), HUD_FONT, 0.32, _REC_RED, 1)

        return frame

    # ── bottom status bar ─────────────────────────────────────────────────────

    def _draw_status_bar(self, frame, telemetry):
        by = CAMERA_HEIGHT - _STATUS_H
        cv2.rectangle(frame, (0, by), (CAMERA_WIDTH, CAMERA_HEIGHT), _PANEL_BG, -1)

        third = CAMERA_WIDTH // 3

        # Left: CMD
        cv2.putText(frame, telemetry["command"], (10, by + 22), HUD_FONT, 0.55, _VALUE, 1)

        # Centre: steering indicator
        line_y  = by + _STATUS_H // 2
        line_x1 = third + 10
        line_x2 = line_x1 + 200
        cv2.line(frame, (line_x1, line_y), (line_x2, line_y), _LABEL, 1)
        # Map steer -90..+90 to line_x1..line_x2
        steer = telemetry["steering"]
        norm  = (steer + 90.0) / 180.0
        dot_x = int(line_x1 + norm * 200)
        dot_x = max(line_x1, min(line_x2, dot_x))
        cv2.circle(frame, (dot_x, line_y), 6, _CYAN, -1)

        # Right: speed arc
        arc_cx = 2 * third + third // 2
        arc_cy = by + _STATUS_H // 2 + 2
        arc_r  = 20
        # Empty arc (195° to 345°)
        cv2.ellipse(frame, (arc_cx, arc_cy), (arc_r, arc_r), 0, 195, 345, _ARC_EMPTY, 2)
        # Filled arc
        speed = telemetry["speed"]
        fill_angle = int((speed / 0.03) * 150)  # 150° span
        fill_angle = max(0, min(150, fill_angle))
        if fill_angle > 0:
            cv2.ellipse(frame, (arc_cx, arc_cy), (arc_r, arc_r), 0, 195, 195 + fill_angle, _VALUE, 3)
        # Speed text
        spd_str = f"{speed:.3f}"
        (tw, _), _ = cv2.getTextSize(spd_str, HUD_FONT, 0.32, 1)
        cv2.putText(frame, spd_str, (arc_cx - tw // 2, arc_cy + 5), HUD_FONT, 0.32, _VALUE, 1)

        return frame
