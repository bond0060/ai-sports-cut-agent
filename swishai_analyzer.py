"""SwishAI-style analysis: 5-class YOLO + shot/basket cooldown scoring.

Ported from sPappalard/SwishAI (BE/app.py) for web A/B testing.
Requires trained weights at models/swishai/best.pt — run scripts/setup_swishai_model.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from ultralytics import YOLO

from analyzer import _create_video_writer, _draw_hud
from utils import get_device

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "swishai" / "best.pt"

THRESHOLDS = {
    0: 0.6,
    1: 0.25,
    2: 0.7,
    3: 0.7,
    4: 0.77,
}

COLORS = {
    0: (0, 165, 255),
    1: (0, 215, 255),
    2: (0, 255, 0),
    3: (0, 0, 255),
    4: (255, 100, 0),
}

CLASSES = {
    0: "Ball",
    1: "Ball in Basket",
    2: "Player",
    3: "Basket",
    4: "Player Shooting",
}

SHOT_COOLDOWN_S = 1.5
BASKET_COOLDOWN_S = 2.0

_model: YOLO | None = None


def _get_model() -> YOLO:
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"SwishAI model missing at {MODEL_PATH}. "
                "Run: python3 scripts/setup_swishai_model.py (requires ROBOFLOW_API_KEY)"
            )
        _model = YOLO(str(MODEL_PATH))
    return _model


class _GameStats:
    def __init__(self, fps: float):
        self.fps = fps
        self.shots_attempted = 0
        self.baskets_made = 0
        self.shot_cooldown_frames = int(fps * SHOT_COOLDOWN_S)
        self.basket_cooldown_frames = int(fps * BASKET_COOLDOWN_S)
        self.last_shot_frame = -self.shot_cooldown_frames
        self.last_basket_frame = -self.basket_cooldown_frames
        self.last_known_basket_pos = None
        self.pending_make_frame: int | None = None

    def register_shot(self, frame_idx: int) -> bool:
        if frame_idx - self.last_shot_frame >= self.shot_cooldown_frames:
            self.shots_attempted += 1
            self.last_shot_frame = frame_idx
            return True
        return False

    def register_basket(self, frame_idx: int, position=None) -> bool:
        if frame_idx - self.last_basket_frame >= self.basket_cooldown_frames:
            if (frame_idx - self.last_shot_frame) > (self.shot_cooldown_frames * 2):
                self.shots_attempted += 1
                self.last_shot_frame = frame_idx
            self.baskets_made += 1
            self.last_basket_frame = frame_idx
            self.pending_make_frame = frame_idx
            return True
        return False


def analyze_video_swishai(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    frame_callback: Callable[[np.ndarray, dict], None] | None = None,
    show_gui: bool = False,
) -> dict:
    input_path = Path(input_path)
    model = _get_model()
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

    stats = _GameStats(fps)
    frame_count = 0
    fade_frames = 20
    fade_counter = 0
    overlay_color = (0, 0, 0)
    overlay_text = "Waiting..."
    shot_log: list[dict] = []
    last_logged_attempt = 0
    last_logged_make = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model.track(
            frame,
            persist=True,
            verbose=False,
            conf=0.25,
            tracker="bytetrack.yaml",
            imgsz=640,
            device=device,
        )

        boxes = results[0].boxes if results else None
        if boxes is not None:
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                if conf < THRESHOLDS.get(cls, 0.3):
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

                color = COLORS.get(cls, (255, 255, 255))
                label = f"{CLASSES.get(cls, cls)} {conf:.0%}"
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(
                    frame,
                    label,
                    (x1, max(y1 - 8, 16)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    2,
                    cv2.LINE_AA,
                )

                if cls == 3:
                    stats.last_known_basket_pos = (cx, cy)
                elif cls == 4 and stats.register_shot(frame_count):
                    if stats.shots_attempted > last_logged_attempt:
                        last_logged_attempt = stats.shots_attempted
                        overlay_text = "Shot"
                        overlay_color = (255, 200, 0)
                        fade_counter = fade_frames // 2
                elif cls == 1 and stats.register_basket(frame_count, (cx, cy)):
                    if stats.baskets_made > last_logged_make:
                        last_logged_make = stats.baskets_made
                        overlay_color = (0, 255, 0)
                        overlay_text = "Make"
                        fade_counter = fade_frames
                        shot_log.append(
                            {
                                "attempt": stats.baskets_made,
                                "frame": frame_count,
                                "time_s": round(frame_count / fps, 2),
                                "result": "Make",
                                "trajectory_cross": True,
                                "net_swish": True,
                                "rim_rebound": False,
                                "net_motion_peak": 0.0,
                            }
                        )

        attempts = stats.shots_attempted
        makes = stats.baskets_made
        misses = max(0, attempts - makes)

        if fade_counter == 0 and overlay_text in ("Waiting...", "Shot"):
            overlay_text = "Ready"

        frame = _draw_hud(
            frame, makes, attempts, overlay_text, overlay_color, fade_counter, fade_frames
        )
        if fade_counter > 0:
            fade_counter -= 1

        cv2.putText(
            frame,
            f"SwishAI / FG {makes}/{attempts}",
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

    attempts = stats.shots_attempted
    makes = stats.baskets_made
    misses = attempts - makes
    percentage = round(100 * makes / attempts, 1) if attempts else 0.0

    for idx in range(len(shot_log), makes):
        shot_log.append(
            {
                "attempt": idx + 1,
                "frame": 0,
                "time_s": 0.0,
                "result": "Make",
                "trajectory_cross": True,
                "net_swish": True,
                "rim_rebound": False,
                "net_motion_peak": 0.0,
            }
        )

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
        "algorithm": "swishai",
        "target_hoop": None,
        "output_path": str(output_path) if output_path else None,
    }
