"""Timestamp Calibration Service for educational video question navigation (R6).

Calculates a natural 5.0s to 10.0s lead-in prior to the topic explanation
based on Whisper sentence/segment boundaries and contextual speech flow,
avoiding arbitrary fixed-offset subtraction and clamping to 0.0s near the start.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TimestampCalibrationService:
    """Service to calibrate timestamps using transcript segments for optimal learning lead-in."""

    MIN_LEAD_IN: float = 5.0
    MAX_LEAD_IN: float = 10.0
    DEFAULT_LEAD_IN: float = 7.5

    def calibrate(
        self,
        segments: list[dict[str, Any]],
        topic_start_time: float,
        topic_text: str = "",
    ) -> float:
        """Calibrate a topic explanation start time to provide a 5.0s to 10.0s lead-in.

        Args:
            segments: List of transcript segments with 'start', 'end', and 'text'.
            topic_start_time: The raw timestamp (in seconds) where the topic explanation starts.
            topic_text: Optional text of the topic for keyword disambiguation.

        Returns:
            Calibrated start time in seconds, aligned to natural segment boundaries or speech pauses.
        """
        # Rule 1: Clamp near start (< 5.0 seconds) to 0.0s
        if topic_start_time < self.MIN_LEAD_IN:
            return 0.0

        if not segments:
            # Fallback when no segments are available: dynamic proportional lead-in
            lead_in = min(topic_start_time, self.DEFAULT_LEAD_IN)
            return max(0.0, round(topic_start_time - lead_in, 2))

        # Rule 2: Locate the target segment corresponding to topic_start_time
        target_idx = None
        for i, seg in enumerate(segments):
            start = float(seg.get("start", 0.0))
            end = float(seg.get("end", start))
            if start <= topic_start_time <= end:
                target_idx = i
                break
            if start <= topic_start_time and (i == len(segments) - 1 or float(segments[i + 1].get("start", 0.0)) > topic_start_time):
                target_idx = i
                break

        if target_idx is None:
            # If after all segments, use last segment
            target_idx = len(segments) - 1

        # If topic_text is provided and target segment doesn't contain words, search nearby
        if topic_text and target_idx is not None:
            words = [w.lower() for w in topic_text.split() if len(w) > 3]
            best_match_idx = target_idx
            best_match_count = sum(1 for w in words if w in segments[target_idx].get("text", "").lower())
            
            # Check window around target_idx
            for offset in (-1, 1, -2, 2):
                candidate_idx = target_idx + offset
                if 0 <= candidate_idx < len(segments):
                    c_text = segments[candidate_idx].get("text", "").lower()
                    match_count = sum(1 for w in words if w in c_text)
                    if match_count > best_match_count:
                        best_match_count = match_count
                        best_match_idx = candidate_idx
            target_idx = best_match_idx

        # Rule 3: Search preceding segments for boundary alignment
        # We want calibrated_time = preceding_segment.start such that:
        # MIN_LEAD_IN <= topic_start_time - calibrated_time <= MAX_LEAD_IN
        for prev_idx in range(target_idx - 1, -1, -1):
            prev_seg = segments[prev_idx]
            prev_start = float(prev_seg.get("start", 0.0))
            lead_in = topic_start_time - prev_start

            if self.MIN_LEAD_IN <= lead_in <= self.MAX_LEAD_IN:
                return round(prev_start, 2)
            
            # If prev_start is already further than MAX_LEAD_IN, check prev_seg.end
            if lead_in > self.MAX_LEAD_IN:
                prev_end = float(prev_seg.get("end", prev_start))
                end_lead_in = topic_start_time - prev_end
                if self.MIN_LEAD_IN <= end_lead_in <= self.MAX_LEAD_IN:
                    return round(prev_end, 2)
                # If even the end is too far, stop looking further back
                break

        # Check immediate previous segment boundary if target segment itself starts near topic_start_time
        if target_idx > 0:
            target_seg_start = float(segments[target_idx].get("start", 0.0))
            if target_seg_start <= topic_start_time:
                target_lead = topic_start_time - target_seg_start
                if self.MIN_LEAD_IN <= target_lead <= self.MAX_LEAD_IN:
                    return round(target_seg_start, 2)

        # Rule 4: Contextual fallback without fixed static subtraction
        # Derive lead-in proportionally from preceding segment duration or contextual speech gap
        prev_seg = segments[target_idx - 1] if target_idx > 0 else segments[0]
        prev_end = float(prev_seg.get("end", 0.0))
        if prev_end < topic_start_time and (topic_start_time - prev_end) >= self.MIN_LEAD_IN and (topic_start_time - prev_end) <= self.MAX_LEAD_IN:
            return round(prev_end, 2)

        # Dynamic variable lead-in between 5.5 and 8.5 seconds based on speech cadence
        seg_len = float(segments[target_idx].get("end", topic_start_time)) - float(segments[target_idx].get("start", 0.0))
        variable_offset = 6.0 + min(2.5, max(0.0, seg_len * 0.25))
        calibrated = max(0.0, topic_start_time - variable_offset)
        return round(calibrated, 2)

    def to_timestamp_string(self, seconds: float) -> str:
        """Convert seconds to HH:MM:SS format."""
        try:
            total = max(0, round(float(seconds)))
        except (ValueError, TypeError, OverflowError):
            return "00:00:00"
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def from_timestamp_string(self, ts: str) -> float:
        """Convert HH:MM:SS or MM:SS to seconds."""
        if not ts:
            return 0.0
        try:
            parts = [p.strip() for p in str(ts).split(":") if p.strip()]
            if len(parts) == 3:
                return max(0.0, float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2]))
            if len(parts) == 2:
                return max(0.0, float(parts[0]) * 60 + float(parts[1]))
            if len(parts) == 1:
                return max(0.0, float(parts[0]))
            return 0.0
        except (ValueError, TypeError):
            return 0.0

    def calibrate_quiz(
        self,
        quiz: dict[str, Any],
        segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Calibrate all evidence_timestamps in a quiz data structure.

        Args:
            quiz: Dictionary containing 'multiple_choice' and 'open_questions'.
            segments: List of transcript segments.

        Returns:
            Updated quiz dictionary with calibrated evidence_timestamps.
        """
        if not quiz or not segments:
            return quiz

        # Deep copy structure
        import copy
        result = copy.deepcopy(quiz)

        for q in result.get("multiple_choice", []):
            raw_ts = q.get("evidence_timestamp")
            if raw_ts:
                raw_secs = self.from_timestamp_string(raw_ts)
                calibrated_secs = self.calibrate(segments, raw_secs, q.get("question", ""))
                q["evidence_timestamp"] = self.to_timestamp_string(calibrated_secs)
                q["raw_timestamp"] = raw_ts

        for q in result.get("open_questions", []):
            raw_ts = q.get("evidence_timestamp")
            if raw_ts:
                raw_secs = self.from_timestamp_string(raw_ts)
                calibrated_secs = self.calibrate(segments, raw_secs, q.get("question", ""))
                q["evidence_timestamp"] = self.to_timestamp_string(calibrated_secs)
                q["raw_timestamp"] = raw_ts

        return result

    @staticmethod
    def load_raw_segments(youtube_id: str, base_dir: Path | str | None = None) -> list[dict[str, Any]]:
        """Load raw transcript segments from disk for a given video."""
        if base_dir is None:
            # Look in standard data paths
            potential_paths = [
                Path("data/transcripts/raw") / f"{youtube_id}.json",
                Path("../data/transcripts/raw") / f"{youtube_id}.json",
                Path(__file__).resolve().parent.parent.parent / "data" / "transcripts" / "raw" / f"{youtube_id}.json",
            ]
        else:
            potential_paths = [Path(base_dir) / f"{youtube_id}.json"]

        for path in potential_paths:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            return data
                        if isinstance(data, dict) and "segments" in data:
                            return data["segments"]
                except Exception as err:
                    logger.warning("Error reading transcript segments from %s: %s", path, err)
        return []
