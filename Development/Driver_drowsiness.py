import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision
import time
import numpy as np
import os
import urllib.request
import winsound
import math
from threading import Thread
model_path = "face_landmarker.task"
if not os.path.exists(model_path):
    print("Downloading face landmarker model...")
    try:
        urllib.request.urlretrieve(
            "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
            model_path
        )
        print("Model downloaded!")
    except Exception as e:
        print(f"Error downloading model: {e}")
        exit(1)

# =========================
# Initialize Face Landmarker in IMAGE mode
# =========================
base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
options = vision.FaceLandmarkerOptions(
    base_options=base_options,
    running_mode=vision.RunningMode.IMAGE,
    num_faces=1
)
landmarker = vision.FaceLandmarker.create_from_options(options)

# =========================
# Constants
# =========================
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# Head pose key points
NOSE_TIP = 1
CHIN = 152
LEFT_EYE_CORNER = 33
RIGHT_EYE_CORNER = 263
LEFT_MOUTH = 61
RIGHT_MOUTH = 291

DROWSY_THRESHOLD = 2      # seconds
EMERGENCY_THRESHOLD = 5   # seconds
EYE_AR_THRESHOLD = 0.25   # EAR threshold

# Head pose thresholds (in degrees)
PITCH_THRESHOLD = 40      # Head nodding forward
YAW_THRESHOLD = 35        # Head turning left/right
ROLL_THRESHOLD = 30       # Head tilting

# Head pose smoothing
POSE_SMOOTHING_ALPHA = 0.25
pose_state = {"initialized": False, "pitch": 0.0, "yaw": 0.0, "roll": 0.0}

# =========================
# Helper functions
# =========================
def eye_aspect_ratio(eye):
    """Calculate the Eye Aspect Ratio."""
    A = np.linalg.norm(eye[1] - eye[5])
    B = np.linalg.norm(eye[2] - eye[4])
    C = np.linalg.norm(eye[0] - eye[3])
    return (A + B) / (2.0 * C) if C != 0 else 0

def rotationMatrixToEulerAngles(R):
    """Convert rotation matrix to yaw, pitch, roll in degrees (normalized)."""
    sy = math.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])
    singular = sy < 1e-6

    if not singular:
        x = math.atan2(R[2, 1], R[2, 2])  # pitch
        y = math.atan2(-R[2, 0], sy)       # yaw
        z = math.atan2(R[1, 0], R[0, 0])   # roll
    else:
        x = math.atan2(-R[1, 2], R[1, 1])
        y = math.atan2(-R[2, 0], sy)
        z = 0

    yaw, pitch, roll = map(math.degrees, [y, -x, z])
    yaw = (yaw + 180) % 360 - 180
    pitch = (pitch) % 360 - 180
    roll = (roll + 180) % 360 - 180
    return yaw, pitch, roll

def get_head_pose(face_landmarks, img_w, img_h):
    """Estimate head pose using solvePnP for stable pitch/yaw/roll angles."""
    global pose_state

    # 2D image points from MediaPipe landmarks (pixel space)
    image_points = np.array([
        (face_landmarks[NOSE_TIP].x * img_w, face_landmarks[NOSE_TIP].y * img_h),     # Nose tip
        (face_landmarks[CHIN].x * img_w, face_landmarks[CHIN].y * img_h),             # Chin
        (face_landmarks[LEFT_EYE_CORNER].x * img_w, face_landmarks[LEFT_EYE_CORNER].y * img_h),   # Left eye corner
        (face_landmarks[RIGHT_EYE_CORNER].x * img_w, face_landmarks[RIGHT_EYE_CORNER].y * img_h), # Right eye corner
        (face_landmarks[LEFT_MOUTH].x * img_w, face_landmarks[LEFT_MOUTH].y * img_h), # Left mouth corner
        (face_landmarks[RIGHT_MOUTH].x * img_w, face_landmarks[RIGHT_MOUTH].y * img_h) # Right mouth corner
    ], dtype="double")

    # Approximate 3D model points of a generic head (in mm)
    model_points = np.array([
        (0.0, 0.0, 0.0),           # Nose tip
        (0.0, -330.0, -65.0),      # Chin
        (-225.0, 170.0, -135.0),   # Left eye corner
        (225.0, 170.0, -135.0),    # Right eye corner
        (-150.0, -150.0, -125.0),  # Left mouth corner
        (150.0, -150.0, -125.0)    # Right mouth corner
    ], dtype="double")

    focal_length = img_w
    center = (img_w / 2, img_h / 2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1]
    ], dtype="double")

    dist_coeffs = np.zeros((4, 1))

    success, rotation_vector, translation_vector = cv2.solvePnP(
        model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
    )

    if not success:
        return 0.0, 0.0, 0.0, None, None

    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    yaw_angle, pitch_angle, roll_angle = rotationMatrixToEulerAngles(rotation_matrix)
    pitch, yaw, roll = pitch_angle, yaw_angle, roll_angle

    # Smooth angles to reduce jitter
    if not pose_state["initialized"]:
        pose_state = {"initialized": True, "pitch": pitch, "yaw": yaw, "roll": roll}
    else:
        pose_state["pitch"] = POSE_SMOOTHING_ALPHA * pitch + (1 - POSE_SMOOTHING_ALPHA) * pose_state["pitch"]
        pose_state["yaw"] = POSE_SMOOTHING_ALPHA * yaw + (1 - POSE_SMOOTHING_ALPHA) * pose_state["yaw"]
        pose_state["roll"] = POSE_SMOOTHING_ALPHA * roll + (1 - POSE_SMOOTHING_ALPHA) * pose_state["roll"]

    return pose_state["pitch"], pose_state["yaw"], pose_state["roll"], rotation_vector, translation_vector

# =========================
# Initialize Webcam
# =========================
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Cannot open webcam! Check camera index or permissions.")
    exit(1)

start_time = None
ear_history = []
previous_status = "ALERT"
debug_mode = True  # Set to False to disable debug output
head_pose_alert_start = None  # Track head pose alerts

# Statistics tracking
stats = {
    'total_drowsy_events': 0,
    'total_drowsy_time': 0,
    'total_emergency_events': 0,
    'last_drowsy_time': 0,
    'blink_count': 0,
    'last_ear': 0
}
last_status = "ALERT"

def play_alarm():
    """Play alarm sound in background thread - siren pattern"""
    try:
        # Siren-like sound with alternating frequencies
        for _ in range(3):
            winsound.Beep(800, 150)   # Low tone
            winsound.Beep(1200, 150)  # High tone
    except:
        pass

print("Driver Drowsiness Detection Started... Press 'q' to quit.")
print(f"EYE_AR_THRESHOLD: {EYE_AR_THRESHOLD}")
print(f"DROWSY_THRESHOLD: {DROWSY_THRESHOLD} seconds")
print(f"EMERGENCY_THRESHOLD: {EMERGENCY_THRESHOLD} seconds")
print(f"HEAD POSE THRESHOLDS - Pitch: {PITCH_THRESHOLD}°, Yaw: {YAW_THRESHOLD}°, Roll: {ROLL_THRESHOLD}°")
print("-" * 60)

# =========================
# Main Loop
# =========================
frame_count = 0
start_time_fps = time.time()
fps = 0

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        frame_count += 1
        
        # Calculate FPS
        if frame_count % 30 == 0:
            elapsed = time.time() - start_time_fps
            fps = 30 / elapsed
            start_time_fps = time.time()
        h, w, _ = frame.shape

        # Convert to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        # Detect face landmarks
        results = landmarker.detect(mp_image)

        status = "ALERT"
        color = (0, 255, 0)
        head_pose_warning = ""

        if results.face_landmarks and len(results.face_landmarks) > 0:
            # Get the list of landmarks for the first detected face
            face_landmarks_list = results.face_landmarks[0]
            
            # Calculate head pose
            pitch, yaw, roll, rotation_vec, translation_vec = get_head_pose(face_landmarks_list, w, h)
            
            # Check for abnormal head pose
            head_pose_abnormal = False
            pose_warnings = []
            
            if abs(pitch) > PITCH_THRESHOLD:
                pose_warnings.append(f"Nodding ({pitch:.1f}°)")
                head_pose_abnormal = True
            if abs(yaw) > YAW_THRESHOLD:
                pose_warnings.append(f"Turning ({yaw:.1f}°)")
                head_pose_abnormal = True
            if abs(roll) > ROLL_THRESHOLD:
                pose_warnings.append(f"Tilting ({roll:.1f}°)")
                head_pose_abnormal = True
            
            if pose_warnings:
                head_pose_warning = " | " + ", ".join(pose_warnings)
                if head_pose_alert_start is None:
                    head_pose_alert_start = time.time()
                    if debug_mode:
                        print(f"[HEAD POSE] Abnormal detected: {', '.join(pose_warnings)}")
            else:
                if head_pose_alert_start is not None and debug_mode:
                    duration = time.time() - head_pose_alert_start
                    print(f"[HEAD POSE] Normal position restored after {duration:.2f}s")
                head_pose_alert_start = None
            
            left_eye = []
            right_eye = []

            # Extract coordinates for left eye
            for idx in LEFT_EYE:
                lm = face_landmarks_list[idx]
                left_eye.append([int(lm.x * w), int(lm.y * h)])

            # Extract coordinates for right eye
            for idx in RIGHT_EYE:
                lm = face_landmarks_list[idx]
                right_eye.append([int(lm.x * w), int(lm.y * h)])

            left_eye = np.array(left_eye)
            right_eye = np.array(right_eye)

            # Draw only eye contours (keep overlays minimal elsewhere)
            cv2.polylines(frame, [left_eye], True, (255, 0, 0), 2)
            cv2.polylines(frame, [right_eye], True, (255, 0, 0), 2)

            # Calculate EAR
            ear = (eye_aspect_ratio(left_eye) + eye_aspect_ratio(right_eye)) / 2
            stats['last_ear'] = ear  # Track for display
            ear_history.append(ear)
            if len(ear_history) > 10:  # Keep only last 10 frames for smoothing
                ear_history.pop(0)
            smooth_ear = np.mean(ear_history)

            # Check drowsiness
            if smooth_ear < EYE_AR_THRESHOLD:
                if start_time is None:
                    start_time = time.time()
                    if debug_mode:
                        print(f"[DEBUG] Eyes CLOSED detected! EAR: {smooth_ear:.3f} (threshold: {EYE_AR_THRESHOLD})")
                
                elapsed = time.time() - start_time

                if elapsed >= EMERGENCY_THRESHOLD:
                    status = "EMERGENCY"
                    color = (0, 0, 255)
                    if status != previous_status and debug_mode:
                        print(f"[ALERT] EMERGENCY! Eyes closed for {elapsed:.2f}s (threshold: {EMERGENCY_THRESHOLD}s)")
                        print(f"        EAR: {smooth_ear:.3f}")
                    # Play alarm
                    if status != previous_status:
                        Thread(target=play_alarm, daemon=True).start()
                    stats['total_emergency_events'] += 1
                elif elapsed >= DROWSY_THRESHOLD:
                    status = "DROWSY"
                    color = (0, 165, 255)
                    if status != previous_status and debug_mode:
                        print(f"[WARNING] DROWSY! Eyes closed for {elapsed:.2f}s (threshold: {DROWSY_THRESHOLD}s)")
                        print(f"          EAR: {smooth_ear:.3f}")
                    # Play alarm
                    if status != previous_status:
                        Thread(target=play_alarm, daemon=True).start()
                    stats['total_drowsy_events'] += 1
                    stats['total_drowsy_time'] = elapsed
                elif debug_mode and int(elapsed) % 1 == 0 and int(elapsed) > 0:
                    # Print every 1 second while eyes are closed
                    print(f"[DEBUG] Eyes closed for {elapsed:.2f}s... EAR: {smooth_ear:.3f}")
            else:
                if start_time is not None and debug_mode:
                    elapsed = time.time() - start_time
                    print(f"[DEBUG] Eyes OPENED! Total closure duration: {elapsed:.2f}s")
                start_time = None
            
            # Upgrade status if head pose is abnormal
            if head_pose_abnormal and status == "ALERT":
                status = "DISTRACTED"
                color = (0, 200, 255)
            
            # Display head pose info
            cv2.putText(frame, f"Pitch: {pitch:.1f}", (w - 200, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, f"Yaw: {yaw:.1f}", (w - 200, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(frame, f"Roll: {roll:.1f}", (w - 200, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
        else:
            status = "NO FACE DETECTED"
            color = (0, 0, 255)  # Red color for warning
            if debug_mode:
                print("[DEBUG] No face detected!")

        # Display status
        cv2.putText(frame, f"Status: {status}{head_pose_warning}", (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

        # Display FPS
        cv2.putText(frame, f"FPS: {fps:.1f}", (30, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Display EAR value
        if results.face_landmarks:
            cv2.putText(frame, f"EAR: {stats['last_ear']:.3f}", (30, 140),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imshow("Driver Drowsiness Detection", frame)
        # Track status changes
        if status != previous_status and debug_mode:
            print(f"[STATUS CHANGE] {previous_status} -> {status}")
        previous_status = status

        # Press 'q' to quit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("[DEBUG] Quit requested by user")
            break

except KeyboardInterrupt:
    print("Interrupted by user")
finally:
    cap.release()
    cv2.destroyAllWindows()
    print("Program ended.")
