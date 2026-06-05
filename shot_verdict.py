"""Deferred make/miss verdict using trajectory + net swish evidence."""

from __future__ import annotations

from dataclasses import dataclass, field

from net_motion import NetMotionDetector
from utils import detect_rim_rebound, score


@dataclass
class PendingShot:
    attempt_index: int
    start_frame: int
    min_end_frame: int
    max_end_frame: int
    ball_snapshot: list
    hoop_snapshot: list
    net_detector: NetMotionDetector = field(default_factory=NetMotionDetector)


class ShotVerdictManager:
    """After an attempt trigger, wait 0.3–1.0s to combine rim trajectory and net motion."""

    def __init__(
        self,
        fps: float,
        *,
        has_net: bool = True,
        verify_min_s: float = 0.3,
        verify_max_s: float = 1.0,
    ) -> None:
        self.has_net = has_net
        self.verify_min_frames = max(int(fps * verify_min_s), 1)
        self.verify_max_frames = max(int(fps * verify_max_s), self.verify_min_frames + 1)
        self.pending: PendingShot | None = None

    def start_pending(
        self,
        attempt_index: int,
        frame_count: int,
        ball_pos: list,
        hoop_pos: list,
    ) -> None:
        self.pending = PendingShot(
            attempt_index=attempt_index,
            start_frame=frame_count,
            min_end_frame=frame_count + self.verify_min_frames,
            max_end_frame=frame_count + self.verify_max_frames,
            ball_snapshot=[*ball_pos],
            hoop_snapshot=[*hoop_pos],
        )

    def update(
        self,
        frame: np.ndarray,
        frame_count: int,
        ball_pos: list,
        hoop_pos: list,
        custom_roi: tuple[int, int, int, int] | None,
    ) -> dict | None:
        if self.pending is None:
            return None

        pending = self.pending
        hoop_ref = hoop_pos if len(hoop_pos) > 0 else pending.hoop_snapshot
        if len(hoop_ref) < 1:
            if frame_count >= pending.max_end_frame:
                self.pending = None
                return self._finalize(
                    pending,
                    frame_count,
                    ball_pos,
                    hoop_ref,
                    custom_roi,
                    forced=True,
                )
            return None

        pending.net_detector.update(frame, hoop_ref)

        if frame_count < pending.min_end_frame:
            return None

        if frame_count >= pending.max_end_frame:
            result = self._finalize(
                pending,
                frame_count,
                ball_pos,
                hoop_ref,
                custom_roi,
                forced=True,
            )
            self.pending = None
            return result

        early = self._try_early_finalize(
            pending, frame_count, ball_pos, hoop_ref, custom_roi
        )
        if early is not None:
            self.pending = None
            return early

        return None

    def flush(
        self,
        frame_count: int,
        ball_pos: list,
        hoop_pos: list,
        custom_roi: tuple[int, int, int, int] | None,
    ) -> dict | None:
        if self.pending is None:
            return None
        pending = self.pending
        hoop_ref = hoop_pos if len(hoop_pos) > 0 else pending.hoop_snapshot
        result = self._finalize(
            pending,
            frame_count,
            ball_pos,
            hoop_ref,
            custom_roi,
            forced=True,
        )
        self.pending = None
        return result

    def _try_early_finalize(
        self,
        pending: PendingShot,
        frame_count: int,
        ball_pos: list,
        hoop_pos: list,
        custom_roi: tuple[int, int, int, int] | None,
    ) -> dict | None:
        trajectory = self._trajectory_cross(
            ball_pos, pending.ball_snapshot, hoop_pos, custom_roi
        )
        net_swish = pending.net_detector.swish_detected
        rebound = detect_rim_rebound(ball_pos, hoop_pos, custom_roi)

        if self.has_net:
            if trajectory and net_swish:
                return self._build_result(pending, frame_count, True, trajectory, net_swish, rebound)
            if rebound and not net_swish:
                return self._build_result(pending, frame_count, False, trajectory, net_swish, rebound)
        else:
            if trajectory:
                return self._build_result(pending, frame_count, True, trajectory, net_swish, rebound)
            if rebound:
                return self._build_result(pending, frame_count, False, trajectory, net_swish, rebound)

        return None

    def _finalize(
        self,
        pending: PendingShot,
        frame_count: int,
        ball_pos: list,
        hoop_pos: list,
        custom_roi: tuple[int, int, int, int] | None,
        *,
        forced: bool = False,
    ) -> dict:
        trajectory = self._trajectory_cross(
            ball_pos, pending.ball_snapshot, hoop_pos, custom_roi
        )
        net_swish = pending.net_detector.swish_detected
        rebound = detect_rim_rebound(ball_pos, hoop_pos, custom_roi)

        if self.has_net:
            made = trajectory and net_swish
            if not made and rebound:
                made = False
            elif not made and not trajectory and not net_swish:
                made = False
            elif not made and trajectory and not net_swish:
                made = False
        else:
            made = trajectory and not rebound
            if rebound:
                made = False
            if not trajectory:
                made = False

        return self._build_result(
            pending, frame_count, made, trajectory, net_swish, rebound, forced=forced
        )

    def _trajectory_cross(
        self,
        ball_pos: list,
        ball_snapshot: list,
        hoop_pos: list,
        custom_roi: tuple[int, int, int, int] | None,
    ) -> bool:
        merged = ball_snapshot + [
            p for p in ball_pos if not ball_snapshot or p[1] > ball_snapshot[-1][1]
        ]
        if len(merged) < 1 or len(hoop_pos) < 1:
            return False
        return score(merged, hoop_pos, custom_roi)

    def _build_result(
        self,
        pending: PendingShot,
        frame_count: int,
        made: bool,
        trajectory: bool,
        net_swish: bool,
        rebound: bool,
        *,
        forced: bool = False,
    ) -> dict:
        stats = pending.net_detector.motion_stats()
        return {
            "attempt": pending.attempt_index,
            "frame": frame_count,
            "made": made,
            "result": "Make" if made else "Miss",
            "trajectory_cross": trajectory,
            "net_swish": net_swish,
            "rim_rebound": rebound,
            "has_net_mode": self.has_net,
            "net_motion_peak": stats["peak"],
            "forced": forced,
        }
