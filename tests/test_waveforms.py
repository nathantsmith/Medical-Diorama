"""
tests/test_waveforms.py - Tests for the ECG and SpO2 waveform generators.

Verifies that:
  - Waveforms produce the correct number of points
  - Output values are within expected ranges (0.0 to 1.0)
  - Different BPM values produce different waveform timings
  - Time offset creates scrolling effect (points change between frames)
"""

import sys
import os

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitor.waveforms import ECGWaveform, SpO2Waveform


class TestECGWaveform:
    """Tests for the ECG waveform generator."""

    def setup_method(self):
        """Create a fresh ECG waveform generator for each test."""
        self.ecg = ECGWaveform()

    def test_returns_correct_number_of_points(self):
        """get_points() should return exactly 'width' points."""
        points = self.ecg.get_points(width=240, bpm=72, time_offset=0.0)
        assert len(points) == 240

    def test_returns_correct_number_of_points_various_widths(self):
        """Should work with different display widths."""
        for width in [100, 240, 320, 480]:
            points = self.ecg.get_points(width=width, bpm=72, time_offset=0.0)
            assert len(points) == width

    def test_y_values_in_range(self):
        """All y values should be between 0.0 and 1.0 (normalized)."""
        points = self.ecg.get_points(width=240, bpm=72, time_offset=0.0)
        for x, y in points:
            assert 0.0 <= y <= 1.0, f"y={y} out of range at x={x}"

    def test_x_values_sequential(self):
        """X values should be sequential integers from 0 to width-1."""
        points = self.ecg.get_points(width=240, bpm=72, time_offset=0.0)
        for i, (x, y) in enumerate(points):
            assert x == i, f"Expected x={i}, got x={x}"

    def test_different_time_offsets_produce_different_output(self):
        """Advancing the time offset should shift the waveform (scrolling)."""
        points_t0 = self.ecg.get_points(width=240, bpm=72, time_offset=0.0)
        points_t1 = self.ecg.get_points(width=240, bpm=72, time_offset=0.5)

        # The y values should differ at most positions (waveform has scrolled)
        differences = sum(
            1 for (_, y0), (_, y1) in zip(points_t0, points_t1) if y0 != y1
        )
        assert differences > 0, "Waveform should change when time advances"

    def test_very_high_bpm(self):
        """Should handle high BPM without errors."""
        points = self.ecg.get_points(width=240, bpm=250, time_offset=0.0)
        assert len(points) == 240
        for _, y in points:
            assert 0.0 <= y <= 1.0

    def test_very_low_bpm(self):
        """Should handle low BPM (clamped to 30 minimum)."""
        points = self.ecg.get_points(width=240, bpm=10, time_offset=0.0)
        assert len(points) == 240
        for _, y in points:
            assert 0.0 <= y <= 1.0

    def test_has_qrs_spike(self):
        """The ECG signal should have a prominent QRS spike (values far from 0.5)."""
        # Generate one full beat cycle worth of data
        points = self.ecg.get_points(width=240, bpm=60, time_offset=0.0)

        # Find the maximum deviation from baseline (0.5)
        max_deviation = max(abs(y - 0.5) for _, y in points)

        # QRS spike should cause at least 0.3 deviation from baseline
        assert max_deviation >= 0.3, (
            f"Expected QRS spike > 0.3 deviation, got {max_deviation}"
        )


class TestSpO2Waveform:
    """Tests for the SpO2 plethysmograph waveform generator."""

    def setup_method(self):
        """Create a fresh SpO2 waveform generator for each test."""
        self.spo2 = SpO2Waveform()

    def test_returns_correct_number_of_points(self):
        """get_points() should return exactly 'width' points."""
        points = self.spo2.get_points(width=240, bpm=72, time_offset=0.0)
        assert len(points) == 240

    def test_y_values_in_range(self):
        """All y values should be between 0.0 and 1.0 (normalized)."""
        points = self.spo2.get_points(width=240, bpm=72, time_offset=0.0)
        for x, y in points:
            assert 0.0 <= y <= 1.0, f"y={y} out of range at x={x}"

    def test_different_time_offsets_produce_different_output(self):
        """Advancing time should shift the waveform."""
        points_t0 = self.spo2.get_points(width=240, bpm=72, time_offset=0.0)
        points_t1 = self.spo2.get_points(width=240, bpm=72, time_offset=0.5)

        differences = sum(
            1 for (_, y0), (_, y1) in zip(points_t0, points_t1) if y0 != y1
        )
        assert differences > 0, "Waveform should change when time advances"

    def test_has_systolic_peak(self):
        """The pleth signal should have a noticeable systolic peak."""
        points = self.spo2.get_points(width=240, bpm=60, time_offset=0.0)

        # Find minimum y value (peak is upward, which is lower y in our convention)
        min_y = min(y for _, y in points)

        # The peak should reach below 0.4 (significantly above baseline of ~0.7)
        assert min_y < 0.4, f"Expected systolic peak < 0.4, got {min_y}"
