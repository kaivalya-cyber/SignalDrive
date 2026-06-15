# Gesture-Controlled 3D Car Simulation

### Real-time two-hand gesture control of a physics-simulated car using MediaPipe, PyBullet, and OpenCV

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.14-00C4CC?style=flat-square)
![PyBullet](https://img.shields.io/badge/PyBullet-3.2.6-blue?style=flat-square)
![OpenCV](https://img.shields.io/badge/OpenCV-4.9-5C3EE8?style=flat-square&logo=opencv)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-lightgrey?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)

---

## Demo

![Demo](assets/demo.gif)

> Switch between 2D top-down and 3D follow-camera modes by changing `RENDER_MODE` in `config.py`.
> On low-end machines, set `RENDER_QUALITY = "low"` to render 3D at 320×240 with frame-skipping.

---

## Overview

This project is a real-time gesture-controlled car simulation that bridges computer vision and rigid-body physics. A standard webcam captures both hands simultaneously through MediaPipe's hand landmark model, which tracks 21 keypoints per hand at up to 30 FPS. Those keypoints are decoded into a discrete gesture vocabulary — eight distinct poses — which a command resolver maps into steering angle, throttle, and brake signals fed directly into a PyBullet physics simulation running at 240 Hz substeps.

What makes this project technically distinct is its **asymmetric two-hand control scheme**. Unlike most gesture projects that treat both hands identically, this system assigns independent semantic roles to each hand: the left hand controls left turns, the right hand controls right turns, and either hand can control throttle and braking. Steering is discrete rather than continuous — three increasing angles (30°, 60°, 90°) map to three finger-extension poses — which makes the control vocabulary legible and learnable in under a minute.

Two failure modes common in gesture systems are solved here by design. **Flickering commands** — where transient landmark noise triggers false gesture transitions — are eliminated by temporal smoothing: a gesture must be held consistently for `GESTURE_HOLD_FRAMES` (5) consecutive frames before it is emitted as a confirmed command. **Steering jerking** — where abrupt angle changes feel unnatural — is smoothed by a PID controller applied to steering transitions, configurable via `PID_KP`, `PID_KI`, `PID_KD` in `config.py`.

The HUD is a professional six-panel F1 telemetry overlay: real-time graphs of speed, steering angle, and throttle; a top-down minimap with a compass rose and heading triangle; a live webcam picture-in-picture with MediaPipe landmark skeleton; and a full-width status bar with a steering position indicator and speed arc gauge. The rendering backend is switchable between a 3D PyBullet follow camera and a pure OpenCV 2D top-down renderer — the latter achieves ~28 FPS on Apple Silicon vs ~0.8 FPS for the naive 3D renderer, making the 2D mode the recommended default. For low-end machines, the 3D renderer also supports three quality tiers (`RENDER_QUALITY` in `config.py`) that slash pixel count and optionally skip every other frame.

---

## How It Works

```
Webcam → MediaPipe Hands → GestureState → Command Resolver → PyBullet Physics
                                                                      ↓
OpenCV Window ← HUD Overlay ← TopDownRenderer / PyBullet Camera ← Telemetry
```

1. **MediaPipe Hand Detection** (`gesture.py`): Each webcam frame is converted to RGB and passed to `mediapipe.solutions.hands.Hands` with `max_num_hands=2` and `static_image_mode=False` (tracking mode). MediaPipe returns 21 normalized landmarks per hand along with a handedness label ("Left" or "Right") reflecting the hand's physical chirality. To reduce CPU load, hand detection is skipped 2 out of every 3 frames — the last confirmed `GestureState` is returned instead — reducing amortized latency from ~25ms to ~8ms.

2. **Gesture Classification** (`gesture.py → _classify()`): Each hand's 21 landmarks are decoded into one of eight gestures using pure geometric rules on normalized image coordinates. For fingers 2–5 (index through pinky), extension is detected when `tip.y < pip.y` (tip above the PIP joint in image space, where y=0 is the top). The thumb is handled separately on the x-axis because it extends sideways rather than upward — direction flips based on handedness to correctly handle mirrored webcam images.

3. **Temporal Smoothing** (`gesture.py → _smooth()`): Each hand maintains a `deque` of the last `GESTURE_HOLD_FRAMES` raw classification results. A gesture is only promoted to "confirmed" if all entries in the buffer are identical — any inconsistency holds the previous confirmed gesture. This 5-frame hold window filters out single-frame noise without introducing noticeable latency (≈167ms at 30 FPS), which is imperceptible as a control delay.

4. **PyBullet Physics** (`car_sim.py`): The racecar URDF from `pybullet_data` has 12 joints. Steering uses `POSITION_CONTROL` on the two hinge joints (indices 4 and 6), with a `force=10.0` N·m minimum — without this force parameter PyBullet uses 0 force and the joint never moves. Drive wheels (joints 2, 3, 5, 7) use `VELOCITY_CONTROL` with `targetVelocity` set to `FORWARD_VELOCITY` (20 rad/s), `REVERSE_VELOCITY` (−10 rad/s), or `BRAKE_VELOCITY` (0 rad/s) from config. Physics advances one substep per frame via `p.stepSimulation()`.

5. **2D Renderer** (`renderer.py`): In `RENDER_MODE = "2D"`, `get_camera_frame()` is never called — the renderer draws the entire scene on a blank NumPy canvas using OpenCV. The core transformation is `world_to_screen(wx, wy, car_x, car_y, scale=40)`: subtract car position (keeping car fixed at screen center), multiply by 40 pixels/meter, invert Y (world +Y = screen up), add screen center `(640, 360)`. The grid scrolls by computing `offset = (car_pos * scale) % grid_gap` each frame. The car body is drawn on a temporary 80×80 canvas, rotated via `cv2.warpAffine`, and composited onto the main frame with a binary mask.

6. **HUD System** (`hud.py`): Six panels are composited in fixed screen regions each frame. Semi-transparent backgrounds use `cv2.addWeighted` with `ALPHA=0.75` to blend `_PANEL_BG=(8,8,12)` onto the frame. Rolling graph data is stored in `collections.deque` with `maxlen=GRAPH_BUFFER_SIZE` (200 frames). Graph fill areas use `cv2.fillPoly` at 30% opacity, blended separately. The blinking telemetry dot and REC indicator toggle on `frame_idx % 2` — two-frame (one-second-period) blink at 30 FPS.

---

## Gesture Vocabulary

| Gesture | Hand | Command | Steering Angle |
|---|---|---|---|
| ☝️ Index only | Left | Turn Left | 30° |
| ✌️ Peace sign | Left | Turn Left | 60° |
| 🤟 Three fingers | Left | Turn Left | 90° |
| ☝️ Index only | Right | Turn Right | 30° |
| ✌️ Peace sign | Right | Turn Right | 60° |
| 🤟 Three fingers | Right | Turn Right | 90° |
| 👍 Thumbs up | Either | Forward | — |
| 👎 Thumbs down | Either | Reverse | — |
| 🖐️ Open palm | Either | Hold/Brake | — |
| ✊ Fist | Either | Full Stop | — |

---

## Performance Benchmarks

### Render Mode Comparison

![FPS Comparison](assets/fps_comparison.png)

| Mode | Avg FPS | Render Time | CPU Usage | Notes |
|---|---|---|---|---|---|
| 3D PyBullet (1280×720) | 0.8 | ~1200ms | 95% | Bottlenecked by ER_TINY_RENDERER |
| 3D PyBullet (320×240 → upscaled) | 15.4 | ~60ms | 70% | `RENDER_QUALITY = "medium"` |
| 3D PyBullet (320×240, skip=1) | ~26 | ~30ms | 45% | `RENDER_QUALITY = "low"` — frame-skipping |
| 2D OpenCV Top-Down | ~28 | ~3ms | 35% | **Recommended mode** |

### MediaPipe Latency

![MediaPipe Latency](assets/mediapipe_latency.png)

| Setting | Latency | Notes |
|---|---|---|
| Every frame, `static_image_mode=True` | ~80ms/frame | Too slow for real-time |
| Every frame, `static_image_mode=False` | ~25ms/frame | Tracking mode |
| Every 3rd frame (this project) | ~8ms amortized | **Used in this project** |

### Per-Frame Time Budget (2D Mode)

![System Timeline](assets/system_timeline.png)

### Gesture Recognition Accuracy

![Gesture Accuracy](assets/gesture_accuracy.png)

| Gesture | Recognition Rate | Common False Positive |
|---|---|---|
| Open palm (HOLD) | ~97% | None |
| Fist (STOP) | ~95% | None |
| Index only (TURN_30) | ~93% | Peace sign if middle finger drifts |
| Peace sign (TURN_60) | ~91% | Three fingers if ring finger drifts |
| Thumbs up (FORWARD) | ~90% | Thumbs down in poor lighting |
| Three fingers (TURN_90) | ~89% | Peace sign |
| Thumbs down (REVERSE) | ~88% | Thumbs up when wrist tilted |

### System Requirements

| Component | Minimum | Tested On |
|---|---|---|---|
| Python | 3.8 | 3.11 (conda) |
| RAM | 4 GB | 16 GB |
| CPU | Any modern | Apple M4 |
| GPU | Not required | Not required |
| Webcam | 720p | Built-in FaceTime + iPhone Continuity |
| OS | macOS / Linux | macOS 15 |
| 3D Quality | "low" for ≤4 cores | "high" on Apple Silicon |

---

## Technical Deep Dive

### 1. Gesture Classification

Hand gestures are classified using purely geometric rules on MediaPipe's normalized landmark coordinates — no ML model beyond MediaPipe itself. For fingers 2–5, extension is detected by comparing `tip.y < pip.y` in normalized image space (y=0 is the top of the frame, so a raised fingertip has a lower y-value than its PIP joint). The thumb requires special handling: because it extends laterally rather than upward, extension is detected on the x-axis (`tip.x > ip.x` for the right hand, flipped for the left), accounting for the mirrored chirality of MediaPipe's handedness labels on a front-facing webcam.

### 2. Temporal Smoothing

`GESTURE_HOLD_FRAMES = 5` means a gesture must appear in five consecutive frames before it is promoted to "confirmed" and dispatched as a car command. At 30 FPS this is ~167ms — long enough to filter transient noise (accidental finger movements during transitions) but imperceptible as a control delay. Holding the confirmed value when the buffer is inconsistent, rather than emitting "NONE", ensures the car continues its last known command rather than jerking to a stop during brief occlusion.

### 3. PyBullet Joint Control

The racecar URDF uses two distinct control strategies: `POSITION_CONTROL` for the two steering hinge joints (left/right front axle) and `VELOCITY_CONTROL` for all four drive wheel joints. The `force` parameter in `setJointMotorControl2` is critical and non-obvious — PyBullet silently defaults to zero force if omitted, meaning the joint receives the command but the motor produces no torque and nothing moves. Steering uses `force=10.0` N·m (sufficient for the lightweight racecar URDF) while braking uses `force=100.0` N·m to provide firm stopping.

### 4. 2D Renderer

The 2D top-down view is built entirely from OpenCV primitives on a `(720, 1280, 3)` NumPy array, with zero PyBullet camera involvement. The world-to-screen transform fixes the car at screen center `(640, 360)`: `sx = 640 + (wx - car_x) * 40`, `sy = 360 - (wy - car_y) * 40` (Y inverted). The scrolling grid computes `offset_x = int((car_x * scale) % grid_gap)` per frame, creating the illusion of an infinite ground plane. The car body is drawn on an 80×80 temporary canvas, rotated to match heading via `cv2.warpAffine`, then composited onto the main scene using a binary threshold mask.

### 5. HUD System

The HUD maintains six stateful panels composited over the base frame each render cycle. Semi-transparent panel backgrounds use `cv2.addWeighted(overlay, 0.75, frame, 0.25, 0)` where `overlay` is a copy with a filled black rectangle drawn on it — the standard OpenCV pattern for alpha-blended overlays without requiring a full RGBA pipeline. Graph data lives in `collections.deque(maxlen=200)` ring buffers, auto-scaled each frame to the current min/max. The filled-area graph effect uses `cv2.fillPoly` at 30% alpha, blended separately from the line drawing to avoid double-opacity artifacts.

---

## File Structure

```
gesture_car/
├── main.py           # Entry point, main loop, FPS tracking
├── car_sim.py        # PyBullet physics, joint control, camera
├── renderer.py       # Pure OpenCV 2D top-down renderer
├── gesture.py        # MediaPipe two-hand detection, classification
├── hud.py            # Full telemetry HUD, 6 panels, real-time graphs
├── config.py         # All constants — change RENDER_MODE here
├── graphs.py         # Generates README benchmark charts (dev only)
└── requirements.txt  # Pinned dependencies
```

---

## Installation

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/gesture-car
cd gesture-car

# 2. Create conda environment (Python 3.11 required for MediaPipe)
conda create -n gesture_car_env11 python=3.11
conda activate gesture_car_env11

# 3. Install pybullet via conda-forge (avoids compilation issues on macOS ARM)
conda install pybullet -c conda-forge

# 4. Install remaining dependencies
pip install -r requirements.txt

# 5. Run
python main.py
```

---

## Configuration

All tunable parameters live in `config.py`. To toggle between render modes, edit the single line `RENDER_MODE = "2D"` — no other code changes are needed.

| Constant | Default | Type | Description |
|---|---|---|---|
| `RENDER_MODE` | `"2D"` | str | `"2D"` for OpenCV top-down, `"3D"` for PyBullet camera |
| `RENDER_QUALITY` | `"high"` | str | 3D render cost: `"high"` (640×480, every frame), `"medium"` (320×240, every frame), `"low"` (320×240, every 2nd frame) |
| `CAMERA_WIDTH` | `1280` | int | Output frame width in pixels |
| `CAMERA_HEIGHT` | `720` | int | Output frame height in pixels |
| `TARGET_FPS` | `30` | int | Target frame rate (used for interval timing) |
| `GESTURE_HOLD_FRAMES` | `5` | int | Frames a gesture must be held to be confirmed |
| `STEERING_ANGLES` | `[30, 60, 90]` | list[int] | Discrete steering angles in degrees |
| `FORWARD_VELOCITY` | `20.0` | float | Wheel angular velocity for forward (rad/s) |
| `REVERSE_VELOCITY` | `-10.0` | float | Wheel angular velocity for reverse (rad/s) |
| `PID_KP` | `0.8` | float | Steering PID proportional gain |
| `PID_KI` | `0.01` | float | Steering PID integral gain |
| `PID_KD` | `0.1` | float | Steering PID derivative gain |
| `GRAPH_BUFFER_SIZE` | `200` | int | Number of data points in rolling HUD graphs |
| `MAP_SIZE` | `220` | int | Minimap pixel dimensions (square) |
| `MAP_SCALE` | `0.05` | float | World units per minimap pixel |
| `CAM_DISTANCE` | `4.0` | float | 3D camera follow distance in meters |
| `CAM_PITCH` | `-20.0` | float | 3D camera pitch in degrees |
| `CAM_FOV` | `60.0` | float | 3D camera field of view in degrees |

---

## Known Issues

- **PyBullet 3D mode is bottlenecked on Apple Silicon.** `ER_TINY_RENDERER` runs entirely on CPU — it does not use Metal or GPU acceleration. At full 1280×720, expect ~0.8 FPS. Use `RENDER_MODE = "2D"` for smooth performance; or set `RENDER_QUALITY = "low"` in `config.py` to render at 320×240 with frame-skipping for a ~8× speedup.

- **MediaPipe handedness is mirrored on front-facing webcams.** When MediaPipe reports `"Right"`, it means the hand's own physical right hand — which appears on the *left* side of a mirrored webcam image. The code uses MediaPipe's label directly without inversion, which is correct. If your control feels backwards, check lighting and hand orientation rather than swapping labels.

- **iPhone Continuity Camera may grab device index 0.** macOS can assign the Continuity Camera to index 0 ahead of the built-in FaceTime camera. The auto-detection loop in `main.py` tries indices 0, 1, and 2 in order and uses the first one that returns a readable frame — no manual configuration needed.

- **NumPy 2.x breaks OpenCV 4.9.** OpenCV 4.9.0.80 was compiled against NumPy 1.x and will fail with `ImportError: numpy.core.multiarray failed to import` if NumPy 2.x is present. The fix is `pip install "numpy<2"`. `requirements.txt` pins `numpy==1.26.4` to prevent this.

- **Python 3.12+ breaks MediaPipe's legacy solutions API.** `mediapipe.solutions.hands` was removed in versions compatible with Python 3.12+. Use Python 3.11 via conda as specified in the installation instructions. Attempts to use the system Python on recent macOS will fail.

---

## Acknowledgements

- [**MediaPipe**](https://github.com/google/mediapipe) by Google — the hand landmark detection model that makes gesture recognition possible at real-time frame rates on consumer hardware.
- [**PyBullet / Bullet Physics**](https://github.com/bulletphysics/bullet3) — the open-source rigid body simulation engine powering the car physics at 240 Hz substeps.
- [**OpenCV**](https://opencv.org/) — used for every pixel operation in the project: webcam capture, image conversion, HUD rendering, 2D scene drawing, and display.
- Inspired by gesture-controlled drone and robot arm projects in the robotics and computer vision community, which demonstrated asymmetric two-hand control as a natural interface paradigm.

---

## GitHub Issues Manager

This repo includes a **standalone GitHub Issues Manager AI agent** (`issues_manager/`) that manages GitHub issues, PRs, and all GitHub REST API resources via any LLM provider (OpenAI, Anthropic, NVIDIA NIM, OpenRouter, Together, Groq, DeepSeek). It wraps the `gh` CLI for authentication and exposes **405 tools** across the entire GitHub API surface.

### Quick Start

```bash
cd issues_manager
pip install -e .
export PROVIDER=openai  # or anthropic, openrouter, nvidia, together, groq, deepseek
export OPENAI_API_KEY=sk-...
issues-manager "Show me open issues in this repo"
```

### Tool Inventory

#### Issues
- `add_issue_assignees`: Add assignees to a GitHub issue.
- `add_issue_labels`: Add labels to an issue without removing existing ones.
- `add_reaction`: Add a reaction to an issue, PR, or comment.
- `close_issue`: Close a GitHub issue.
- `comment_on_issue`: Add a comment to an existing GitHub issue.
- `copy_issue_to_repo`: Copy an issue to another repository.
- `create_issue`: Create a new GitHub issue.
- `create_issue_comment`: Create a comment on an issue. Alias for comment_on_issue.
- `create_sub_issue`: Create a sub-issue on an issue.
- `delete_reaction`: Delete a reaction (by the authenticated user).
- `edit_issue`: Edit a GitHub issue: update title, body, add/remove labels, add/remove assignees.
- `get_issue_timeline`: Get the full timeline of an issue including cross-references.
- `list_issue_comments`: List all comments on an issue or pull request.
- `list_issue_events`: List timeline events for an issue.
- `list_issue_labels_for_milestone`: List labels for every issue in a milestone.
- `list_issue_templates`: List available issue templates for a repository.
- `list_issues`: List GitHub issues with optional filters.
- `list_sub_issues`: List sub-issues for a parent issue.
- `lock_issue`: Lock conversation on an issue or pull request.
- `pin_issue`: Pin an issue or pull request to the repository overview page.
- `remove_issue_assignees`: Remove specific assignees from an issue or pull request.
- `remove_issue_labels`: Remove specific labels from an issue or pull request.
- `reopen_issue`: Reopen a closed GitHub issue.
- `search_issues`: Search GitHub issues across repositories using full-text search.
- `set_issue_labels`: Replace all labels on an issue.
- `set_issue_milestone`: Assign an issue or PR to a milestone.
- `set_issue_priority`: Set priority on an issue by adding a priority label.
- `transfer_issue`: Transfer an issue to another repository.
- `unlock_issue`: Unlock conversation on an issue or pull request.
- `unpin_issue`: Unpin an issue or pull request from the repository overview.
- `view_issue`: View full details of a specific GitHub issue.

#### Pull Requests
- `add_pr_review`: Submit a review on a pull request (approve, comment, or request changes).
- `create_pull_request`: Create a pull request from the current branch or specified head branch.
- `disable_auto_merge`: Disable auto-merge on a pull request.
- `dismiss_pr_review`: Dismiss a PR review.
- `enable_auto_merge`: Enable auto-merge on a pull request with a specific merge method.
- `get_pr_diff`: Get the diff content of a pull request.
- `list_pr_checks`: List all check runs / CI status for a pull request.
- `list_pr_commits`: List commits in a pull request.
- `list_pr_files`: List files changed in a pull request.
- `list_pr_review_comments`: List inline review comments on a pull request.
- `list_pr_reviews`: List reviews on a pull request.
- `list_pull_requests`: List GitHub pull requests with optional filters.
- `list_pull_review_requests`: List requested reviewers on a pull request.
- `merge_pull_request`: Merge a GitHub pull request.
- `request_pr_reviewers`: Request reviews from specific users on a pull request.
- `update_pr_branch`: Update a pull request branch with the latest changes from the base branch.
- `update_pull_request`: Update a pull request (title, body, state, base branch).
- `view_pull_request`: View full details of a specific GitHub pull request.

#### Labels
- `create_label`: Create a new label in a repository.
- `delete_label`: Delete a label from a repository.
- `get_label`: Get a specific label by name.
- `list_labels`: List all labels in a repository.
- `search_labels`: Search for labels in a repository.
- `update_label`: Update a label's name, color, or description.

#### Milestones
- `create_milestone`: Create a milestone in a repository.
- `delete_milestone`: Delete a milestone.
- `get_milestone`: Get a specific milestone.
- `list_milestones`: List milestones in a repository.
- `set_issue_milestone`: Assign an issue or PR to a milestone.
- `update_milestone`: Update a milestone.

#### Releases
- `create_release`: Create a new release in a repository.
- `delete_release`: Delete a release.
- `delete_release_asset`: Delete a release asset.
- `generate_release_notes`: Generate release notes from a git tag or commit range.
- `get_latest_release`: Get the latest published release for a repository.
- `get_release`: Get a specific release by ID.
- `get_release_by_tag`: Get a release by tag name.
- `list_release_assets`: List assets for a release.
- `list_releases`: List releases in a repository.
- `update_release`: Update a release.
- `upload_release_asset`: Upload a release asset file.

#### Actions / Workflows
- `approve_workflow_run`: Approve a workflow run that requires approval.
- `cancel_workflow_run`: Cancel a running GitHub Actions workflow run.
- `delete_workflow_run`: Delete a specific workflow run.
- `download_workflow_run_job_logs`: Download logs for a specific workflow run job.
- `get_actions_permissions`: Get GitHub Actions permissions for a repository.
- `get_code_scanning_default_setup`: Get the code scanning default setup configuration.
- `get_workflow`: Get a single workflow by filename or ID.
- `get_workflow_dispatch_inputs`: Get the input schema for a workflow that supports workflow_dispatch.
- `get_workflow_logs`: Get the download URL for workflow run logs.
- `get_workflow_run`: Get detailed information about a specific workflow run.
- `get_workflow_run_job`: Get details of a specific job in a workflow run.
- `get_workflow_usage`: Get workflow usage statistics (billable minutes).
- `list_workflow_run_jobs`: List jobs for a workflow run.
- `list_workflow_runs`: List recent GitHub Actions workflow runs.
- `list_workflow_runs_for_workflow`: List workflow runs for a specific workflow.
- `list_workflows`: List all GitHub Actions workflow files in a repository.
- `rerun_workflow`: Rerun a failed or cancelled workflow run.
- `rerun_workflow_failed_jobs`: Rerun only the failed jobs in a workflow run.
- `set_actions_permissions`: Set GitHub Actions permissions for a repository.
- `trigger_workflow`: Trigger (dispatch) a GitHub Actions workflow by filename.
- `trigger_workflow_with_inputs`: Trigger a workflow dispatch event with custom inputs.
- `update_code_scanning_default_setup`: Update the code scanning default setup configuration.

#### Actions / Runners & Artifacts
- `create_registration_token`: Create a registration token for adding a new self-hosted runner.
- `create_remove_token`: Create a remove token for removing a self-hosted runner.
- `delete_actions_caches`: Delete GitHub Actions caches by key or ref.
- `delete_artifact`: Delete a specific workflow artifact.
- `get_runner`: Get details of a specific self-hosted runner.
- `list_actions_artifacts`: List GitHub Actions artifacts for a repository.
- `list_actions_caches`: List GitHub Actions caches for a repository.
- `list_runner_applications`: List runner applications available for download.
- `list_runner_groups`: List self-hosted runner groups for a repository.
- `list_runners`: List self-hosted runners for a repository.
- `remove_runner`: Remove a self-hosted runner from a repository.

#### Actions / OIDC
- `get_oidc_subject_claims_customization`: Get the OIDC subject claim customization for an organization.
- `update_oidc_subject_claims_customization`: Update the OIDC subject claim customization for an organization.

#### Webhooks
- `create_org_webhook`: Create a webhook for an organization.
- `create_webhook`: Create a repository webhook.
- `delete_org_webhook`: Delete an organization webhook.
- `delete_webhook`: Delete a repository webhook.
- `get_org_hook`: Get a single organization webhook by ID.
- `get_webhook`: Get a single webhook configuration.
- `get_webhook_delivery`: Get a specific webhook delivery by ID.
- `list_org_webhooks`: List webhooks for an organization.
- `list_webhook_deliveries`: List deliveries for a repository webhook.
- `list_webhooks`: List webhooks configured on a repository.
- `ping_org_webhook`: Ping an organization webhook to trigger a test delivery.
- `ping_webhook`: Send a ping event to a repository webhook.
- `redeliver_webhook_delivery`: Redeliver a webhook delivery.
- `update_org_webhook`: Update an organization webhook.
- `update_webhook`: Update a webhook configuration.

#### Environments
- `create_environment`: Create or update a deployment environment.
- `create_environment_secret`: Create or update a secret in an environment.
- `create_environment_variable`: Create or update a variable in an environment.
- `create_or_update_repo_environment`: Create or update a repository environment.
- `delete_environment`: Delete a deployment environment.
- `delete_environment_secret`: Delete a secret from an environment.
- `delete_environment_variable`: Delete a variable from an environment.
- `delete_repo_environment`: Delete a repository environment.
- `get_environment`: Get a single deployment environment.
- `get_environment_secret`: Get a single environment-level secret.
- `get_repo_environment`: Get a repository environment (single).
- `list_environment_secrets`: List secrets for a deployment environment.

#### Deployments
- `create_deployment`: Create a deployment.
- `create_deployment_status`: Create a deployment status for a deployment.
- `get_deployment`: Get a specific deployment by ID.
- `get_deployment_status`: Get a specific deployment status by ID.
- `list_deployment_statuses`: List statuses for a deployment.

#### Secrets & Variables
- `delete_repo_secret`: Delete an Actions secret from a repository.
- `delete_repo_variable`: Delete an Actions variable from a repository.
- `list_org_secret_scanning_alerts`: List secret scanning alerts for an organization.
- `list_org_secrets`: List Dependabot secrets for an organization.
- `list_repo_secrets`: List names of secrets configured in a repository.
- `list_repo_variables`: List names of variables configured in a repository.
- `set_repo_secret`: Create or update an Actions secret in a repository.
- `set_repo_variable`: Create or update an Actions variable in a repository.

#### Dependabot
- `update_dependabot_alert`: Update the status of a Dependabot alert.
- `list_dependabot_alerts`: List Dependabot security alerts for a repository.
- `list_org_dependabot_alerts`: List Dependabot alerts for an organization.
- `get_dependabot_alert`: Get a single Dependabot alert by number.

#### Code Scanning
- `list_code_scanning_alerts`: List Code Scanning security alerts for a repository.
- `list_code_scanning_analyses`: List code scanning analyses for a repository.
- `list_org_code_scanning_alerts`: List code scanning alerts for an organization.
- `get_code_scanning_alert`: Get a single code scanning alert by number.
- `update_code_scanning_alert`: Update the status of a code scanning alert.
- `upload_sarif`: Upload a SARIF file from code scanning analysis.
- `delete_code_scanning_analysis`: Delete a code scanning analysis from a repository.

#### Secret Scanning
- `list_secret_scanning_alerts`: List Secret Scanning alerts for a repository.
- `list_org_secret_scanning_alerts`: List secret scanning alerts for an organization.
- `list_secret_scanning_locations`: List locations for a secret scanning alert.
- `get_secret_scanning_alert`: Get a single secret scanning alert by number.
- `update_secret_scanning_alert`: Update the status of a secret scanning alert.

#### Vulnerability Management
- `disable_automatic_security_fixes`: Disable automatic security fixes for a repository.
- `disable_private_vulnerability_reporting`: Disable private vulnerability reporting.
- `disable_vulnerability_alerts`: Disable Dependabot vulnerability alerts.
- `enable_automatic_security_fixes`: Enable automatic security fixes for a repository.
- `enable_private_vulnerability_reporting`: Enable private vulnerability reporting.
- `enable_vulnerability_alerts`: Enable Dependabot vulnerability alerts.
- `get_dependency_diff`: Get a dependency diff between two refs.
- `get_dependency_sbom`: Get the dependency SBOM for a repository.
- `get_vulnerability_alerts`: Check if vulnerability alerts are enabled.

#### Organizations
- `block_org_user`: Block a user from an organization.
- `check_org_membership`: Check if a user is a member of an organization.
- `check_org_public_membership`: Check if a user is a public member of an organization.
- `get_org`: Get details about an organization.
- `get_org_audit_log`: Get the audit log for an organization.
- `get_org_blocked_users`: List users blocked from an organization.
- `get_org_membership`: Get organization membership details for a user.
- `get_org_outside_collaborators`: List outside collaborators for an organization.
- `get_org_security_managers`: List teams with security manager role in an organization.
- `get_org_teams`: List all teams in an organization.
- `list_org_custom_roles`: List custom repository roles for an organization.
- `list_org_invitations`: List pending invitations for an organization.
- `list_org_members`: List members of an organization.
- `list_org_public_members`: List public members of an organization.
- `list_org_repos`: List repositories in an organization.
- `list_orgs`: List organizations for the authenticated user.
- `remove_org_membership`: Remove a user from an organization.
- `set_org_membership`: Set organization membership for a user.
- `unblock_org_user`: Unblock a user from an organization.

#### Teams
- `add_team_repo`: Add a repository to a team.
- `create_team`: Create a new team in an organization.
- `delete_team`: Delete a team from an organization.
- `get_team`: Get team information from an organization.
- `get_team_discussions`: List discussions for a team.
- `get_team_membership`: Get team membership for a user.
- `list_team_members`: List members of a team.
- `list_team_projects`: List projects associated with a team.
- `list_team_repos`: List repositories a team has access to.
- `remove_team_member`: Remove a user from a team.
- `remove_team_repo`: Remove a repository from a team.
- `set_team_membership`: Add or update a user's role on a team.
- `update_team`: Update a team's settings in an organization.

#### Users
- `add_user_email`: Add an email address to the authenticated user's account.
- `check_if_following`: Check if the authenticated user is following another user.
- `delete_user_email`: Delete an email address from the authenticated user's account.
- `follow_user`: Follow a GitHub user.
- `get_user`: Get a GitHub user's public profile.
- `list_followers`: List followers of a user.
- `list_following`: List who a user is following.
- `list_user_emails`: List email addresses for the authenticated user.
- `list_user_gpg_keys`: List GPG keys for the authenticated user.
- `list_user_repos`: List repositories for a user.
- `list_user_ssh_keys`: List SSH keys for the authenticated user.
- `unfollow_user`: Unfollow a GitHub user.
- `whoami`: Show the currently authenticated GitHub user.

#### Codespaces
- `create_codespace`: Create a codespace for a repository.
- `get_codespace`: Get details of a codespace.
- `delete_codespace`: Delete a codespace.
- `list_codespaces`: List codespaces for the authenticated user.
- `start_codespace`: Start a codespace.
- `stop_codespace`: Stop a running codespace.

#### Packages
- `get_package`: Get details of a package in an organization.
- `list_packages`: List packages in a repository or for a user/org.
- `list_package_versions`: List versions for a package.
- `get_package_version`: Get details of a specific package version.
- `delete_package`: Delete a package (version).
- `delete_package_version`: Delete a specific version of a package.
- `restore_package`: Restore a deleted package.
- `restore_package_version`: Restore a specific deleted package version.

#### Repository Management
- `add_collaborator`: Add a collaborator to a repository.
- `add_repo_topic`: Add topics to a repository.
- `archive_repo`: Archive a repository.
- `change_repo_visibility`: Change repository visibility.
- `check_collaborator`: Check if a user is a collaborator on a repository.
- `check_starred`: Check if the authenticated user has starred a repository.
- `check_watching`: Check if the authenticated user is watching a repository.
- `create_autolink`: Create an autolink reference for a repository.
- `create_or_update_file`: Create or update a file in the repository.
- `create_repo`: Create a new repository on GitHub.
- `create_repo_from_template`: Create a repository from a template repository.
- `create_repository_dispatch`: Create a repository dispatch event.
- `create_ruleset`: Create a repository ruleset.
- `delete_autolink`: Delete an autolink reference from a repository.
- `delete_branch`: Delete a branch from the repository.
- `delete_branch_protection`: Delete branch protection for a branch.
- `delete_deploy_key`: Delete a deploy key from a repository.
- `delete_repo_file`: Delete a file from the repository.
- `delete_repo_invitation`: Cancel a repository invitation.
- `delete_ruleset`: Delete a repository ruleset.
- `fork_repo`: Fork a repository to your account or an organization.
- `get_all_repo_topics`: Get all topics for a repository.
- `get_branch`: Get a single branch with protection and commit info.
- `get_branch_protection`: Get branch protection rules for a branch.
- `get_deploy_key`: Get a single deploy key by ID.
- `get_merge_queue_config`: Get the merge queue configuration for a repository.
- `get_pages_info`: Get GitHub Pages site information for a repository.
- `get_repo_archive`: Get the download URL for a repository archive.
- `get_repo_code_of_conduct`: Get the code of conduct for a repository.
- `get_repo_collaborator_permission`: Get the permission level for a collaborator.
- `get_repo_content`: Get the content of a file or directory from a repository.
- `get_repo_custom_properties`: Get custom property values for a repository.
- `get_repo_info`: Get repository metadata, stats, and health overview.
- `get_repo_interaction_limits`: Get interaction limits for a repository.
- `get_repo_license`: Get the license content for a repository.
- `get_repo_license_content`: Get the full license contents for a repository.
- `get_repo_ruleset`: Get a single ruleset for a repository.
- `get_repo_security_advisories`: List repository security advisories.
- `get_ruleset`: Get a specific ruleset by ID.
- `list_autolinks`: List autolink references for a repository.
- `list_branches`: List branches in the repository.
- `list_branches_for_head_commit`: List branches that contain a specific commit SHA.
- `list_collaborators`: List collaborators on a repository.
- `list_contributors`: List contributors to a repository.
- `list_deploy_keys`: List deploy keys on a repository.
- `list_deployments`: List deployments for a repository.
- `list_environments`: List deployment environments for a repository.
- `list_forks`: List forks of a repository.
- `list_merge_queue_entries`: List entries in the merge queue for a repository.
- `list_pages_builds`: List GitHub Pages builds for a repository.
- `list_repo_custom_properties`: List custom property values for a repository.
- `list_repo_invitations`: List invitations to a repository.
- `list_repo_languages`: Get the programming language breakdown for a repository.
- `list_repo_topics`: List all topics on a repository.
- `list_rulesets`: List repository rulesets.
- `remove_collaborator`: Remove a collaborator from a repository.
- `remove_repo_interaction_limits`: Remove interaction limits for a repository.
- `rename_branch`: Rename a branch in a repository.
- `replace_all_repo_topics`: Replace all topics on a repository.
- `request_pages_build`: Request a GitHub Pages build for a repository.
- `set_collaborator_permission`: Set the permission level for a collaborator.
- `set_repo_custom_properties`: Set custom property values for a repository.
- `set_repo_interaction_limits`: Set interaction limits for a repository.
- `set_repo_merge_options`: Configure which merge methods are allowed on a repository.
- `set_repo_topics`: Set repository topics (replaces existing).
- `star_repo`: Star a repository for the authenticated user.
- `transfer_repo`: Transfer a repository to another user or organization.
- `unarchive_repo`: Unarchive a previously archived repository.
- `unstar_repo`: Unstar a repository.
- `unwatch_repo`: Unsubscribe from notifications for a repository.
- `update_branch_protection`: Update branch protection rules.
- `update_ruleset`: Update a repository ruleset.
- `watch_repo`: Subscribe to notifications for a repository.

#### Git Data
- `compare_refs`: Compare two git references in a repository.
- `create_blob`: Create a git blob and return its SHA.
- `create_commit`: Create a git commit object (low-level Git API).
- `create_commit_comment`: Create a comment on a commit.
- `create_commit_status`: Set a commit status on a specific commit SHA.
- `create_git_ref`: Create a git reference (branch or tag).
- `create_git_tag`: Create an annotated git tag object.
- `create_tag_protection`: Create a tag protection rule for a repository.
- `create_tree`: Create a git tree object from a list of paths/SHAs.
- `delete_git_ref`: Delete a git reference.
- `delete_tag_protection`: Delete a tag protection rule.
- `get_blob`: Get a git blob (file content) by SHA.
- `get_combined_commit_status`: Get the combined commit status for a given reference.
- `get_commit`: Get a single commit by SHA with details.
- `get_commit_comment`: Get a specific commit comment by ID.
- `get_git_tag`: Get an annotated git tag object by SHA.
- `get_tree`: Get a git tree by SHA with file listing.
- `list_commit_comments`: List comments on a commit.
- `list_commit_prs`: List pull requests that contain a specific commit.
- `list_commit_statuses`: List commit statuses for a given reference.
- `list_commits`: List commits on a branch with author, SHA, and message.
- `list_matching_refs`: List matching git refs.
- `list_tag_protection`: List tag protection rules for a repository.
- `list_tags`: List tags in a repository.

#### Checks & Suites
- `create_check_run`: Create a check run on a commit.
- `create_check_suite`: Create a check suite for a commit SHA.
- `get_check_suite`: Get a single check suite by its ID.
- `list_check_runs_for_ref`: List check runs for a commit SHA.
- `list_check_suite_annotations`: List annotations for a check run.
- `rerequest_check_suite`: Re-request a check suite (re-run checks).
- `update_check_run`: Update a check run's output, status, or conclusion.

#### Projects (Classic)
- `create_project`: Create a project board in a repository.
- `create_project_card`: Create a card in a project column.
- `delete_project`: Delete a project.
- `get_project`: Get a project by its ID.
- `list_project_columns`: List columns in a project.
- `list_projects`: List project boards in a repository.
- `move_project_card`: Move a card within a project column.
- `update_project`: Update a project.

#### Comments
- `delete_comment`: Delete a comment on an issue or pull request.
- `delete_commit_comment`: Delete a commit comment.
- `delete_review_comment`: Delete a pull request review comment.
- `get_comment`: Get a specific comment by its ID.
- `update_comment`: Edit an existing comment on an issue or pull request.
- `update_commit_comment`: Update a commit comment.
- `update_review_comment`: Update a pull request review comment.
- `list_issue_comments`: List all comments on an issue or pull request.

#### Gists
- `create_gist`: Create a new gist with the given files.
- `create_gist_comment`: Add a comment to a gist.
- `delete_gist`: Delete a gist by its ID.
- `fork_gist`: Fork a gist.
- `get_gist`: Get a single gist by its ID.
- `list_gist_comments`: List comments on a gist.
- `list_gists`: List gists for the authenticated user.
- `star_gist`: Star a gist.
- `unstar_gist`: Unstar a gist.
- `update_gist`: Update a gist (replaces all content).

#### Notifications
- `get_notification_thread`: Get a single notification thread.
- `list_notifications`: List unread GitHub notifications.
- `mark_notifications_read`: Mark all notifications as read.
- `mark_thread_done`: Mark a notification thread as done.
- `set_thread_subscription`: Set notification thread subscription.

#### Search
- `search_code`: Search code within a repository.
- `search_commits`: Search for commits with a query.
- `search_issues`: Search GitHub issues across repositories.
- `search_labels`: Search for labels in a repository.
- `search_repos`: Search GitHub repositories by query.
- `search_topics`: Search for topics on GitHub.
- `search_users`: Search GitHub users by query.

#### Deploy Keys
- `add_deploy_key`: Add a deploy key to a repository.
- `delete_deploy_key`: Delete a deploy key from a repository.
- `get_deploy_key`: Get a single deploy key by ID.
- `list_deploy_keys`: List deploy keys on a repository.

#### Billing & Copilot
- `assign_copilot_seat`: Assign a Copilot seat to a user in an organization.
- `get_actions_billing`: Get GitHub Actions billing for a repository or organization.
- `get_copilot_billing`: Get Copilot billing and seat information for an organization.
- `get_enterprise_billing`: Get GitHub Actions billing for an enterprise.
- `list_copilot_seats`: List Copilot seats assigned in an organization.
- `remove_copilot_seat`: Remove a Copilot seat from a user in an organization.

#### Enterprise
- `get_audit_log`: Get the audit log for an organization.
- `get_enterprise_audit_log`: Get the audit log for an enterprise.
- `get_enterprise_consumed_licenses`: Get consumed licenses for an enterprise.

#### Organization Custom Properties
- `create_org_custom_property`: Create a new custom property definition in an organization.
- `get_org_custom_properties`: Get all custom property definitions for an organization.
- `org_custom_property_values`: Get custom property values for all repos in an organization.
- `remove_org_custom_property`: Remove a custom property definition from an organization.
- `update_org_custom_property`: Update an existing custom property definition in an organization.

#### Organization Custom Roles
- `create_org_custom_role`: Create a custom repository role in an organization.
- `delete_org_custom_role`: Delete a custom repository role from an organization.
- `get_org_custom_role`: Get a single custom repository role from an organization.
- `update_org_custom_role`: Update a custom repository role in an organization.

#### Organization Security Managers
- `add_org_security_manager`: Add a team as a security manager for an organization.
- `remove_org_security_manager`: Remove a team as a security manager from an organization.

#### Organization Interaction Limits
- `get_org_interaction_limits`: Get interaction limits for an organization.
- `remove_org_interaction_limits`: Remove interaction limits for an organization.
- `set_org_interaction_limits`: Set interaction limits for an organization.

#### Organization Secrets & Variables
- `delete_org_secret`: Delete an organization-level secret.
- `delete_org_variable`: Delete an organization-level variable.
- `list_org_variables`: List organization-level variables.
- `set_org_secret`: Create or update an organization-level secret.
- `set_org_variable`: Create or update an organization-level variable.

#### Actions / Permissions & Required Workflows
- `get_allowed_actions`: Get the allowed actions for an organization or repository.
- `get_org_actions_permissions`: Get the Actions permissions for an organization.
- `list_org_required_workflows`: List all required workflows in an organization.
- `set_allowed_actions`: Set the allowed actions for an organization or repository.
- `set_org_actions_permissions`: Set the Actions permissions for an organization.

#### GitHub Pages
- `get_pages_info`: Get GitHub Pages site information for a repository.
- `list_pages_builds`: List GitHub Pages builds for a repository.
- `request_pages_build`: Request a GitHub Pages build for a repository.

#### Utilities
- `community_profile`: Get the community health metrics for a repository.
- `get_code_frequency`: Get code frequency (weekly additions/deletions).
- `get_contributor_stats`: Get contributor statistics.
- `get_emojis`: Get GitHub emoji URLs and codes.
- `get_feeds`: Get GitHub feeds available to the authenticated user.
- `get_gitignore_template`: Get a specific .gitignore template.
- `get_license`: Get a specific open source license template.
- `get_meta`: Get GitHub API meta info (IP ranges, SSH keys, etc.).
- `get_octocat`: Get a random Zen saying or Octocat ASCII art.
- `get_participation_stats`: Get participation stats for a repository.
- `get_punch_card`: Get the punch card for a repository.
- `get_rate_limit_details`: Get detailed rate limit status.
- `get_root`: Get GitHub API root endpoint info.
- `get_weekly_commit_activity`: Get weekly commit activity for a repository.
- `get_zen`: Get a random Zen of GitHub design philosophy.
- `list_codes_of_conduct`: List all codes of conduct.
- `list_gitignore_templates`: List all .gitignore templates.
- `list_licenses`: List all available open source license templates.
- `list_stargazers`: List users who have starred a repository.
- `list_tools`: List all available tools in the GitHub Issues Manager with descriptions.
- `list_watchers`: List users watching a repository.
- `rate_limit`: Check GitHub API rate limit status.
- `render_markdown`: Render GitHub Flavored Markdown text to HTML.
- `repo_traffic`: Get repository traffic data (clones and views).

---

## License

MIT License — see `LICENSE` for details.
