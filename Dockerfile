FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MODELS_DIR=/app/models

WORKDIR /app

# Piper's release bundle includes its runtime components. espeak-ng is
# installed explicitly as requested, alongside common runtime libraries.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates espeak-ng libgomp1 tar \
    && rm -rf /var/lib/apt/lists/*

# Piper Linux x86-64 release bundle. Render's standard Docker service is
# expected to build/run on x86-64. See README if using another architecture.
RUN mkdir -p /opt/piper && \
    curl -fL --retry 3 \
      https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz \
      -o /tmp/piper.tar.gz && \
    tar -xzf /tmp/piper.tar.gz -C /opt/piper && \
    rm /tmp/piper.tar.gz && \
    PIPER_BIN="$(find /opt/piper -type f -name piper -perm /111 | head -n 1)" && \
    test -n "$PIPER_BIN" && \
    ln -s "$PIPER_BIN" /usr/local/bin/piper && \
    piper --help >/dev/null

# Download only the four requested voices and their matching JSON configs.
RUN set -eux; \
    BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"; \
    mkdir -p /app/models; \
    curl -fL --retry 3 "$BASE/en/en_US/hfc_male/medium/en_US-hfc_male-medium.onnx" -o /app/models/en_US-hfc_male-medium.onnx; \
    curl -fL --retry 3 "$BASE/en/en_US/hfc_male/medium/en_US-hfc_male-medium.onnx.json" -o /app/models/en_US-hfc_male-medium.onnx.json; \
    curl -fL --retry 3 "$BASE/en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx" -o /app/models/en_US-libritts_r-medium.onnx; \
    curl -fL --retry 3 "$BASE/en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx.json" -o /app/models/en_US-libritts_r-medium.onnx.json; \
    curl -fL --retry 3 "$BASE/en/en_US/ryan/medium/en_US-ryan-medium.onnx" -o /app/models/en_US-ryan-medium.onnx; \
    curl -fL --retry 3 "$BASE/en/en_US/ryan/medium/en_US-ryan-medium.onnx.json" -o /app/models/en_US-ryan-medium.onnx.json; \
    curl -fL --retry 3 "$BASE/ml/ml_IN/arjun/medium/ml_IN-arjun-medium.onnx" -o /app/models/ml_IN-arjun-medium.onnx; \
    curl -fL --retry 3 "$BASE/ml/ml_IN/arjun/medium/ml_IN-arjun-medium.onnx.json" -o /app/models/ml_IN-arjun-medium.onnx.json; \
    test "$(find /app/models -maxdepth 1 -type f | wc -l)" -eq 8

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Render sets PORT automatically. Fall back to 10000 for local runs.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
