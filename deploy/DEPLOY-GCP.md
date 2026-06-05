# 部署到 Google Cloud（GCP）

本项目是 **FastAPI + YOLO + OpenCV**，单次分析可能耗时很长，且支持 **GB 级视频上传**。请优先使用 **Compute Engine 虚拟机**，而不是直接上 Cloud Run（Cloud Run 单次 HTTP 请求体默认约 **32MB**，不适合 3GB 直传）。

---

## 方案对比

| 方案 | 适合场景 | 大视频上传 | 长任务 | 成本 |
|------|----------|------------|--------|------|
| **Compute Engine + Docker**（推荐） | 个人/小团队生产 | ✅ 磁盘够大即可 | ✅ | 按 VM 计费，可关机省钱 |
| Cloud Run | 轻量、偶发、小视频 | ❌ 需改 GCS 直传 | ⚠️ 最长 60 分钟/请求 | 按调用计费 |
| GKE | 大规模多实例 | 需配套存储 | ✅ | 偏高 |

下文以 **GCE 虚拟机** 为主；文末附 Cloud Run 简要说明。

---

## 前置准备

1. [Google Cloud 控制台](https://console.cloud.google.com/) 创建项目，记下 **项目 ID**（如 `my-basketball-app`）。
2. 本机安装 [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)：

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable compute.googleapis.com artifactregistry.googleapis.com
```

3. 确保项目目录含 `best.pt`（约 6MB），Docker 构建会打进镜像。

---

## 方案 A：Compute Engine（推荐）

### 1. 创建虚拟机

控制台：**Compute Engine → VM 实例 → 创建**

建议配置：

| 项 | 建议值 |
|----|--------|
| 区域 | 离你近的（如 `asia-east1` 台湾） |
| 机器类型 | `e2-standard-4`（4 vCPU / 16GB）或更大 |
| 启动磁盘 | Ubuntu 22.04 LTS，**≥ 100GB**（存上传与输出） |
| 防火墙 | 勾选「允许 HTTP 流量」 |

或用命令行：

```bash
gcloud compute instances create basketball-detector \
  --zone=asia-east1-a \
  --machine-type=e2-standard-4 \
  --boot-disk-size=100GB \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --tags=http-server
```

### 2. 开放端口（防火墙）

应用监听 **8080**（容器内）映射到主机 8080：

```bash
gcloud compute firewall-rules create allow-basketball-8080 \
  --allow=tcp:8080 \
  --target-tags=http-server \
  --description="Basketball shot detector web"
```

生产环境建议前面加 **Nginx + HTTPS**（见下文「绑定域名与 HTTPS」）。

### 3. SSH 登录并安装 Docker

```bash
gcloud compute ssh basketball-detector --zone=asia-east1-a
```

在 VM 上：

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER
# 退出 SSH 再登录一次，使 docker 组生效
```

### 4. 上传代码并构建（在 VM 上）

**方式 1 — Git（推荐）**

```bash
git clone YOUR_REPO_URL basketball-app
cd basketball-app
docker build -t basketball-detector .
```

**方式 2 — 本机构建后推送到 Artifact Registry**

在本机（项目根目录）：

```bash
export PROJECT_ID=YOUR_PROJECT_ID
export REGION=asia-east1

gcloud auth configure-docker ${REGION}-docker.pkg.dev

gcloud artifacts repositories create basketball \
  --repository-format=docker \
  --location=${REGION} \
  --description="Basketball detector images" || true

docker build -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/basketball/detector:latest .
docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/basketball/detector:latest
```

在 VM 上拉取并运行：

```bash
docker pull asia-east1-docker.pkg.dev/YOUR_PROJECT_ID/basketball/detector:latest

docker run -d \
  --name basketball \
  --restart unless-stopped \
  -p 8080:8080 \
  -v /var/basketball/uploads:/app/uploads \
  -v /var/basketball/outputs:/app/outputs \
  asia-east1-docker.pkg.dev/YOUR_PROJECT_ID/basketball/detector:latest
```

访问：`http://VM_EXTERNAL_IP:8080`

查外网 IP：

```bash
gcloud compute instances describe basketball-detector \
  --zone=asia-east1-a \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

### 5. 持久化目录

`-v` 把上传与输出挂到宿主机，避免容器删除后丢文件：

```bash
sudo mkdir -p /var/basketball/uploads /var/basketball/outputs
```

---

## 绑定域名与 HTTPS（可选）

1. 将域名 A 记录指向 VM 外网 IP。
2. 在 VM 安装 Nginx + Certbot，反向代理到 `127.0.0.1:8080`：

```nginx
server {
    listen 80;
    server_name your-domain.com;
    client_max_body_size 0;   # 不限制上传大小（由磁盘容量决定）

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_request_buffering off;
    }
}
```

```bash
sudo certbot --nginx -d your-domain.com
```

`client_max_body_size 0` 与长超时对大视频分析很重要。

---

## 方案 B：Cloud Run（仅适合小视频或后续改造）

限制：

- 请求体约 **32MB**，不能直接上传 3GB 文件。
- 需改为：**浏览器 → 上传到 Cloud Storage → 后台 Job 读 GCS 分析**（当前代码未实现）。

若仍要试跑（测试用小视频）：

```bash
gcloud run deploy basketball-detector \
  --source . \
  --region asia-east1 \
  --allow-unauthenticated \
  --memory 4Gi \
  --cpu 2 \
  --timeout 3600 \
  --max-instances 1
```

`--max-instances 1` 避免多实例导致内存里 `jobs` 状态不一致。

---

## GPU 加速（可选）

若命中率/速度要求高，可创建带 GPU 的 VM（如 `n1-standard-4` + NVIDIA T4），在 Dockerfile 中改用 CUDA 版 PyTorch，并安装 NVIDIA Container Toolkit。CPU 版镜像在 `e2-standard-4` 上通常已可运行。

---

## 运维提示

1. **任务状态在内存**：重启容器会丢失进行中的任务；生产可后续接 Redis + 任务队列。
2. **磁盘空间**：定期清理 `uploads/`、`outputs/`，或挂更大磁盘 / 生命周期策略。
3. **安全**：公网部署请加 HTTPS、访问密码或 IAP；勿把 API 长期裸露在无鉴权环境。
4. **费用**：不用时 **停止 VM** 可省计算费（磁盘仍计费）。

```bash
gcloud compute instances stop basketball-detector --zone=asia-east1-a
gcloud compute instances start basketball-detector --zone=asia-east1-a
```

---

## 快速检查清单

- [ ] `best.pt` 已包含在镜像或挂载卷中  
- [ ] 防火墙已放行 8080（或 443）  
- [ ] 磁盘 ≥ 100GB（若常分析长视频）  
- [ ] Nginx `client_max_body_size` 与 `proxy_read_timeout` 已调大  
- [ ] 浏览器访问 `http://IP:8080` 能打开上传页  

---

## 常见问题

**Q: 上传很慢或超时？**  
增大 Nginx 超时；确保 VM 带宽足够；超大文件可考虑先压缩或分段。

**Q: 分析到一半失败？**  
查看容器日志：`docker logs basketball`。多为内存不足，可换更大机器类型。

**Q: 想用 Cloud Run 又要大文件？**  
需要开发 GCS 直传 + 异步 Worker，属于下一阶段架构改造。
