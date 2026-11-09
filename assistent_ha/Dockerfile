# Imatge base oficial de Python, multi-arquitectura (amd64 i aarch64).
# Es manté a Debian 12 perquè totes les dependències (ctranslate2, onnxruntime,
# PyAV) tenen rodes precompilades per a Python 3.12.
FROM python:3.12-slim-bookworm

ARG BUILD_VERSION=dev
ARG BUILD_ARCH=amd64

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1

LABEL io.hass.type="app" \
      io.hass.version="${BUILD_VERSION}" \
      io.hass.arch="${BUILD_ARCH}"

# ca-certificates per a HTTPS; tzdata per a les zones horàries.
# ffmpeg no cal: PyAV (dependència de faster-whisper) ja porta els còdecs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install -r requirements.txt

COPY app ./app

EXPOSE 8099

CMD ["python3", "-m", "app.main"]
