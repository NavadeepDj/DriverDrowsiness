# Driver Drowsiness Detection and Emergency Warning System

A real-time driver drowsiness detection system that monitors driver alertness using computer vision and AI, with progressive alerting. **Runs completely offline** (no Firebase, no cloud dashboard) on Windows or Raspberry Pi, with local JSONL logging.

## Features

- **Real-time Face & Eye Detection**: Uses MediaPipe Face Mesh for robust detection at ~30 FPS
- **Drowsiness Metrics**: Calculates Eye Aspect Ratio (EAR), PERCLOS, Blink Rate, Blink Duration, and Microsleep events
- **Intelligent Scoring**: Research-inspired multi-metric drowsiness scoring (0–100 scale)
- **Two-Level Alert System**:
  - Level 1: Internal audio/visual warning when drowsiness is detected
  - Level 2: Escalated emergency-style alert if drowsiness persists
- **Local Logging Only**: All alerts and session data saved to local files under `edge/logs/`
- **No Internet Required**: Fully functional without any cloud connectivity or login/signup

## System Requirements

### Hardware
- Raspberry Pi 5 (recommended), Raspberry Pi 4, or a Windows PC
- USB or built‑in webcam
- Optional: Display for visual overlay

### Software
- Python 3.10–3.11
- OpenCV, MediaPipe, NumPy, Pygame (all pinned in `requirements.txt`)

## Installation

### 1. Create and activate a virtual environment (recommended)

```bash
cd hackefx2.0
python -m venv venv
```

On Windows:

```powershell
.\venv\Scripts\activate
```

On Linux/Raspberry Pi:

```bash
source venv/bin/activate
```

### 2. Install Python packages (exact versions)

From the project root:

```bash
.\venv\Scripts\python.exe -m pip install -r requirements.txt    # Windows
# or
python -m pip install -r requirements.txt                      # Linux / Pi
```

The root `requirements.txt` contains **exact pinned versions** (generated via `pip freeze`) so others can reproduce your working environment.

## Usage

### Running the Detection System (Windows)

From the project root:

```powershell
cd edge
..\venv\Scripts\python.exe main.py
```

Or use the helper script:

```powershell
cd edge
.\run.ps1
```

### Running on Raspberry Pi / Linux

```bash
cd edge
python main.py
```

**Controls**:
- `q` — Quit the application
- `r` — Manually reset alerts and timers

### Viewing Logs (offline)

All alerts and session data are saved locally in the `edge/logs/` directory:
- `alerts.jsonl` — All Level 1 / Level 2 alert events (timestamped JSON lines)
- `sessions.jsonl` — Driving session summaries (duration, avg/max score, number of alerts)

You can open these files with any text editor or JSON viewer.

## Configuration

Edit `edge/config.py` to adjust thresholds and settings. Key values:

- `EAR_CLOSED_THRESHOLD`: EAR value treated as “eyes closed” (default: `0.15`)
- `EYE_CLOSED_DROWSY_SECONDS`: Continuous closure duration to flag drowsiness (default: `0.7s`)
- `PERCLOS_WINDOW_SIZE`: Time window for PERCLOS calculation (default: `60s`)
- `PERCLOS_ALERT_MAX`: PERCLOS upper bound for clearly alert state (default: `10%`)
- `PERCLOS_DROWSY_MIN` / `PERCLOS_HIGH_DROWSY_MIN`: Drowsy PERCLOS ranges (default: `30%` / `40%`)
- `BLINK_RATE_WINDOW`: Window for blink rate (default: `60s`)
- `BLINK_RATE_ALERT_MAX` / `BLINK_RATE_DROWSY_MIN`: Normal vs. high blink rate
- `BLINK_DURATION_DROWSY_MIN` / `BLINK_DURATION_MICROSLEEP_MIN`: Long blink & microsleep thresholds
- `SCORE_ALERT` / `SCORE_SLIGHTLY_DROWSY` / `SCORE_DROWSY` / `SCORE_VERY_DROWSY`: Score → state mapping
- `LEVEL1_SCORE_THRESHOLD`: Score threshold for Level 1 alert (default: `60`)
- `LEVEL1_DURATION_SECONDS` / `LEVEL2_DURATION_SECONDS`: Time above threshold for Level 1 & Level 2
- `CAMERA_INDEX`: Which camera to open (0, 1, …)
- `CAMERA_BACKEND`: `"AUTO"`, `"DSHOW"`, or `"MSMF"` (Windows capture backend)

## System Architecture

```
┌─────────────────┐
│   Webcam        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Face Detection │  (MediaPipe Face Mesh)
└────────┬────────┘
         │
         ▼
┌────────────────────────────┐
│ Metrics Calculation        │
│  - EAR                     │
│  - PERCLOS                 │
│  - Blink rate & duration   │
│  - Microsleep count        │
└────────┬───────────────────┘
         │
         ▼
┌─────────────────┐
│ Drowsiness      │
│ Scoring Engine  │  (0–100)
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌──────────┐
│ Alerts │ │ Local    │
│(Audio/ │ │ Logging  │
│Visual) │ └──────────┘
└────────┘
```

## Drowsiness Metrics & Scoring (How it works)

### Eye Aspect Ratio (EAR)
- Uses 6 landmarks per eye from MediaPipe Face Mesh.
- Formula: EAR = (‖p2−p6‖ + ‖p3−p5‖) / (2 × ‖p1−p4‖)
- Typical values:
  - Open eyes: ~0.25–0.35
  - Closed eyes: < 0.15 (controlled by `EAR_CLOSED_THRESHOLD`)

### PERCLOS (Percentage of Eyelid Closure)
- Percentage of time eyes are “closed” (EAR below threshold) in the last 60 seconds.
- Used as the primary drowsiness indicator.
- Rough interpretation:
  - < 10% → clearly alert
  - 10–30% → getting drowsy
  - > 30–40% → strongly drowsy

### Blink Rate
- Blinks per minute over a 60s window.
- Higher than normal blink rate can indicate fatigue.
- Typical:
  - 10–20 blinks/min → normal
  - > 30 blinks/min → suspicious/fatigued

### Blink Duration
- Time eyes remain closed during each blink.
- Normal blinks: ~0.1–0.2s
- Long blinks (> 0.3s) contribute to the drowsiness score.

### Microsleep Events
- Closures lasting ≥ 0.5s are treated as microsleeps.
- Even a small number of microsleeps significantly increases the score.

### Scoring (0–100)
The `DrowsinessScorer` combines:
- PERCLOS (largest contribution)
- Blink rate
- Average blink duration
- Continuous closure duration
- Microsleep count
- Current EAR (small, instant contribution)

Score interpretation (defaults from `config.py`):
- 0–30 → `ALERT`
- 31–60 → `SLIGHTLY_DROWSY`
- 61–80 → `DROWSY`
- 81–100 → `VERY_DROWSY`

## Alert System (Offline)

### Level 1 Alert (Warning)
- Triggered when:
  - Drowsiness score ≥ `LEVEL1_SCORE_THRESHOLD` (default 60) for at least `LEVEL1_DURATION_SECONDS` (3s).
- Behavior:
  - Periodic audio beeps (Windows uses `winsound.Beep`, others use Pygame).
  - Visual warning overlay on the video.
  - Event appended to `edge/logs/alerts.jsonl`.

### Level 2 Alert (Emergency)
- Triggered if the Level 1 condition persists for `LEVEL2_DURATION_SECONDS` (default 10s) beyond Level 1.
- Behavior:
  - Stronger / continuous alert pattern.
  - Logged as a Level 2 event to `alerts.jsonl`.
  - Requires the driver to recover (score dropping back down) or manual reset (`r`).

## Troubleshooting

### Camera Not Detected or “Failed to capture frame”
- Make sure no other apps (Zoom, Teams, browser, camera app) are using the webcam.
- Try changing `CAMERA_INDEX` in `edge/config.py` (e.g., 0 → 1).
- On Windows, set `CAMERA_BACKEND = "DSHOW"` or `"MSMF"` in `edge/config.py`.
- The app will automatically retry several times and attempt to re-open the camera if frames fail.

### Low FPS
- Reduce `FRAME_WIDTH` and `FRAME_HEIGHT` in `edge/config.py`.
- Close other CPU-heavy applications.

### Audio Alerts Not Working
- On Windows: ensure system volume is on and not muted.
- On Linux/Pi: install ALSA utilities and test:

```bash
sudo apt install alsa-utils
aplay /usr/share/sounds/alsa/Front_Left.wav
```

## License

This project is provided as-is for educational and research purposes.

## Contributing

Feel free to submit issues and enhancement requests!


