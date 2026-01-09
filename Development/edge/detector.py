"""
Face and Eye Detection Module
Uses MediaPipe Face Mesh for robust face and eye landmark detection
"""

import cv2
import numpy as np

# Import MediaPipe solutions
#
# IMPORTANT:
# - `mp.solutions` exists, but `import mediapipe.solutions` often DOES NOT.
# - So we only use either `mp.solutions...` or `mediapipe.python.solutions...`.
try:
    import mediapipe as mp
except Exception as e:
    raise ImportError(
        f"Failed to import mediapipe: {e}\n"
        "Fix: pip install --upgrade mediapipe\n"
        "If you previously installed TensorFlow, uninstall it (it can cause protobuf conflicts):\n"
        "  pip uninstall -y tensorflow tensorflow-cpu tensorflow-hub"
    )

try:
    # Preferred (works on MediaPipe 0.8+)
    mp_face_mesh = mp.solutions.face_mesh
    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles
except AttributeError:
    # Fallback (sometimes needed depending on installation)
    from mediapipe.python.solutions import face_mesh as mp_face_mesh
    from mediapipe.python.solutions import drawing_utils as mp_drawing
    from mediapipe.python.solutions import drawing_styles as mp_drawing_styles


class FaceDetector:
    """Detects face and extracts eye landmarks using MediaPipe Face Mesh"""
    
    # MediaPipe Face Mesh landmark indices for eyes
    # 6 points for EAR calculation in the order:
    # p1 (outer corner), p2 (upper), p3 (upper), p4 (inner corner), p5 (lower), p6 (lower)
    #
    # These are widely used stable indices for MediaPipe FaceMesh.
    # Left eye (subject's left): 33-133 are corners.
    LEFT_EYE_INDICES = [33, 160, 158, 133, 153, 144]
    # Right eye (subject's right): 362-263 are corners.
    RIGHT_EYE_INDICES = [362, 385, 387, 263, 373, 380]
    
    def __init__(self):
        """Initialize MediaPipe Face Mesh detector"""
        self.face_mesh = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,  # Enables iris landmarks for better accuracy
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_drawing = mp_drawing
        self.mp_drawing_styles = mp_drawing_styles
    
    def detect(self, frame):
        """
        Detect face and extract landmarks from frame
        
        Args:
            frame: BGR image frame from webcam
            
        Returns:
            face_landmarks: MediaPipe face landmarks object or None if no face detected
        """
        # Convert BGR to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb_frame)
        
        if results.multi_face_landmarks:
            return results.multi_face_landmarks[0]
        return None
    
    def get_eye_landmarks(self, face_landmarks, frame_shape):
        """
        Extract eye landmark coordinates from face landmarks
        
        Args:
            face_landmarks: MediaPipe face landmarks object
            frame_shape: Tuple of (height, width) of the frame
            
        Returns:
            left_eye: List of (x, y) coordinates for left eye
            right_eye: List of (x, y) coordinates for right eye
        """
        h, w = frame_shape[:2]
        
        left_eye = []
        right_eye = []
        
        if face_landmarks:
            # Extract left eye landmarks
            for idx in self.LEFT_EYE_INDICES:
                landmark = face_landmarks.landmark[idx]
                x = int(landmark.x * w)
                y = int(landmark.y * h)
                left_eye.append((x, y))
            
            # Extract right eye landmarks
            for idx in self.RIGHT_EYE_INDICES:
                landmark = face_landmarks.landmark[idx]
                x = int(landmark.x * w)
                y = int(landmark.y * h)
                right_eye.append((x, y))
        
        return left_eye, right_eye
    
    def draw_landmarks(self, frame, face_landmarks):
        """
        Draw face mesh landmarks on frame for visualization
        
        Args:
            frame: BGR image frame
            face_landmarks: MediaPipe face landmarks object
            
        Returns:
            frame: Frame with landmarks drawn
        """
        if face_landmarks:
            self.mp_drawing.draw_landmarks(
                frame,
                face_landmarks,
                mp_face_mesh.FACEMESH_CONTOURS,
                None,
                self.mp_drawing_styles.get_default_face_mesh_contours_style()
            )
        return frame

