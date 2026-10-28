import asyncio
import os
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

APP_HOME = Path("/app")
MODELS_DIR = APP_HOME / "models"
PIPER_BIN = "/usr/local/bin/piper"
MAX_TEXT_LENGTH = 2000
GENERATION_TIMEOUT_SECONDS = 60
MAX_CONCURRENT_GENERATIONS = 2

generation_semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATIONS)

VOICES = {
    "hfc_male": MODELS_DIR / "en_US-hfc_male-medium.onnx",
    "libritts_r": MODELS_DIR / "en_US-libritts_r-medium.onnx",
    "ryan": MODELS_DIR / "en_US-ryan-medium.onnx",
    "arjun": MODELS_DIR / "ml_IN-arjun-medium.onnx",
}

app = FastAPI(
    title="Kelku TTS",
    description="Text-to-speech API powered by Piper, with English and Malayalam voices.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def validate_installation():
    if not Path(PIPER_BIN).is_file():
        raise RuntimeError(f"Piper executable not found at {PIPER_BIN}")

    for voice, model_path in VOICES.items():
        config_path = Path(f"{model_path}.json")
        if not model_path.is_file():
            raise RuntimeError(f"Model for voice '{voice}' is missing: {model_path}")
        if not config_path.is_file():
            raise RuntimeError(f"Config for voice '{voice}' is missing: {config_path}")


@app.get("/")
async def root():
    return {
        "name": "Kelku TTS",
        "status": "online",
        "default_voice": "ryan",
        "voices": list(VOICES.keys()),
        "usage": "/generate?text=Hello%20world&voice=ryan",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/generate")
async def generate_speech(
    text: str = Query(..., min_length=1, max_length=MAX_TEXT_LENGTH),
    voice: Literal["hfc_male", "libritts_r", "ryan", "arjun"] = "ryan",
):
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    model_path = VOICES[voice]
    temp = tempfile.NamedTemporaryFile(
        prefix="kelku_tts_", suffix=".wav", dir="/tmp", delete=False
    )
    wav_path = Path(temp.name)
    temp.close()

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
            error = stderr.decode("utf-8", errors="replace")[-1500:]
            raise HTTPException(
                status_code=500,
                detail=f"Piper failed to generate audio: {error}",
            )

        if not wav_path.is_file() or wav_path.stat().st_size == 0:
            raise HTTPException(status_code=500, detail="Piper returned an empty audio file.")

        return FileResponse(
            path=str(wav_path),
            media_type="audio/wav",
            filename=f"kelku_{voice}.wav",
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
