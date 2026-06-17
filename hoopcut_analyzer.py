"""HoopCut analysis — original ericbh22/HoopCut_FH logic (detector.py), unmodified."""

from __future__ import annotations

import math
from collections import deque
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from ultralytics import YOLO

from analyzer import _create_video_writer, _draw_hud
from utils import get_device

BASE_DIR = Path(__file__).resolve().parent
BALL_MODEL = BASE_DIR / "models" / "hoopcut" / "ball.pt"
HOOP_MODEL = BASE_DIR / "models" / "hoopcut" / "hoop.pt"

_ball_model: YOLO | None = None
_hoop_model: YOLO | None = None


def _get_ball_model() -> YOLO:
    global _ball_model
    if _ball_model is None:
        if not BALL_MODEL.exists():
            raise FileNotFoundError(
                f"HoopCut ball model missing at {BALL_MODEL}. "
                "Copy from HoopCut_FH/models/best.pt"
            )
        _ball_model = YOLO(str(BALL_MODEL))
    return _ball_model


def _get_hoop_model() -> YOLO:
    global _hoop_model
    if _hoop_model is None:
        if not HOOP_MODEL.exists():
            raise FileNotFoundError(
                f"HoopCut hoop model missing at {HOOP_MODEL}. "
                "Copy from HoopCut_FH/models/hoop.pt"
            )
        _hoop_model = YOLO(str(HOOP_MODEL))
    return _hoop_model


def find_hoop(
    video_path: str | Path,
    *,
    three_point_toggle: bool = True,
) -> tuple[list[int], list[int]]:
    """Original HoopCut find_hoop: first detected hoop rim line in video."""
    model = _get_hoop_model()
    device = get_device()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    y_offset = 10 if three_point_toggle else 3

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        results = model(frame, imgsz=1280, conf=0.33, device=device, verbose=False)
        boxes = results[0].boxes if results else None
        if boxes is None:
            continue
        for box in boxes:
            cls_id = int(box.cls[0])
            if model.names[cls_id] != "hoop":
                continue
            x1, y1, x2, y2 = box.xyxy[0]
            cap.release()
            return [int(x1), int(y1) + y_offset], [int(x2), int(y1) + y_offset]

    cap.release()
    raise ValueError("HoopCut: no hoop detected in video")


def _solve_parabola_y_to_x(a: float, b: float, c: float, y: float) -> list[float]:
    d = c - y
    discriminant = b**2 - 4 * a * d
    if discriminant < 0:
        return []
    if discriminant == 0:
        return [-b / (2 * a)]
    sqrt_disc = math.sqrt(discriminant)
    return [(-b + sqrt_disc) / (2 * a), (-b - sqrt_disc) / (2 * a)]


def ball_intersect_parabola(
    points: list[list[int]],
    hoop_x_1: int,
    hoop_x_2: int,
    hoop_y_1: int,
    hoop_y_2: int,
    rad: float,
) -> bool:
    if len(points) < 3:
        return False
    hoop_mid_y = (hoop_y_1 + hoop_y_2) // 2
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    a, b, c = np.polyfit(np.array(xs), np.array(ys), deg=2)
    x_candidates = _solve_parabola_y_to_x(a, b, c, hoop_mid_y)
    if not x_candidates:
        return False
    positive_x = max(x_candidates)
    return hoop_x_1 + rad < positive_x < hoop_x_2 - rad


def ball_intersect_linear(
    last10: list[list[int]],
    after10: list[list[int]],
    hoop_x_1: int,
    hoop_x_2: int,
    hoop_y_1: int,
    hoop_y_2: int,
) -> bool:
    if not after10 or not last10:
        return False
    hoop_mid_y = (hoop_y_1 + hoop_y_2) // 2
    x1, y1 = last10[-1]
    x2, y2 = after10[0]
    run = x2 - x1
    if run == 0:
        return hoop_x_1 <= x1 <= hoop_x_2
    gradient = (y2 - y1) / run
    x_at_hoop_y = ((hoop_mid_y - y1) / gradient) + x1
    return hoop_x_1 <= x_at_hoop_y <= hoop_x_2


def analyze_video_hoopcut(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    frame_callback: Callable[[np.ndarray, dict], None] | None = None,
    show_gui: bool = False,
) -> dict:
    input_path = Path(input_path)
    device = get_device()
    ball_model = _get_ball_model()
    hoop_point_1, hoop_point_2 = find_hoop(input_path, three_point_toggle=True)

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

    last10: deque[list[int]] = deque(maxlen=10)
    totalshottracking: list[list[int]] = []
    aftershot10: list[list[int]] = []
    frame_count = 0
    makes = 0
    attempts = 0
    crosstime: float | None = None
    first_release = None
    fade_frames = 20
    fade_counter = 0
    overlay_color = (0, 0, 0)
    overlay_text = "Waiting..."
    shot_log: list[dict] = []

    hoop_x_1, hoop_y_1 = hoop_point_1
    hoop_x_2, hoop_y_2 = hoop_point_2
    hoop_y = (hoop_y_1 + hoop_y_2) / 2

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        rad = 12.0
        basketballs_in_frame: list[tuple[list[int], float]] = []

        results = ball_model(frame, imgsz=1280, conf=0.33, device=device, verbose=False)
        boxes = results[0].boxes if results else None
        if boxes is not None:
            for box in boxes:
                cls_id = int(box.cls[0])
                if ball_model.names[cls_id] != "Basketball":
                    continue
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                rad = max(rad, abs(x2 - x1) / 2)
                centre = [int((x1 + x2) / 2), int((y1 + y2) / 2)]
                basketballs_in_frame.append((centre, float(box.conf[0])))

        basketballs_in_frame.sort(key=lambda b: -b[1])

        cv2.line(
            frame,
            (hoop_x_1, hoop_y_1),
            (hoop_x_2, hoop_y_2),
            (0, 255, 255),
            3,
            cv2.LINE_AA,
        )

        if basketballs_in_frame:
            basketballcentre = basketballs_in_frame[0][0]
            bx, by = basketballcentre
            cv2.circle(frame, (bx, by), 8, (0, 0, 255), -1)

            if by < hoop_y:
                if first_release is None:
                    first_release = basketballcentre
                last10.append(basketballcentre)
                totalshottracking.append(basketballcentre)
                crosstime = timestamp
            elif len(last10) >= 1 and crosstime is not None:
                if timestamp - crosstime <= 0.6:
                    aftershot10.append(basketballcentre)
                elif timestamp - crosstime > 0.6:
                    aftershot10.sort(key=lambda b: b[1])
                    made = (
                        ball_intersect_parabola(
                            list(last10),
                            hoop_x_1,
                            hoop_x_2,
                            hoop_y_1,
                            hoop_y_2,
                            rad,
                        )
                        and ball_intersect_parabola(
                            totalshottracking,
                            hoop_x_1,
                            hoop_x_2,
                            hoop_y_1,
                            hoop_y_2,
                            rad,
                        )
                    ) or ball_intersect_linear(
                        list(last10),
                        aftershot10,
                        hoop_x_1,
                        hoop_x_2,
                        hoop_y_1,
                        hoop_y_2,
                    )

                    attempts += 1
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
                            "time_s": round(timestamp, 2),
                            "result": "Make" if made else "Miss",
                            "trajectory_cross": made,
                            "net_swish": False,
                            "rim_rebound": False,
                            "net_motion_peak": 0.0,
                        }
                    )
                    last10.clear()
                    aftershot10.clear()
                    first_release = None
                    totalshottracking.clear()
                    crosstime = None

        if fade_counter == 0 and overlay_text == "Waiting...":
            overlay_text = "Track ball..." if not basketballs_in_frame else "Ready"

        frame = _draw_hud(
            frame, makes, attempts, overlay_text, overlay_color, fade_counter, fade_frames
        )
        if fade_counter > 0:
            fade_counter -= 1

        cv2.putText(
            frame,
            "HoopCut / Linear + Parabola",
            (24, height - 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
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
        "algorithm": "hoopcut",
        "target_hoop": None,
        "output_path": str(output_path) if output_path else None,
    }
