"""Reusable basketball shot detection for CLI and web API."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

import cv2
import cvzone
import numpy as np
from ultralytics import YOLO

from net_motion import NetMotionDetector, draw_net_roi
from shot_verdict import ShotVerdictManager
from utils import (
    clean_ball_pos,
    clean_hoop_pos,
    detect_down,
    detect_up,
    filter_ball_pos_by_roi,
    get_active_roi,
    get_device,
    get_rim_bounds,
    get_up_frame_index,
    in_active_roi,
    in_ball_track_zone,
    normalize_roi,
)

# #region agent log
import json as _json
import time as _time

_DBG_LOG_PATH = "/Users/tiancihuang/Downloads/AI-Basketball-Shot-Detection-Tracker-master/.cursor/debug-5746cf.log"


def _dbg(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    try:
        with open(_DBG_LOG_PATH, "a") as _f:
            _f.write(
                _json.dumps(
                    {
                        "sessionId": "5746cf",
                        "runId": "run1",
                        "hypothesisId": hypothesis_id,
                        "location": location,
                        "message": message,
                        "data": data,
                        "timestamp": int(_time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
# #endregion

CLASS_NAMES = ["Basketball", "Basketball Hoop"]
DEFAULT_MODEL = Path(__file__).resolve().parent / "best.pt"


def _dominant_hoop(candidates: list[dict]) -> dict:
    return max(candidates, key=lambda c: (c["w"] * c["h"] * c["conf"], c["conf"]))


def select_locked_hoop(candidates: list[dict], lock: dict, max_miss: int) -> dict | None:
    """Track one hoop identity across frames.

    Returns the candidate chosen as the primary hoop this frame, or None when the
    locked hoop is temporarily not visible (caller should hold the last ROI).
    """
    if not candidates:
        if lock["center"] is not None:
            lock["miss"] += 1
        return None

    if lock["center"] is None:
        chosen = _dominant_hoop(candidates)
        lock["center"] = chosen["center"]
        lock["w"] = chosen["w"]
        lock["h"] = chosen["h"]
        lock["miss"] = 0
        return chosen

    lx, ly = lock["center"]
    gate = max(2.5 * max(lock["w"], 1), 90)
    nearest = min(
        candidates,
        key=lambda c: (c["center"][0] - lx) ** 2 + (c["center"][1] - ly) ** 2,
    )
    nd = ((nearest["center"][0] - lx) ** 2 + (nearest["center"][1] - ly) ** 2) ** 0.5

    if nd <= gate:
        lock["center"] = nearest["center"]
        lock["w"] = nearest["w"]
        lock["h"] = nearest["h"]
        lock["miss"] = 0
        return nearest

    # Locked hoop not visible this frame: hold briefly, then re-lock to the dominant one.
    lock["miss"] += 1
    if lock["miss"] > max_miss:
        chosen = _dominant_hoop(candidates)
        lock["center"] = chosen["center"]
        lock["w"] = chosen["w"]
        lock["h"] = chosen["h"]
        lock["miss"] = 0
        return chosen
    return None
BALL_COLOR = (0, 0, 255)
HOOP_COLOR = (0, 255, 255)
ROI_COLOR = (0, 220, 255)
TRAJECTORY_COLOR = (0, 140, 255)
SHOT_COOLDOWN_S = 3.0
SHOOTING_TIMEOUT_S = 4.0

_model: YOLO | None = None


def get_model(model_path: str | Path | None = None) -> YOLO:
    global _model
    if _model is None:
        _model = YOLO(str(model_path or DEFAULT_MODEL))
    return _model


def _create_video_writer(output_path: Path, fps: float, width: int, height: int) -> cv2.VideoWriter:
    for codec in ("avc1", "mp4v"):
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*codec),
            fps,
            (width, height),
        )
        if writer.isOpened():
            return writer
    raise RuntimeError("Cannot create output video writer")


def _draw_box_label(
    frame: np.ndarray,
    x1: int,
    y1: int,
    w: int,
    h: int,
    label: str,
    color: tuple[int, int, int],
) -> None:
    cvzone.cornerRect(frame, (x1, y1, w, h), colorC=color, colorR=color)
    cv2.rectangle(frame, (x1, y1 - 28), (x1 + len(label) * 14 + 12, y1), color, -1)
    cv2.putText(
        frame,
        label,
        (x1 + 6, y1 - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 0, 0),
        2,
    )


def _draw_roi(
    frame: np.ndarray,
    hoop_pos: list,
    custom_roi: tuple[int, int, int, int] | None = None,
) -> None:
    roi = get_active_roi(hoop_pos, custom_roi)
    if roi is None:
        return

    x1, y1, x2, y2 = roi
    h, w = frame.shape[:2]
    x1 = max(0, min(x1, w - 1))
    x2 = max(0, min(x2, w - 1))
    y1 = max(0, min(y1, h - 1))
    y2 = max(0, min(y2, h - 1))

    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), ROI_COLOR, -1)
    frame[:] = cv2.addWeighted(frame, 0.82, overlay, 0.18, 0)
    cv2.rectangle(frame, (x1, y1), (x2, y2), ROI_COLOR, 3, cv2.LINE_AA)

    if len(hoop_pos) > 0:
        rim_y, rim_x1, rim_x2, _ = get_rim_bounds(hoop_pos)
        cv2.line(
            frame,
            (int(rim_x1), int(rim_y)),
            (int(rim_x2), int(rim_y)),
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    label = "Custom ROI" if custom_roi is not None else "Auto ROI"
    cv2.putText(
        frame,
        label,
        (x1 + 8, max(y1 + 28, 24)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        ROI_COLOR,
        2,
        cv2.LINE_AA,
    )

def _draw_trajectory(
    frame: np.ndarray,
    ball_pos: list,
    hoop_pos: list,
    custom_roi: tuple[int, int, int, int] | None = None,
) -> None:
    roi_ball_pos = filter_ball_pos_by_roi(ball_pos, hoop_pos, custom_roi)

    if len(roi_ball_pos) > 1:
        points = np.array([point[0] for point in roi_ball_pos], dtype=np.int32)
        cv2.polylines(frame, [points], False, TRAJECTORY_COLOR, 3, cv2.LINE_AA)

    for index, point in enumerate(roi_ball_pos):
        radius = 5 if index == len(roi_ball_pos) - 1 else 3
        cv2.circle(frame, point[0], radius, BALL_COLOR, -1, cv2.LINE_AA)

    if len(hoop_pos) > 0:
        center = hoop_pos[-1][0]
        cv2.circle(frame, center, 8, HOOP_COLOR, 2, cv2.LINE_AA)
        cv2.circle(frame, center, 3, HOOP_COLOR, -1, cv2.LINE_AA)


def _draw_hud(
    frame: np.ndarray,
    makes: int,
    attempts: int,
    overlay_text: str,
    overlay_color: tuple[int, int, int],
    fade_counter: int,
    fade_frames: int,
) -> np.ndarray:
    score_text = f"{makes} / {attempts}"
    cv2.putText(
        frame, score_text, (50, 125), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 255, 255), 6, cv2.LINE_AA
    )
    cv2.putText(
        frame, score_text, (50, 125), cv2.FONT_HERSHEY_SIMPLEX, 3, (0, 0, 0), 3, cv2.LINE_AA
    )

    text_width, _ = cv2.getTextSize(overlay_text, cv2.FONT_HERSHEY_SIMPLEX, 3, 6)[0]
    text_x = frame.shape[1] - text_width - 40
    cv2.putText(
        frame,
        overlay_text,
        (text_x, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        3,
        overlay_color,
        6,
        cv2.LINE_AA,
    )

    if fade_counter > 0:
        alpha = 0.2 * (fade_counter / fade_frames)
        frame = cv2.addWeighted(
            frame, 1 - alpha, np.full_like(frame, overlay_color), alpha, 0
        )

    return frame


def analyze_video(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    custom_roi: tuple[int, int, int, int] | None = None,
    has_net: bool = True,
    algorithm: str = "optimized",
    target_hoop: tuple[int, int, int, int] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    frame_callback: Callable[[np.ndarray, dict], None] | None = None,
    show_gui: bool = False,
    model_path: str | Path | None = None,
) -> dict:
    from original_analyzer import analyze_video_original
    from optimized_analyzer import analyze_video_optimized

    if algorithm == "original":
        return analyze_video_original(
            input_path,
            output_path,
            progress_callback=progress_callback,
            frame_callback=frame_callback,
            show_gui=show_gui,
            model_path=model_path,
        )

    if algorithm == "optimized":
        if target_hoop is None:
            raise ValueError("Optimized mode requires a target hoop selection")
        return analyze_video_optimized(
            input_path,
            output_path,
            target_hoop=target_hoop,
            progress_callback=progress_callback,
            frame_callback=frame_callback,
            show_gui=show_gui,
            model_path=model_path,
        )

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Video not found: {input_path}")

    model = get_model(model_path)
    device = get_device()

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    shot_cooldown_frames = max(int(fps * SHOT_COOLDOWN_S), 1)

    if custom_roi is not None:
        custom_roi = normalize_roi(custom_roi, width, height)

    writer = None
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = _create_video_writer(output_path, fps, width, height)

    ball_pos: list = []
    hoop_pos: list = []
    frame_count = 0
    makes = 0
    attempts = 0
    up = False
    down = False
    up_frame = 0
    down_frame = 0
    last_attempt_frame = -shot_cooldown_frames
    fade_frames = 20
    fade_counter = 0
    overlay_color = (0, 0, 0)
    overlay_text = "Waiting..."
    shot_log: list[dict] = []
    roi_ready = custom_roi is not None
    verdict_mgr = ShotVerdictManager(fps, has_net=has_net)
    net_detector_viz = NetMotionDetector() if has_net else None
    is_shooting = False
    shooting_release_frame = -9999
    sequence_fired = False
    hoop_lock: dict = {"center": None, "w": 0, "h": 0, "miss": 0}
    hoop_max_miss = max(int(fps * 1.0), 10)
    def _status_overlay() -> str:
        if verdict_mgr.pending is not None:
            return "Verifying..."
        if len(hoop_pos) < 1:
            return "Find hoop..."
        if len(ball_pos) < 1:
            return "Track ball..."
        if up and not down:
            return "Shot up"
        if up and down:
            return "Shot down"
        return "Ready"

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame, stream=True, device=device, verbose=False)
        hoop_candidates: list[dict] = []
        ball_candidates: list[dict] = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0]
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                w, h = x2 - x1, y2 - y1
                conf = math.ceil((box.conf[0] * 100)) / 100
                cls = int(box.cls[0])
                current_class = CLASS_NAMES[cls]
                center = (int(x1 + w / 2), int(y1 + h / 2))

                if conf > 0.5 and current_class == "Basketball Hoop":
                    if roi_ready and not in_active_roi(center, custom_roi=custom_roi):
                        continue
                    hoop_candidates.append(
                        {
                            "x1": x1,
                            "y1": y1,
                            "w": w,
                            "h": h,
                            "conf": conf,
                            "center": center,
                        }
                    )
                    continue

                if current_class == "Basketball":
                    ball_candidates.append(
                        {
                            "x1": x1,
                            "y1": y1,
                            "w": w,
                            "h": h,
                            "conf": conf,
                            "center": center,
                        }
                    )

        # Track a single locked hoop identity across frames (stable primary).
        prev_hoop_center = hoop_pos[-1][0] if len(hoop_pos) > 0 else None
        primary_hoop = select_locked_hoop(hoop_candidates, hoop_lock, hoop_max_miss)
        if primary_hoop is not None:
            # #region agent log
            _chosen_c = primary_hoop["center"]
            _jump = (
                ((_chosen_c[0] - prev_hoop_center[0]) ** 2 + (_chosen_c[1] - prev_hoop_center[1]) ** 2) ** 0.5
                if prev_hoop_center is not None
                else 0.0
            )
            if len(hoop_candidates) >= 2 or _jump > 60:
                _dbg(
                    "A",
                    "analyzer.py:307",
                    "hoop candidate selection",
                    {
                        "frame": frame_count,
                        "n_candidates": len(hoop_candidates),
                        "candidates": [
                            {"cx": c["center"][0], "cy": c["center"][1], "area": c["w"] * c["h"], "conf": c["conf"]}
                            for c in hoop_candidates
                        ],
                        "chosen_cx": _chosen_c[0],
                        "chosen_cy": _chosen_c[1],
                        "prev_cx": prev_hoop_center[0] if prev_hoop_center else None,
                        "prev_cy": prev_hoop_center[1] if prev_hoop_center else None,
                        "jump_px": round(_jump, 1),
                    },
                )
            # #endregion
            hoop_pos.append(
                (
                    primary_hoop["center"],
                    frame_count,
                    primary_hoop["w"],
                    primary_hoop["h"],
                    primary_hoop["conf"],
                )
            )
            _draw_box_label(
                frame,
                primary_hoop["x1"],
                primary_hoop["y1"],
                primary_hoop["w"],
                primary_hoop["h"],
                f"Hoop {primary_hoop['conf']:.0%}",
                HOOP_COLOR,
            )
        # #region agent log
        elif len(hoop_pos) > 0:
            _dbg(
                "B",
                "analyzer.py:330",
                "locked hoop not visible this frame; ROI holds last position",
                {
                    "frame": frame_count,
                    "n_candidates": len(hoop_candidates),
                    "stale_cx": hoop_pos[-1][0][0],
                    "stale_cy": hoop_pos[-1][0][1],
                    "stale_age_frames": frame_count - hoop_pos[-1][1],
                    "lock_miss": hoop_lock["miss"],
                },
            )
        # #endregion

        for ball in ball_candidates:
            center = ball["center"]
            conf = ball["conf"]
            if roi_ready and not in_ball_track_zone(
                center,
                hoop_pos=hoop_pos,
                custom_roi=custom_roi,
                frame_width=width,
                frame_height=height,
            ):
                continue
            if not roi_ready and len(hoop_pos) > 0 and not in_ball_track_zone(
                center,
                hoop_pos=hoop_pos,
                custom_roi=custom_roi,
                frame_width=width,
                frame_height=height,
            ):
                continue

            min_conf = 0.15 if roi_ready or (
                len(hoop_pos) > 0
                and in_active_roi(center, hoop_pos=hoop_pos, custom_roi=custom_roi)
            ) else 0.3
            if conf >= min_conf:
                ball_pos.append((center, frame_count, ball["w"], ball["h"], conf))
                _draw_box_label(
                    frame,
                    ball["x1"],
                    ball["y1"],
                    ball["w"],
                    ball["h"],
                    f"Ball {conf:.0%}",
                    BALL_COLOR,
                )

        ball_pos = clean_ball_pos(
            ball_pos, frame_count, hoop_pos, custom_roi, width, height
        )
        if len(hoop_pos) > 1:
            hoop_pos = clean_hoop_pos(hoop_pos, custom_roi)

        if roi_ready or len(hoop_pos) > 0:
            _draw_roi(frame, hoop_pos, custom_roi)

        _draw_trajectory(frame, ball_pos, hoop_pos, custom_roi)

        if has_net and len(hoop_pos) > 0:
            if verdict_mgr.pending is not None:
                draw_net_roi(frame, hoop_pos, verdict_mgr.pending.net_detector)
            else:
                net_detector_viz = net_detector_viz or NetMotionDetector()
                net_detector_viz.update(frame, hoop_pos)
                draw_net_roi(frame, hoop_pos, net_detector_viz)

        pending_result = verdict_mgr.update(
            frame, frame_count, ball_pos, hoop_pos, custom_roi
        )
        if verdict_mgr.pending is not None:
            sequence_fired = False

        if pending_result is not None:
            sequence_fired = False
            if pending_result["made"]:
                makes += 1
                overlay_color = (0, 255, 0)
                overlay_text = "Make"
            else:
                overlay_color = (255, 0, 0)
                overlay_text = "Miss"
            fade_counter = fade_frames
            shot_log.append(
                {
                    "attempt": pending_result["attempt"],
                    "frame": pending_result["frame"],
                    "time_s": round(pending_result["frame"] / fps, 2),
                    "result": pending_result["result"],
                    "trajectory_cross": pending_result["trajectory_cross"],
                    "net_swish": pending_result["net_swish"],
                    "rim_rebound": pending_result["rim_rebound"],
                    "net_motion_peak": pending_result["net_motion_peak"],
                }
            )

        tracking_ready = roi_ready or len(hoop_pos) > 0
        if (
            verdict_mgr.pending is None
            and tracking_ready
            and len(ball_pos) > 0
            and (roi_ready or len(hoop_pos) > 0)
        ):
            if not up:
                if detect_up(ball_pos, hoop_pos, custom_roi, width, height):
                    up = True
                    up_frame = ball_pos[-1][1]
                    is_shooting = True
                    shooting_release_frame = frame_count

            if len(ball_pos) >= 2:
                dy = ball_pos[-1][0][1] - ball_pos[-2][0][1]
                if dy < -4:
                    is_shooting = True
                    shooting_release_frame = frame_count

            if up and not down:
                down = detect_down(ball_pos, hoop_pos, custom_roi, width, height)
                if down:
                    down_frame = ball_pos[-1][1]

            if not up:
                early_up = get_up_frame_index(
                    ball_pos, hoop_pos, custom_roi, width, height
                )
                down_now = detect_down(ball_pos, hoop_pos, custom_roi, width, height)
                if down_now and early_up is not None:
                    up = True
                    up_frame = early_up
                    down = True
                    down_frame = ball_pos[-1][1]
                    is_shooting = True

            if is_shooting and frame_count - shooting_release_frame > int(
                fps * SHOOTING_TIMEOUT_S
            ):
                is_shooting = False

            cooldown_ok = frame_count - last_attempt_frame >= shot_cooldown_frames
            sequence_ok = up and down and up_frame < down_frame
            if not sequence_ok:
                sequence_fired = False

            if (
                sequence_ok
                and cooldown_ok
                and not sequence_fired
                and len(hoop_pos) > 0
            ):
                attempts += 1
                last_attempt_frame = frame_count
                sequence_fired = True
                overlay_text = "Verifying..."
                overlay_color = (0, 200, 255)
                verdict_mgr.start_pending(attempts, frame_count, ball_pos, hoop_pos)
                up = False
                down = False
                is_shooting = False

        if fade_counter == 0 and overlay_text in (
            "Waiting...",
            "Ready",
            "Track ball...",
            "Find hoop...",
            "Shot up",
            "Shot down",
        ):
            overlay_text = _status_overlay()

        frame = _draw_hud(
            frame, makes, attempts, overlay_text, overlay_color, fade_counter, fade_frames
        )
        cv2.putText(
            frame,
            "Optimized Algorithm",
            (24, height - 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        if fade_counter > 0:
            fade_counter -= 1

        if writer is not None:
            writer.write(frame)

        if frame_callback is not None:
            frame_callback(
                frame,
                {
                    "frame": frame_count,
                    "makes": makes,
                    "attempts": attempts,
                    "overlay_text": overlay_text,
                },
            )

        if show_gui:
            cv2.imshow("Frame", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        frame_count += 1
        if progress_callback and total_frames > 0:
            progress_callback(frame_count, total_frames)

    flush_result = verdict_mgr.flush(frame_count, ball_pos, hoop_pos, custom_roi)
    if flush_result is not None:
        if flush_result["made"]:
            makes += 1
        shot_log.append(
            {
                "attempt": flush_result["attempt"],
                "frame": flush_result["frame"],
                "time_s": round(flush_result["frame"] / fps, 2),
                "result": flush_result["result"],
                "trajectory_cross": flush_result["trajectory_cross"],
                "net_swish": flush_result["net_swish"],
                "rim_rebound": flush_result["rim_rebound"],
                "net_motion_peak": flush_result["net_motion_peak"],
            }
        )

    cap.release()
    if writer is not None:
        writer.release()
    if show_gui:
        cv2.destroyAllWindows()

    misses = attempts - makes
    percentage = round(100 * makes / attempts, 1) if attempts else 0.0

    return {
        "makes": makes,
        "attempts": attempts,
        "misses": misses,
        "percentage": percentage,
        "shots": shot_log,
        "video_info": {
            "width": width,
            "height": height,
            "fps": round(fps, 2),
            "total_frames": total_frames,
            "duration_s": round(total_frames / fps, 1) if fps else 0,
        },
        "custom_roi": list(custom_roi) if custom_roi else None,
        "has_net": has_net,
        "algorithm": "optimized",
        "output_path": str(output_path) if output_path else None,
    }
