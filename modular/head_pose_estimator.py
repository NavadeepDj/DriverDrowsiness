"""
Head Pose Estimation Module
Estimates head pose (yaw, pitch, roll) and determines attentiveness
"""

import cv2
import numpy as np
import math
from collections import deque
from config import YAW_THRESHOLD, PITCH_THRESHOLD


def rotation_matrix_to_euler_angles(R):
    """
    Convert 3x3 rotation matrix to yaw, pitch, roll in degrees.
    
    Args:
        R: 3x3 rotation matrix
        
    Returns:
        Tuple of (yaw, pitch, roll) in degrees
    """
    sy = math.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])
    singular = sy < 1e-6
    
    if not singular:
        x = math.atan2(R[2, 1], R[2, 2])   # pitch
        y = math.atan2(-R[2, 0], sy)       # yaw
        z = math.atan2(R[1, 0], R[0, 0])   # roll
    else:
        x = math.atan2(-R[1, 2], R[1, 1])
        y = math.atan2(-R[2, 0], sy)
        z = 0.0
    
    yaw, pitch, roll = map(math.degrees, [y, -x, z])
    yaw = (yaw + 180.0) % 360.0 - 180.0
    pitch = pitch % 360.0 - 180.0
    roll = (roll + 180.0) % 360.0 - 180.0
    
    return yaw, pitch, roll


class HeadPoseEstimator:
    """
    Estimates head pose (yaw, pitch, roll) using MediaPipe landmarks.
    
    Uses solvePnP to estimate 3D head pose from 2D facial landmarks.
    """
    
    # MediaPipe Face Mesh landmark indices
    NOSE_TIP = 1
    CHIN = 152
    LEFT_EYE_OUTER = 33
    RIGHT_EYE_OUTER = 263
    MOUTH_LEFT = 61
    MOUTH_RIGHT = 291
    
    def __init__(self, smooth_window=5):
        """
        Initialize head pose estimator.
        
        Args:
            smooth_window: Number of frames to smooth angles over
        """
        self._angle_history = deque(maxlen=smooth_window)
    
    def estimate(self, face_landmarks, frame_shape):
        """
        Estimate head-pose (yaw, pitch, roll) and attentiveness flag.
        
        Args:
            face_landmarks: MediaPipe face landmarks object
            frame_shape: Shape of BGR frame (H, W, C)
            
        Returns:
            Tuple of (yaw, pitch, roll, looking)
            If estimation fails, returns (None, None, None, False)
        """
        if face_landmarks is None:
            return None, None, None, False
        
        h, w = frame_shape[:2]
        
        def lm2xy(i):
            """Convert landmark index to pixel coordinates."""
            lm = face_landmarks.landmark[i]
            return np.array([lm.x * w, lm.y * h], dtype=np.float64)
        
        # 2D image points (pixels)
        image_points = np.array([
            lm2xy(self.NOSE_TIP),
            lm2xy(self.CHIN),
            lm2xy(self.LEFT_EYE_OUTER),
            lm2xy(self.RIGHT_EYE_OUTER),
            lm2xy(self.MOUTH_LEFT),
            lm2xy(self.MOUTH_RIGHT),
        ], dtype=np.float64)
        
        # Generic 3D model points (in mm), matching the indices above
        model_points = np.array([
            [0.0, 0.0, 0.0],           # Nose tip
            [0.0, -63.6, -12.5],       # Chin
            [-43.3, 32.7, -26.0],      # Left eye outer
            [43.3, 32.7, -26.0],       # Right eye outer
            [-28.9, -28.9, -24.1],     # Mouth left
            [28.9, -28.9, -24.1],      # Mouth right
        ], dtype=np.float64)
        
        # Camera matrix
        focal_length = w
        center = (w / 2.0, h / 2.0)
        camera_matrix = np.array([
            [focal_length, 0.0, center[0]],
            [0.0, focal_length, center[1]],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)
        
        dist_coeffs = np.zeros((4, 1), dtype=np.float64)
        
        # Solve PnP to get rotation vector
        success, rvec, _ = cv2.solvePnP(
            model_points,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        
        if not success:
            return None, None, None, False
        
        # Convert rotation vector to rotation matrix
        R_mat, _ = cv2.Rodrigues(rvec)
        yaw, pitch, roll = rotation_matrix_to_euler_angles(R_mat)
        
        # Smooth angles over history
        self._angle_history.append((yaw, pitch, roll))
        yaw_s = float(np.mean([a[0] for a in self._angle_history]))
        pitch_s = float(np.mean([a[1] for a in self._angle_history]))
        roll_s = float(np.mean([a[2] for a in self._angle_history]))
        
        # Determine if driver is looking at road/camera
        yaw_abs = abs(yaw_s)
        pitch_mod = min(abs(pitch_s), abs(abs(pitch_s) - 180.0))
        looking = yaw_abs < YAW_THRESHOLD and pitch_mod < PITCH_THRESHOLD
        
        return yaw_s, pitch_s, roll_s, looking

