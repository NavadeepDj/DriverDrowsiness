"""
Two-Level Alert System Module
Implements progressive alerts based on drowsiness symptoms (state-based)

Level 1: Triggers when drowsiness symptoms are detected
Level 2: Escalates only if Level 1 persists
"""

import sys
import time
import threading
from array import array

try:
    import pygame
    pygame_available = True
except ImportError:
    pygame_available = False

from config import (
    LEVEL1_DURATION_SECONDS,
    LEVEL2_DURATION_SECONDS,
    YAWN_ALERT_WINDOW_SECONDS,
    YAWN_ALERT_THRESHOLD,
    YAWN_RECENT_WINDOW_SECONDS,
    BLINK_RATE_LEVEL1_THRESHOLD,
    MICROSLEEP_LEVEL1_TRIGGER,
    PERCLOS_LEVEL1_MIN,
    PERCLOS_LEVEL1_MAX,
    LEVEL1_FREQUENCY_WINDOW_SECONDS,
    LEVEL1_FREQUENCY_THRESHOLD,
    EAR_CLOSED_THRESHOLD
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
    if pygame_available:
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
        except Exception:
            pass


class AlertEngine:
    """
    Manages two-level alert system with audio and visual feedback.
    
    Alert Logic:
    - Level 1: Triggers when driver state indicates drowsiness symptoms
               (SLIGHTLY_DROWSY, DROWSY, VERY_DROWSY, INATTENTIVE)
    - Level 2: Escalates only if Level 1 persists for LEVEL2_DURATION_SECONDS
    """
    
    # States that indicate drowsiness symptoms (trigger Level 1)
    DROWSY_STATES = ["SLIGHTLY_DROWSY", "DROWSY", "VERY_DROWSY", "INATTENTIVE"]
    
    def __init__(self):
        """Initialize alert engine."""
        self.level1_start = None
        self.level1_triggered_at = None
        self.level2_triggered = False
        self.level1_active = False
        self.level2_active = False
        
        # Yawn-based alert tracking
        self.yawn_timestamps = []  # List of yawn timestamps for alert tracking
        self.yawns_since_level1 = 0  # Count of yawns since Level 1 was triggered
        
        # Level 1 frequency tracking (for repeated alert pattern detection)
        self.level1_trigger_history = []  # List of timestamps when Level 1 was triggered
        
        # Store last alert details for logging
        self.last_alert_reason = None
        self.last_alert_details = None
        
        # Initialize pygame mixer for audio alerts
        self.audio_enabled = False
        if pygame_available:
            try:
                pygame.mixer.init()
                self.audio_enabled = True
            except Exception:
                print("Warning: Audio alerts disabled (pygame mixer not available)")
        else:
            print("Warning: pygame not available, audio alerts disabled")
        
        # Alert thread control
        self.alert_thread = None
        self.stop_alert = False
    
    def process(self, state, timestamp, yawn_timestamps=None, 
                perclos=None, blink_rate=None, microsleep_count=0, ear=None):
        """
        Process driver state and metrics, trigger appropriate alerts based on symptoms.
        
        Args:
            state: Current driver state string (ALERT, SLIGHTLY_DROWSY, DROWSY, etc.)
            timestamp: Current timestamp in seconds
            yawn_timestamps: List of recent yawn timestamps (optional, for yawn-based alerts)
            perclos: Current PERCLOS percentage (optional, for PERCLOS-based alerts)
            blink_rate: Current blink rate in blinks/min (optional, for blink rate alerts)
            microsleep_count: Number of microsleep events (optional, for microsleep alerts)
            ear: Current EAR value (optional, for EAR-based Level 2 escalation)
        """
        # Update yawn timestamps if provided
        if yawn_timestamps is not None:
            # Add new yawns that aren't already tracked
            for ts in yawn_timestamps:
                if ts not in self.yawn_timestamps:
                    self.yawn_timestamps.append(ts)
                    # Track if yawn occurred after Level 1 was triggered
                    if self.level1_triggered_at is not None and ts >= self.level1_triggered_at:
                        self.yawns_since_level1 += 1
        
        # Check if state indicates drowsiness symptoms
        has_drowsiness_symptoms = state in self.DROWSY_STATES
        
        # Check all independent symptom triggers
        yawn_trigger = self._check_yawn_trigger(timestamp)
        blink_rate_trigger = self._check_blink_rate_trigger(blink_rate)
        microsleep_trigger = self._check_microsleep_trigger(microsleep_count)
        perclos_trigger = self._check_perclos_trigger(perclos)
        
        # Microsleep triggers immediately (no 3-second delay) - most dangerous
        if microsleep_trigger and not self.level1_active:
            self.trigger_level1(timestamp, "microsleep event", microsleep_count=microsleep_count)
            return  # Exit early for immediate microsleep alert
        
        # Level 1 can be triggered by ANY symptom scenario
        should_trigger_level1 = (
            has_drowsiness_symptoms or 
            yawn_trigger or 
            blink_rate_trigger or 
            perclos_trigger
        )
        
        if should_trigger_level1:
            # Start tracking Level 1 alert duration
            if self.level1_start is None:
                self.level1_start = timestamp
            
            elapsed = timestamp - self.level1_start
            
            # Trigger Level 1 after duration threshold
            if elapsed >= LEVEL1_DURATION_SECONDS and not self.level1_active:
                # Determine trigger reason(s)
                triggers = []
                if yawn_trigger:
                    triggers.append("yawn frequency")
                if blink_rate_trigger:
                    triggers.append("excessive blink rate")
                if perclos_trigger:
                    triggers.append("high PERCLOS")
                if has_drowsiness_symptoms:
                    triggers.append("drowsiness symptoms")
                
                trigger_reason = " + ".join(triggers) if triggers else "drowsiness symptoms"
                self.trigger_level1(timestamp, trigger_reason, 
                                   perclos=perclos, blink_rate=blink_rate)
            
            # Check if Level 1 should be reset (state is ALERT and no symptom triggers active)
            if self.level1_active and self.level1_triggered_at is not None:
                # If state is ALERT and no symptom triggers active, reset immediately
                if (not has_drowsiness_symptoms and 
                    not yawn_trigger and 
                    not blink_rate_trigger and 
                    not perclos_trigger and
                    self.yawns_since_level1 == 0):
                    # Check if enough time has passed since Level 1 (at least 5 seconds)
                    level1_elapsed = timestamp - self.level1_triggered_at
                    if level1_elapsed >= 5.0:  # Give a small buffer before reset
                        # All symptoms cleared → reset Level 1
                        self.reset()
                        return  # Exit early, don't check for Level 2
            
            # Check for frequent Level 1 alerts (repeated drowsiness pattern)
            # This detects if driver repeatedly becomes drowsy and recovers
            # This check works even when Level 1 is not currently active
            frequent_level1_trigger = self._check_frequent_level1_trigger(timestamp)
            
            # Check for frequent Level 1 pattern (immediate escalation, even if Level 1 not active)
            if frequent_level1_trigger and not self.level2_active:
                self.trigger_level2(timestamp, reason="frequent Level 1 alerts")
            
            # Trigger Level 2 if Level 1 persists AND trigger condition is STILL active
            if self.level1_active and self.level1_triggered_at is not None:
                level1_elapsed = timestamp - self.level1_triggered_at
                
                # Check for persistent symptoms (standard escalation)
                if level1_elapsed >= LEVEL2_DURATION_SECONDS and not self.level2_active:
                    # Only escalate if symptoms still present
                    should_escalate = False
                    if has_drowsiness_symptoms:
                        # State-based symptoms persist → escalate
                        should_escalate = True
                    elif yawn_trigger:
                        # Yawn frequency still high - check if yawns continued after Level 1
                        # AND (PERCLOS issues OR EAR issues)
                        if self.yawns_since_level1 > 0:
                            # Check for PERCLOS or EAR issues
                            has_perclos_issue = perclos is not None and perclos >= PERCLOS_LEVEL1_MIN
                            has_ear_issue = ear is not None and ear < EAR_CLOSED_THRESHOLD
                            
                            if has_perclos_issue or has_ear_issue:
                                should_escalate = True
                    elif blink_rate_trigger:
                        # Excessive blink rate persists → escalate
                        should_escalate = True
                    elif perclos_trigger:
                        # High PERCLOS persists → escalate
                        should_escalate = True
                    
                    if should_escalate:
                        self.trigger_level2(timestamp)
        else:
            # Reset if all symptoms clear (driver becomes alert) AND no symptom triggers
            if state == "ALERT" or state == "NO_FACE":
                # Reset if all symptom triggers dropped
                if not yawn_trigger and not blink_rate_trigger and not perclos_trigger:
                    self.reset()
            elif not yawn_trigger and not blink_rate_trigger and not perclos_trigger:
                # If symptom triggers dropped but state is still drowsy, 
                # reset Level 1 but keep monitoring state-based symptoms
                if self.level1_active and self.level1_triggered_at is not None:
                    # Check if Level 1 was triggered by symptom triggers only
                    # If so, reset it since symptoms cleared
                    if not has_drowsiness_symptoms:
                        self.reset()
    
    def _check_yawn_trigger(self, timestamp):
        """
        Check if yawn frequency triggers Level 1 alert.
        
        Threshold: >2 yawns in 30 seconds → Level 1 Alert
        
        Uses rolling 30-second window for yawn frequency calculation.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            True if yawn frequency should trigger Level 1, False otherwise
        """
        # Clean old yawns outside the tracking window (keep 30 seconds)
        cutoff_time = timestamp - YAWN_ALERT_WINDOW_SECONDS
        self.yawn_timestamps = [ts for ts in self.yawn_timestamps if ts >= cutoff_time]
        
        # Count yawns in the last 30 seconds (rolling window)
        window_start = timestamp - YAWN_ALERT_WINDOW_SECONDS
        yawns_in_window = sum(1 for ts in self.yawn_timestamps if ts >= window_start)
        
        # Trigger Level 1 if > threshold yawns in 30 seconds (>2 yawns/30s)
        if yawns_in_window > YAWN_ALERT_THRESHOLD:
            return True
        
        return False
    
    def _check_blink_rate_trigger(self, blink_rate):
        """
        Check if excessive blink rate triggers Level 1 alert.
        
        Research-backed threshold:
        - ≥ 30 blinks/min → Excessive (indicates fatigue/drowsiness) → Level 1 Alert
        
        Args:
            blink_rate: Current blink rate (blinks per minute)
            
        Returns:
            True if blink rate should trigger Level 1, False otherwise
        """
        if blink_rate is None:
            return False
        
        return blink_rate >= BLINK_RATE_LEVEL1_THRESHOLD
    
    def _check_microsleep_trigger(self, microsleep_count):
        """
        Check if microsleep event triggers Level 1 alert.
        
        Microsleep is a dangerous symptom - triggers immediately (no delay).
        
        Args:
            microsleep_count: Number of microsleep events in window
            
        Returns:
            True if microsleep detected, False otherwise
        """
        if microsleep_count is None:
            return False
        
        return MICROSLEEP_LEVEL1_TRIGGER and microsleep_count > 0
    
    def _check_perclos_trigger(self, perclos):
        """
        Check if PERCLOS triggers Level 1 alert (independent of state).
        
        Research-backed threshold:
        - 15% ≤ PERCLOS ≤ 40% → Level 1 Alert (independent trigger)
        - PERCLOS > 40% → Handled by state-based classification
        
        Args:
            perclos: Current PERCLOS percentage (0-100)
            
        Returns:
            True if PERCLOS should trigger Level 1, False otherwise
        """
        if perclos is None:
            return False
        
        return PERCLOS_LEVEL1_MIN <= perclos <= PERCLOS_LEVEL1_MAX
    
    def _check_frequent_level1_trigger(self, timestamp):
        """
        Check if Level 1 alerts are occurring too frequently (repeated drowsiness pattern).
        
        This detects a pattern where the driver repeatedly becomes drowsy, triggers Level 1,
        recovers, but then becomes drowsy again. This indicates persistent fatigue.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            True if Level 1 alerts are too frequent, False otherwise
        """
        # Clean old Level 1 triggers outside the tracking window
        cutoff_time = timestamp - LEVEL1_FREQUENCY_WINDOW_SECONDS
        self.level1_trigger_history = [
            ts for ts in self.level1_trigger_history if ts >= cutoff_time
        ]
        
        # Count Level 1 triggers in the rolling window
        window_start = timestamp - LEVEL1_FREQUENCY_WINDOW_SECONDS
        level1_count = sum(1 for ts in self.level1_trigger_history if ts >= window_start)
        
        # Trigger Level 2 if threshold exceeded
        return level1_count >= LEVEL1_FREQUENCY_THRESHOLD
    
    def _check_recent_yawns(self, timestamp):
        """
        Check if there were yawns in the recent window (for Level 2 escalation).
        This prevents escalation based on old yawns that are just lingering in the rolling window.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            True if yawns occurred in the recent window, False otherwise
        """
        if not self.yawn_timestamps:
            return False
        
        # Check if any yawns occurred in the last YAWN_RECENT_WINDOW_SECONDS
        recent_cutoff = timestamp - YAWN_RECENT_WINDOW_SECONDS
        recent_yawns = [ts for ts in self.yawn_timestamps if ts >= recent_cutoff]
        
        return len(recent_yawns) > 0
    
    def get_yawn_frequency(self, timestamp):
        """
        Get current yawn frequency (yawns in 30-second window).
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            Yawns in 30-second window (float)
        """
        # Clean old yawns
        cutoff_time = timestamp - YAWN_ALERT_WINDOW_SECONDS
        self.yawn_timestamps = [ts for ts in self.yawn_timestamps if ts >= cutoff_time]
        
        # Count yawns in last 30 seconds
        window_start = timestamp - YAWN_ALERT_WINDOW_SECONDS
        yawns_in_window = sum(1 for ts in self.yawn_timestamps if ts >= window_start)
        
        return float(yawns_in_window)  # yawns in 30-second window
    
    def trigger_level1(self, timestamp, reason="drowsiness symptoms", 
                      perclos=None, blink_rate=None, microsleep_count=0):
        """
        Trigger Level 1 alert (drowsiness symptoms or specific symptom detected).
        
        Args:
            timestamp: Timestamp when alert was triggered
            reason: Reason for trigger (e.g., "yawn frequency", "excessive blink rate", "high PERCLOS", "microsleep event")
            perclos: PERCLOS value (for display)
            blink_rate: Blink rate value (for display)
            microsleep_count: Microsleep count (for display)
        """
        if self.level1_active:
            return
        
        self.level1_active = True
        self.level1_triggered_at = timestamp
        self.yawns_since_level1 = 0  # Reset counter when Level 1 triggers
        
        # Track Level 1 trigger for frequency analysis
        self.level1_trigger_history.append(timestamp)
        
        # Store alert details for logging
        self.last_alert_reason = reason
        self.last_alert_details = {}
        
        print(f"[LEVEL 1 ALERT] Triggered at {timestamp:.2f}s - Reason: {reason}")
        
        if reason == "yawn frequency":
            yawn_freq = self.get_yawn_frequency(timestamp)
            print(f"  → Yawn Frequency: {yawn_freq:.1f} yawns in last 30s")
            print(f"  → Threshold: >{YAWN_ALERT_THRESHOLD} yawns/30s indicates unusual/drowsy behavior")
            self.last_alert_details = {
                'yawn_frequency': round(yawn_freq, 1),
                'threshold': YAWN_ALERT_THRESHOLD
            }
        elif reason == "excessive blink rate":
            print(f"  → Blink Rate: {blink_rate:.1f} blinks/min (≥{BLINK_RATE_LEVEL1_THRESHOLD} = excessive)")
            print(f"  → Research: High blink rate indicates fatigue/drowsiness")
            self.last_alert_details = {
                'blink_rate': round(blink_rate, 1) if blink_rate else None,
                'threshold': BLINK_RATE_LEVEL1_THRESHOLD
            }
        elif reason == "high PERCLOS":
            print(f"  → PERCLOS: {perclos:.1f}% ({PERCLOS_LEVEL1_MIN}-{PERCLOS_LEVEL1_MAX}% range)")
            print(f"  → Research: PERCLOS 15-40% indicates drowsiness")
            self.last_alert_details = {
                'perclos': round(perclos, 1) if perclos else None,
                'perclos_range': f"{PERCLOS_LEVEL1_MIN}-{PERCLOS_LEVEL1_MAX}%"
            }
        elif reason == "microsleep event":
            print(f"  → Microsleep: {microsleep_count} event(s) detected (eyes closed ≥0.48s)")
            print(f"  → CRITICAL: Microsleep is dangerous - immediate alert")
            self.last_alert_details = {
                'microsleep_count': microsleep_count,
                'microsleep_threshold_seconds': 0.48,
                'critical': True
            }
        else:
            print("  → Symptoms: Eye closure, high PERCLOS, excessive blinking, yawning, or inattention")
            self.last_alert_details = {
                'symptoms': 'multiple'
            }
        
        # Start audio/visual alerts
        self.start_level1_alerts()
    
    def trigger_level2(self, timestamp, reason="persistent symptoms"):
        """
        Trigger Level 2 alert (emergency escalation - symptoms persist or frequent alerts).
        
        Args:
            timestamp: Timestamp when alert was triggered
            reason: Reason for escalation ("persistent symptoms" or "frequent Level 1 alerts")
        """
        if self.level2_active:
            return
        
        self.level2_active = True
        self.level2_triggered = True
        
        # Store alert details for logging
        self.last_alert_reason = reason
        self.last_alert_details = {}
        
        print(f"[LEVEL 2 EMERGENCY] Emergency alert at {timestamp:.2f}s - Reason: {reason}")
        
        if reason == "frequent Level 1 alerts":
            # Count recent Level 1 triggers
            cutoff_time = timestamp - LEVEL1_FREQUENCY_WINDOW_SECONDS
            recent_triggers = [ts for ts in self.level1_trigger_history if ts >= cutoff_time]
            alert_count = len(recent_triggers)
            window_minutes = round(LEVEL1_FREQUENCY_WINDOW_SECONDS / 60, 1)
            
            print(f"  → Level 1 alerts triggered {alert_count} times in last {window_minutes} minutes")
            print(f"  → Threshold: ≥{LEVEL1_FREQUENCY_THRESHOLD} alerts indicates persistent fatigue")
            print("  → Driver repeatedly becoming drowsy - Immediate attention required!")
            
            self.last_alert_details = {
                'level1_alert_count': alert_count,
                'window_minutes': window_minutes,
                'threshold': LEVEL1_FREQUENCY_THRESHOLD,
                'message': f'Level 1 alerts triggered {alert_count} times in last {window_minutes} minutes. Threshold: ≥{LEVEL1_FREQUENCY_THRESHOLD} alerts indicates persistent fatigue. Driver repeatedly becoming drowsy - Immediate attention required!'
            }
        else:
            print("  → Driver unresponsive to Level 1 warnings - Immediate attention required!")
            self.last_alert_details = {
                'symptoms': 'persistent',
                'message': 'Driver unresponsive to Level 1 warnings - Immediate attention required!'
            }
        
        # Start emergency alerts
        self.start_level2_alerts()
    
    def start_level1_alerts(self):
        """Start Level 1 audio and visual alerts."""
        if self.alert_thread and self.alert_thread.is_alive():
            return
        
        self.stop_alert = False
        self.alert_thread = threading.Thread(target=self._level1_alert_loop, daemon=True)
        self.alert_thread.start()
    
    def start_level2_alerts(self):
        """Start Level 2 emergency alerts."""
        self.stop_alert = False
        if self.alert_thread and self.alert_thread.is_alive():
            # Stop Level 1 alerts
            self.stop_alert = True
            time.sleep(0.5)
        
        self.alert_thread = threading.Thread(target=self._level2_alert_loop, daemon=True)
        self.alert_thread.start()
    
    def _level1_alert_loop(self):
        """Level 1 alert loop - beep every 2 seconds (warning tone)."""
        while not self.stop_alert and self.level1_active:
            if self.audio_enabled:
                try:
                    _beep(800, 0.2)  # Warning tone
                except Exception as e:
                    print(f"Audio alert error: {e}")
            
            time.sleep(2)  # Beep every 2 seconds
    
    def _level2_alert_loop(self):
        """Level 2 alert loop - continuous loud alarm (emergency tone)."""
        while not self.stop_alert and self.level2_active:
            if self.audio_enabled:
                try:
                    _beep(1000, 0.3)  # Emergency tone (louder, longer)
                except Exception as e:
                    print(f"Emergency audio error: {e}")
            
            time.sleep(0.5)  # More frequent alerts for emergency
    
    def reset(self):
        """Reset alert state when driver becomes alert again (symptoms clear)."""
        if self.level1_start is not None:
            self.level1_start = None
            self.level1_triggered_at = None
            self.level1_active = False
            self.level2_active = False
            self.stop_alert = True
            # Clear yawn tracking when reset
            self.yawn_timestamps = []
            self.yawns_since_level1 = 0
            # Note: We keep level1_trigger_history to track frequency patterns
            # It will be cleaned automatically by _check_frequent_level1_trigger
            print("[ALERT RESET] Driver alertness restored - symptoms cleared")
    
    def manual_reset(self):
        """Manually reset alerts (for testing or manual intervention)."""
        self.reset()
        self.level2_triggered = False
    
    def get_alert_level(self):
        """
        Get current alert level.
        
        Returns:
            alert_level: 0 (no alert), 1 (Level 1), or 2 (Level 2)
        """
        if self.level2_active:
            return 2
        elif self.level1_active:
            return 1
        return 0
    
    def get_level1_elapsed(self, current_time):
        """
        Get elapsed time since Level 1 was triggered.
        
        Args:
            current_time: Current timestamp
            
        Returns:
            Elapsed seconds since Level 1 trigger, or 0 if not active
        """
        if self.level1_triggered_at is not None:
            return max(0.0, current_time - self.level1_triggered_at)
        return 0.0
    
    def get_last_alert_info(self):
        """
        Get the last alert reason and details for logging.
        
        Returns:
            Tuple of (reason, details_dict) or (None, None) if no alert info available
        """
        return self.last_alert_reason, self.last_alert_details

