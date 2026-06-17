#!/usr/bin/env python3
"""Export trained SwishAI YOLO11 weights to Core ML for iOS."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEIGHTS = ROOT / "models" / "swishai" / "best.pt"
OUT_DIR = ROOT / "models" / "swishai"


def main() -> int:
    if not WEIGHTS.exists():
        print(f"Missing weights: {WEIGHTS}")
        print("Train or copy best.pt into models/swishai/ first.")
        return 1

    try:
        from ultralytics import YOLO
    except ImportError:
        print("Install ultralytics: pip install ultralytics")
        return 1

    print(f"Exporting {WEIGHTS} → Core ML (640×640)...")
    model = YOLO(str(WEIGHTS))
    out = model.export(format="coreml", imgsz=640, nms=True)
    out_path = Path(out)
    target = OUT_DIR / "SwishAI.mlpackage"
    if out_path.resolve() != target.resolve():
        if target.exists():
            import shutil

            shutil.rmtree(target)
        import shutil

        shutil.move(str(out_path), str(target))
        out_path = target

    print(f"Core ML model ready: {out_path}")
    print("Drag SwishAI.mlpackage into your Xcode project.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
