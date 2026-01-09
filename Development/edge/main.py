"""
Main Entry Point for Driver Drowsiness Detection System
Runs real-time detection loop on Raspberry Pi with webcam
"""

import cv2
import time
import sys
from detector import FaceDetector
from drowsiness import DrowsinessMetrics, calculate_average_ear
from scorer import DrowsinessScorer
from alerter import AlertEngine
from cloud_sync import CloudSync
from config import (
    CAMERA_INDEX,
    CAMERA_BACKEND,
    CAMERA_PROBE_COUNT,
    TARGET_FPS,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    LOG_UPDATE_INTERVAL
)

def _backend_candidates():
    # Prefer explicit backend if configured
    backend = str(CAMERA_BACKEND).upper()
    if backend == "DSHOW" and hasattr(cv2, "CAP_DSHOW"):
        return [cv2.CAP_DSHOW]
    if backend == "MSMF" and hasattr(cv2, "CAP_MSMF"):
        return [cv2.CAP_MSMF]

    # AUTO: try common Windows backends first, then default
    candidates = []
    if hasattr(cv2, "CAP_DSHOW"):
        candidates.append(cv2.CAP_DSHOW)
    if hasattr(cv2, "CAP_MSMF"):
        candidates.append(cv2.CAP_MSMF)
    candidates.append(None)  # default backend
    return candidates


def open_camera():
    """
    Open a working camera capture device.
    Tries multiple backends and indices to avoid 'Failed to capture frame' on Windows.
    """
    indices = [CAMERA_INDEX] + [i for i in range(CAMERA_PROBE_COUNT) if i != CAMERA_INDEX]

    last_error = None
    for backend in _backend_candidates():
        for idx in indices:
            try:
                cap = cv2.VideoCapture(idx, backend) if backend is not None else cv2.VideoCapture(idx)
                if not cap.isOpened():
                    cap.release()
                    continue

                # Apply desired properties (some drivers ignore these; that's okay)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
                cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)

                # Warm up a few frames
                ok = False
                for _ in range(10):
                    ret, _frame = cap.read()
                    if ret:
                        ok = True
                        break
                    time.sleep(0.05)

                if ok:
                    backend_name = "DEFAULT" if backend is None else str(backend)
                    print(f"Camera opened: index={idx}, backend={backend_name}")
                    return cap

                cap.release()
            except Exception as e:
                last_error = e

    msg = (
        f"Error: Could not read frames from any camera.\n"
        f"Tried indices: {indices}\n"
        f"Tried backends: {['DEFAULT' if b is None else b for b in _backend_candidates()]}\n"
        f"Tips:\n"
        f"- Close other apps using the camera (Teams/Zoom/Browser).\n"
        f"- Try changing CAMERA_INDEX in config.py.\n"
        f"- On Windows, set CAMERA_BACKEND to 'DSHOW' or 'MSMF' in config.py.\n"
    )
    if last_error:
        msg += f"Last error: {last_error}\n"
    raise RuntimeError(msg)


class DrowsinessDetectionSystem:
    """Main system orchestrating all components"""
    
    def __init__(self):
        """Initialize all system components"""
        print("Initializing Driver Drowsiness Detection System...")
        
        # Initialize components
        self.detector = FaceDetector()
        self.metrics = DrowsinessMetrics()
        self.scorer = DrowsinessScorer()
        
        # Initialize local logging (offline mode)
        self.cloud_sync = CloudSync()
        
        # Initialize alert engine with local logging
        self.alerter = AlertEngine(self.cloud_sync)
        
        # Initialize camera
        try:
            self.cap = open_camera()
        except Exception as e:
            print(str(e))
            sys.exit(1)
        
        # Set camera properties
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)
        
        print(f"Camera initialized: {FRAME_WIDTH}x{FRAME_HEIGHT} @ {TARGET_FPS} FPS")
        
        # Timing variables
        self.last_log_update = 0
        self.frame_count = 0
        self.start_time = time.time()
        
        # Session tracking
        self.session_start = time.time()
        self.session_scores = []
        self.session_alert_count = 0

        # Camera failure tracking (to avoid exiting on a single bad frame)
        self.consecutive_capture_failures = 0
    
    def run(self):
        """Main detection loop"""
        print("\nStarting detection loop...")
        print("Press 'q' to quit, 'r' to reset alerts\n")
        
        try:
            while True:
                frame_start = time.time()
                
                # Capture frame with basic retry / re-open logic
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    self.consecutive_capture_failures += 1

                    # Few transient failures: just skip this iteration
                    if self.consecutive_capture_failures <= 10:
                        if self.consecutive_capture_failures == 1:
                            print("Warning: Failed to capture frame, retrying...")
                        time.sleep(0.05)
                        continue

                    # Many consecutive failures: try to re-open the camera once
                    print("Error: Failed to capture frame repeatedly, trying to re-open camera...")
                    try:
                        self.cap.release()
                    except Exception:
                        pass

                    try:
                        self.cap = open_camera()
                        self.consecutive_capture_failures = 0
                        print("Camera successfully re-opened, resuming...")
                        continue
                    except Exception as e:
                        print(str(e))
                        break

                # Successful read: reset failure counter
                self.consecutive_capture_failures = 0
                
                # Detect face
                face_landmarks = self.detector.detect(frame)
                
                # Initialize variables
                state = "NO_FACE"
                score = 0
                ear = None
                perclos = 0
                blink_rate = 0
                alert_level = 0
                
                if face_landmarks:
                    # Extract eye landmarks
                    left_eye, right_eye = self.detector.get_eye_landmarks(
                        face_landmarks, frame.shape
                    )
                    
                    # Calculate EAR
                    ear = calculate_average_ear(left_eye, right_eye)
                    
                    if ear is not None:
                        # Update metrics
                        current_time = time.time()
                        self.metrics.update(ear, current_time)
                        
                        # Calculate drowsiness metrics
                        perclos = self.metrics.calculate_perclos(current_time)
                        blink_rate = self.metrics.calculate_blink_rate(current_time)
                        avg_blink_duration = self.metrics.get_avg_blink_duration(current_time)
                        closed_duration = self.metrics.get_current_closed_duration(current_time)
                        microsleep_count = self.metrics.get_microsleep_count(current_time)
                        
                        # Calculate drowsiness score
                        score = self.scorer.calculate_score(
                            perclos,
                            blink_rate,
                            ear,
                            closed_duration=closed_duration,
                            avg_blink_duration=avg_blink_duration,
                            microsleep_count=microsleep_count,
                        )
                        state = self.scorer.classify_state(score)
                        
                        # Process alerts
                        self.alerter.process(score, current_time)
                        alert_level = self.alerter.get_alert_level()
                        
                        # Track session data
                        self.session_scores.append(score)
                        # Count alert events (not per-frame) to avoid huge counts
                        if not hasattr(self, "_last_alert_level"):
                            self._last_alert_level = 0
                        if alert_level > self._last_alert_level:
                            self.session_alert_count += 1
                        self._last_alert_level = alert_level
                        
                        # Update local logging (throttled)
                        if current_time - self.last_log_update >= LOG_UPDATE_INTERVAL:
                            if self.cloud_sync.initialized:
                                self.cloud_sync.update_driver_state(
                                    state, score, ear, perclos, blink_rate, alert_level
                                )
                            self.last_log_update = current_time
                        
                        # Display information on frame
                        self._draw_info(frame, state, score, ear, perclos, blink_rate, alert_level)
                        
                        # Draw face landmarks (optional, can be disabled for performance)
                        # frame = self.detector.draw_landmarks(frame, face_landmarks)
                    else:
                        self._draw_no_face(frame)
                else:
                    self._draw_no_face(frame)
                
                # Display frame
                cv2.imshow('Driver Drowsiness Detection', frame)
                
                # Handle keyboard input
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    self.alerter.manual_reset()
                    print("Alerts manually reset")
                
                # Calculate FPS
                self.frame_count += 1
                elapsed = time.time() - frame_start
                fps = 1.0 / elapsed if elapsed > 0 else 0
                
                # Print status every 30 frames
                if self.frame_count % 30 == 0:
                    avg_fps = self.frame_count / (time.time() - self.start_time)
                    if ear is not None:
                        print(f"FPS: {fps:.1f} (avg: {avg_fps:.1f}) | "
                              f"State: {state} | Score: {score:.1f} | "
                              f"EAR: {ear:.3f} | PERCLOS: {perclos:.1f}% | "
                              f"Blink Rate: {blink_rate:.1f}/min | Alert: {alert_level}")
                    else:
                        print(f"FPS: {fps:.1f} (avg: {avg_fps:.1f}) | No face detected")
        
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.cleanup()
    
    def _draw_info(self, frame, state, score, ear, perclos, blink_rate, alert_level):
        """Draw detection information on frame"""
        # Color coding based on state
        color_map = {
            'ALERT': (0, 255, 0),  # Green
            'SLIGHTLY_DROWSY': (0, 255, 255),  # Yellow
            'DROWSY': (0, 165, 255),  # Orange
            'VERY_DROWSY': (0, 0, 255)  # Red
        }
        color = color_map.get(state, (255, 255, 255))
        
        # Draw state and score
        cv2.putText(frame, f"State: {state}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(frame, f"Score: {score:.1f}/100", (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        # Draw metrics
        cv2.putText(frame, f"EAR: {ear:.3f}", (10, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"PERCLOS: {perclos:.1f}%", (10, 110),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Blink Rate: {blink_rate:.1f}/min", (10, 130),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Draw alert level
        if alert_level > 0:
            alert_text = f"ALERT LEVEL {alert_level}"
            alert_color = (0, 0, 255) if alert_level == 2 else (0, 165, 255)
            cv2.putText(frame, alert_text, (10, frame.shape[0] - 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, alert_color, 2)
    
    def _draw_no_face(self, frame):
        """Draw message when no face is detected"""
        cv2.putText(frame, "No face detected", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    
    def cleanup(self):
        """Cleanup resources and log session summary"""
        print("\nCleaning up...")
        
        # Log session summary
        if len(self.session_scores) > 0:
            avg_score = sum(self.session_scores) / len(self.session_scores)
            max_score = max(self.session_scores)
            duration = time.time() - self.session_start
            
            if self.cloud_sync.initialized:
                self.cloud_sync.log_session_summary(
                    avg_score, max_score, self.session_alert_count, duration
                )
            
            print(f"\nSession Summary:")
            print(f"  Duration: {duration:.1f}s")
            print(f"  Average Score: {avg_score:.1f}")
            print(f"  Max Score: {max_score:.1f}")
            print(f"  Alerts: {self.session_alert_count}")
        
        # Release resources
        self.cap.release()
        cv2.destroyAllWindows()
        print("System shutdown complete")


def main():
    """Main entry point"""
    system = DrowsinessDetectionSystem()
    system.run()


if __name__ == "__main__":
    main()

