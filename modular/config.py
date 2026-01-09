"""
Configuration file for all drowsiness detection thresholds and settings
"""

# Eye Aspect Ratio (EAR) thresholds
EAR_CLOSED_THRESHOLD = 0.16
EAR_DROWSY_THRESHOLD = 0.16

# Lip Aspect Ratio (LAR) thresholds for yawn detection
LAR_THRESHOLD = 0.65                  # LAR > threshold => mouth open (yawning) - increased for accuracy
YAWN_DURATION_SECONDS = 2.0           # Mouth open for >= 2.0s => yawn event
LAR_SMOOTHING_WINDOW = 5              # Number of frames to average LAR for smoothing (reduces noise)
LAR_CONSECUTIVE_FRAMES = 3            # Require LAR > threshold for N consecutive frames before detecting yawn

# Continuous closure durations (seconds)
EYE_CLOSED_DROWSY_SECONDS = 0.6       # EAR < threshold for >= 0.6s => drowsy
MICROSLEEP_SECONDS = 0.45             # closure >= 0.45s => microsleep event

# PERCLOS configuration
PERCLOS_WINDOW_SIZE = 10              # seconds
PERCLOS_ALERT_MAX = 10.0
PERCLOS_DROWSY_MIN = 30.0
PERCLOS_HIGH_DROWSY_MIN = 40.0

# Blink thresholds
BLINK_RATE_WINDOW = 60                # seconds
BLINK_RATE_ALERT_MAX = 18.0
BLINK_RATE_DROWSY_MIN = 28.0

# Blink duration thresholds (seconds)
BLINK_DURATION_ALERT_MAX = 0.18       # 100–180ms alert range
BLINK_DURATION_DROWSY_MIN = 0.28      # 280–500ms drowsy range
BLINK_DURATION_MICROSLEEP_MIN = 0.48  # >480ms microsleep

# Blink detection debounce
BLINK_MIN_SECONDS = 0.08
BLINK_MAX_SECONDS = 0.80
BLINK_MIN_INTERVAL_SECONDS = 0.10

# Drowsiness score thresholds
SCORE_ALERT = 25
SCORE_SLIGHTLY_DROWSY = 55
SCORE_DROWSY = 80
SCORE_VERY_DROWSY = 100

# Camera settings
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
TARGET_FPS = 30

# Camera backend (mainly for Windows reliability)
# Options: "AUTO", "DSHOW", "MSMF"
CAMERA_BACKEND = "AUTO"

# How many camera indices to probe if CAMERA_INDEX fails (0..N-1)
CAMERA_PROBE_COUNT = 4

# Visualization settings
DRAW_FACE_MESH = True  # Set to True to draw full face mesh, False for eye contours only

# Two-Level Alert System Configuration
# Level 1: Triggers when drowsiness symptoms are detected (state-based)
# Level 2: Escalates only if Level 1 persists for specified duration

# Level 1 Alert: Triggered when driver state indicates drowsiness symptoms
# States that trigger Level 1: "SLIGHTLY_DROWSY", "DROWSY", "VERY_DROWSY", "INATTENTIVE"
LEVEL1_DURATION_SECONDS = 3  # Duration in seconds before Level 1 alert triggers

# Level 1 Alert: Yawn-based trigger (Research-backed thresholds)
# Based on driver monitoring research:
# - 0-1 yawns/30s: Normal/Alert (Low risk)
# - >2 yawns/30s: Unusual (Moderate risk) → Level 1 Alert
YAWN_ALERT_WINDOW_SECONDS = 30  # Rolling 30-second window for yawn frequency calculation
YAWN_ALERT_THRESHOLD = 2  # Minimum yawns in 30s to trigger Level 1 (>2 yawns/30s = unusual)

# Level 2 Alert: Escalates if Level 1 persists
LEVEL2_DURATION_SECONDS = 10  # Duration in seconds after Level 1 before Level 2 triggers

# Yawn-based Level 2 escalation: Only escalate if yawns are RECENT (not just in rolling window)
YAWN_RECENT_WINDOW_SECONDS = 20  # Check if yawns occurred in last 20 seconds for Level 2 escalation

# Level 1 Alert: Additional Independent Symptom Triggers
# Excessive Blink Rate trigger
BLINK_RATE_LEVEL1_THRESHOLD = 30.0  # Blinks per minute to trigger Level 1 (≥30 blinks/min = excessive)

# Microsleep event trigger (immediate, no delay)
MICROSLEEP_LEVEL1_TRIGGER = True  # Microsleep triggers Level 1 immediately

# PERCLOS-based trigger (independent of state)
PERCLOS_LEVEL1_MIN = 15.0  # Minimum PERCLOS to trigger Level 1 (≥15%)
PERCLOS_LEVEL1_MAX = 40.0  # Maximum PERCLOS for Level 1 trigger (≤40%, above goes to state-based)

# Level 2 Alert: Frequent Level 1 Alerts Escalation
# If Level 1 alerts are triggered too frequently (driver repeatedly becomes drowsy and recovers),
# this indicates persistent fatigue and should escalate to Level 2
LEVEL1_FREQUENCY_WINDOW_SECONDS = 300  # 5 minutes rolling window to track Level 1 frequency
LEVEL1_FREQUENCY_THRESHOLD = 3  # If ≥3 Level 1 alerts occur within the window, escalate to Level 2

