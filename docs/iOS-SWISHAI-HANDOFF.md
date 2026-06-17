# SwishAI 算法 — iOS 客户端集成说明

> **用途**：在 iOS 本地使用本仓库已训练好的 **SwishAI YOLO11s 5-class** 模型进行投篮检测与计分。  
> **Web 对照**：`algorithm=swishai` → `swishai_analyzer.py`  
> **权重路径**：`models/swishai/best.pt`（31 epochs，验证 mAP50 ≈ 0.941）

---

## 1. 算法概述

SwishAI 与「优化版 / 原版」轨迹算法不同，采用 **5 类 YOLO 检测 + 冷却时间计分**：

| Class ID | 名称 | 置信度阈值 | 作用 |
|----------|------|------------|------|
| 0 | Ball | 0.60 | 可视化 |
| 1 | Ball in Basket | 0.25 | **进球**（Make） |
| 2 | Player | 0.70 | 可视化 |
| 3 | Basket | 0.70 | 记录篮筐位置 |
| 4 | Player Shooting | 0.77 | **投篮出手**（Attempt） |

**计分逻辑**（见 `swishai_analyzer.py` → `_GameStats`）：

- 检测到 class **4** 且距上次出手 ≥ **1.5s** → `shots_attempted += 1`
- 检测到 class **1** 且距上次进球 ≥ **2.0s** → `baskets_made += 1`；若距上次出手过久，自动补一次 attempt
- **不需要**手选篮筐、ROI、轨迹 up/down

---

## 2. 仓库内文件清单

| 路径 | 说明 |
|------|------|
| `models/swishai/best.pt` | 已训练权重（YOLO11s，~18MB，含导出用结构） |
| `swishai_analyzer.py` | Python 参考实现（iOS 移植对照） |
| `scripts/export_swishai_coreml.py` | 导出 Core ML |
| `scripts/setup_swishai_model.py` | 重新训练 / 续训（需 Roboflow Key） |
| `ios-starter/BasketballShot/Models/SwishAIConstants.swift` | 类别与阈值 |
| `ios-starter/BasketballShot/Services/SwishAITracker.swift` | 计分状态机 |
| `ios-starter/BasketballShot/Services/SwishAIVideoAnalyzer.swift` | 逐帧分析骨架 |

---

## 3. 导出 Core ML（Xcode Mac 上执行）

```bash
cd /path/to/AI-Basketball-Shot-Detection-Tracker-master
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt coremltools

python3 scripts/export_swishai_coreml.py
# 输出: models/swishai/SwishAI.mlpackage
```

将 **`SwishAI.mlpackage`** 拖入 Xcode 工程（Copy items + Target 勾选）。

---

## 4. Python 标准答案（iOS 回归对照）

```bash
python3 -c "
from swishai_analyzer import analyze_video_swishai
r = analyze_video_swishai('video_test_5.mp4', output_path=None)
print('algorithm:', r['algorithm'])
print('FG:', r['makes'], '/', r['attempts'])
for s in r['shots']:
    print(s)
"
```

API 请求对照：`POST /api/analyze`，表单字段 `algorithm=swishai`。

---

## 5. iOS 集成步骤

1. 导出并加入 `SwishAI.mlpackage`
2. 复制 `ios-starter/BasketballShot/` 下 SwishAI 相关 Swift 文件到 Xcode 工程
3. 在 App 中增加算法选择：**SwishAI** vs 优化版（2-class 轨迹）
4. 使用 `SwishAIVideoAnalyzer` + `SwishAITracker` 替代 `ShotTracker`（轨迹版）
5. 按 `SwishAIConstants.classThresholds` 过滤检测框
6. 真机对比 Python 同视频的 makes / attempts

---

## 6. 与优化版 iOS 的差异

| 项目 | 优化版（2-class） | SwishAI（5-class） |
|------|-------------------|---------------------|
| 模型 | `best.pt` → Core ML | `models/swishai/best.pt` → Core ML |
| 计分 | up/down + score() | Shooting / Ball in Basket 事件 |
| 多篮筐 | 需选手动目标区 | 模型自行识别（仍建议单筐场景） |
| 追踪 | 可选 ByteTrack | Python 端用 `model.track(persist=True)` |
| 冷却 | 3.0s | 出手 1.5s / 进球 2.0s |

---

## 7. 训练信息（本次 baseline）

- 基座：YOLO11s
- 数据：Roboflow `basketball-detection-srfkd` v1
- 训练：31 epochs（早停 patience=20），Apple M4 CPU
- 验证：P=0.888, R=0.909, mAP50=0.941, mAP50-95=0.715

续训：

```bash
caffeinate -dims python3 -c "
from ultralytics import YOLO
YOLO('vendor/SwishAI/BE/basketball_training/yolo11s_5classes/weights/last.pt').train(resume=True)
"
```

---

## 8. 版本记录

| 日期 | 说明 |
|------|------|
| 2026-06-17 | 首版：训练完成权重入库 + iOS SwishAI 起步代码与文档 |
