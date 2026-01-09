import cv2
import mediapipe as mp
import math
import time
from collections import deque

# -------------------------------
# Configuration
# -------------------------------
EAR_THRESHOLD = 0.20
PERCLOS_WINDOW = 30.0  # seconds

# -------------------------------
# MediaPipe Face Mesh
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
# Helpers
# -------------------------------
def dist(p1, p2):
    return math.dist(p1, p2)

# Stores (timestamp, eye_closed_bool)
eye_history = deque()

eye_closed = False
eye_closed_start = None

# -------------------------------
# Main loop
# -------------------------------
while True:
    ret, frame = cap.read()
    if not ret:
        break

    h, w = frame.shape[:2]
    current_time = time.time()

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb)

    if results.multi_face_landmarks:
        lm = results.multi_face_landmarks[0].landmark

        # Left eye landmarks
        p1 = (lm[33].x * w, lm[33].y * h)
        p2 = (lm[133].x * w, lm[133].y * h)
        p3 = (lm[160].x * w, lm[160].y * h)
        p4 = (lm[144].x * w, lm[144].y * h)
        p5 = (lm[158].x * w, lm[158].y * h)
        p6 = (lm[153].x * w, lm[153].y * h)

        vertical = dist(p3, p4) + dist(p5, p6)
        horizontal = 2 * dist(p1, p2)
        ear = vertical / horizontal if horizontal != 0 else 0

        # -------------------------------
        # Eye open / close state
        # -------------------------------
        if ear < EAR_THRESHOLD:
            if not eye_closed:
                eye_closed = True
                eye_closed_start = current_time
        else:
            if eye_closed:
                eye_history.append((eye_closed_start, current_time))
            eye_closed = False
            eye_closed_start = None

        # -------------------------------
        # Maintain sliding window
        # -------------------------------
        while eye_history and eye_history[0][1] < current_time - PERCLOS_WINDOW:
            eye_history.popleft()

        # -------------------------------
        # Compute closed time in window
        # -------------------------------
        closed_time = sum(end - start for start, end in eye_history)

        # If currently closed, include ongoing closure
        if eye_closed and eye_closed_start is not None:
            closed_time += current_time - eye_closed_start

        perclos = closed_time / PERCLOS_WINDOW

        # -------------------------------
        # Debug overlay
        # -------------------------------
        cv2.putText(frame, f"EAR: {ear:.2f}", (30, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.putText(frame, f"PERCLOS: {perclos:.2f}", (30, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        if perclos > 0.30:
            cv2.putText(frame, "SEVERE DROWSINESS", (30, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 3)
        elif perclos > 0.15:
            cv2.putText(frame, "DROWSINESS WARNING", (30, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 165, 255), 3)

    cv2.imshow("PERCLOS Detection", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
