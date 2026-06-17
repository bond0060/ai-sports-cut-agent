const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const selectedFile = document.getElementById("selected-file");
const fileName = document.getElementById("file-name");
const clearFileBtn = document.getElementById("clear-file");
const analyzeBtn = document.getElementById("analyze-btn");
const algorithmOptimizedInput = document.getElementById("algorithm-optimized");
const algorithmOriginalInput = document.getElementById("algorithm-original");
const algorithmHoopcutInput = document.getElementById("algorithm-hoopcut");
const algorithmSwishaiInput = document.getElementById("algorithm-swishai");
const algorithmChoices = document.querySelectorAll(".algorithm-choice");
const algorithmHint = document.getElementById("algorithm-hint");
const algorithmBadge = document.getElementById("algorithm-badge");
const hoopSelectSection = document.getElementById("hoop-select-section");
const hoopChoiceButtons = document.getElementById("hoop-choice-buttons");
const hoopPickerCanvas = document.getElementById("hoop-picker-canvas");
const confirmHoopBtn = document.getElementById("confirm-hoop-btn");
const cancelHoopBtn = document.getElementById("cancel-hoop-btn");

const roiSection = document.getElementById("roi-section");
const roiCanvas = document.getElementById("roi-canvas");
const roiSourceVideo = document.getElementById("roi-source-video");
const resetRoiBtn = document.getElementById("reset-roi-btn");
const confirmRoiBtn = document.getElementById("confirm-roi-btn");
const hasNetInput = document.getElementById("has-net-input");

const playerSection = document.getElementById("player-section");
const playerTitle = document.getElementById("player-title");
const playerBadge = document.getElementById("player-badge");
const livePreview = document.getElementById("live-preview");
const resultVideo = document.getElementById("result-video");

const progressSection = document.getElementById("progress-section");
const progressFill = document.getElementById("progress-fill");
const progressLabel = document.getElementById("progress-label");
const progressDetail = document.getElementById("progress-detail");

const liveStats = document.getElementById("live-stats");
const liveScore = document.getElementById("live-score");
const liveStatus = document.getElementById("live-status");

const errorSection = document.getElementById("error-section");
const errorMessage = document.getElementById("error-message");

const resultsSection = document.getElementById("results-section");
const statAttempts = document.getElementById("stat-attempts");
const statMakes = document.getElementById("stat-makes");
const statMisses = document.getElementById("stat-misses");
const statPercentage = document.getElementById("stat-percentage");
const shotsBody = document.getElementById("shots-body");
const shotCount = document.getElementById("shot-count");
const emptyShots = document.getElementById("empty-shots");
const clipSettingsToggle = document.getElementById("clip-settings-toggle");
const clipSettingsPanel = document.getElementById("clip-settings-panel");
const clipBeforeInput = document.getElementById("clip-before");
const clipAfterInput = document.getElementById("clip-after");
const clipInfo = document.getElementById("clip-info");
const videoDock = document.getElementById("video-dock");
const videoDockBar = document.getElementById("video-dock-bar");
const videoDockTitle = document.getElementById("video-dock-title");
const videoDockPlaceholder = document.getElementById("video-dock-placeholder");
const playerScrollAnchor = document.getElementById("player-scroll-anchor");
const dockBackBtn = document.getElementById("dock-back-btn");
const dockCloseBtn = document.getElementById("dock-close-btn");
const CLIP_SETTINGS_KEY = "basketball_clip_settings";
const ALGORITHM_SETTINGS_KEY = "basketball_algorithm";
const USE_AUTO_ROI_FOR_TEST = true;

let currentFile = null;
let pollTimer = null;
let previewTimer = null;
let selectedRoi = null;
let roiSelector = null;
let currentResult = null;
let currentJobId = null;
let clipTimeUpdateHandler = null;
let activeShotRow = null;
let videoDockObserver = null;
let floatDismissed = false;
let dockObserverEnabled = false;
let selectedTargetHoop = null;
let hoopPicker = null;

function loadClipSettings() {
  try {
    const saved = JSON.parse(localStorage.getItem(CLIP_SETTINGS_KEY) || "{}");
    return {
      before: Number.isFinite(saved.before) ? saved.before : 3,
      after: Number.isFinite(saved.after) ? saved.after : 3,
    };
  } catch {
    return { before: 3, after: 3 };
  }
}

function saveClipSettings() {
  const settings = {
    before: Math.max(0, parseFloat(clipBeforeInput.value) || 0),
    after: Math.max(0, parseFloat(clipAfterInput.value) || 0),
  };
  localStorage.setItem(CLIP_SETTINGS_KEY, JSON.stringify(settings));
  return settings;
}

function getClipSettings() {
  return {
    before: Math.max(0, parseFloat(clipBeforeInput.value) || 0),
    after: Math.max(0, parseFloat(clipAfterInput.value) || 0),
  };
}

function initClipSettings() {
  const settings = loadClipSettings();
  clipBeforeInput.value = settings.before;
  clipAfterInput.value = settings.after;
}

function stopClipPlayback() {
  if (clipTimeUpdateHandler) {
    resultVideo.removeEventListener("timeupdate", clipTimeUpdateHandler);
    clipTimeUpdateHandler = null;
  }
}

function syncDockTitle() {
  videoDockTitle.textContent = playerTitle.textContent;
}

function setVideoFloating(enabled) {
  const shouldFloat = enabled && !resultVideo.classList.contains("hidden");
  videoDock.classList.toggle("is-floating", shouldFloat);
  videoDockBar.classList.toggle("hidden", !shouldFloat);
  videoDockPlaceholder.classList.toggle("hidden", !shouldFloat);
  if (shouldFloat) {
    syncDockTitle();
  }
}

function teardownVideoDockObserver() {
  if (videoDockObserver) {
    videoDockObserver.disconnect();
    videoDockObserver = null;
  }
  dockObserverEnabled = false;
}

function setupVideoDockObserver() {
  teardownVideoDockObserver();
  floatDismissed = false;
  dockObserverEnabled = true;

  videoDockObserver = new IntersectionObserver(
    ([entry]) => {
      if (!dockObserverEnabled || floatDismissed || !currentResult) {
        return;
      }
      if (!entry.isIntersecting) {
        setVideoFloating(true);
      } else if (!clipTimeUpdateHandler) {
        setVideoFloating(false);
      }
    },
    { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
  );

  videoDockObserver.observe(playerScrollAnchor);
}

function playShotClip(shot, rowEl) {
  if (!currentResult || !shot) {
    return;
  }

  const { before, after } = getClipSettings();
  const duration =
    currentResult.video_info?.duration_s || resultVideo.duration || Infinity;
  const eventTime = shot.time_s;
  const start = Math.max(0, eventTime - before);
  const end = Math.min(duration, eventTime + after);

  stopClipPlayback();

  if (activeShotRow) {
    activeShotRow.classList.remove("row-active");
  }
  activeShotRow = rowEl;
  if (activeShotRow) {
    activeShotRow.classList.add("row-active");
  }

  show(playerSection);
  hide(livePreview);
  show(resultVideo);
  playerTitle.textContent = `片段回放 · 第 ${shot.attempt} 球`;
  syncDockTitle();
  clipInfo.textContent = `事件 ${eventTime}s · 播放 ${start.toFixed(1)}s – ${end.toFixed(1)}s（前 ${before}s / 后 ${after}s）`;
  show(clipInfo);

  floatDismissed = false;
  setVideoFloating(true);

  const runClip = () => {
    resultVideo.currentTime = start;
    resultVideo.play().catch(() => {});

    clipTimeUpdateHandler = () => {
      if (resultVideo.currentTime >= end - 0.05) {
        resultVideo.pause();
        stopClipPlayback();
      }
    };
    resultVideo.addEventListener("timeupdate", clipTimeUpdateHandler);
  };

  if (resultVideo.readyState >= 1 && !Number.isNaN(resultVideo.duration)) {
    runClip();
  } else {
    resultVideo.addEventListener("loadedmetadata", runClip, { once: true });
    resultVideo.load();
  }
}

function getSelectedAlgorithm() {
  const checked = document.querySelector('input[name="algorithm"]:checked');
  return checked?.value || "optimized";
}

function algorithmNeedsHoopScan(algorithm) {
  return algorithm === "optimized";
}

function setSelectedAlgorithm(algorithm) {
  const inputs = [
    algorithmOptimizedInput,
    algorithmOriginalInput,
    algorithmHoopcutInput,
    algorithmSwishaiInput,
  ];
  inputs.forEach((input) => {
    if (input) {
      input.checked = input.value === algorithm;
    }
  });
  algorithmChoices.forEach((choice) => {
    const input = choice.querySelector('input[type="radio"]');
    choice.classList.toggle("is-active", Boolean(input?.checked));
  });
}

const ALGORITHM_LABELS = {
  optimized: "优化版（解决多篮筐 · 目标区域）",
  original: "原版（avishah3 · 全部篮筐）",
  hoopcut: "HoopCut（线性 + 抛物线双轨迹）",
  swishai: "SwishAI（5 类检测 + 冷却计分）",
};

const ALGORITHM_HINTS = {
  optimized:
    "优化版：与原版检测逻辑相同；多个篮筐时先选定目标区域，区域内检测均视为目标篮筐。",
  original: "原版：检测画面中所有篮筐，不做目标筛选。适合与其他算法做 A/B 对比。",
  hoopcut:
    "HoopCut（ericbh22 原版）：开头自动检测篮筐，线性 + 抛物线双轨迹判进，无需手动选框。",
  swishai:
    "SwishAI（sPappalard 原版）：5 类 YOLO 检测 + 冷却计分，无需手动选框。",
};

const ALGORITHM_BUTTONS = {
  optimized: "开始分析（优化版）",
  original: "开始分析（原版）",
  hoopcut: "开始分析（HoopCut）",
  swishai: "开始分析（SwishAI）",
};

function getAlgorithmLabel(algorithm) {
  return ALGORITHM_LABELS[algorithm] || ALGORITHM_LABELS.optimized;
}

function syncAlgorithmUi() {
  const algorithm = getSelectedAlgorithm();

  if (algorithmHint) {
    algorithmHint.textContent = ALGORITHM_HINTS[algorithm] || ALGORITHM_HINTS.optimized;
  }

  if (hasNetInput) {
    hasNetInput.disabled = true;
    hasNetInput.closest(".net-option")?.classList.add("disabled-option");
  }

  analyzeBtn.textContent = ALGORITHM_BUTTONS[algorithm] || ALGORITHM_BUTTONS.optimized;
}

function loadAlgorithmSetting() {
  try {
    const saved = localStorage.getItem(ALGORITHM_SETTINGS_KEY);
    if (saved && ALGORITHM_LABELS[saved]) {
      setSelectedAlgorithm(saved);
    }
  } catch {
    // ignore
  }
  syncAlgorithmUi();
}

function saveAlgorithmSetting() {
  localStorage.setItem(ALGORITHM_SETTINGS_KEY, getSelectedAlgorithm());
}

initClipSettings();
loadAlgorithmSetting();

algorithmChoices.forEach((choice) => {
  choice.addEventListener("click", () => {
    const input = choice.querySelector('input[type="radio"]');
    if (!input) {
      return;
    }
    input.checked = true;
    setSelectedAlgorithm(input.value);
    saveAlgorithmSetting();
    syncAlgorithmUi();
  });
});

clipSettingsToggle.addEventListener("click", () => {
  clipSettingsPanel.classList.toggle("hidden");
});

clipBeforeInput.addEventListener("change", saveClipSettings);
clipAfterInput.addEventListener("change", saveClipSettings);

dockBackBtn.addEventListener("click", () => {
  floatDismissed = false;
  setVideoFloating(false);
  playerSection.scrollIntoView({ behavior: "smooth", block: "start" });
});

dockCloseBtn.addEventListener("click", () => {
  floatDismissed = true;
  setVideoFloating(false);
  stopClipPlayback();
});

function show(el) {
  el.classList.remove("hidden");
}

function hide(el) {
  el.classList.add("hidden");
}

function resetUI() {
  hide(errorSection);
  hide(resultsSection);
  hide(playerSection);
  hide(progressSection);
  hide(liveStats);
  hide(livePreview);
  hide(resultVideo);
  hide(roiSection);
  hide(hoopSelectSection);
  progressFill.style.width = "0%";
  progressLabel.textContent = "0%";
  selectedRoi = null;
  selectedTargetHoop = null;
  currentResult = null;
  currentJobId = null;
  hide(algorithmBadge);
  teardownVideoDockObserver();
  setVideoFloating(false);
  floatDismissed = false;
  stopClipPlayback();
  hide(clipInfo);
  if (activeShotRow) {
    activeShotRow.classList.remove("row-active");
    activeShotRow = null;
  }
  stopPreviewPolling();
}

function setFile(file) {
  currentFile = file;
  if (!file) {
    hide(selectedFile);
    analyzeBtn.disabled = true;
    return;
  }

  fileName.textContent = file.name;
  show(selectedFile);
  analyzeBtn.disabled = false;
}

function stopPreviewPolling() {
  if (previewTimer) {
    clearInterval(previewTimer);
    previewTimer = null;
  }
}

function startPreviewPolling(jobId) {
  stopPreviewPolling();

  previewTimer = setInterval(async () => {
    try {
      const response = await fetch(`/api/jobs/${jobId}/preview.jpg?t=${Date.now()}`);
      if (!response.ok) {
        return;
      }

      const blob = await response.blob();
      livePreview.src = URL.createObjectURL(blob);
      show(livePreview);
      hide(resultVideo);
    } catch {
      // Ignore transient preview errors while processing.
    }
  }, 120);
}

class RoiSelector {
  constructor(canvas, video) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.video = video;
    this.roi = null;
    this.dragMode = null;
    this.dragStart = null;
    this.startRoi = null;
    this.minSize = 80;
    this.handleSize = 10;

    this.onPointerDown = this.onPointerDown.bind(this);
    this.onPointerMove = this.onPointerMove.bind(this);
    this.onPointerUp = this.onPointerUp.bind(this);

    canvas.addEventListener("pointerdown", this.onPointerDown);
    canvas.addEventListener("pointermove", this.onPointerMove);
    canvas.addEventListener("pointerup", this.onPointerUp);
    canvas.addEventListener("pointerleave", this.onPointerUp);
  }

  loadFile(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      this.video.src = url;
      this.video.onloadeddata = () => {
        this.video.currentTime = 0;
      };
      this.video.onseeked = () => {
        this.resizeCanvas();
        this.roi = this.defaultRoi();
        this.draw();
        resolve();
      };
      this.video.onerror = () => reject(new Error("无法读取视频首帧"));
    });
  }

  resizeCanvas() {
    const maxWidth = this.canvas.parentElement.clientWidth || 960;
    const scale = Math.min(1, maxWidth / this.video.videoWidth);
    this.displayWidth = Math.round(this.video.videoWidth * scale);
    this.displayHeight = Math.round(this.video.videoHeight * scale);
    this.canvas.width = this.displayWidth;
    this.canvas.height = this.displayHeight;
    this.scaleX = this.video.videoWidth / this.displayWidth;
    this.scaleY = this.video.videoHeight / this.displayHeight;
  }

  defaultRoi() {
    const vw = this.video.videoWidth;
    const vh = this.video.videoHeight;
    const w = vw * 0.42;
    const h = vh * 0.48;
    const x = vw * 0.48;
    const y = vh * 0.08;
    return { x, y, w, h };
  }

  reset() {
    this.roi = this.defaultRoi();
    this.draw();
  }

  toNativeRect() {
    const x1 = Math.round(this.roi.x);
    const y1 = Math.round(this.roi.y);
    const x2 = Math.round(this.roi.x + this.roi.w);
    const y2 = Math.round(this.roi.y + this.roi.h);
    return { x1, y1, x2, y2 };
  }

  toDisplayRect(roi = this.roi) {
    return {
      x: roi.x / this.scaleX,
      y: roi.y / this.scaleY,
      w: roi.w / this.scaleX,
      h: roi.h / this.scaleY,
    };
  }

  fromDisplayPoint(x, y) {
    return { x: x * this.scaleX, y: y * this.scaleY };
  }

  draw() {
    const { ctx, canvas, video } = this;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const rect = this.toDisplayRect();
    ctx.fillStyle = "rgba(255, 212, 0, 0.18)";
    ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
    ctx.strokeStyle = "#ffd400";
    ctx.lineWidth = 3;
    ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);

    ctx.fillStyle = "#ffd400";
    ctx.font = "bold 16px sans-serif";
    ctx.fillText("观察区域 ROI", rect.x + 8, Math.max(rect.y + 22, 20));

    this.drawHandles(rect);
  }

  drawHandles(rect) {
    const points = [
      ["nw", rect.x, rect.y],
      ["ne", rect.x + rect.w, rect.y],
      ["sw", rect.x, rect.y + rect.h],
      ["se", rect.x + rect.w, rect.y + rect.h],
      ["n", rect.x + rect.w / 2, rect.y],
      ["s", rect.x + rect.w / 2, rect.y + rect.h],
      ["w", rect.x, rect.y + rect.h / 2],
      ["e", rect.x + rect.w, rect.y + rect.h / 2],
    ];

    this.ctx.fillStyle = "#ffffff";
    this.ctx.strokeStyle = "#ff6b35";
    this.ctx.lineWidth = 2;
    for (const [, x, y] of points) {
      this.ctx.beginPath();
      this.ctx.rect(x - this.handleSize / 2, y - this.handleSize / 2, this.handleSize, this.handleSize);
      this.ctx.fill();
      this.ctx.stroke();
    }
  }

  hitTest(x, y) {
    const rect = this.toDisplayRect();
    const hs = this.handleSize + 4;
    const handles = {
      nw: [rect.x, rect.y],
      ne: [rect.x + rect.w, rect.y],
      sw: [rect.x, rect.y + rect.h],
      se: [rect.x + rect.w, rect.y + rect.h],
      n: [rect.x + rect.w / 2, rect.y],
      s: [rect.x + rect.w / 2, rect.y + rect.h],
      w: [rect.x, rect.y + rect.h / 2],
      e: [rect.x + rect.w, rect.y + rect.h / 2],
    };

    for (const [name, [hx, hy]] of Object.entries(handles)) {
      if (Math.abs(x - hx) <= hs && Math.abs(y - hy) <= hs) {
        return name;
      }
    }

    if (x >= rect.x && x <= rect.x + rect.w && y >= rect.y && y <= rect.y + rect.h) {
      return "move";
    }

    return null;
  }

  onPointerDown(event) {
    const rect = this.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    this.dragMode = this.hitTest(x, y);
    if (!this.dragMode) {
      return;
    }

    this.canvas.setPointerCapture(event.pointerId);
    this.dragStart = this.fromDisplayPoint(x, y);
    this.startRoi = { ...this.roi };
  }

  onPointerMove(event) {
    if (!this.dragMode) {
      return;
    }

    const rect = this.canvas.getBoundingClientRect();
    const point = this.fromDisplayPoint(
      event.clientX - rect.left,
      event.clientY - rect.top
    );
    const dx = point.x - this.dragStart.x;
    const dy = point.y - this.dragStart.y;
    const next = { ...this.startRoi };

    if (this.dragMode === "move") {
      next.x += dx;
      next.y += dy;
    } else {
      if (this.dragMode.includes("w")) {
        next.x += dx;
        next.w -= dx;
      }
      if (this.dragMode.includes("e")) {
        next.w += dx;
      }
      if (this.dragMode.includes("n")) {
        next.y += dy;
        next.h -= dy;
      }
      if (this.dragMode.includes("s")) {
        next.h += dy;
      }
    }

    this.roi = this.clampRoi(next);
    this.draw();
  }

  onPointerUp(event) {
    if (!this.dragMode) {
      return;
    }
    this.dragMode = null;
    this.canvas.releasePointerCapture(event.pointerId);
  }

  clampRoi(roi) {
    const vw = this.video.videoWidth;
    const vh = this.video.videoHeight;
    let { x, y, w, h } = roi;

    if (w < this.minSize) {
      if (this.dragMode && this.dragMode.includes("w")) {
        x -= this.minSize - w;
      }
      w = this.minSize;
    }
    if (h < this.minSize) {
      if (this.dragMode && this.dragMode.includes("n")) {
        y -= this.minSize - h;
      }
      h = this.minSize;
    }

    x = Math.max(0, Math.min(x, vw - w));
    y = Math.max(0, Math.min(y, vh - h));
    w = Math.min(w, vw - x);
    h = Math.min(h, vh - y);

    return { x, y, w, h };
  }
}

class HoopPicker {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.hoops = [];
    this.selectedId = null;
    this.image = new Image();
    this.scaleX = 1;
    this.scaleY = 1;
    this.onSelect = null;
    this.onClick = this.onClick.bind(this);
    canvas.addEventListener("click", this.onClick);
  }

  drawCheckmark(ctx, cx, cy, size, color) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(3.5, size * 0.16);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(cx - size * 0.24, cy + size * 0.02);
    ctx.lineTo(cx - size * 0.04, cy + size * 0.24);
    ctx.lineTo(cx + size * 0.28, cy - size * 0.2);
    ctx.stroke();
    ctx.restore();
  }

  drawLabel(ctx, text, x, y, bgColor, textColor) {
    ctx.font = "bold 15px -apple-system, BlinkMacSystemFont, sans-serif";
    const paddingX = 10;
    const paddingY = 6;
    const metrics = ctx.measureText(text);
    const boxW = metrics.width + paddingX * 2;
    const boxH = 24;
    const boxX = x;
    const boxY = y - boxH + 4;
    ctx.fillStyle = bgColor;
    ctx.fillRect(boxX, boxY, boxW, boxH);
    ctx.fillStyle = textColor;
    ctx.fillText(text, boxX + paddingX, boxY + boxH - paddingY);
  }

  selectHoop(hoopId) {
    this.selectedId = hoopId;
    this.draw();
    const hoop = this.getSelected();
    if (hoop && this.onSelect) {
      this.onSelect(hoop);
    }
    renderHoopChoiceButtons();
  }

  getCheckButtonRect(hoop) {
    const rect = this.toDisplayRect(hoop);
    const size = 42;
    const x = rect.x + rect.w / 2 - size / 2;
    const y = Math.max(rect.y - size - 12, 8);
    return { x, y, w: size, h: size };
  }

  load(previewBase64, hoops) {
    return new Promise((resolve, reject) => {
      this.hoops = hoops;
      this.selectedId = hoops.length === 1 ? hoops[0].id : null;
      this.image.onload = () => {
        const maxWidth = this.canvas.parentElement.clientWidth || 960;
        const scale = Math.min(1, maxWidth / this.image.width);
        this.canvas.width = Math.round(this.image.width * scale);
        this.canvas.height = Math.round(this.image.height * scale);
        this.scaleX = this.image.width / this.canvas.width;
        this.scaleY = this.image.height / this.canvas.height;
        this.draw();
        resolve();
      };
      this.image.onerror = () => reject(new Error("无法加载篮筐预览图"));
      this.image.src = `data:image/jpeg;base64,${previewBase64}`;
    });
  }

  toDisplayRect(hoop) {
    return {
      x: hoop.x1 / this.scaleX,
      y: hoop.y1 / this.scaleY,
      w: hoop.w / this.scaleX,
      h: hoop.h / this.scaleY,
    };
  }

  draw() {
    const { ctx, canvas, image } = this;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);

    for (const hoop of this.hoops) {
      const rect = this.toDisplayRect(hoop);
      const selected = hoop.id === this.selectedId;
      const accent = selected ? "#00ff78" : "#ffd400";
      const accentSoft = selected ? "rgba(0, 255, 120, 0.24)" : "rgba(255, 212, 0, 0.18)";

      ctx.fillStyle = accentSoft;
      ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
      ctx.strokeStyle = accent;
      ctx.lineWidth = selected ? 4 : 3;
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);

      const label = selected
        ? `目标区域 ${Math.round(hoop.conf * 100)}%`
        : `篮筐 ${Math.round(hoop.conf * 100)}%`;
      this.drawLabel(
        ctx,
        label,
        rect.x + 6,
        Math.max(rect.y + 4, 18),
        selected ? "rgba(0, 255, 120, 0.92)" : "rgba(255, 212, 0, 0.92)",
        selected ? "#0f1419" : "#1a1200"
      );

      const btn = this.getCheckButtonRect(hoop);
      const btnCx = btn.x + btn.w / 2;
      const btnCy = btn.y + btn.h / 2;
      const btnRadius = btn.w / 2;

      ctx.save();
      ctx.shadowColor = "rgba(0, 0, 0, 0.35)";
      ctx.shadowBlur = 8;
      ctx.shadowOffsetY = 2;
      ctx.beginPath();
      ctx.arc(btnCx, btnCy, btnRadius, 0, Math.PI * 2);
      ctx.fillStyle = selected ? "#00ff78" : "#ffffff";
      ctx.fill();
      ctx.restore();

      ctx.beginPath();
      ctx.arc(btnCx, btnCy, btnRadius, 0, Math.PI * 2);
      ctx.strokeStyle = selected ? "#00ff78" : "#ffd400";
      ctx.lineWidth = selected ? 3 : 3.5;
      ctx.stroke();

      this.drawCheckmark(
        ctx,
        btnCx,
        btnCy,
        btn.w,
        selected ? "#0f1419" : "#111111"
      );
    }
  }

  hitTestCheckButton(displayX, displayY) {
    for (const hoop of this.hoops) {
      const btn = this.getCheckButtonRect(hoop);
      const cx = btn.x + btn.w / 2;
      const cy = btn.y + btn.h / 2;
      const radius = btn.w / 2 + 4;
      if ((displayX - cx) ** 2 + (displayY - cy) ** 2 <= radius ** 2) {
        return hoop;
      }
    }
    return null;
  }

  onClick(event) {
    const rect = this.canvas.getBoundingClientRect();
    const displayX = event.clientX - rect.left;
    const displayY = event.clientY - rect.top;

    const checkHit = this.hitTestCheckButton(displayX, displayY);
    if (checkHit) {
      this.selectHoop(checkHit.id);
      return;
    }

    const x = displayX * this.scaleX;
    const y = displayY * this.scaleY;

    let chosen = null;
    for (const hoop of this.hoops) {
      const pad = Math.max(18, hoop.w * 0.15);
      if (
        x >= hoop.x1 - pad &&
        x <= hoop.x2 + pad &&
        y >= hoop.y1 - pad &&
        y <= hoop.y2 + pad
      ) {
        chosen = hoop;
      }
    }

    if (!chosen) {
      return;
    }

    this.selectHoop(chosen.id);
  }

  getSelected() {
    return this.hoops.find((hoop) => hoop.id === this.selectedId) || null;
  }
}

function renderHoopChoiceButtons() {
  if (!hoopChoiceButtons || !hoopPicker) {
    return;
  }

  hoopChoiceButtons.innerHTML = "";
  hoopPicker.hoops.forEach((hoop, index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "hoop-choice-btn";
    if (hoop.id === hoopPicker.selectedId) {
      btn.classList.add("is-active");
    }
    btn.innerHTML = `<span class="check-icon" aria-hidden="true"></span><span>篮筐 ${index + 1} · ${Math.round(hoop.conf * 100)}%</span>`;
    btn.addEventListener("click", () => {
      hoopPicker.selectHoop(hoop.id);
      selectedTargetHoop = hoopPicker.getSelected();
      confirmHoopBtn.disabled = !selectedTargetHoop;
    });
    hoopChoiceButtons.appendChild(btn);
  });
}

async function openHoopPicker(scanResult) {
  hide(errorSection);
  hide(resultsSection);
  hide(playerSection);
  hide(progressSection);
  hide(liveStats);
  show(hoopSelectSection);

  if (!hoopPicker) {
    hoopPicker = new HoopPicker(hoopPickerCanvas);
  }

  confirmHoopBtn.disabled = true;
  await hoopPicker.load(scanResult.preview_jpeg_base64, scanResult.hoops);
  hoopPicker.onSelect = (hoop) => {
    selectedTargetHoop = hoop;
    confirmHoopBtn.disabled = false;
    renderHoopChoiceButtons();
  };
  renderHoopChoiceButtons();

  if (scanResult.hoops.length === 1) {
    hoopPicker.selectHoop(scanResult.hoops[0].id);
    selectedTargetHoop = scanResult.hoops[0];
    confirmHoopBtn.disabled = false;
  }
}

async function prepareTargetHoopAnalysis() {
  if (!currentFile) {
    return;
  }

  const algorithm = getSelectedAlgorithm();
  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "正在扫描篮筐…";

  try {
    const formData = new FormData();
    formData.append("file", currentFile);
    const response = await fetch("/api/detect-hoops", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "篮筐扫描失败");
    }

    if (!payload.hoops || payload.hoops.length === 0) {
      if (algorithm === "optimized") {
        throw new Error("未检测到篮筐，请换一段篮筐更清晰的视频");
      }
      await submitAnalysis(null);
      return;
    }

    if (payload.hoops.length === 1) {
      selectedTargetHoop = payload.hoops[0];
      await submitAnalysis(selectedTargetHoop);
      return;
    }

    await openHoopPicker(payload);
  } catch (error) {
    showError(error.message);
  } finally {
    syncAlgorithmUi();
    analyzeBtn.disabled = false;
  }
}

async function submitAnalysis(targetHoop = null) {
  if (!currentFile) {
    return;
  }

  hide(hoopSelectSection);
  hide(roiSection);
  show(playerSection);
  show(progressSection);
  show(liveStats);
  playerTitle.textContent = "分析预览";
  playerBadge.textContent = "实时分析中";
  show(playerBadge);
  confirmRoiBtn.disabled = true;
  analyzeBtn.disabled = true;
  confirmHoopBtn.disabled = true;

  const formData = new FormData();
  formData.append("file", currentFile);
  if (selectedRoi && !USE_AUTO_ROI_FOR_TEST) {
    formData.append("roi_x1", selectedRoi.x1);
    formData.append("roi_y1", selectedRoi.y1);
    formData.append("roi_x2", selectedRoi.x2);
    formData.append("roi_y2", selectedRoi.y2);
  }
  formData.append("has_net", "false");
  formData.append("algorithm", getSelectedAlgorithm());
  if (targetHoop) {
    formData.append("target_hoop_cx", targetHoop.cx);
    formData.append("target_hoop_cy", targetHoop.cy);
    formData.append("target_hoop_w", targetHoop.w);
    formData.append("target_hoop_h", targetHoop.h);
  }
  const clipSettings = getClipSettings();
  formData.append("clip_before", clipSettings.before);
  formData.append("clip_after", clipSettings.after);

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "上传失败");
    }

    currentJobId = payload.job_id;
    startPreviewPolling(payload.job_id);
    pollJob(payload.job_id);
  } catch (error) {
    showError(error.message);
    analyzeBtn.disabled = false;
    confirmRoiBtn.disabled = false;
    confirmHoopBtn.disabled = false;
  }
}

async function startAnalysis() {
  selectedRoi = null;
  selectedTargetHoop = null;

  const algorithm = getSelectedAlgorithm();
  if (algorithm === "original" || algorithm === "hoopcut" || algorithm === "swishai") {
    await submitAnalysis(null);
    return;
  }

  await prepareTargetHoopAnalysis();
}

async function openRoiSetup() {
  if (!currentFile) {
    return;
  }

  hide(errorSection);
  hide(resultsSection);
  hide(playerSection);
  show(roiSection);

  if (!roiSelector) {
    roiSelector = new RoiSelector(roiCanvas, roiSourceVideo);
  }

  try {
    confirmRoiBtn.disabled = true;
    await roiSelector.loadFile(currentFile);
    selectedRoi = roiSelector.toNativeRect();
    confirmRoiBtn.disabled = false;
  } catch (error) {
    showError(error.message);
  }
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("dragover");
});

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  const file = event.dataTransfer.files[0];
  if (file) {
    setFile(file);
  }
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (file) {
    setFile(file);
  }
});

clearFileBtn.addEventListener("click", () => {
  fileInput.value = "";
  setFile(null);
  resetUI();
});

if (USE_AUTO_ROI_FOR_TEST) {
  analyzeBtn.addEventListener("click", startAnalysis);
} else {
  analyzeBtn.addEventListener("click", openRoiSetup);
}

confirmHoopBtn.addEventListener("click", () => {
  if (!selectedTargetHoop) {
    return;
  }
  submitAnalysis(selectedTargetHoop);
});

cancelHoopBtn.addEventListener("click", () => {
  hide(hoopSelectSection);
  selectedTargetHoop = null;
  analyzeBtn.disabled = !currentFile;
});
resetRoiBtn.addEventListener("click", () => {
  if (roiSelector) {
    roiSelector.reset();
    selectedRoi = roiSelector.toNativeRect();
  }
});

confirmRoiBtn.addEventListener("click", () => {
  if (roiSelector) {
    selectedRoi = roiSelector.toNativeRect();
  }
  startAnalysis();
});

function showError(message) {
  hide(progressSection);
  hide(playerSection);
  hide(roiSection);
  errorMessage.textContent = message;
  show(errorSection);
}

function pollJob(jobId) {
  if (pollTimer) {
    clearInterval(pollTimer);
  }

  pollTimer = setInterval(async () => {
    try {
      const response = await fetch(`/api/jobs/${jobId}`);
      const job = await response.json();

      if (!response.ok) {
        throw new Error(job.detail || "查询任务失败");
      }

      updateProgress(job);
      updateLiveStats(job);

      if (job.status === "completed") {
        clearInterval(pollTimer);
        pollTimer = null;
        stopPreviewPolling();
        renderResults(job.result, jobId);
        analyzeBtn.disabled = false;
        confirmRoiBtn.disabled = false;
      }

      if (job.status === "failed") {
        clearInterval(pollTimer);
        pollTimer = null;
        stopPreviewPolling();
        showError(job.error || "分析过程中出现错误");
        analyzeBtn.disabled = false;
        confirmRoiBtn.disabled = false;
      }
    } catch (error) {
      clearInterval(pollTimer);
      pollTimer = null;
      stopPreviewPolling();
      showError(error.message);
      analyzeBtn.disabled = false;
      confirmRoiBtn.disabled = false;
    }
  }, 800);
}

function updateProgress(job) {
  const progress = job.progress || 0;
  progressFill.style.width = `${progress}%`;
  progressLabel.textContent = `${progress}%`;

  if (job.status === "queued") {
    progressDetail.textContent = "任务排队中…";
  } else if (job.processed_frames && job.total_frames) {
    progressDetail.textContent = `已处理 ${job.processed_frames} / ${job.total_frames} 帧`;
  } else {
    progressDetail.textContent = "正在分析视频…";
  }
}

function updateLiveStats(job) {
  const stats = job.live_stats;
  if (!stats) {
    return;
  }

  liveScore.textContent = `${stats.makes} / ${stats.attempts}`;
  liveStatus.textContent = stats.overlay_text || "Analyzing...";
}

function renderResults(result, jobId) {
  hide(progressSection);
  show(resultsSection);
  show(playerSection);

  currentResult = result;
  currentJobId = jobId || currentJobId;
  stopClipPlayback();
  hide(clipInfo);
  if (activeShotRow) {
    activeShotRow.classList.remove("row-active");
    activeShotRow = null;
  }

  playerTitle.textContent = "标注回放";
  hide(playerBadge);

  statAttempts.textContent = result.attempts;
  statMakes.textContent = result.makes;
  statMisses.textContent = result.misses;
  statPercentage.textContent = `${result.percentage}%`;

  if (algorithmBadge) {
    algorithmBadge.textContent = `当前结果 · ${getAlgorithmLabel(result.algorithm || "optimized")}`;
    show(algorithmBadge);
  }

  hide(livePreview);
  show(resultVideo);
  resultVideo.src = `${result.output_url}?t=${Date.now()}`;
  resultVideo.load();
  resultVideo.play().catch(() => {});
  setupVideoDockObserver();

  shotsBody.innerHTML = "";
  if (!result.shots.length) {
    show(emptyShots);
    shotCount.textContent = "0 次投篮";
    return;
  }

  hide(emptyShots);
  shotCount.textContent = `${result.shots.length} 次投篮`;

  for (const shot of result.shots) {
    const row = document.createElement("tr");
    const resultClass = shot.result === "Make" ? "make" : "miss";
    const resultLabel = shot.result === "Make" ? "进球" : "未进";

    const traj = shot.trajectory_cross ? "✓" : "—";
    const net = shot.net_swish ? "✓" : "—";

    row.innerHTML = `
      <td>${shot.attempt}</td>
      <td>${shot.time_s}s</td>
      <td>${shot.frame}</td>
      <td><span class="tag ${resultClass}">${resultLabel}</span></td>
      <td>${traj}</td>
      <td>${net}</td>
      <td><button type="button" class="play-btn">▶ 回放</button></td>
    `;

    const playBtn = row.querySelector(".play-btn");
    playBtn.addEventListener("click", () => playShotClip(shot, row));

    shotsBody.appendChild(row);
  }
}

resultVideo.addEventListener("play", () => {
  if (!clipTimeUpdateHandler) {
    hide(clipInfo);
    playerTitle.textContent = "标注回放";
    syncDockTitle();
  }
});
