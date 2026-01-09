"""
Configuration file for drowsiness detection thresholds and settings
"""

# Eye Aspect Ratio (EAR) thresholds
# Typical EAR(open) ~ 0.25–0.35, EAR(closed) < 0.15 (varies per camera/face).
# We use two thresholds:
# - EAR_CLOSED_THRESHOLD: counts as "closed" for PERCLOS / blink duration
# - EAR_DROWSY_THRESHOLD: indicates strong drowsiness (very low EAR)
EAR_CLOSED_THRESHOLD = 0.15
EAR_DROWSY_THRESHOLD = 0.15

# Continuous closure durations (seconds)
EYE_CLOSED_DROWSY_SECONDS = 0.7      # EAR < threshold for >= 0.7s => drowsy
MICROSLEEP_SECONDS = 0.5             # closure >= 0.5s => microsleep event

# PERCLOS (Percentage of Eye Closure) thresholds
# PERCLOS = % time eyes are >=80% closed over window (commonly 60s)
PERCLOS_WINDOW_SIZE = 60  # seconds
PERCLOS_ALERT_MAX = 10.0
PERCLOS_DROWSY_MIN = 30.0
PERCLOS_HIGH_DROWSY_MIN = 40.0

# Blink thresholds (research-backed)
BLINK_RATE_WINDOW = 60  # seconds
BLINK_RATE_ALERT_MAX = 20.0
BLINK_RATE_DROWSY_MIN = 30.0

# Blink duration thresholds (seconds)
BLINK_DURATION_ALERT_MAX = 0.20      # 100–200ms alert range
BLINK_DURATION_DROWSY_MIN = 0.30     # 300–500ms drowsy range
BLINK_DURATION_MICROSLEEP_MIN = 0.50 # >500ms microsleep

# Blink detection debounce
BLINK_MIN_SECONDS = 0.08
BLINK_MAX_SECONDS = 0.80
BLINK_MIN_INTERVAL_SECONDS = 0.10

# Drowsiness score thresholds
SCORE_ALERT = 30  # Score below this is ALERT state
SCORE_SLIGHTLY_DROWSY = 60  # Score below this is SLIGHTLY_DROWSY
SCORE_DROWSY = 80  # Score below this is DROWSY
SCORE_VERY_DROWSY = 100  # Score above this is VERY_DROWSY

# Alert system thresholds
LEVEL1_SCORE_THRESHOLD = 60  # Score threshold to trigger Level 1 alert
LEVEL1_DURATION_SECONDS = 3  # Duration in seconds before Level 1 triggers
LEVEL2_DURATION_SECONDS = 10  # Duration in seconds before Level 2 triggers (after Level 1)

# Camera settings
CAMERA_INDEX = 0  # Default webcam index
TARGET_FPS = 30  # Target frames per second
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Camera backend (mainly for Windows reliability)
# Options: "AUTO", "DSHOW", "MSMF"
CAMERA_BACKEND = "AUTO"

# How many camera indices to probe if CAMERA_INDEX fails (0..N-1)
CAMERA_PROBE_COUNT = 4

# Local logging settings
LOG_UPDATE_INTERVAL = 1  # Update local logs every N seconds

