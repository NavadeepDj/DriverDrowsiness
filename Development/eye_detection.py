import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision
import time
import numpy as np
import os
import urllib.request

# =========================
# Download model if not present
# =========================
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

# Head pose thresholds (in degrees) - adjusted for the geometric calculation method
PITCH_THRESHOLD = 50      # Head nodding forward
YAW_THRESHOLD = 40        # Head turning left/right
ROLL_THRESHOLD = 35       # Head tilting

# =========================
# Helper functions
# =========================
def eye_aspect_ratio(eye):
    """Calculate the Eye Aspect Ratio."""
    A = np.linalg.norm(eye[1] - eye[5])
    B = np.linalg.norm(eye[2] - eye[4])
    C = np.linalg.norm(eye[0] - eye[3])
    return (A + B) / (2.0 * C) if C != 0 else 0

def get_head_pose(face_landmarks, img_w, img_h):
    """Calculate head pose (pitch, yaw, roll) from face landmarks using simple geometry."""
    
    # Get key landmark positions
    nose = np.array([face_landmarks[NOSE_TIP].x * img_w, face_landmarks[NOSE_TIP].y * img_h])
    chin = np.array([face_landmarks[CHIN].x * img_w, face_landmarks[CHIN].y * img_h])
    left_eye = np.array([face_landmarks[LEFT_EYE_CORNER].x * img_w, face_landmarks[LEFT_EYE_CORNER].y * img_h])
    right_eye = np.array([face_landmarks[RIGHT_EYE_CORNER].x * img_w, face_landmarks[RIGHT_EYE_CORNER].y * img_h])
    left_mouth = np.array([face_landmarks[LEFT_MOUTH].x * img_w, face_landmarks[LEFT_MOUTH].y * img_h])
    right_mouth = np.array([face_landmarks[RIGHT_MOUTH].x * img_w, face_landmarks[RIGHT_MOUTH].y * img_h])
    
    # Calculate eye center
    eye_center = (left_eye + right_eye) / 2
    
    # Calculate mouth center
    mouth_center = (left_mouth + right_mouth) / 2
    
    # Pitch: vertical distance between eyes and mouth
    # When looking straight: mouth is below eyes (positive value)
    # When looking down: mouth appears closer to eyes
    vertical_dist = mouth_center[1] - eye_center[1]
    face_height = np.linalg.norm(chin - eye_center)
    pitch = (vertical_dist / face_height - 0.5) * 100  # Normalized pitch
    
    # Yaw: left-right head turn based on nose position relative to eye center
    nose_offset = nose[0] - eye_center[0]
    eye_width = np.linalg.norm(right_eye - left_eye)
    yaw = (nose_offset / eye_width) * 60
    
    # Roll: head tilt based on eye line angle
    eye_diff = right_eye - left_eye
    roll = np.degrees(np.arctan2(eye_diff[1], eye_diff[0]))
    
    # Normalize roll to be close to 0 when head is upright
    if roll > 90:
        roll = roll - 180
    elif roll < -90:
        roll = roll + 180
    
    return pitch, yaw, roll, None, None

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

print("Driver Drowsiness Detection Started... Press 'q' to quit.")
print(f"EYE_AR_THRESHOLD: {EYE_AR_THRESHOLD}")
print(f"DROWSY_THRESHOLD: {DROWSY_THRESHOLD} seconds")
print(f"EMERGENCY_THRESHOLD: {EMERGENCY_THRESHOLD} seconds")
print(f"HEAD POSE THRESHOLDS - Pitch: {PITCH_THRESHOLD}°, Yaw: {YAW_THRESHOLD}°, Roll: {ROLL_THRESHOLD}°")
print("-" * 60)

# =========================
# Main Loop
# =========================
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        frame = cv2.flip(frame, 1)
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

            # Draw eye contours
            cv2.polylines(frame, [left_eye], True, (255, 0, 0), 1)
            cv2.polylines(frame, [right_eye], True, (255, 0, 0), 1)

            # Calculate EAR
            ear = (eye_aspect_ratio(left_eye) + eye_aspect_ratio(right_eye)) / 2
            ear_history.append(ear)
            if len(ear_history) > 5:
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
                elif elapsed >= DROWSY_THRESHOLD:
                    status = "DROWSY"
                    color = (0, 165, 255)
                    if status != previous_status and debug_mode:
                        print(f"[WARNING] DROWSY! Eyes closed for {elapsed:.2f}s (threshold: {DROWSY_THRESHOLD}s)")
                        print(f"          EAR: {smooth_ear:.3f}")
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
            if debug_mode:
                print("[DEBUG] No face detected!")

        # Display status
        cv2.putText(frame, f"Status: {status}{head_pose_warning}", (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)

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




