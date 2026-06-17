# Algorithm model weights

## HoopCut (`models/hoopcut/`)

Copied from [ericbh22/HoopCut_FH](https://github.com/ericbh22/HoopCut_FH):

- `ball.pt` — basketball detection
- `hoop.pt` — hoop/rim detection

## SwishAI (`models/swishai/`)

**Trained baseline (2026-06-17)** — YOLO11s, 5 classes, 31 epochs (early stop).

| File | Description |
|------|-------------|
| `best.pt` | Inference weights (~18 MB, committed for iOS/Web) |
| `SwishAI.mlpackage` | Core ML export (generate locally, gitignored) |

**Validation metrics:** P=0.888, R=0.909, mAP50=0.941, mAP50-95=0.715

**Classes:** Ball, Ball in Basket, Player, Basket, Player Shooting

### Web / Python

```bash
# API: algorithm=swishai
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
```

### iOS Core ML export

```bash
python3 scripts/export_swishai_coreml.py
# → models/swishai/SwishAI.mlpackage
```

See `docs/iOS-SWISHAI-HANDOFF.md` for full iOS integration.

### Retrain / resume

Upstream: [sPappalard/SwishAI](https://github.com/sPappalard/SwishAI)

```bash
git clone --depth 1 https://github.com/sPappalard/SwishAI.git vendor/SwishAI
pip install roboflow
ROBOFLOW_API_KEY=your_key python3 scripts/setup_swishai_model.py
```

Resume from checkpoint:

```bash
python3 -c "
from ultralytics import YOLO
YOLO('vendor/SwishAI/BE/basketball_training/yolo11s_5classes/weights/last.pt').train(resume=True)
"
cp vendor/SwishAI/BE/basketball_training/yolo11s_5classes/weights/best.pt models/swishai/best.pt
```
