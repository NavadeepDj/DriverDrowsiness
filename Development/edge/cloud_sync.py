"""
Local Logging Module (Offline Mode)
Provides local logging functionality without cloud dependencies
"""

import json
import time
from datetime import datetime
import os


class CloudSync:
    """Local logging stub - system runs in offline mode"""
    
    def __init__(self, config_path=None):
        """
        Initialize local logging (offline mode)
        
        Args:
            config_path: Not used in offline mode (kept for compatibility)
        """
        self.initialized = False
        self.log_dir = "logs"
        
        # Create logs directory if it doesn't exist
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
            print(f"Created logs directory: {self.log_dir}")
        
        self.initialized = True
        print("Local logging initialized (offline mode)")
    
    def update_driver_state(self, status, score, ear, perclos, blink_rate, alert_level):
        """
        Log driver state locally (offline mode)
        
        Args:
            status: Driver state string (ALERT, SLIGHTLY_DROWSY, etc.)
            score: Drowsiness score (0-100)
            ear: Current EAR value
            perclos: PERCLOS percentage
            blink_rate: Blink rate (blinks/min)
            alert_level: Current alert level (0, 1, or 2)
        """
        # In offline mode, we can optionally log to a local file
        # For now, this is a no-op to keep the system lightweight
        pass
    
    def log_alert(self, alert_type, timestamp):
        """
        Log alert event locally
        
        Args:
            alert_type: "LEVEL1" or "LEVEL2"
            timestamp: Timestamp in seconds
        """
        try:
            alert_data = {
                'type': alert_type,
                'timestamp': int(timestamp * 1000),
                'datetime': datetime.now().isoformat(),
                'severity': 'warning' if alert_type == 'LEVEL1' else 'emergency'
            }
            
            log_file = os.path.join(self.log_dir, 'alerts.jsonl')
            with open(log_file, 'a') as f:
                f.write(json.dumps(alert_data) + '\n')
        except Exception as e:
            print(f"Error logging alert: {e}")
    
    def send_emergency(self, timestamp):
        """
        Log emergency event locally
        
        Args:
            timestamp: Timestamp in seconds
        """
        try:
            emergency_data = {
                'type': 'EMERGENCY',
                'timestamp': int(timestamp * 1000),
                'datetime': datetime.now().isoformat(),
                'severity': 'critical',
                'status': 'active'
            }
            
            log_file = os.path.join(self.log_dir, 'alerts.jsonl')
            with open(log_file, 'a') as f:
                f.write(json.dumps(emergency_data) + '\n')
            
            print("Emergency event logged locally")
        except Exception as e:
            print(f"Error logging emergency: {e}")
    
    def log_session_summary(self, avg_score, max_score, alert_count, duration):
        """
        Log driving session summary locally
        
        Args:
            avg_score: Average drowsiness score for the session
            max_score: Maximum drowsiness score
            alert_count: Number of alerts triggered
            duration: Session duration in seconds
        """
        try:
            session_data = {
                'avg_drowsiness_score': round(avg_score, 2),
                'max_drowsiness_score': round(max_score, 2),
                'alert_count': alert_count,
                'duration_seconds': duration,
                'timestamp': int(time.time() * 1000),
                'datetime': datetime.now().isoformat()
            }
            
            log_file = os.path.join(self.log_dir, 'sessions.jsonl')
            with open(log_file, 'a') as f:
                f.write(json.dumps(session_data) + '\n')
        except Exception as e:
            print(f"Error logging session: {e}")

