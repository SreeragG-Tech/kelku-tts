import asyncio
import os
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
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


@app.get("/", response_class=HTMLResponse)
async def root():
    return r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0b1020">
<title>Kelku TTS · Text to Speech</title>
<style>
:root{color-scheme:dark;--bg:#080c18;--panel:#11182a;--panel2:#151f35;--line:#26324b;--text:#f4f7ff;--muted:#9aa8c2;--accent:#8b9dff;--accent2:#67e8d1;--danger:#ff9a9a}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 15% 0%,#172344 0,transparent 42%),radial-gradient(ellipse at 100% 15%,#153b42 0,transparent 28%),var(--bg);color:var(--text);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}
.wrap{width:min(1080px,92%);margin:auto}.nav{display:flex;align-items:center;justify-content:space-between;padding:26px 0}.brand{display:flex;gap:12px;align-items:center;font-weight:800;font-size:20px;letter-spacing:-.5px}.logo{display:grid;place-items:center;width:42px;height:42px;border-radius:14px;background:linear-gradient(135deg,#a5b4fc,#5eead4);color:#07111e;font-size:21px;box-shadow:0 8px 30px #67e8d133}.badge{font-size:12px;color:#b7c4dc;border:1px solid var(--line);padding:7px 11px;border-radius:999px}.hero{padding:54px 0 32px;max-width:760px}.eyebrow{color:var(--accent2);font-size:12px;font-weight:800;letter-spacing:2px;text-transform:uppercase}.hero h1{font-size:clamp(38px,6vw,66px);line-height:1.02;letter-spacing:-2.7px;margin:17px 0}.hero h1 span{background:linear-gradient(90deg,#c7d2fe,#67e8d1);color:transparent;background-clip:text}.hero p{color:var(--muted);font-size:17px;line-height:1.7;max-width:650px;margin:0}
.grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(280px,.75fr);gap:20px;margin:24px 0 60px}.card{background:linear-gradient(180deg,#121a2c,#0e1525);border:1px solid var(--line);border-radius:24px;padding:25px;box-shadow:0 20px 70px #0002}.card h2{font-size:19px;margin:0 0 8px;letter-spacing:-.4px}.sub{font-size:13px;color:var(--muted);line-height:1.6;margin:0 0 22px}.label{display:block;font-size:13px;color:#d5def0;font-weight:650;margin:18px 0 9px}textarea,select{width:100%;background:#0a1020;border:1px solid #34415d;border-radius:12px;color:var(--text);font:inherit;padding:14px;outline:none}textarea{min-height:150px;resize:vertical;line-height:1.55}textarea:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px #8b9dff22}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.counter{display:flex;justify-content:space-between;color:var(--muted);font-size:12px;margin-top:7px}.btn{border:0;border-radius:12px;padding:13px 17px;font:inherit;font-weight:750;cursor:pointer;transition:transform .15s,opacity .15s}.btn:hover{transform:translateY(-1px)}.btn:disabled{opacity:.55;cursor:wait;transform:none}.primary{width:100%;margin-top:20px;background:linear-gradient(100deg,#a5b4fc,#67e8d1);color:#07111e}.secondary{background:#1a2540;color:#e5eaff;border:1px solid #34415d}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}.status{font-size:13px;color:var(--muted);margin-top:14px;min-height:20px}.status.error{color:var(--danger)}.player{margin-top:19px;padding:15px;border:1px solid var(--line);border-radius:15px;background:#0a1020}.player audio{width:100%;margin-top:10px}.hidden{display:none}.voice-list{display:grid;gap:10px;margin-top:18px}.voice{padding:13px;border:1px solid var(--line);border-radius:14px;background:#0d1424;display:flex;align-items:center;gap:12px}.voice-icon{width:38px;height:38px;display:grid;place-items:center;border-radius:12px;background:#202d49;font-size:18px}.voice strong{display:block;font-size:13px}.voice small{display:block;color:var(--muted);font-size:12px;margin-top:4px}.pill{margin-left:auto;font-size:10px;color:#a7f3d0;background:#12352f;padding:5px 7px;border-radius:999px}.info{margin-top:20px;padding:16px;border-radius:14px;background:#121d31;color:var(--muted);font-size:12px;line-height:1.7}.footer{display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap;border-top:1px solid var(--line);padding:22px 0 30px;color:var(--muted);font-size:12px}.footer a,.api-link{color:#c6d0ff;text-decoration:none}.footer a:hover,.api-link:hover{text-decoration:underline}
@media(max-width:760px){.hero{padding-top:35px}.grid{grid-template-columns:1fr}.card{padding:20px}.row{grid-template-columns:1fr}.nav{padding:18px 0}.hero h1{letter-spacing:-1.7px}}
</style>
</head>
<body>
<div class="wrap">
<header class="nav">
  <div class="brand"><div class="logo">♫</div><span>Kelku TTS</span></div>
  <a class="badge api-link" href="/docs">API documentation ↗</a>
</header>
<main>
  <section class="hero">
    <div class="eyebrow">Text to speech · Powered by Piper</div>
    <h1>Give your words<br><span>a voice.</span></h1>
    <p>Generate natural-sounding speech in English or Malayalam. Choose a voice, enter your text, and listen or download the audio.</p>
  </section>
  <section class="grid">
    <div class="card">
      <h2>Create speech</h2>
      <p class="sub">Your text is converted into a WAV audio file by the Kelku TTS API.</p>
      <form id="ttsForm">
        <label class="label" for="text">Text to speak</label>
        <textarea id="text" maxlength="2000" placeholder="Type something you want to hear..." required>Hello, welcome to Kelku TTS.</textarea>
        <div class="counter"><span>Maximum 2,000 characters</span><span id="count">34 / 2000</span></div>
        <div class="row">
          <div><label class="label" for="voice">Voice</label>
            <select id="voice">
              <option value="ryan">Ryan · English US</option>
              <option value="hfc_male">HFC Male · English US</option>
              <option value="libritts_r">LibriTTS R · English US</option>
              <option value="arjun">Arjun · Malayalam</option>
            </select>
          </div>
          <div><label class="label" for="format">Output</label><select id="format" disabled><option>WAV audio</option></select></div>
        </div>
        <button class="btn primary" id="generate" type="submit">✦ Generate speech</button>
        <div id="status" class="status" role="status" aria-live="polite"></div>
        <div id="playerBox" class="player hidden">
          <strong>🎧 Your audio is ready</strong>
          <audio id="audio" controls></audio>
          <div class="actions"><a id="download" class="btn secondary" download="kelku-speech.wav" style="text-decoration:none">Download WAV ↓</a><button class="btn secondary" id="reset" type="button">Clear audio</button></div>
        </div>
      </form>
    </div>
    <aside class="card">
      <h2>Choose your voice</h2>
      <p class="sub">Four voices, two languages. Switch voices any time.</p>
      <div class="voice-list">
        <div class="voice"><div class="voice-icon">🎙️</div><div><strong>Ryan</strong><small>English · US · Medium</small></div><span class="pill">DEFAULT</span></div>
        <div class="voice"><div class="voice-icon">🗣️</div><div><strong>HFC Male</strong><small>English · US · Medium</small></div></div>
        <div class="voice"><div class="voice-icon">📖</div><div><strong>LibriTTS R</strong><small>English · US · Medium</small></div></div>
        <div class="voice"><div class="voice-icon">🇮🇳</div><div><strong>Arjun</strong><small>Malayalam · Medium</small></div></div>
      </div>
      <div class="info"><strong style="color:#e5eaff">A quick note</strong><br>Free hosting can take a little longer to respond after inactivity. Keep this page open while your first request wakes the service.</div>
    </aside>
  </section>
</main>
<footer class="footer"><span>© <span id="year"></span> Kelku TTS · Built with FastAPI + Piper</span><span><a href="/docs">API docs</a> &nbsp;·&nbsp; <a href="/openapi.json">OpenAPI schema</a></span></footer>
</div>
<script>
const textEl=document.getElementById('text'), countEl=document.getElementById('count');
const form=document.getElementById('ttsForm'), button=document.getElementById('generate');
const statusEl=document.getElementById('status'), playerBox=document.getElementById('playerBox');
const audio=document.getElementById('audio'), download=document.getElementById('download');
let currentUrl=null;
document.getElementById('year').textContent=new Date().getFullYear();
function updateCount(){countEl.textContent=`${textEl.value.length} / 2000`}
textEl.addEventListener('input',updateCount);updateCount();
document.getElementById('voice').addEventListener('change',e=>{
  if(e.target.value==='arjun' && !textEl.value.trim()) textEl.value='നമസ്കാരം';
});
form.addEventListener('submit',async e=>{
  e.preventDefault();
  const text=textEl.value.trim(), voice=document.getElementById('voice').value;
  if(!text){statusEl.textContent='Enter some text first.';statusEl.className='status error';return}
  button.disabled=true;button.textContent='Generating audio…';statusEl.className='status';statusEl.textContent='Generating speech. The first request may take longer on free hosting.';
  playerBox.classList.add('hidden');
  try{
    const params=new URLSearchParams({text,voice});
    const response=await fetch(`/generate?${params.toString()}`);
    if(!response.ok){
      let message=`Request failed (${response.status})`;
      try{const data=await response.json();message=data.detail||message}catch{}
      throw new Error(message);
    }
    const blob=await response.blob();
    if(!blob.size)throw new Error('The API returned an empty audio file.');
    if(currentUrl)URL.revokeObjectURL(currentUrl);
    currentUrl=URL.createObjectURL(blob);audio.src=currentUrl;download.href=currentUrl;download.download=`kelku-${voice}.wav`;
    playerBox.classList.remove('hidden');statusEl.textContent='Audio generated successfully.';
    try{await audio.play()}catch{}
  }catch(err){statusEl.textContent=err.message||'Could not generate speech. Please try again.';statusEl.className='status error'}
  finally{button.disabled=false;button.textContent='✦ Generate speech'}
});
document.getElementById('reset').addEventListener('click',()=>{
  audio.pause();audio.removeAttribute('src');audio.load();playerBox.classList.add('hidden');
  if(currentUrl){URL.revokeObjectURL(currentUrl);currentUrl=null}
  statusEl.textContent='';
});
</script>
</body>
</html>"""


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
