#!/usr/bin/env python3
"""Download SwishAI training data and train YOLO11 weights for local inference."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_OUT = ROOT / "models" / "swishai" / "best.pt"
TRAIN_SCRIPT = ROOT / "vendor" / "SwishAI" / "BE" / "train_model.py"


def main() -> int:
    api_key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if not api_key:
        print(
            "SwishAI requires a Roboflow API key to download the training dataset.\n"
            "1. Create a free key at https://app.roboflow.com/settings/api\n"
            "2. Run: ROBOFLOW_API_KEY=your_key python3 scripts/setup_swishai_model.py"
        )
        return 1

    try:
        from roboflow import Roboflow
    except ImportError:
        print("Install roboflow first: pip install roboflow")
        return 1

    be_dir = ROOT / "vendor" / "SwishAI" / "BE"
    if not be_dir.exists():
        print("Clone SwishAI first:")
        print("  git clone --depth 1 https://github.com/sPappalard/SwishAI.git vendor/SwishAI")
        return 1

    os.chdir(be_dir)
    print("Downloading Roboflow dataset basketball-detection-srfkd ...")
    rf = Roboflow(api_key=api_key)
    project = rf.workspace("basketball-6vyfz").project("basketball-detection-srfkd")
    dataset = project.version(1).download("yolov11")
    print(f"Dataset saved to {dataset.location}")

    print("Training YOLO11s (this may take a while)...")
    from ultralytics import YOLO

    data_yaml = Path(dataset.location) / "data.yaml"
    if not data_yaml.exists():
        candidates = list(Path(dataset.location).glob("**/data.yaml"))
        if not candidates:
            print("Could not find data.yaml in downloaded dataset")
            return 1
        data_yaml = candidates[0]

    model = YOLO("yolo11s.pt")
    model.train(
        data=str(data_yaml),
        epochs=int(os.environ.get("SWISHAI_EPOCHS", "50")),
        imgsz=640,
        batch=8,
        project=str(be_dir / "basketball_training"),
        name="yolo11s_5classes",
        patience=20,
        workers=0,
    )

    trained = be_dir / "basketball_training" / "yolo11s_5classes" / "weights" / "best.pt"
    if not trained.exists():
        print(f"Training finished but weights not found at {trained}")
        return 1

    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(trained, MODEL_OUT)
    print(f"SwishAI model ready at {MODEL_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
