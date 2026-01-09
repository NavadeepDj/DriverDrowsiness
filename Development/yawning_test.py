import cv2
import mediapipe as mp
import numpy as np
import time
import math

# -------------------------------
# Configuration (TUNABLE)
# -------------------------------
LAR_THRESHOLD = 0.6          # Mouth openness threshold
YAWN_TIME_THRESHOLD = 1.5    # Seconds (continuous)

# -------------------------------
# MediaPipe Face Mesh setup
# -------------------------------
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)

cap = cv2.VideoCapture(0)

# -------------------------------
# Helper: Euclidean distance
# -------------------------------
def distance(p1, p2):
    return math.dist(p1, p2)

# -------------------------------
# Yawning state variables
# -------------------------------
mouth_open_start_time = None
yawning_detected = False

prev_time = time.time()
fps = 0

# -------------------------------
# Main loop
# -------------------------------
while True:
    ret, frame = cap.read()
    if not ret:
        break

    h, w = frame.shape[:2]

    # FPS calculation (smoothed)
    current_time = time.time()
    fps = 0.9 * fps + 0.1 * (1 / (current_time - prev_time))
    prev_time = current_time

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb)

    if results.multi_face_landmarks:
        face_landmarks = results.multi_face_landmarks[0]

        # -------------------------------
        # Lip landmarks (MediaPipe)
        # -------------------------------
        upper_lip = face_landmarks.landmark[13]
        lower_lip = face_landmarks.landmark[14]
        left_mouth = face_landmarks.landmark[61]
        right_mouth = face_landmarks.landmark[291]

        # Convert to pixel coordinates
        upper = (int(upper_lip.x * w), int(upper_lip.y * h))
        lower = (int(lower_lip.x * w), int(lower_lip.y * h))
        left = (int(left_mouth.x * w), int(left_mouth.y * h))
        right = (int(right_mouth.x * w), int(right_mouth.y * h))

        # -------------------------------
        # Lip Aspect Ratio (LAR)
        # -------------------------------
        vertical_dist = distance(upper, lower)
        horizontal_dist = distance(left, right)

        lar = vertical_dist / horizontal_dist if horizontal_dist != 0 else 0

        # -------------------------------
        # Yawning detection logic
        # -------------------------------
        if lar > LAR_THRESHOLD:
            if mouth_open_start_time is None:
                mouth_open_start_time = time.time()
            elif time.time() - mouth_open_start_time > YAWN_TIME_THRESHOLD:
                yawning_detected = True
        else:
            mouth_open_start_time = None
            yawning_detected = False

        # -------------------------------
        # Debug overlay
        # -------------------------------
        cv2.putText(frame, f"LAR: {lar:.2f}", (30, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.putText(frame, f"FPS: {int(fps)}", (30, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        if yawning_detected:
            cv2.putText(frame, "YAWNING DETECTED", (30, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 3)

        # Draw lip points (optional visual aid)
        cv2.circle(frame, upper, 3, (255, 0, 0), -1)
        cv2.circle(frame, lower, 3, (255, 0, 0), -1)
        cv2.circle(frame, left, 3, (255, 0, 0), -1)
        cv2.circle(frame, right, 3, (255, 0, 0), -1)

    cv2.imshow("Yawning Detection", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
