# Basketball Shot Detector — CPU image (suitable for GCP VM / Cloud Run)
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads outputs

ENV PORT=8080
EXPOSE 8080

# Cloud Run / GCE: bind all interfaces
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT}
