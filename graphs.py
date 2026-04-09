"""
graphs.py
---------
Generates four publication-quality benchmark charts for the README.
Saves to assets/ directory. Run with:
    conda run -n gesture_car_env11 python graphs.py
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")  # headless backend — no display needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap

os.makedirs("assets", exist_ok=True)

plt.style.use("dark_background")

_FIG_SIZE  = (8, 4)   # 1200×600 at 150 DPI
_DPI       = 150
_FACE      = "#0D0D14"
_GRID_CLR  = "#2A2A3A"
_TIGHT     = dict(pad=0.4)

def _fig():
    fig, ax = plt.subplots(figsize=_FIG_SIZE, dpi=_DPI)
    fig.patch.set_facecolor(_FACE)
    ax.set_facecolor(_FACE)
    ax.grid(color=_GRID_CLR, linestyle="--", linewidth=0.6, alpha=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#444455")
    ax.spines["bottom"].set_color("#444455")
    ax.tick_params(colors="#AAAACC", labelsize=9)
    return fig, ax

# ─────────────────────────────────────────────────────────────────────────────
# Graph 1 — FPS Comparison
# ─────────────────────────────────────────────────────────────────────────────
fig, ax = _fig()

modes  = ["3D 1280×720", "3D 320×240\n→ upscaled", "2D OpenCV"]
fps    = [0.8, 15.4, 28.0]
colors = ["#FF4444", "#FFAA00", "#00FFB4"]

bars = ax.bar(modes, fps, color=colors, width=0.5, edgecolor="#222233", linewidth=1.2, zorder=3)

for bar, val in zip(bars, fps):
    ax.text(bar.get_x() + bar.get_width() / 2, val + 0.6,
            f"{val} FPS", ha="center", va="bottom", color="#EEEEFF", fontsize=11,
            fontweight="bold")

ax.axhline(30, color="#00FFB4", linestyle="--", linewidth=1.2, alpha=0.7, zorder=4)
ax.text(2.42, 30.8, "Target 30 FPS", color="#00FFB4", fontsize=8, va="bottom", ha="right")

ax.set_ylim(0, 35)
ax.set_ylabel("Frames per Second", color="#AAAACC", fontsize=10)
ax.set_title("Render Mode FPS Comparison", color="#EEEEFF", fontsize=13, fontweight="bold", pad=12)

fig.tight_layout(**_TIGHT)
fig.savefig("assets/fps_comparison.png", dpi=_DPI, transparent=True)
plt.close(fig)
print("  ✓  assets/fps_comparison.png")

# ─────────────────────────────────────────────────────────────────────────────
# Graph 2 — Gesture Recognition Accuracy
# ─────────────────────────────────────────────────────────────────────────────
fig, ax = _fig()

gestures  = ["Open Palm\n(HOLD)", "Fist\n(STOP)", "Index Only\n(TURN_30)",
             "Peace Sign\n(TURN_60)", "Thumbs Up\n(FORWARD)", "Three Fingers\n(TURN_90)",
             "Thumbs Down\n(REVERSE)"]
accuracy  = [97, 95, 93, 91, 90, 89, 88]

# Colour gradient: mint green (best) to red (lowest)
cmap = LinearSegmentedColormap.from_list("acc", ["#FF6B6B", "#00FFB4"])
norm_vals = [(v - min(accuracy)) / (max(accuracy) - min(accuracy)) for v in accuracy]
bar_colors = [cmap(n) for n in norm_vals]

y_pos = list(range(len(gestures)))
bars  = ax.barh(y_pos, accuracy, color=bar_colors, edgecolor="#222233", linewidth=0.8,
                height=0.6, zorder=3)

for bar, val in zip(bars, accuracy):
    ax.text(val + 0.15, bar.get_y() + bar.get_height() / 2,
            f"{val}%", va="center", ha="left", color="#EEEEFF", fontsize=10, fontweight="bold")

ax.set_yticks(y_pos)
ax.set_yticklabels(gestures, fontsize=8.5, color="#CCCCDD")
ax.set_xlim(80, 100)
ax.set_xlabel("Recognition Rate (%)", color="#AAAACC", fontsize=10)
ax.set_title("Gesture Recognition Accuracy (%)", color="#EEEEFF", fontsize=13,
             fontweight="bold", pad=12)

fig.tight_layout(**_TIGHT)
fig.savefig("assets/gesture_accuracy.png", dpi=_DPI, transparent=True)
plt.close(fig)
print("  ✓  assets/gesture_accuracy.png")

# ─────────────────────────────────────────────────────────────────────────────
# Graph 3 — MediaPipe Amortized Latency vs Frame Skip
# ─────────────────────────────────────────────────────────────────────────────
fig, ax = _fig()

x_vals  = [1, 2, 3, 4, 5]
y_vals  = [25, 13, 8, 6, 5]
clr     = "#00CFFF"

ax.fill_between(x_vals, y_vals, alpha=0.15, color=clr, zorder=2)
ax.plot(x_vals, y_vals, color=clr, linewidth=2.2, marker="o",
        markersize=8, markerfacecolor="white", markeredgecolor=clr, zorder=4)

for x, y in zip(x_vals, y_vals):
    ax.text(x, y + 0.7, f"{y}ms", ha="center", va="bottom", color="#EEEEFF", fontsize=9)

ax.annotate("← Used in\nthis project", xy=(3, 8), xytext=(3.7, 15),
            arrowprops=dict(arrowstyle="->", color="#FFDD44", lw=1.5),
            color="#FFDD44", fontsize=9, fontweight="bold")

ax.set_xticks(x_vals)
ax.set_xticklabels([f"Every {n}{'st' if n==1 else 'nd' if n==2 else 'rd' if n==3 else 'th'} frame"
                    for n in x_vals], fontsize=8)
ax.set_xlim(0.6, 5.4)
ax.set_ylim(0, 30)
ax.set_ylabel("Amortized Latency (ms)", color="#AAAACC", fontsize=10)
ax.set_xlabel("Frame Skip Interval", color="#AAAACC", fontsize=10)
ax.set_title("MediaPipe Amortized Latency vs Frame Skip", color="#EEEEFF",
             fontsize=13, fontweight="bold", pad=12)

fig.tight_layout(**_TIGHT)
fig.savefig("assets/mediapipe_latency.png", dpi=_DPI, transparent=True)
plt.close(fig)
print("  ✓  assets/mediapipe_latency.png")

# ─────────────────────────────────────────────────────────────────────────────
# Graph 4 — Per-Frame Time Budget (2D mode)
# ─────────────────────────────────────────────────────────────────────────────
fig, ax = _fig()

categories   = ["MediaPipe\n(8ms)", "Physics Step\n(2ms)", "2D Render\n(3ms)",
                "HUD Draw\n(4ms)", "Display\n(1ms)"]
durations    = [8, 2, 3, 4, 1]
colors       = ["#FF6B6B", "#FFD93D", "#00FFB4", "#00CFFF", "#A855F7"]

lefts = [sum(durations[:i]) for i in range(len(durations))]

for left, dur, col, label in zip(lefts, durations, colors, categories):
    ax.barh(["Frame budget"], [dur], left=left, color=col, edgecolor="#1A1A26",
            linewidth=0.8, height=0.4, zorder=3)
    # Center label inside bar (only if wide enough)
    if dur >= 2:
        cx = left + dur / 2
        ax.text(cx, 0, label, ha="center", va="center", fontsize=7.5,
                color="black" if col in ("#FFD93D", "#00FFB4") else "white",
                fontweight="bold", zorder=5)

total = sum(durations)
ax.set_xlim(0, 42)
ax.axvline(33.3, color="#FFDD44", linestyle="--", linewidth=1.5, alpha=0.85, zorder=4)
ax.text(33.8, 0.22, "33ms budget\n(30 FPS)", color="#FFDD44", fontsize=8,
        va="center", fontweight="bold")

ax.text(total / 2, -0.26, f"Total: {total}ms", ha="center", color="#AAAACC",
        fontsize=10, va="top")

ax.set_xlabel("Time (ms)", color="#AAAACC", fontsize=10)
ax.set_yticks([])
ax.set_title("Per-Frame Time Budget — 2D Mode (18ms total)", color="#EEEEFF",
             fontsize=13, fontweight="bold", pad=12)

# Legend
patches = [mpatches.Patch(color=c, label=lbl.replace("\n", " "))
           for c, lbl in zip(colors, categories)]
ax.legend(handles=patches, loc="lower right", fontsize=7.5,
          facecolor="#1A1A26", edgecolor="#444455", labelcolor="#CCCCDD")

fig.tight_layout(**_TIGHT)
fig.savefig("assets/system_timeline.png", dpi=_DPI, transparent=True)
plt.close(fig)
print("  ✓  assets/system_timeline.png")

print("\nAll graphs saved to assets/")
