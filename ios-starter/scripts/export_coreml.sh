#!/bin/bash
# 在仓库根目录执行: bash ios-starter/scripts/export_coreml.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ ! -f best.pt ]]; then
  echo "错误: 未找到 best.pt"
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install "numpy>=1.26" coremltools

python -c "from ultralytics import YOLO; YOLO('best.pt').export(format='coreml', imgsz=640)"

echo ""
echo "完成。请将生成的 *.mlpackage 拖入 Xcode 工程。"
ls -d *.mlpackage 2>/dev/null || ls -d best.mlpackage 2>/dev/null || true
