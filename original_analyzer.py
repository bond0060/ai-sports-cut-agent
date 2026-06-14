"""Web-compatible port of the original avishah3 shot detection loop."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

import cv2
import cvzone
import numpy as np

from analyzer import _create_video_writer, _draw_hud, get_model
from original_utils import (
    clean_ball_pos,
    clean_hoop_pos,
    detect_down,
    detect_up,
    in_hoop_region,
    score,
)
from utils import get_device

CLASS_NAMES = ["Basketball", "Basketball Hoop"]
BALL_COLOR = (0, 0, 255)
HOOP_COLOR = (0, 255, 255)


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


def _draw_original_motion(frame: np.ndarray, ball_pos: list, hoop_pos: list) -> None:
    for point in ball_pos:
        cv2.circle(frame, point[0], 2, BALL_COLOR, 2, cv2.LINE_AA)

    if len(hoop_pos) > 0:
        cv2.circle(frame, hoop_pos[-1][0], 2, (128, 128, 0), 2, cv2.LINE_AA)


def analyze_video_original(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    frame_callback: Callable[[np.ndarray, dict], None] | None = None,
    show_gui: bool = False,
    model_path: str | Path | None = None,
) -> dict:
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
    fade_frames = 20
    fade_counter = 0
    overlay_color = (0, 0, 0)
    overlay_text = "Waiting..."
    shot_log: list[dict] = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame, stream=True, device=device, verbose=False)
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0]
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                w, h = x2 - x1, y2 - y1
                conf = math.ceil((box.conf[0] * 100)) / 100
                cls = int(box.cls[0])
                current_class = CLASS_NAMES[cls]
                center = (int(x1 + w / 2), int(y1 + h / 2))

                if current_class == "Basketball":
                    if conf > 0.3 or (
                        len(hoop_pos) > 0 and in_hoop_region(center, hoop_pos) and conf > 0.15
                    ):
                        ball_pos.append((center, frame_count, w, h, conf))
                        _draw_box_label(
                            frame,
                            x1,
                            y1,
                            w,
                            h,
                            f"Ball {conf:.0%}",
                            BALL_COLOR,
                        )

                if conf > 0.5 and current_class == "Basketball Hoop":
                    hoop_pos.append((center, frame_count, w, h, conf))
                    _draw_box_label(
                        frame,
                        x1,
                        y1,
                        w,
                        h,
                        f"Hoop {conf:.0%}",
                        HOOP_COLOR,
                    )

        ball_pos = clean_ball_pos(ball_pos, frame_count)
        if len(hoop_pos) > 1:
            hoop_pos = clean_hoop_pos(hoop_pos)

        _draw_original_motion(frame, ball_pos, hoop_pos)

        if len(hoop_pos) > 0 and len(ball_pos) > 0:
            if not up:
                up = detect_up(ball_pos, hoop_pos)
                if up:
                    up_frame = ball_pos[-1][1]

            if up and not down:
                down = detect_down(ball_pos, hoop_pos)
                if down:
                    down_frame = ball_pos[-1][1]

            if frame_count % 10 == 0 and up and down and up_frame < down_frame:
                attempts += 1
                made = score(ball_pos, hoop_pos)
                if made:
                    makes += 1
                    overlay_color = (0, 255, 0)
                    overlay_text = "Make"
                else:
                    overlay_color = (255, 0, 0)
                    overlay_text = "Miss"
                fade_counter = fade_frames
                shot_log.append(
                    {
                        "attempt": attempts,
                        "frame": frame_count,
                        "time_s": round(frame_count / fps, 2),
                        "result": "Make" if made else "Miss",
                        "trajectory_cross": made,
                        "net_swish": False,
                        "rim_rebound": False,
                        "net_motion_peak": 0.0,
                    }
                )
                up = False
                down = False

        if fade_counter == 0 and overlay_text == "Waiting...":
            if len(hoop_pos) < 1:
                overlay_text = "Find hoop..."
            elif len(ball_pos) < 1:
                overlay_text = "Track ball..."
            else:
                overlay_text = "Ready"

        frame = _draw_hud(
            frame, makes, attempts, overlay_text, overlay_color, fade_counter, fade_frames
        )
        if fade_counter > 0:
            fade_counter -= 1

        cv2.putText(
            frame,
            "Original Algorithm",
            (24, height - 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

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
        "custom_roi": None,
        "has_net": False,
        "algorithm": "original",
        "output_path": str(output_path) if output_path else None,
    }
