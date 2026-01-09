"""
Two-Level Alert System
Implements progressive alerts and emergency escalation
"""

import sys
import time
import threading
from array import array

import pygame
from config import (
    LEVEL1_SCORE_THRESHOLD,
    LEVEL1_DURATION_SECONDS,
    LEVEL2_DURATION_SECONDS
)

def _beep(frequency_hz: int, duration_s: float):
    """
    Cross-platform beep:
    - Windows: winsound.Beep (reliable)
    - Else: pygame mixer tone
    """
    if sys.platform.startswith("win"):
        try:
            import winsound
            winsound.Beep(int(frequency_hz), int(duration_s * 1000))
            return
        except Exception:
            pass

    # Fallback: pygame tone (best-effort)
    try:
        sample_rate = 22050
        n_samples = int(duration_s * sample_rate)
        # simple square-ish wave
        buf = array("h")
        period = max(1, int(sample_rate / max(1, frequency_hz)))
        amp = 12000
        for i in range(n_samples):
            buf.append(amp if (i % period) < (period // 2) else -amp)
        sound = pygame.mixer.Sound(buffer=buf.tobytes())
        sound.play()
    except Exception as e:
        raise e


class AlertEngine:
    """Manages two-level alert system with audio and visual feedback"""
    
    def __init__(self, cloud_sync=None):
        """
        Initialize alert engine
        
        Args:
            cloud_sync: Optional CloudSync instance for local logging (offline mode)
        """
        self.cloud_sync = cloud_sync
        self.level1_start = None
        self.level2_triggered = False
        self.level1_active = False
        self.level2_active = False
        
        # Initialize pygame mixer for audio alerts
        try:
            pygame.mixer.init()
            self.audio_enabled = True
        except:
            self.audio_enabled = False
            print("Warning: Audio alerts disabled (pygame mixer not available)")
        
        # Alert thread control
        self.alert_thread = None
        self.stop_alert = False
    
    def process(self, score, timestamp):
        """
        Process drowsiness score and trigger appropriate alerts
        
        Args:
            score: Current drowsiness score
            timestamp: Current timestamp in seconds
        """
        if score > LEVEL1_SCORE_THRESHOLD:
            # Start tracking Level 1 alert duration
            if self.level1_start is None:
                self.level1_start = timestamp
            
            elapsed = timestamp - self.level1_start
            
            # Trigger Level 1 after duration threshold
            if elapsed >= LEVEL1_DURATION_SECONDS and not self.level1_active:
                self.trigger_level1(timestamp)
            
            # Trigger Level 2 if Level 1 persists
            if elapsed >= (LEVEL1_DURATION_SECONDS + LEVEL2_DURATION_SECONDS) and not self.level2_active:
                self.trigger_level2(timestamp)
        else:
            # Reset if score drops below threshold
            self.reset()
    
    def trigger_level1(self, timestamp):
        """
        Trigger Level 1 alert (internal warning)
        
        Args:
            timestamp: Timestamp when alert was triggered
        """
        if self.level1_active:
            return
        
        self.level1_active = True
        print(f"[LEVEL 1 ALERT] Driver drowsiness detected at {timestamp:.2f}s")
        
        # Log alert locally if available
        if self.cloud_sync:
            self.cloud_sync.log_alert("LEVEL1", timestamp)
        
        # Start audio/visual alerts
        self.start_level1_alerts()
    
    def trigger_level2(self, timestamp):
        """
        Trigger Level 2 alert (emergency escalation)
        
        Args:
            timestamp: Timestamp when alert was triggered
        """
        if self.level2_active:
            return
        
        self.level2_active = True
        self.level2_triggered = True
        print(f"[LEVEL 2 EMERGENCY] Driver unresponsive - Emergency alert triggered at {timestamp:.2f}s")
        
        # Log emergency locally
        if self.cloud_sync:
            self.cloud_sync.log_alert("LEVEL2", timestamp)
            self.cloud_sync.send_emergency(timestamp)
        
        # Start emergency alerts
        self.start_level2_alerts()
    
    def start_level1_alerts(self):
        """Start Level 1 audio and visual alerts"""
        if self.alert_thread and self.alert_thread.is_alive():
            return
        
        self.stop_alert = False
        self.alert_thread = threading.Thread(target=self._level1_alert_loop, daemon=True)
        self.alert_thread.start()
    
    def start_level2_alerts(self):
        """Start Level 2 emergency alerts"""
        self.stop_alert = False
        if self.alert_thread and self.alert_thread.is_alive():
            # Stop Level 1 alerts
            self.stop_alert = True
            time.sleep(0.5)
        
        self.alert_thread = threading.Thread(target=self._level2_alert_loop, daemon=True)
        self.alert_thread.start()
    
    def _level1_alert_loop(self):
        """Level 1 alert loop - beep every 2 seconds"""
        while not self.stop_alert and self.level1_active:
            if self.audio_enabled:
                try:
                    _beep(800, 0.2)
                except Exception as e:
                    print(f"Audio alert error: {e}")
            
            # Visual alert (print to console, can be extended to GUI)
            print("⚠️  WARNING: Driver drowsiness detected!")
            
            time.sleep(2)  # Beep every 2 seconds
    
    def _level2_alert_loop(self):
        """Level 2 alert loop - continuous loud alarm"""
        while not self.stop_alert and self.level2_active:
            if self.audio_enabled:
                try:
                    _beep(1000, 0.3)
                except Exception as e:
                    print(f"Emergency audio error: {e}")
            
            # Emergency visual alert
            print("🚨 EMERGENCY: Driver unresponsive! Immediate attention required!")
            
            time.sleep(0.5)  # More frequent alerts for emergency
    
    def reset(self):
        """Reset alert state when driver becomes alert again"""
        if self.level1_start is not None:
            self.level1_start = None
            self.level1_active = False
            self.level2_active = False
            self.stop_alert = True
            print("[ALERT RESET] Driver alertness restored")
    
    def manual_reset(self):
        """Manually reset alerts (for testing or manual intervention)"""
        self.reset()
        self.level2_triggered = False
    
    def get_alert_level(self):
        """
        Get current alert level
        
        Returns:
            alert_level: 0 (no alert), 1 (Level 1), or 2 (Level 2)
        """
        if self.level2_active:
            return 2
        elif self.level1_active:
            return 1
        return 0

