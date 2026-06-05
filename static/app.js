const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const selectedFile = document.getElementById("selected-file");
const fileName = document.getElementById("file-name");
const clearFileBtn = document.getElementById("clear-file");
const analyzeBtn = document.getElementById("analyze-btn");

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
const downloadAllClips = document.getElementById("download-all-clips");

const CLIP_SETTINGS_KEY = "basketball_clip_settings";
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

initClipSettings();

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
  progressFill.style.width = "0%";
  progressLabel.textContent = "0%";
  selectedRoi = null;
  currentResult = null;
  currentJobId = null;
  hide(downloadAllClips);
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

async function startAnalysis() {
  if (!currentFile) {
    return;
  }

  hide(roiSection);
  show(playerSection);
  show(progressSection);
  show(liveStats);
  playerTitle.textContent = "分析预览";
  playerBadge.textContent = "实时分析中";
  show(playerBadge);
  confirmRoiBtn.disabled = true;
  analyzeBtn.disabled = true;

  const formData = new FormData();
  formData.append("file", currentFile);
  if (selectedRoi && !USE_AUTO_ROI_FOR_TEST) {
    formData.append("roi_x1", selectedRoi.x1);
    formData.append("roi_y1", selectedRoi.y1);
    formData.append("roi_x2", selectedRoi.x2);
    formData.append("roi_y2", selectedRoi.y2);
  }
  formData.append("has_net", hasNetInput && hasNetInput.checked ? "true" : "false");
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
  analyzeBtn.textContent = "开始分析（自动 ROI）";
  analyzeBtn.addEventListener("click", () => {
    selectedRoi = null;
    startAnalysis();
  });
} else {
  analyzeBtn.addEventListener("click", openRoiSetup);
}
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
    hide(downloadAllClips);
    return;
  }

  hide(emptyShots);
  shotCount.textContent = `${result.shots.length} 次投篮`;

  if (result.clips_zip_url) {
    downloadAllClips.href = `${result.clips_zip_url}?t=${Date.now()}`;
    downloadAllClips.download = `shots_${currentJobId || "export"}.zip`;
    show(downloadAllClips);
  } else {
    hide(downloadAllClips);
  }

  for (const shot of result.shots) {
    const row = document.createElement("tr");
    const resultClass = shot.result === "Make" ? "make" : "miss";
    const resultLabel = shot.result === "Make" ? "进球" : "未进";

    const traj = shot.trajectory_cross ? "✓" : "—";
    const net = shot.net_swish ? "✓" : "—";

    const saveCell = shot.clip_download_url
      ? `<a class="save-btn ${resultClass === "miss" ? "miss-save" : ""}" href="${shot.clip_download_url}" download="${shot.clip_filename || ""}">↓ 保存</a>`
      : `<span class="muted">—</span>`;

    row.innerHTML = `
      <td>${shot.attempt}</td>
      <td>${shot.time_s}s</td>
      <td>${shot.frame}</td>
      <td><span class="tag ${resultClass}">${resultLabel}</span></td>
      <td>${traj}</td>
      <td>${net}</td>
      <td><button type="button" class="play-btn">▶ 回放</button></td>
      <td>${saveCell}</td>
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
