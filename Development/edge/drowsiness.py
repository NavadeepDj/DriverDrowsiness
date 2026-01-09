"""
Drowsiness Metrics Calculation Module
Implements PERCLOS, Eye Aspect Ratio (EAR), and Blink Rate calculations
"""

import numpy as np
from collections import deque
import time
from config import (
    EAR_CLOSED_THRESHOLD,
    EYE_CLOSED_DROWSY_SECONDS,
    MICROSLEEP_SECONDS,
    PERCLOS_WINDOW_SIZE,
    BLINK_RATE_WINDOW,
    BLINK_MIN_SECONDS,
    BLINK_MAX_SECONDS,
    BLINK_MIN_INTERVAL_SECONDS,
    BLINK_DURATION_MICROSLEEP_MIN
)


def calculate_ear(eye_landmarks):
    """
    Calculate Eye Aspect Ratio (EAR) for a single eye
    
    EAR = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    where p1-p6 are the 6 eye landmark points
    
    Args:
        eye_landmarks: List of 6 (x, y) tuples representing eye landmarks
        
    Returns:
        ear: Eye Aspect Ratio value (float)
    """
    if len(eye_landmarks) != 6:
        return None
    
    # Convert to numpy array for easier calculation
    points = np.array(eye_landmarks)
    
    # Calculate vertical distances (height)
    vertical_1 = np.linalg.norm(points[1] - points[5])
    vertical_2 = np.linalg.norm(points[2] - points[4])
    
    # Calculate horizontal distance (width)
    horizontal = np.linalg.norm(points[0] - points[3])
    
    # Avoid division by zero
    if horizontal == 0:
        return None
    
    # Calculate EAR
    ear = (vertical_1 + vertical_2) / (2.0 * horizontal)
    return ear


def calculate_average_ear(left_eye, right_eye):
    """
    Calculate average EAR for both eyes
    
    Args:
        left_eye: List of left eye landmarks
        right_eye: List of right eye landmarks
        
    Returns:
        average_ear: Average EAR value or None if calculation fails
    """
    left_ear = calculate_ear(left_eye)
    right_ear = calculate_ear(right_eye)
    
    if left_ear is None or right_ear is None:
        return None
    
    return (left_ear + right_ear) / 2.0


class DrowsinessMetrics:
    """Tracks and calculates drowsiness-related metrics"""
    
    def __init__(self):
        """Initialize metric trackers"""
        # Store EAR values with timestamps (used for PERCLOS + debugging)
        self.ear_history = deque(maxlen=PERCLOS_WINDOW_SIZE * 30)
        self.ear_timestamps = deque(maxlen=PERCLOS_WINDOW_SIZE * 30)
        
        # Blink and closure tracking
        self.blink_timestamps = deque(maxlen=300)  # recent blink timestamps
        self.blink_durations = deque(maxlen=300)   # recent blink durations (seconds)
        self.microsleep_timestamps = deque(maxlen=50)
        self.microsleep_durations = deque(maxlen=50)

        self.last_ear = None
        self.eyes_closed = False
        self.closed_start_ts = None
        self.last_blink_ts = None
        
        # Track closed/open state over time for PERCLOS
        self.closed_state = deque(maxlen=PERCLOS_WINDOW_SIZE * 30)  # bool
        self.state_timestamps = deque(maxlen=PERCLOS_WINDOW_SIZE * 30)
    
    def update(self, ear, timestamp):
        """
        Update metrics with new EAR value
        
        Args:
            ear: Current Eye Aspect Ratio value
            timestamp: Current timestamp in seconds
        """
        if ear is None:
            return
        
        # Store EAR value
        self.ear_history.append(ear)
        self.ear_timestamps.append(timestamp)
        is_closed = ear < EAR_CLOSED_THRESHOLD
        self.closed_state.append(is_closed)
        self.state_timestamps.append(timestamp)
        
        # Detect blinks (open -> closed -> open), measure closure duration
        if self.last_ear is not None:
            # Eye closed: EAR drops below closed threshold
            if not self.eyes_closed and is_closed:
                self.eyes_closed = True
                self.closed_start_ts = timestamp

            # Eye opened: EAR rises above threshold (closure ended)
            elif self.eyes_closed and not is_closed:
                self.eyes_closed = False
                if self.closed_start_ts is not None:
                    duration = max(0.0, timestamp - self.closed_start_ts)

                    # Debounce noisy toggling around threshold
                    if self.last_blink_ts is None or (timestamp - self.last_blink_ts) >= BLINK_MIN_INTERVAL_SECONDS:
                        # Classify closure
                        if duration >= BLINK_DURATION_MICROSLEEP_MIN:
                            self.microsleep_timestamps.append(timestamp)
                            self.microsleep_durations.append(duration)
                        elif BLINK_MIN_SECONDS <= duration <= BLINK_MAX_SECONDS:
                            self.blink_timestamps.append(timestamp)
                            self.blink_durations.append(duration)
                            self.last_blink_ts = timestamp

                self.closed_start_ts = None
        
        self.last_ear = ear
    
    def calculate_perclos(self, current_time):
        """
        Calculate PERCLOS (Percentage of Eyelid Closure)
        
        PERCLOS = (Time eyes closed / Total time) * 100
        
        Args:
            current_time: Current timestamp in seconds
            
        Returns:
            perclos: Percentage value (0-100)
        """
        if len(self.closed_state) == 0:
            return 0.0
        
        # Calculate PERCLOS over the window: % time eyes are "closed" (EAR < EAR_CLOSED_THRESHOLD)
        window_start = current_time - PERCLOS_WINDOW_SIZE
        
        # Count frames in window
        closed_count = 0
        total_count = 0
        
        for is_closed, ts in zip(self.closed_state, self.state_timestamps):
            if ts >= window_start:
                total_count += 1
                if is_closed:
                    closed_count += 1
        
        if total_count == 0:
            return 0.0
        
        perclos = (closed_count / total_count) * 100.0
        return perclos
    
    def calculate_blink_rate(self, current_time):
        """
        Calculate blink rate (blinks per minute)
        
        Args:
            current_time: Current timestamp in seconds
            
        Returns:
            blink_rate: Blinks per minute
        """
        if len(self.blink_timestamps) == 0:
            return 0.0
        
        # Count blinks in the last BLINK_RATE_WINDOW seconds
        window_start = current_time - BLINK_RATE_WINDOW
        recent_blinks = [ts for ts in self.blink_timestamps if ts >= window_start]
        
        # Calculate blinks per minute
        blink_count = len(recent_blinks)
        blink_rate = (blink_count / BLINK_RATE_WINDOW) * 60.0
        
        return blink_rate

    def get_last_blink_duration(self):
        if not self.blink_durations:
            return 0.0
        return float(self.blink_durations[-1])

    def get_avg_blink_duration(self, current_time):
        # Average over the same window as blink rate
        window_start = current_time - BLINK_RATE_WINDOW
        durations = [d for d, ts in zip(self.blink_durations, self.blink_timestamps) if ts >= window_start]
        if not durations:
            return 0.0
        return float(sum(durations) / len(durations))

    def get_current_closed_duration(self, current_time):
        if self.eyes_closed and self.closed_start_ts is not None:
            return float(max(0.0, current_time - self.closed_start_ts))
        return 0.0

    def get_microsleep_count(self, current_time):
        window_start = current_time - BLINK_RATE_WINDOW
        return sum(1 for ts in self.microsleep_timestamps if ts >= window_start)
    
    def get_current_ear(self):
        """
        Get the most recent EAR value
        
        Returns:
            ear: Most recent EAR value or None
        """
        if len(self.ear_history) == 0:
            return None
        return self.ear_history[-1]
    
    def reset(self):
        """Reset all metrics"""
        self.ear_history.clear()
        self.ear_timestamps.clear()
        self.blink_timestamps.clear()
        self.blink_durations.clear()
        self.microsleep_timestamps.clear()
        self.microsleep_durations.clear()
        self.last_ear = None
        self.eyes_closed = False
        self.closed_start_ts = None
        self.last_blink_ts = None
        self.closed_state.clear()
        self.state_timestamps.clear()

