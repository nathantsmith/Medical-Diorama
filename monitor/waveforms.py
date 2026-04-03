"""
monitor/waveforms.py - Synthetic ECG and SpO2 waveform generators.

These classes generate realistic-looking medical waveform data for the
patient monitor display. The waveforms scroll from right to left, with
the newest data appearing at the right edge of the screen.

Both generators are pure functions of (time_offset, bpm) — they have no
internal state that changes between frames, making them easy to test.

How scrolling works:
  - Each frame, time_offset increases by 1/FPS seconds.
  - For each pixel column (x=0 to x=width), we calculate what "time" that
    column represents: time_at_x = time_offset - (width - x) * time_per_pixel
  - We then evaluate the waveform function at that time to get the y-value.
  - This creates a smooth scrolling effect as time_offset advances.
"""

import math
import numpy as np


class ECGWaveform:
    """
    Generates a synthetic ECG (electrocardiogram) waveform.

    The ECG signal is built from a piecewise function that mimics the
    classic PQRST complex of a real heartbeat:
      - P wave: small upward bump (atrial depolarization)
      - QRS complex: sharp spike (ventricular depolarization)
      - T wave: gentle upward bump (ventricular repolarization)
      - Baseline: flat line between beats

    The cycle length adjusts automatically based on the current BPM.
    """

    def get_points(self, width, bpm, time_offset):
        """
        Generate pixel coordinates for the ECG waveform.

        Args:
            width: Number of horizontal pixels (e.g., 240).
            bpm: Current heart rate in beats per minute.
            time_offset: Current time in seconds (increases each frame).

        Returns:
            List of (x, y) tuples where y is in the range [0, 1].
            0.0 = top of waveform area, 1.0 = bottom.
            The caller scales these to actual pixel coordinates.
        """
        # How long one heartbeat cycle takes in seconds
        beat_duration = 60.0 / max(bpm, 30)  # Clamp to avoid division issues

        # How much "time" each pixel column represents
        # Show about 3 seconds of waveform across the display width
        time_window = 3.0  # seconds visible on screen
        time_per_pixel = time_window / width

        points = []
        for x in range(width):
            # Calculate what time this pixel column represents
            # Left edge = oldest data, right edge = newest
            t = time_offset - (width - 1 - x) * time_per_pixel

            # Where are we within the current heartbeat cycle? (0.0 to 1.0)
            phase = (t % beat_duration) / beat_duration

            # Generate the ECG signal value at this phase
            y = self._ecg_signal(phase)

            points.append((x, y))

        return points

    def _ecg_signal(self, phase):
        """
        Evaluate the ECG signal at a given phase within one heartbeat.

        Args:
            phase: Position within the beat cycle (0.0 to 1.0).

        Returns:
            Signal value where 0.5 is baseline, 0.0 is max upward deflection,
            and 1.0 is max downward deflection.
        """
        # Define the timing of each wave component (as fraction of beat cycle)
        # These percentages roughly mimic a real ECG at normal heart rates

        if 0.05 <= phase < 0.12:
            # P wave: small upward bump
            # Map phase to 0-1 within the P wave window
            t = (phase - 0.05) / 0.07
            return 0.5 - 0.08 * math.sin(math.pi * t)

        elif 0.15 <= phase < 0.18:
            # Q wave: small downward dip before the big spike
            t = (phase - 0.15) / 0.03
            return 0.5 + 0.06 * math.sin(math.pi * t)

        elif 0.18 <= phase < 0.22:
            # R wave: tall sharp upward spike (the main QRS peak)
            t = (phase - 0.18) / 0.04
            return 0.5 - 0.42 * math.sin(math.pi * t)

        elif 0.22 <= phase < 0.25:
            # S wave: small downward dip after the spike
            t = (phase - 0.22) / 0.03
            return 0.5 + 0.1 * math.sin(math.pi * t)

        elif 0.30 <= phase < 0.42:
            # T wave: gentle upward bump (repolarization)
            t = (phase - 0.30) / 0.12
            return 0.5 - 0.12 * math.sin(math.pi * t)

        else:
            # Baseline: flat line at the middle
            return 0.5


class SpO2Waveform:
    """
    Generates a synthetic SpO2 plethysmograph waveform.

    The plethysmograph (pulse oximeter waveform) shows blood volume changes
    in the fingertip with each heartbeat. It has a characteristic shape:
      - Sharp upstroke (systolic rise) as the heart pumps blood
      - Dicrotic notch (small dip from aortic valve closure)
      - Gradual downslope (diastolic decline) as blood flows away

    The waveform repeats at the heart rate, since each pulse corresponds
    to one heartbeat.
    """

    def get_points(self, width, bpm, time_offset):
        """
        Generate pixel coordinates for the SpO2 plethysmograph waveform.

        Args:
            width: Number of horizontal pixels (e.g., 240).
            bpm: Current heart rate in beats per minute.
            time_offset: Current time in seconds (increases each frame).

        Returns:
            List of (x, y) tuples where y is in the range [0, 1].
            0.0 = top of waveform area, 1.0 = bottom.
        """
        beat_duration = 60.0 / max(bpm, 30)
        time_window = 3.0  # seconds visible on screen
        time_per_pixel = time_window / width

        points = []
        for x in range(width):
            t = time_offset - (width - 1 - x) * time_per_pixel
            phase = (t % beat_duration) / beat_duration
            y = self._pleth_signal(phase)
            points.append((x, y))

        return points

    def _pleth_signal(self, phase):
        """
        Evaluate the plethysmograph signal at a given phase.

        Args:
            phase: Position within the beat cycle (0.0 to 1.0).

        Returns:
            Signal value where 0.5 is baseline, lower values = upward peaks.
        """
        if phase < 0.10:
            # Sharp systolic upstroke: rapid rise from baseline to peak
            t = phase / 0.10
            # Use a sine curve for smooth acceleration
            return 0.7 - 0.45 * math.sin(math.pi * t / 2)

        elif phase < 0.20:
            # Initial descent from peak
            t = (phase - 0.10) / 0.10
            return 0.25 + 0.15 * t

        elif phase < 0.30:
            # Dicrotic notch: small upward bump in the descent
            t = (phase - 0.20) / 0.10
            return 0.40 - 0.06 * math.sin(math.pi * t)

        elif phase < 0.80:
            # Gradual diastolic descent back to baseline
            t = (phase - 0.30) / 0.50
            return 0.40 + 0.30 * t

        else:
            # Baseline (waiting for next beat)
            return 0.70
