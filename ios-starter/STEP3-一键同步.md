# 第 3 步：一键同步到 Xcode（你已建好工程）

## 一条命令（把路径改成你保存 Xcode 工程的位置）

```bash
cd ~/Downloads/AI-Basketball-Shot-Detection-Tracker-master

bash ios-starter/scripts/sync_to_xcode.sh ~/Projects/BasketballShot-iOS
```

> 把 `~/Projects/BasketballShot-iOS` 换成你第 2 步保存工程时的**文件夹**（里面有 `BasketballShot.xcodeproj` 的那一层）。

脚本会：

1. 复制 `best.mlpackage` 到工程  
2. 复制全部 Swift 源码（含检测 + 简易分析）  
3. 尝试自动打开 Xcode  

---

## 然后在 Xcode 里做 3 件事（约 2 分钟）

### A. 把新文件加入 Target

若左侧看不到 `best.mlpackage` / `Models` / `Services`：

1. 菜单 **File → Add Files to "BasketballShot"...**
2. 选中工程里的 `best.mlpackage`、`Models`、`Services`、`Views`、`AppViewModel.swift`
3. 勾选 **Copy items if needed**、**Add to targets: BasketballShot**

### B. 删掉重复的 ContentView

若有两个 `ContentView.swift`，**只保留 `Views/ContentView.swift`**，删除另一个。

### C. 相册权限 + 真机运行

**Target → Info** 添加：

- Photo Library Usage Description  
- Photo Library Additions Usage Description  

连接 iPhone → **⌘R** 运行。

---

## 当前 App 已具备

- 相册选视频  
- Core ML 检测（YOLO `best.mlpackage`）  
- 简易投篮统计（v0.1，与 Python 完全对齐仍在迭代）  
- 进度条  

**尚未包含**：片段保存相册、ROI 框选、Net Swish（可下一步加）。

---

## 编译报错对照

| 报错 | 处理 |
|------|------|
| Cannot find `best` in scope | 确认 `best.mlpackage` 已勾选 Target |
| Duplicate `ContentView` | 只留一份 |
| Multiple commands produce | Build Phases → Copy Bundle Resources 里去掉重复 mlpackage |
