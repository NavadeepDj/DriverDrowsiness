import cv2
import mediapipe as mp
import math
import time

# -------------------------------
# Configuration (TUNABLE)
# -------------------------------
EAR_THRESHOLD = 0.20            # Eye closed threshold
BLINK_MAX_TIME = 0.4            # seconds
DROWSY_EYE_TIME = 1.5           # seconds

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

eye_closed_start = None
blink_count = 0
drowsy_eye = False

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

    # FPS (smoothed)
    now = time.time()
    fps = 0.9 * fps + 0.1 * (1 / (now - prev_time))
    prev_time = now

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

        # EAR calculation
        vertical = dist(p3, p4) + dist(p5, p6)
        horizontal = 2 * dist(p1, p2)
        ear = vertical / horizontal if horizontal != 0 else 0

        # -------------------------------
        # Eye state logic
        # -------------------------------
        if ear < EAR_THRESHOLD:
            if eye_closed_start is None:
                eye_closed_start = time.time()
            else:
                duration = time.time() - eye_closed_start
                if duration > DROWSY_EYE_TIME:
                    drowsy_eye = True
        else:
            if eye_closed_start is not None:
                duration = time.time() - eye_closed_start
                if duration < BLINK_MAX_TIME:
                    blink_count += 1
            eye_closed_start = None
            drowsy_eye = False

        # -------------------------------
        # Debug overlay
        # -------------------------------
        cv2.putText(frame, f"EAR: {ear:.2f}", (30, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.putText(frame, f"Blinks: {blink_count}", (30, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        cv2.putText(frame, f"FPS: {int(fps)}", (30, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        if drowsy_eye:
            cv2.putText(frame, "EYES CLOSED - DROWSY", (30, 130),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 3)

    cv2.imshow("EAR & Blink Detection", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
