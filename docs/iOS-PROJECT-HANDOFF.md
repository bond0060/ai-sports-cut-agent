# 篮球投篮检测 — iOS 测试版工程交接文档

> **文档用途**：将本仓库（Python Web 版）迁移为 **iOS 原生本地处理** 测试 App 的完整说明。  
> **使用方式**：把整个项目文件夹拷贝到装有 Xcode 的 Mac，本文档放在仓库 `docs/iOS-PROJECT-HANDOFF.md`。

**文档版本**：2026-06-04  
**源项目路径示例**：`AI-Basketball-Shot-Detection-Tracker-master`

---

## 1. 产品是什么

自动分析用户从相册选择的篮球视频，检测每次投篮，判定 **进球 / 未进**，并可导出每次投篮前后若干秒的 **短视频片段** 保存到相册。

- **v0（Web，本仓库）**：浏览器上传 → 服务器 Python + YOLO 分析 → 下载片段  
- **v1（iOS 测试版，待建）**：相册选视频 → **手机本地** Core ML 推理 + 本地裁切 → 保存相册，**无需上传云端**

---

## 2. 为什么做 iOS 本地版

| 平台 | 本地 AI 检测 | 说明 |
|------|--------------|------|
| 微信小程序 | ❌ | 不能跑 Python/YOLO |
| 网页 + 服务器 | ❌（需上传） | 与现网相同 |
| **iOS 原生 App** | ✅ | Core ML + AVFoundation |
| Android | ✅ | 二期，模型可共用转换思路 |

---

## 3. 源仓库必带文件清单

拷贝到 Xcode Mac 时，**至少包含**：

| 路径 | 大小级 | 用途 |
|------|--------|------|
| `best.pt` | ~6 MB | YOLOv8 权重，需转 Core ML |
| `config.yaml` | 极小 | 类别：`Basketball`, `Basketball Hoop` |
| `analyzer.py` | — | 主分析循环（移植核心） |
| `utils.py` | — | ROI、轨迹、up/down、score |
| `net_motion.py` | — | 篮网 Swish（iOS v0.2 可选） |
| `shot_verdict.py` | — | 延迟判定 Make/Miss（有网模式） |
| `clip_exporter.py` | — | 按时间裁切 MP4（参考逻辑） |
| `video_test_5.mp4` | ~34 MB | 回归测试视频（可选） |
| `requirements.txt` | — | Python 环境参考 |
| `docs/iOS-PROJECT-HANDOFF.md` | — | 本文档 |
| `deploy/DEPLOY-GCP.md` | — | 云端部署（iOS 不依赖，供参考） |

**不必拷贝**：`uploads/`、`outputs/`、`__pycache__/`（运行时生成）。

---

## 4. 在 Xcode Mac 上需要准备的环境

### 4.1 硬件与软件

- Mac + **Xcode**（建议最新稳定版）
- **Apple Developer Program**（$99/年）— 真机测试强烈建议
- iPhone 真机（A12 芯片及以上更佳）

### 4.2 Python（仅用于模型转换与对照测试）

```bash
cd /path/to/AI-Basketball-Shot-Detection-Tracker-master
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install coremltools
```

### 4.3 模型转换：best.pt → Core ML

```bash
# 在仓库根目录
yolo export model=best.pt format=coreml imgsz=640
# 或
python3 -c "from ultralytics import YOLO; YOLO('best.pt').export(format='coreml', imgsz=640)"
```

导出产物（名称以实际为准）加入 Xcode 工程，例如：

- `best.mlpackage` 或 `BasketballDetector.mlpackage`

**注意**：导出后需在 Mac 上用样例图验证检测框是否合理；与 Python 版可能有轻微偏差。

### 4.4 用 Python 版生成「标准答案」

在 iOS 开发前，对测试视频跑一遍并记录结果，便于对比：

```bash
python3 -c "
from pathlib import Path
from analyzer import analyze_video
r = analyze_video('video_test_5.mp4', has_net=True)
print('makes', r['makes'], 'attempts', r['attempts'])
for s in r['shots']:
    print(s)
"
```

建议整理成表格：`视频名 | attempt | time_s | result | trajectory_cross | net_swish`。

---

## 5. iOS 测试版（v0.1）功能范围建议

### 5.1 必做（MVP）

- [ ] 从相册选择单个视频（`PHPicker` / `PhotosUI`）
- [ ] 可选：第一帧上手指框选 **ROI**（对标 Web 黄框）
- [ ] 本地逐帧 Core ML 检测（球、筐）
- [ ] 移植投篮状态机：up → down → 计一次 attempt
- [ ] 判定 Make / Miss（首版可仅轨迹 `score()`，见下文）
- [ ] 列表展示每次投篮：时间、结果
- [ ] 按「事件前/后 3 秒」裁切（可调），**保存到相册**
- [ ] 分析进度条（长视频必需）

### 5.2 建议二期

- [ ] Net Swish（`net_motion.py`）有网/无网开关
- [ ] 延迟 0.3–1.0s 判定窗（`shot_verdict.py`）
- [ ] 扩大球跟踪区 `get_ball_track_zone`（侧投）
- [ ] 实时相机预览分析

### 5.3 暂不做

- 微信登录、云同步、后端 API
- 多球多筐场景（与 README 一致：单球单筐）

---

## 6. 推荐 iOS 技术栈

| 层级 | 建议 |
|------|------|
| UI | SwiftUI |
| 最低系统 | iOS 16+（或 17+） |
| 推理 | Core ML + Vision |
| 视频读写 | AVFoundation（`AVAssetReader` / `AVAssetExportSession`） |
| 相册 | PhotosUI + PhotoKit |
| 语言 | Swift 5.9+ |

**Bundle ID 示例**：`com.yourcompany.basketballshot`（自行替换）

**Info.plist 隐私文案（必填）**：

- `NSPhotoLibraryUsageDescription` — 选择篮球视频进行分析  
- `NSPhotoLibraryAddUsageDescription` — 保存投篮片段到相册  

---

## 7. 算法逻辑摘要（移植对照表）

Python 模块与 iOS 建议模块对应关系：

| Python 文件 | 职责 | iOS 建议 |
|-------------|------|----------|
| `analyzer.py` | 主循环、YOLO 调用、HUD、shot 触发 | `VideoAnalyzer.swift` |
| `utils.py` | ROI、清洗、up/down、score、rim | `ShotGeometry.swift` |
| `net_motion.py` | 篮网区域运动分 | `NetMotionDetector.swift`（二期） |
| `shot_verdict.py` | 延迟 Make/Miss | `ShotVerdictManager.swift`（二期） |
| `clip_exporter.py` | 按时间裁 MP4 | `ClipExporter.swift` |

### 7.1 检测类别与阈值

```text
CLASS_NAMES = ["Basketball", "Basketball Hoop"]
筐 conf > 0.5
球 conf：ROI 内可低至 0.15，否则 0.3
```

### 7.2 区域（ROI）

- **Custom ROI**：用户框选矩形 `(x1,y1,x2,y2)`，用于严格判定与轨迹  
- **Ball track zone**：比 ROI 更宽（约为筐宽 2.8 倍向两侧扩展），用于**检测球**（侧投）  
- **Net ROI**：筐沿下方竖条，用于网动检测（见 `net_motion.get_net_roi`）

关键函数（见 `utils.py`）：

- `get_active_roi` / `in_active_roi`
- `get_ball_track_zone` / `in_ball_track_zone`
- `get_rim_bounds` → `rim_y`, `rim_x1`, `rim_x2`, `rim_bottom`

### 7.3 投篮触发（attempt）

满足以下条件计一次 **attempt**（投篮尝试）：

1. 已有筐检测或已设 custom ROI  
2. 球轨迹满足 **up**（球在 ROI 上半/筐沿之上）再 **down**（过筐下沿）  
3. `up_frame < down_frame`  
4. 冷却 **3 秒**（`SHOT_COOLDOWN_S = 3.0`）  
5. 使用 `sequence_fired` 防止同一序列重复触发；pending 判定期间要重置该标志  

辅助：`get_up_frame_index` 用于补检「先看到 down、后补 up」的片段。

### 7.4 进球判定

**无网模式（简单）**：

- `score(ball_pos, hoop_pos)`：球心穿过 rim 平面，或轨迹线性外推与 rim 相交 → Make  

**有网模式（Web 现行）**：

- 触发 attempt 后进入 **0.3～1.0s** 验证窗  
- **Make** = `trajectory_cross` **且** `net_swish`  
- **Miss** = 有轨迹无网动、或 rim 反弹（`detect_rim_rebound`）  

iOS v0.1 可只做 `score()`，v0.2 再加 Net Swish。

### 7.5 片段导出

- 默认：事件时间 `time_s` 前 **3s**、后 **3s**（与 Web `clip_before` / `clip_after` 一致）  
- 文件名示例：`01_make_9.85s.mp4`、`02_miss_13.49s.mp4`  
- 裁切源：标注后视频逻辑在 Web 是对 **output** 裁切；iOS 本地可对 **原视频** 或 **自绘标注后缓存** 裁切

### 7.6 关键常量

```text
SHOT_COOLDOWN_S = 3.0
SHOOTING_TIMEOUT_S = 4.0
Net swish 阈值见 net_motion.py（peak_ratio ≈ 1.7, std_ratio ≈ 1.4）
```

---

## 8. Web 版功能对照（避免 iOS 遗漏）

当前 Web（`static/` + `app.py`）已实现、iOS 可分期对齐：

| 功能 | Web | iOS v0.1 |
|------|-----|----------|
| 相册/文件选视频 | ✅ | ✅ |
| 手动画 ROI | ✅ | 建议 ✅ |
| 有篮网开关 | ✅ | 二期 |
| 实时预览帧 | ✅ | 可选进度+当前帧 |
| 逐球列表 | ✅ | ✅ |
| 片段回放 | ✅ | ✅ 本地播放器 |
| 保存片段 | ✅ 下载 | ✅ 相册 |
| 片段时长设置 | ✅ 前后秒数 | ✅ |
| 浮动播放器 | ✅ | N/A |
| 导出 ZIP | ✅ | 可选分享多文件 |

---

## 9. 建议新建的 iOS 工程结构

在 Xcode Mac 上**新建独立仓库/目录**（勿与 Python 混在一个 target）：

```text
BasketballShot-iOS/
├── BasketballShot.xcodeproj
├── BasketballShot/
│   ├── App/
│   ├── Views/              # SwiftUI
│   ├── ViewModels/
│   ├── Services/
│   │   ├── VideoAnalyzer.swift
│   │   ├── CoreMLDetector.swift
│   │   ├── ShotGeometry.swift
│   │   └── ClipExporter.swift
│   ├── Models/
│   │   └── ShotRecord.swift
│   └── Resources/
│       └── BasketballDetector.mlpackage
├── TestVideos/             # .gitignore 大文件
└── Docs/
    └── iOS-PROJECT-HANDOFF.md  # 本文档副本
```

---

## 10. 测试与验收

### 10.1 测试素材

1. `video_test_5.mp4` — 基准  
2. 暗光 + 有篮网（你方常遇误检场景）  
3. 侧投、球经常出在 ROI 边缘外  

### 10.2 通过标准（测试版）

- [ ] 全流程不崩溃  
- [ ] 与 Python 版 **attempts 数量级一致**（允许 ±少量偏差）  
- [ ] 至少 1 条 Make / Miss 片段成功写入相册并可播放  
- [ ] 1080p、约 3 分钟视频在真机上 **&lt; 15 分钟** 分析完成（视机型调整）

### 10.3 性能优化方向（后期）

- 不必每帧推理：投篮检测区无球时跳帧  
- 分析分辨率降至 720p  
- `VNCoreMLRequest` 后台队列 + 进度回调  

---

## 11. 常见问题

**Q：能否直接把 Python 嵌进 iOS？**  
A：不行。必须用 Swift + Core ML（或 ONNX Runtime iOS），逻辑按本文档移植。

**Q：best.pt 和 Core ML 检测结果不一致？**  
A：正常。以真机实拍调 conf、NMS、ROI；用第三节「标准答案」做回归。

**Q：要不要先做 Android？**  
A：iOS 跑通后，可将同一 Core ML 转 TFLite 或重导 ONNX 给 Android。

**Q：Git 是否包含 best.pt？**  
A：当前仓库含 `best.pt`；若用 Git LFS 或网盘传大文件，注意 `.gitignore` 不要误排除。

---

## 12. 拷贝到 Xcode Mac 的操作步骤

1. 将整个 `AI-Basketball-Shot-Detection-Tracker-master` 文件夹拷贝（U 盘 / AirDrop / Git clone）。  
2. 确认 `best.pt` 存在。  
3. 阅读本文档第 4 节，完成 Core ML 导出。  
4. Xcode → New Project → iOS App → SwiftUI。  
5. 将 `.mlpackage` 拖入工程，按第 7 节实现 `VideoAnalyzer`。  
6. 用 `video_test_5.mp4` 进相册或放进 App 沙盒测试。  

---

## 13. 联系与参考链接

- 原项目 README：`README.md` / `README-zh.md`  
- GCP 部署（非 iOS 必需）：`deploy/DEPLOY-GCP.md`  
- Ultralytics 导出文档：https://docs.ultralytics.com/modes/export/  
- Apple Core ML：https://developer.apple.com/documentation/coreml  

---

## 14. 版本记录

| 日期 | 说明 |
|------|------|
| 2026-06-04 | 初版：iOS 测试版交接，基于 Python Web + Net Swish + 片段导出 |

---

**附：Python 本地快速验证命令（Xcode Mac 上对照用）**

```bash
# CLI 弹窗预览
python3 shot_detector.py

# Web 服务（可选）
python3 -m uvicorn app:app --host 0.0.0.0 --port 8080

# Docker（可选）
docker build -t basketball-detector .
docker run -p 8080:8080 -v $(pwd)/uploads:/app/uploads -v $(pwd)/outputs:/app/outputs basketball-detector
```

---

*本文档随 Python 仓库更新；iOS 工程里程碑请在独立仓库维护 CHANGELOG。*
