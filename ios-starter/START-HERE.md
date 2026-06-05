# iOS 测试版 — 第 1 天起步（已有 Xcode + 开发者账号）

按顺序完成下面步骤。每步预计时间已标注。

---

## 第 0 步：确认材料在同一台 Mac 上

确保本仓库在 **装 Xcode 的这台 Mac** 上，且存在：

- `best.pt`
- `docs/iOS-PROJECT-HANDOFF.md`
- `ios-starter/` 目录（本文件夹内的 Swift 起步代码）

---

## 第 1 步：导出 Core ML 模型（约 15 分钟）

在终端执行（**务必用虚拟环境**，避免系统 Python 缺依赖）：

```bash
cd /path/to/AI-Basketball-Shot-Detection-Tracker-master

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install "numpy>=1.26" coremltools

yolo export model=best.pt format=coreml imgsz=640
```

成功后根目录会出现类似 **`best.mlpackage`** 的文件夹。

验证：

```bash
ls -la best.mlpackage
```

> 若 `yolo` 命令找不到：`pip install ultralytics` 后重试，或用  
> `python -c "from ultralytics import YOLO; YOLO('best.pt').export(format='coreml', imgsz=640)"`

**记下**：导出后类名、输入尺寸以 Xcode 里模型预览为准（一般为 640×640）。

---

## 第 2 步：用 Python 生成对照答案（约 5 分钟）

```bash
source .venv/bin/activate
python3 -c "
from analyzer import analyze_video
r = analyze_video('video_test_5.mp4', has_net=True)
print('=== Summary ===')
print(r['makes'], '/', r['attempts'])
for s in r['shots'][:5]:
    print(s)
print('... total shots:', len(r['shots']))
"
```

把输出保存到笔记，iOS 跑通后要对比。

---

## 第 3 步：创建 Xcode 工程（约 20 分钟）

1. 打开 **Xcode** → **File → New → Project**
2. 选 **iOS → App** → Next
3. 填写：
   - **Product Name**: `BasketballShot`
   - **Team**: 你的开发者账号
   - **Organization Identifier**: `com.你的名字`（例 `com.tianci.basketballshot`）
   - **Interface**: SwiftUI
   - **Language**: Swift
   - 不勾选 Core Data / Tests（测试版可后加）
4. 保存到：与 Python 仓库**并列**的目录，例如  
   `~/Projects/BasketballShot-iOS/`  
   （不要保存在 Python 的 `uploads/` 里）

5. **Signing**：选中工程 Target → **Signing & Capabilities** → Team 选你的账号，勾选 **Automatically manage signing**

6. **真机**：iPhone 用数据线连接 → 顶部设备选你的 iPhone → 若提示信任开发者，在手机上同意

---

## 第 4 步：加入 Core ML 模型（约 5 分钟）

1. 将 **`best.mlpackage`** 拖进 Xcode 左侧工程导航（勾上 **Copy items if needed**、Target 勾选 BasketballShot）
2. 点击模型文件，右侧 **Preview** 可看输入输出
3. Xcode 会自动生成 Swift 类名（常见为 `best` 或 `Best`），后面代码里要用这个名字

---

## 第 5 步：加入起步 Swift 代码（约 15 分钟）

把本目录 `ios-starter/BasketballShot/` 下所有 `.swift` 文件拖入 Xcode 工程（与 `ContentView.swift` 同级或建 Groups）：

- `BasketballShotApp.swift` — 若与 Xcode 自动生成冲突，**保留 Xcode 的 App 入口**，只合并我们写的 `ContentView` 逻辑
- `Models/ShotRecord.swift`
- `Models/AppConstants.swift`
- `Services/CoreMLDetector.swift` — 需按你的 `.mlpackage` 类名改一行
- `Views/ContentView.swift` — **替换** 默认 ContentView
- `Views/VideoPicker.swift`

**操作**：删除 Xcode 自带的空 `ContentView.swift` 内容，用我们提供的替换；或删除原文件后拖入新文件。

---

## 第 6 步：配置隐私权限（必做）

在 Target → **Info** 中添加（或编辑 `Info.plist`）：

| Key | 中文说明（Value 填用户可见文案） |
|-----|----------------------------------|
| Privacy - Photo Library Usage Description | 需要访问相册以选择篮球视频进行分析 |
| Privacy - Photo Library Additions Usage Description | 需要保存投篮片段到您的相册 |

---

## 第 7 步：第一次运行（约 10 分钟）

1. 选择 **iPhone 真机**（模拟器无法测真实相册视频）
2. **Product → Run** (⌘R)
3. 预期界面：
   - 标题「篮球投篮检测」
   - 按钮「选择视频」
   - 选一段短视频后显示文件名
   - 「开始分析」暂时显示占位结果（检测逻辑待接 Core ML）

若编译报错 `Cannot find type 'best' in scope`：打开 `CoreMLDetector.swift`，把模型类名改成 Xcode 里 `.mlpackage` 生成的名字。

---

## 第 8 步：本周开发顺序（路线图）

| 顺序 | 任务 | 参考 Python |
|------|------|-------------|
| ① | `CoreMLDetector` 单帧检测 + 画框预览 | `analyzer.py` 检测循环 |
| ② | `VideoFrameReader` 用 AVAssetReader 逐帧 | — |
| ③ | 移植 `ShotTracker`（up/down、attempt） | `utils.py` + `analyzer.py` |
| ④ | `score()` 判 Make/Miss | `utils.score` |
| ⑤ | `ClipExporter` 裁切保存相册 | `clip_exporter.py` |
| ⑥ | 可选 ROI 框选 | Web `RoiSelector` |
| ⑦ | 可选 Net Swish | `net_motion.py` |

详细算法见：`docs/iOS-PROJECT-HANDOFF.md` 第 7 节。

---

## 第 9 步：验收测试版

- [ ] 真机选 30s～1min 视频能跑完不崩溃  
- [ ] 检测框能在预览/日志里看到球和筐  
- [ ] attempts 数量与 Python 同视频「同一数量级」  
- [ ] 至少导出 1 个片段到相册  

---

## 遇到问题

| 现象 | 处理 |
|------|------|
| 模型导出失败 | 用本文第 1 步 venv + 升级 numpy |
| Signing 失败 | Xcode → Settings → Accounts 登录 Apple ID |
| 真机无法安装 | iPhone 设置 → 通用 → VPN与设备管理 → 信任开发者 |
| Core ML 类名不对 | 点 `.mlpackage` 看 Generated Class Name |

---

**下一步（你完成第 7 步后）**：把 Xcode 里模型类名、第一张检测截图发出来，可继续接 `VideoAnalyzer` 逐帧逻辑。
