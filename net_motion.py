"""Net swish detection via frame differencing and edge energy in a hoop-derived ROI."""

from __future__ import annotations

from collections import deque

import cv2
import numpy as np

from utils import get_rim_bounds

NET_COLOR = (255, 180, 0)


def get_net_roi(
    hoop_pos: list,
    frame_width: int,
    frame_height: int,
) -> tuple[int, int, int, int] | None:
    """Build a rectangle under the rim for net motion analysis."""
    if len(hoop_pos) < 1:
        return None

    cx, cy = hoop_pos[-1][0]
    w, h = hoop_pos[-1][2], hoop_pos[-1][3]
    rim_y, rim_x1, rim_x2, rim_bottom = get_rim_bounds(hoop_pos)

    half_net_w = max(int(0.45 * w), 12)
    net_top = int(rim_y + 0.05 * h)
    net_bottom = int(rim_bottom + 0.95 * h)

    x1 = int(cx - half_net_w)
    x2 = int(cx + half_net_w)
    y1 = net_top
    y2 = net_bottom

    x1 = max(0, min(x1, frame_width - 2))
    x2 = max(x1 + 8, min(x2, frame_width - 1))
    y1 = max(0, min(y1, frame_height - 2))
    y2 = max(y1 + 8, min(y2, frame_height - 1))

    return (x1, y1, x2, y2)


class NetMotionDetector:
    """Track temporal motion inside the net ROI to detect swish events."""

    def __init__(
        self,
        window_size: int = 15,
        diff_weight: float = 0.65,
        edge_weight: float = 0.35,
        swish_peak_ratio: float = 1.7,
        swish_std_ratio: float = 1.4,
        min_baseline: float = 0.008,
    ) -> None:
        self.window_size = window_size
        self.diff_weight = diff_weight
        self.edge_weight = edge_weight
        self.swish_peak_ratio = swish_peak_ratio
        self.swish_std_ratio = swish_std_ratio
        self.min_baseline = min_baseline

        self._scores: deque[float] = deque(maxlen=window_size)
        self._prev_gray: np.ndarray | None = None
        self._baseline: float = 0.02
        self.last_score: float = 0.0
        self.peak_score: float = 0.0
        self.swish_detected: bool = False

    def reset(self) -> None:
        self._scores.clear()
        self._prev_gray = None
        self._baseline = 0.02
        self.last_score = 0.0
        self.peak_score = 0.0
        self.swish_detected = False

    def _extract_patch(self, frame: np.ndarray, net_roi: tuple[int, int, int, int]) -> np.ndarray:
        x1, y1, x2, y2 = net_roi
        return frame[y1:y2, x1:x2]

    def _frame_energy(self, patch: np.ndarray) -> tuple[float, float]:
        gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        edges = cv2.Canny(gray, 40, 120)
        edge_energy = float(np.mean(edges)) / 255.0

        diff_energy = 0.0
        if self._prev_gray is not None and self._prev_gray.shape == gray.shape:
            diff = cv2.absdiff(gray, self._prev_gray)
            diff_energy = float(np.mean(diff)) / 255.0

        self._prev_gray = gray
        combined = self.diff_weight * diff_energy + self.edge_weight * edge_energy
        return combined, edge_energy

    def update(
        self,
        frame: np.ndarray,
        hoop_pos: list,
    ) -> float:
        """Process one frame; return combined motion score for this frame."""
        h, w = frame.shape[:2]
        net_roi = get_net_roi(hoop_pos, w, h)
        if net_roi is None:
            self.last_score = 0.0
            return 0.0

        patch = self._extract_patch(frame, net_roi)
        if patch.size == 0:
            self.last_score = 0.0
            return 0.0

        score, _ = self._frame_energy(patch)
        self.last_score = score
        self._scores.append(score)

        if len(self._scores) >= 5:
            quiet = float(np.percentile(list(self._scores), 25))
            self._baseline = max(self.min_baseline, 0.85 * self._baseline + 0.15 * quiet)

        self.peak_score = max(self.peak_score, score)

        peak_threshold = self._baseline * self.swish_peak_ratio
        std_threshold = self._baseline * self.swish_std_ratio
        window_std = float(np.std(list(self._scores))) if len(self._scores) > 3 else 0.0

        if score >= peak_threshold or window_std >= std_threshold:
            self.swish_detected = True

        return score

    def motion_stats(self) -> dict:
        scores = list(self._scores)
        return {
            "last": round(self.last_score, 4),
            "peak": round(self.peak_score, 4),
            "baseline": round(self._baseline, 4),
            "window_std": round(float(np.std(scores)), 4) if scores else 0.0,
            "swish": self.swish_detected,
        }


def draw_net_roi(
    frame: np.ndarray,
    hoop_pos: list,
    detector: NetMotionDetector | None = None,
) -> tuple[int, int, int, int] | None:
    h, w = frame.shape[:2]
    net_roi = get_net_roi(hoop_pos, w, h)
    if net_roi is None:
        return None

    x1, y1, x2, y2 = net_roi
    color = NET_COLOR
    if detector is not None and detector.swish_detected:
        color = (0, 255, 120)

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
    label = "Net ROI"
    if detector is not None:
        label = f"Net {detector.last_score:.2f}"
    cv2.putText(
        frame,
        label,
        (x1 + 6, y2 - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        2,
        cv2.LINE_AA,
    )
    return net_roi
