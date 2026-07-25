"""Timestamp-based output pacing helpers."""

from __future__ import annotations


class TimestampResampler:
    """Map irregular/source timestamps onto a fixed output frame clock."""

    def __init__(self, output_fps: float):
        if output_fps <= 0:
            raise ValueError("output_fps must be positive")
        self.output_fps = float(output_fps)
        self.period = 1.0 / self.output_fps
        self.next_output_timestamp: float | None = None

    def emit_count(self, source_timestamp: float) -> int:
        if self.next_output_timestamp is None:
            self.next_output_timestamp = float(source_timestamp)
        count = 0
        while self.next_output_timestamp <= source_timestamp + 1e-9:
            count += 1
            self.next_output_timestamp += self.period
        return count

    def flush_count(self, end_timestamp_exclusive: float) -> int:
        if self.next_output_timestamp is None:
            return 0
        count = 0
        while self.next_output_timestamp < end_timestamp_exclusive - 1e-9:
            count += 1
            self.next_output_timestamp += self.period
        return count
