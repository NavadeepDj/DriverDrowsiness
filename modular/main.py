"""
Main Entry Point for Modular Driver Drowsiness Detection System

This modular version separates each detection type into its own module:
- ear_detector.py: EAR calculations
- perclos_calculator.py: PERCLOS tracking and calculation
- blink_analyzer.py: Blink rate and duration analysis
- yawn_detector.py: Yawn detection using LAR
- head_pose_estimator.py: Head pose (yaw, pitch, roll) estimation
- face_detector.py: MediaPipe face detection
- score_calculator.py: Drowsiness score calculation with weightage
- visualizer.py: Overlay drawing
- camera_utils.py: Camera handling
- config.py: All configuration constants

Run with: python main.py
"""

import cv2
import time
from config import DRAW_FACE_MESH, YAWN_ALERT_WINDOW_SECONDS
from camera_utils import open_camera
from face_detector import FaceDetector
from ear_detector import calculate_average_ear
from perclos_calculator import PERCLOSCalculator
from blink_analyzer import BlinkAnalyzer
from yawn_detector import YawnDetector, calculate_lar
from head_pose_estimator import HeadPoseEstimator
from score_calculator import ScoreCalculator
from visualizer import draw_overlay
from alerter import AlertEngine


def main():
    """Main detection loop."""
    print("Starting Driver Drowsiness & Attentiveness Detector (Modular Version)...")
    print("=" * 70)
    print("Module Structure:")
    print("  - EAR Detection: ear_detector.py")
    print("  - PERCLOS Calculation: perclos_calculator.py")
    print("  - Blink Analysis: blink_analyzer.py")
    print("  - Yawn Detection: yawn_detector.py")
    print("  - Head Pose: head_pose_estimator.py")
    print("  - Score Calculation: score_calculator.py")
    print("=" * 70)
    
    # Initialize camera
    cap = open_camera()
    
    # Initialize all detection modules
    face_detector = FaceDetector(draw_face_mesh=DRAW_FACE_MESH)
    perclos_calc = PERCLOSCalculator()
    blink_analyzer = BlinkAnalyzer()
    yawn_detector = YawnDetector()
    head_pose = HeadPoseEstimator()
    score_calculator = ScoreCalculator()
    alerter = AlertEngine()  # Two-level alert system
    
    
    frame_count = 0
    start_time = time.time()
    consecutive_failures = 0
    last_warning_time = 0
    
    try:
        while True:
            ret, frame = cap.read()
            
            # Validate frame
            if not ret or frame is None or frame.size == 0:
                consecutive_failures += 1
                
                # Few transient failures: silently retry (common camera glitches)
                if consecutive_failures <= 5:
                    time.sleep(0.01)
                    continue
                
                # Moderate failures: warn occasionally
                if consecutive_failures <= 20:
                    current_time = time.time()
                    if current_time - last_warning_time > 5.0:
                        print(f"Warning: Camera glitch detected ({consecutive_failures} failures), retrying...")
                        last_warning_time = current_time
                    time.sleep(0.05)
                    continue
                
                # Many consecutive failures: try to re-open the camera
                print("Error: Camera appears stuck, attempting to re-open...")
                try:
                    cap.release()
                    time.sleep(0.5)
                    cap = open_camera()
                    consecutive_failures = 0
                    last_warning_time = 0
                    print("Camera successfully re-opened, resuming...")
                    continue
                except Exception as e:
                    print(f"Failed to re-open camera: {e}")
                    break
            
            # Successful read: reset failure counter
            if consecutive_failures > 0:
                consecutive_failures = 0
                last_warning_time = 0
            
            now = time.time()  # Get current time once per frame
            
            # Detect face
            face_landmarks = face_detector.detect(frame)
            
            # Initialize default values
            state = "NO_FACE"
            score = 0.0
            ear = None
            perclos = 0.0
            blink_rate = 0.0
            yaw = pitch = roll = None
            looking = False
            lar = None
            yawn_count = 0
            is_yawning_now = False
            
            if face_landmarks:
                # Draw face mesh if enabled
                face_detector.draw_face_mesh_landmarks(frame, face_landmarks)
                
                # Extract landmarks
                left_eye, right_eye = face_detector.get_eye_landmarks(face_landmarks, frame.shape)
                mouth_landmarks = face_detector.get_mouth_landmarks(face_landmarks, frame.shape)
                
                # Calculate EAR
                if left_eye and right_eye:
                    if not DRAW_FACE_MESH:
                        face_detector.draw_eye_contours(frame, left_eye, right_eye)
                    ear = calculate_average_ear(left_eye, right_eye)
                
                # Calculate LAR
                if mouth_landmarks and len(mouth_landmarks) == 4:
                    lar = calculate_lar(mouth_landmarks)
                
                # Update all analyzers if EAR is available
                if ear is not None:
                    # Update PERCLOS calculator
                    perclos_calc.update(ear, now)
                    
                    # Update blink analyzer
                    blink_analyzer.update(ear, now)
                    
                    # Update yawn detector
                    if lar is not None:
                        yawn_detector.update(lar, now)
                    
                    # Get all metrics
                    perclos = perclos_calc.calculate(now)
                    blink_rate = blink_analyzer.calculate_blink_rate(now)
                    avg_blink = blink_analyzer.get_avg_blink_duration(now)
                    closed_dur = blink_analyzer.get_current_closed_duration(now)
                    micro_count = blink_analyzer.get_microsleep_count(now)
                    
                    yawn_count = yawn_detector.get_yawn_count(now)
                    current_yawn_dur = yawn_detector.get_current_yawn_duration(now)
                    is_yawning_now = yawn_detector.is_yawning(now, current_lar=lar)
                    
                    # Get recent yawn timestamps for alert tracking (1-minute rolling window)
                    recent_yawn_timestamps = yawn_detector.get_recent_yawn_timestamps(now, YAWN_ALERT_WINDOW_SECONDS)
                    
                    # Estimate head pose
                    yaw, pitch, roll, looking = head_pose.estimate(face_landmarks, frame.shape)
                    
                    # Calculate score
                    score = score_calculator.calculate_score(
                        perclos,
                        blink_rate,
                        ear,
                        closed_duration=closed_dur,
                        avg_blink_duration=avg_blink,
                        microsleep_count=micro_count,
                        yawn_count=yawn_count,
                        current_yawn_duration=current_yawn_dur,
                    )
                    
                    # Classify state
                    state = score_calculator.classify_state(score)
                    
                    # Attentiveness override
                    if yaw is not None and not looking:
                        state = "INATTENTIVE"
            
            # Process alerts based on driver state and all symptom metrics (symptom-based)
            recent_yawn_ts = recent_yawn_timestamps if face_landmarks else []
            alerter.process(
                state, now, 
                yawn_timestamps=recent_yawn_ts,
                perclos=perclos if face_landmarks else None,
                blink_rate=blink_rate if face_landmarks else None,
                microsleep_count=micro_count if face_landmarks else 0,
                ear=ear if face_landmarks else None
            )
            alert_level = alerter.get_alert_level()
            level1_elapsed = alerter.get_level1_elapsed(now)
            yawn_frequency = alerter.get_yawn_frequency(now) if face_landmarks else 0.0
            
            # Get LAR for display
            lar_display = lar if face_landmarks and lar is not None else (
                yawn_detector.get_current_lar() if face_landmarks else None
            )
            current_yawn_dur_display = (
                yawn_detector.get_current_yawn_duration(now) if face_landmarks else 0.0
            )
            
            # Draw overlay
            draw_overlay(
                frame, state, score, ear, perclos, blink_rate,
                yaw, pitch, roll, looking, lar_display, yawn_count,
                is_yawning_now, current_yawn_dur_display,
                alert_level, level1_elapsed, yawn_frequency
            )
            
            # Display frame
            cv2.imshow("Driver Drowsiness (Modular)", frame)
            
            # Print metrics periodically
            frame_count += 1
            if frame_count % 30 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed if elapsed > 0 else 0
                if ear is not None:
                    alert_status = f"Alert: L{alert_level}" if alert_level > 0 else "Alert: None"
                    print(
                        f"FPS: {fps:.1f} | State: {state} | Score: {score:.1f} | "
                        f"EAR: {ear:.3f} | PERCLOS: {perclos:.1f}% | "
                        f"Blink Rate: {blink_rate:.1f}/min | Yawns: {yawn_count} | {alert_status}"
                    )
                else:
                    print(f"FPS: {fps:.1f} | No face detected")
            
            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):
                # Manual reset of alerts
                alerter.manual_reset()
                print("Alerts manually reset")
    
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Shutdown complete.")


if __name__ == "__main__":
    main()

