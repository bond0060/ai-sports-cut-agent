#!/bin/bash
# 把模型 + Swift 源码同步到你已创建的 Xcode 工程目录
#
# 用法:
#   bash ios-starter/scripts/sync_to_xcode.sh ~/Projects/BasketballShot-iOS
#
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "用法: bash ios-starter/scripts/sync_to_xcode.sh <Xcode工程所在目录>"
  echo "示例: bash ios-starter/scripts/sync_to_xcode.sh ~/Projects/BasketballShot-iOS"
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="$1"
APP_NAME="BasketballShot"

# 常见结构: ~/Projects/BasketballShot-iOS/BasketballShot/
if [[ -d "$DEST/$APP_NAME" ]]; then
  APP_DIR="$DEST/$APP_NAME"
elif [[ -d "$DEST" ]] && [[ -f "$DEST/${APP_NAME}.xcodeproj/project.pbxproj" ]] 2>/dev/null; then
  APP_DIR="$DEST/$APP_NAME"
else
  echo "在 $DEST 下未找到 $APP_NAME 文件夹。"
  echo "请传入 Xcode 保存的工程根目录（包含 .xcodeproj 的那一层）。"
  exit 1
fi

echo "→ 同步到: $APP_DIR"

# Core ML 模型
if [[ -d "$ROOT/best.mlpackage" ]]; then
  rm -rf "$APP_DIR/best.mlpackage"
  cp -R "$ROOT/best.mlpackage" "$APP_DIR/"
  echo "  ✓ best.mlpackage"
else
  echo "  ✗ 未找到 $ROOT/best.mlpackage，请先运行 export_coreml.sh"
fi

# Swift 源码
SRC="$ROOT/ios-starter/BasketballShot"
cp -f "$SRC/AppViewModel.swift" "$APP_DIR/" 2>/dev/null || true
for dir in Models Services Views; do
  mkdir -p "$APP_DIR/$dir"
  cp -f "$SRC/$dir"/*.swift "$APP_DIR/$dir/" 2>/dev/null || true
done

# 覆盖 ContentView
cp -f "$SRC/Views/ContentView.swift" "$APP_DIR/Views/ContentView.swift" 2>/dev/null \
  || cp -f "$SRC/Views/ContentView.swift" "$APP_DIR/ContentView.swift"

echo "  ✓ Swift 文件 (Models, Services, Views)"

# Info 权限提示
PLIST="$APP_DIR/Info.plist"
if [[ ! -f "$PLIST" ]]; then
  PLIST="$DEST/$APP_NAME/Info.plist"
fi

cat <<'EOF'

========================================
请在 Xcode 中手动完成（约 2 分钟）:
========================================
1. 若左侧没有新文件: 右键工程 → Add Files to "BasketballShot"
   → 选中 best.mlpackage 与 Models/Services/Views 文件夹
   → 勾选 Copy items + Add to targets

2. 删除重复的 ContentView.swift（只保留 Views 里那份）

3. Target → Info → 添加相册权限两条（见 START-HERE.md）

4. 连接 iPhone → ⌘R 运行

5. 若编译报错 'best' not found:
   点 best.mlpackage 看 Model Class 名称是否为 best
========================================
EOF

open -a Xcode "$DEST/${APP_NAME}.xcodeproj" 2>/dev/null || true
