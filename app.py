import asyncio
import os
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

MODELS_DIR = Path(os.getenv("MODELS_DIR", "/app/models"))
PIPER_BIN = os.getenv("PIPER_BIN", "/usr/local/bin/piper")
MAX_TEXT_LENGTH = 2000
GENERATION_TIMEOUT_SECONDS = 60
MAX_CONCURRENT_GENERATIONS = int(os.getenv("MAX_CONCURRENT_GENERATIONS", "1"))

VOICES = {
    "hfc_male": MODELS_DIR / "en_US-hfc_male-medium.onnx",
    "libritts_r": MODELS_DIR / "en_US-libritts_r-medium.onnx",
    "ryan": MODELS_DIR / "en_US-ryan-medium.onnx",
    "arjun": MODELS_DIR / "ml_IN-arjun-medium.onnx",
}

generation_semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)

app = FastAPI(
    title="Piper TTS API",
    description="Text-to-speech API with four Piper voices.",
    version="1.0.0",
)

# Public CORS, as requested. This does not provide authentication or rate limiting.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def validate_runtime():
    if not Path(PIPER_BIN).is_file():
        raise RuntimeError(f"Piper executable not found: {PIPER_BIN}")

    for name, model in VOICES.items():
        if not model.is_file():
            raise RuntimeError(f"Model missing for voice '{name}': {model}")
        if not Path(str(model) + ".json").is_file():
            raise RuntimeError(f"Model JSON missing for voice '{name}'")


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Piper TTS API",
        "default_voice": "ryan",
        "voices": list(VOICES.keys()),
        "usage": "/generate?text=Hello%20world&voice=ryan",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/generate")
async def generate(
    text: str = Query(..., min_length=1, max_length=MAX_TEXT_LENGTH),
    voice: Literal["hfc_male", "libritts_r", "ryan", "arjun"] = "ryan",
):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    model_path = VOICES[voice]
    fd, output_path = tempfile.mkstemp(prefix="piper-", suffix=".wav", dir="/tmp")
    os.close(fd)
    wav_path = Path(output_path)

    try:
        async with generation_semaphore:
            process = await asyncio.create_subprocess_exec(
                PIPER_BIN,
                "--model", str(model_path),
                "--output_file", str(wav_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(input=(text + "\n").encode("utf-8")),
                    timeout=GENERATION_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise HTTPException(
                    status_code=504,
                    detail="Speech generation timed out. Try shorter text.",
                )

        if process.returncode != 0:
            details = stderr.decode("utf-8", errors="replace")[-1500:]
            raise HTTPException(
                status_code=500,
                detail=f"Piper failed to generate audio: {details}",
            )

        if not wav_path.is_file() or wav_path.stat().st_size <= 44:
            raise HTTPException(status_code=500, detail="Piper returned an empty WAV.")

        return FileResponse(
            path=str(wav_path),
            media_type="audio/wav",
            filename=f"speech_{voice}.wav",
            headers={"Cache-Control": "no-store"},
            background=BackgroundTask(lambda: wav_path.unlink(missing_ok=True)),
        )

    except HTTPException:
        wav_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        wav_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail="Internal speech generation error.",
        ) from exc
