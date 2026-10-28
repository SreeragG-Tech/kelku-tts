FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    PIPER_MODEL_CACHE_SIZE=2

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    espeak-ng \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Piper's Python API so ONNX models can remain loaded between requests.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download exactly the four requested ONNX models and matching JSON files.
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
    curl -fL --retry 3 "$BASE/ml/ml_IN/arjun/medium/ml_IN-arjun-medium.onnx.json" -o /app/models/ml_IN-arjun-medium.onnx.json

COPY app.py .

EXPOSE 10000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
