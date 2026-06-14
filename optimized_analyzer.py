"""Hoop preview scan and optimized analysis (multi-hoop target zone selection).

Optimized algorithm note: 解决多篮筐检测 — same detection/scoring as avishah3 original;
when multiple hoops appear, user selects a target zone; detections inside the zone
are treated as the target hoop. Intended iOS baseline after Web validation.
"""

from __future__ import annotations

import base64
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
HOOP_ACTIVE_COLOR = (0, 255, 120)
HOOP_DIM_COLOR = (120, 120, 120)


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


def _draw_motion(frame: np.ndarray, ball_pos: list, hoop_pos: list) -> None:
    for point in ball_pos:
        cv2.circle(frame, point[0], 2, BALL_COLOR, 2, cv2.LINE_AA)
    if len(hoop_pos) > 0:
        cv2.circle(frame, hoop_pos[-1][0], 2, (128, 128, 0), 2, cv2.LINE_AA)


def _cluster_hoops(hoops: list[dict], merge_dist: float = 110.0) -> list[dict]:
    clusters: list[dict] = []
    for hoop in hoops:
        matched = None
        for idx, cluster in enumerate(clusters):
            if math.hypot(hoop["cx"] - cluster["cx"], hoop["cy"] - cluster["cy"]) < merge_dist:
                matched = idx
                break
        if matched is None:
            clusters.append({**hoop})
            continue
        cluster = clusters[matched]
        weight = cluster.get("_count", 1)
        new_weight = weight + 1
        cluster["cx"] = int((cluster["cx"] * weight + hoop["cx"]) / new_weight)
        cluster["cy"] = int((cluster["cy"] * weight + hoop["cy"]) / new_weight)
        cluster["w"] = int((cluster["w"] * weight + hoop["w"]) / new_weight)
        cluster["h"] = int((cluster["h"] * weight + hoop["h"]) / new_weight)
        cluster["conf"] = max(cluster["conf"], hoop["conf"])
        cluster["center"] = (cluster["cx"], cluster["cy"])
        cluster["x1"] = cluster["cx"] - cluster["w"] // 2
        cluster["y1"] = cluster["cy"] - cluster["h"] // 2
        cluster["x2"] = cluster["x1"] + cluster["w"]
        cluster["y2"] = cluster["y1"] + cluster["h"]
        cluster["_count"] = new_weight

    for idx, cluster in enumerate(clusters):
        cluster["id"] = idx
        cluster.pop("_count", None)
    return clusters


def _hoop_dict(center, frame_count: int, w: int, h: int, conf: float) -> dict:
    cx, cy = center
    return {
        "center": center,
        "cx": cx,
        "cy": cy,
        "w": w,
        "h": h,
        "conf": conf,
        "x1": cx - w // 2,
        "y1": cy - h // 2,
        "x2": cx + w // 2,
        "y2": cy + h // 2,
    }


def _box_iou(a: dict, b: dict) -> float:
    x1 = max(a["x1"], b["x1"])
    y1 = max(a["y1"], b["y1"])
    x2 = min(a["x2"], b["x2"])
    y2 = min(a["y2"], b["y2"])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    if union <= 0:
        return 0.0
    return inter / union


def _target_zone_from_hoop(
    target_hoop: dict | tuple[int, int, int, int],
    *,
    scale: float = 1.45,
) -> dict:
    if isinstance(target_hoop, tuple):
        cx, cy, w, h = target_hoop
    else:
        cx = int(target_hoop["cx"])
        cy = int(target_hoop["cy"])
        w = int(target_hoop["w"])
        h = int(target_hoop["h"])
    return {
        "cx": cx,
        "cy": cy,
        "half_w": max(int(w * scale / 2), 48),
        "half_h": max(int(h * scale / 2), 48),
    }


def _zone_as_box(zone: dict) -> dict:
    x1 = zone["cx"] - zone["half_w"]
    y1 = zone["cy"] - zone["half_h"]
    x2 = zone["cx"] + zone["half_w"]
    y2 = zone["cy"] + zone["half_h"]
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "w": x2 - x1,
        "h": y2 - y1,
        "cx": zone["cx"],
        "cy": zone["cy"],
    }


def _hoop_in_target_zone(hoop: dict, zone: dict) -> bool:
    """True when a detection lies inside the user-selected target region."""
    zx1 = zone["cx"] - zone["half_w"]
    zy1 = zone["cy"] - zone["half_h"]
    zx2 = zone["cx"] + zone["half_w"]
    zy2 = zone["cy"] + zone["half_h"]
    if zx1 <= hoop["cx"] <= zx2 and zy1 <= hoop["cy"] <= zy2:
        return True
    return _box_iou(hoop, _zone_as_box(zone)) >= 0.12


def _follow_target_zone(zone: dict, in_zone_hoops: list[dict]) -> None:
    if not in_zone_hoops:
        return
    zone["cx"] = int(sum(h["cx"] for h in in_zone_hoops) / len(in_zone_hoops))
    zone["cy"] = int(sum(h["cy"] for h in in_zone_hoops) / len(in_zone_hoops))


def scan_hoops_in_video(
    input_path: str | Path,
    *,
    model_path: str | Path | None = None,
    sample_count: int = 8,
) -> dict:
    input_path = Path(input_path)
    model = get_model(model_path)
    device = get_device()
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {input_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    sample_indices = sorted(
        {
            min(total_frames - 1, max(0, int(total_frames * ratio)))
            for ratio in [0.08, 0.18, 0.28, 0.4, 0.52, 0.64, 0.76, 0.88][:sample_count]
        }
    )

    all_hoops: list[dict] = []
    preview_frame = None
    preview_index = sample_indices[len(sample_indices) // 2] if sample_indices else 0

    for frame_index in sample_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ret, frame = cap.read()
        if not ret:
            continue
        if frame_index == preview_index:
            preview_frame = frame.copy()
        for r in model(frame, stream=True, device=device, verbose=False):
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0]
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                w, h = x2 - x1, y2 - y1
                conf = math.ceil((box.conf[0] * 100)) / 100
                cls = int(box.cls[0])
                if conf > 0.5 and CLASS_NAMES[cls] == "Basketball Hoop":
                    center = (int(x1 + w / 2), int(y1 + h / 2))
                    all_hoops.append(_hoop_dict(center, frame_index, w, h, conf))

    cap.release()
    if preview_frame is None:
        cap = cv2.VideoCapture(str(input_path))
        ret, preview_frame = cap.read()
        cap.release()
        if not ret:
            raise ValueError("Cannot read preview frame")

    hoops = _cluster_hoops(all_hoops)
    preview = preview_frame.copy()
    for hoop in hoops:
        _draw_box_label(
            preview,
            hoop["x1"],
            hoop["y1"],
            hoop["w"],
            hoop["h"],
            f"Hoop {hoop['conf']:.0%}",
            (0, 255, 255),
        )

    ok, encoded = cv2.imencode(".jpg", preview, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        raise RuntimeError("Cannot encode hoop preview")

    return {
        "width": width,
        "height": height,
        "frame_index": preview_index,
        "hoops": hoops,
        "needs_selection": len(hoops) > 1,
        "preview_jpeg_base64": base64.b64encode(encoded.tobytes()).decode("ascii"),
    }


def analyze_video_optimized(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    target_hoop: dict | tuple[int, int, int, int],
    progress_callback: Callable[[int, int], None] | None = None,
    frame_callback: Callable[[np.ndarray, dict], None] | None = None,
    show_gui: bool = False,
    model_path: str | Path | None = None,
) -> dict:
    input_path = Path(input_path)
    model = get_model(model_path)
    device = get_device()
    target_zone = _target_zone_from_hoop(target_hoop)

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
    frame_hoops: list[dict] = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_hoops.clear()
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
                            frame, x1, y1, w, h, f"Ball {conf:.0%}", BALL_COLOR
                        )
                    continue

                if conf > 0.5 and current_class == "Basketball Hoop":
                    frame_hoops.append(_hoop_dict(center, frame_count, w, h, conf))

        in_zone_hoops = [hoop for hoop in frame_hoops if _hoop_in_target_zone(hoop, target_zone)]
        _follow_target_zone(target_zone, in_zone_hoops)

        zone_box = _zone_as_box(target_zone)
        cv2.rectangle(
            frame,
            (zone_box["x1"], zone_box["y1"]),
            (zone_box["x2"], zone_box["y2"]),
            HOOP_ACTIVE_COLOR,
            1,
            cv2.LINE_AA,
        )

        for hoop in in_zone_hoops:
            _draw_box_label(
                frame,
                hoop["x1"],
                hoop["y1"],
                hoop["w"],
                hoop["h"],
                f"Target Hoop {hoop['conf']:.0%}",
                HOOP_ACTIVE_COLOR,
            )

        for hoop in frame_hoops:
            if _hoop_in_target_zone(hoop, target_zone):
                continue
            _draw_box_label(
                frame,
                hoop["x1"],
                hoop["y1"],
                hoop["w"],
                hoop["h"],
                f"Ignored {hoop['conf']:.0%}",
                HOOP_DIM_COLOR,
            )

        if in_zone_hoops:
            primary = max(in_zone_hoops, key=lambda c: (c["conf"], c["w"] * c["h"]))
            hoop_pos.append(
                (primary["center"], frame_count, primary["w"], primary["h"], primary["conf"])
            )

        ball_pos = clean_ball_pos(ball_pos, frame_count)
        if len(hoop_pos) > 1:
            hoop_pos = clean_hoop_pos(hoop_pos)

        _draw_motion(frame, ball_pos, hoop_pos)

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
            "Optimized / Target Zone",
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
        "algorithm": "optimized",
        "target_hoop": [
            target_zone["cx"],
            target_zone["cy"],
            target_zone["half_w"] * 2,
            target_zone["half_h"] * 2,
        ],
        "output_path": str(output_path) if output_path else None,
    }
