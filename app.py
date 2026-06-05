"""Web server for uploading basketball videos and running shot detection."""

from __future__ import annotations

import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from typing import Optional

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from analyzer import analyze_video
from clip_exporter import export_shot_clips, zip_clips

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

jobs: dict[str, dict] = {}
preview_frames: dict[str, bytes] = {}
jobs_lock = threading.Lock()

app = FastAPI(title="Basketball Shot Detector", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clips_dir(job_id: str) -> Path:
    return OUTPUT_DIR / job_id / "clips"


def _enqueue_job(
    *,
    input_path: Path,
    output_path: Path,
    filename: str,
    custom_roi: tuple[int, int, int, int] | None,
    use_net_swish: bool,
    clip_before_s: float,
    clip_after_s: float,
) -> str:
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
            "filename": filename,
            "created_at": _utc_now(),
            "preview_ready": False,
            "live_stats": {
                "makes": 0,
                "attempts": 0,
                "overlay_text": "Waiting...",
                "frame": 0,
            },
        }

    thread = threading.Thread(
        target=_run_job,
        args=(
            job_id,
            input_path,
            output_path,
            custom_roi,
            use_net_swish,
            clip_before_s,
            clip_after_s,
        ),
        daemon=True,
    )
    thread.start()
    return job_id


def _run_job(
    job_id: str,
    input_path: Path,
    output_path: Path,
    custom_roi: tuple[int, int, int, int] | None = None,
    has_net: bool = True,
    clip_before_s: float = 3.0,
    clip_after_s: float = 3.0,
) -> None:
    def on_progress(current: int, total: int) -> None:
        percent = round(100 * current / total) if total else 0
        with jobs_lock:
            jobs[job_id]["progress"] = percent
            jobs[job_id]["processed_frames"] = current
            jobs[job_id]["total_frames"] = total

    def on_frame(frame, stats: dict) -> None:
        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            return

        preview_frames[job_id] = encoded.tobytes()

        with jobs_lock:
            jobs[job_id]["live_stats"] = {
                "makes": stats["makes"],
                "attempts": stats["attempts"],
                "overlay_text": stats["overlay_text"],
                "frame": stats["frame"],
            }
            jobs[job_id]["preview_ready"] = True

    try:
        with jobs_lock:
            jobs[job_id]["status"] = "processing"
            jobs[job_id]["started_at"] = _utc_now()
            jobs[job_id]["preview_ready"] = False
            jobs[job_id]["live_stats"] = {
                "makes": 0,
                "attempts": 0,
                "overlay_text": "Waiting...",
                "frame": 0,
            }

        result = analyze_video(
            input_path,
            output_path,
            custom_roi=custom_roi,
            has_net=has_net,
            progress_callback=on_progress,
            frame_callback=on_frame,
        )

        shots = result["shots"]
        clips_dir = _clips_dir(job_id)
        clip_source = output_path if output_path.exists() else input_path
        if shots and clip_source.exists():
            shots = export_shot_clips(
                clip_source,
                shots,
                clips_dir,
                before_s=clip_before_s,
                after_s=clip_after_s,
            )
            for shot in shots:
                shot["clip_download_url"] = (
                    f"/api/jobs/{job_id}/clips/{shot['clip_filename']}"
                )
            zip_clips(clips_dir, clips_dir.parent / "clips.zip")

        with jobs_lock:
            jobs[job_id].update(
                {
                    "status": "completed",
                    "progress": 100,
                    "completed_at": _utc_now(),
                    "result": {
                        "makes": result["makes"],
                        "attempts": result["attempts"],
                        "misses": result["misses"],
                        "percentage": result["percentage"],
                        "shots": shots,
                        "video_info": result["video_info"],
                        "has_net": result.get("has_net", has_net),
                        "clip_before_s": clip_before_s,
                        "clip_after_s": clip_after_s,
                        "clips_zip_url": (
                            f"/api/jobs/{job_id}/clips.zip" if shots else None
                        ),
                        "output_url": f"/api/jobs/{job_id}/video",
                    },
                }
            )
    except Exception as exc:
        with jobs_lock:
            jobs[job_id].update(
                {
                    "status": "failed",
                    "completed_at": _utc_now(),
                    "error": str(exc),
                }
            )
    finally:
        preview_frames.pop(job_id, None)


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    roi_x1: Optional[float] = Form(None),
    roi_y1: Optional[float] = Form(None),
    roi_x2: Optional[float] = Form(None),
    roi_y2: Optional[float] = Form(None),
    has_net: Optional[str] = Form("true"),
    clip_before: Optional[float] = Form(3.0),
    clip_after: Optional[float] = Form(3.0),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未选择文件")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的视频格式。请上传: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    custom_roi = None
    if None not in (roi_x1, roi_y1, roi_x2, roi_y2):
        custom_roi = (int(roi_x1), int(roi_y1), int(roi_x2), int(roi_y2))

    use_net_swish = str(has_net or "true").lower() in ("true", "1", "yes", "on")
    clip_before_s = max(0.0, float(clip_before if clip_before is not None else 3.0))
    clip_after_s = max(0.0, float(clip_after if clip_after is not None else 3.0))

    job_id = uuid.uuid4().hex
    input_path = UPLOAD_DIR / f"{job_id}{suffix}"
    output_path = OUTPUT_DIR / f"{job_id}.mp4"

    with input_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    job_id = _enqueue_job(
        input_path=input_path,
        output_path=output_path,
        filename=file.filename,
        custom_roi=custom_roi,
        use_net_swish=use_net_swish,
        clip_before_s=clip_before_s,
        clip_after_s=clip_after_s,
    )
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")

    return job


@app.get("/api/jobs/{job_id}/preview.jpg")
async def get_job_preview(job_id: str):
    data = preview_frames.get(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="预览帧尚未就绪")

    return Response(content=data, media_type="image/jpeg")


@app.get("/api/jobs/{job_id}/video")
async def get_job_video(job_id: str):
    output_path = OUTPUT_DIR / f"{job_id}.mp4"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="输出视频尚未就绪")

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"analysis_{job_id}.mp4",
    )


@app.get("/api/jobs/{job_id}/clips/{filename}")
async def get_job_clip(job_id: str, filename: str):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")

    clip_path = _clips_dir(job_id) / filename
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="片段不存在")

    return FileResponse(
        clip_path,
        media_type="video/mp4",
        filename=filename,
    )


@app.get("/api/jobs/{job_id}/clips.zip")
async def get_job_clips_zip(job_id: str):
    zip_path = OUTPUT_DIR / job_id / "clips.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="片段压缩包尚未就绪")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"shots_{job_id}.zip",
    )
