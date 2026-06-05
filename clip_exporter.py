"""Export per-shot video clips for download."""

from __future__ import annotations

import zipfile
from pathlib import Path

import cv2


def _create_clip_writer(output_path: Path, fps: float, width: int, height: int) -> cv2.VideoWriter:
    for codec in ("avc1", "mp4v"):
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*codec),
            fps,
            (width, height),
        )
        if writer.isOpened():
            return writer
    raise RuntimeError(f"Cannot create clip writer: {output_path}")


def export_shot_clips(
    video_path: str | Path,
    shots: list[dict],
    clips_dir: str | Path,
    *,
    before_s: float = 3.0,
    after_s: float = 3.0,
) -> list[dict]:
    """Cut annotated (or source) video into one MP4 per shot."""
    video_path = Path(video_path)
    clips_dir = Path(clips_dir)
    clips_dir.mkdir(parents=True, exist_ok=True)

    if not shots:
        return []

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video for clips: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    enriched: list[dict] = []

    for shot in shots:
        event_t = float(shot.get("time_s", 0))
        if event_t <= 0 and shot.get("frame"):
            event_t = float(shot["frame"]) / fps

        start_frame = max(0, int((event_t - before_s) * fps))
        end_frame = int((event_t + after_s) * fps)
        if total_frames > 0:
            end_frame = min(total_frames - 1, end_frame)
        if end_frame < start_frame:
            end_frame = start_frame

        result_label = shot.get("result", "Shot")
        tag = "make" if result_label == "Make" else "miss"
        filename = f"{shot.get('attempt', 0):02d}_{tag}_{event_t:.2f}s.mp4"
        out_path = clips_dir / filename

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        writer = _create_clip_writer(out_path, fps, width, height)

        frame_idx = start_frame
        while frame_idx <= end_frame:
            ret, frame = cap.read()
            if not ret:
                break
            writer.write(frame)
            frame_idx += 1

        writer.release()

        enriched.append(
            {
                **shot,
                "clip_filename": filename,
                "clip_start_s": round(start_frame / fps, 2),
                "clip_end_s": round(end_frame / fps, 2),
            }
        )

    cap.release()
    return enriched


def zip_clips(clips_dir: str | Path, zip_path: str | Path) -> Path:
    clips_dir = Path(clips_dir)
    zip_path = Path(zip_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for clip_file in sorted(clips_dir.glob("*.mp4")):
            archive.write(clip_file, arcname=clip_file.name)

    return zip_path
