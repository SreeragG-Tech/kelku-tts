import asyncio
import io
import os
import threading
import time
import wave
from collections import OrderedDict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from piper import PiperVoice

APP_HOME = Path("/app")
MODELS_DIR = APP_HOME / "models"
MAX_TEXT_LENGTH = 2000

# Render Free is memory-constrained. Keep a small LRU cache of loaded ONNX
# sessions rather than loading all four models at once.
MODEL_CACHE_SIZE = max(1, int(os.getenv("PIPER_MODEL_CACHE_SIZE", "2")))
VOICES = {
    "hfc_male": MODELS_DIR / "en_US-hfc_male-medium.onnx",
    "libritts_r": MODELS_DIR / "en_US-libritts_r-medium.onnx",
    "ryan": MODELS_DIR / "en_US-ryan-medium.onnx",
    "arjun": MODELS_DIR / "ml_IN-arjun-medium.onnx",
}

_voice_cache = OrderedDict()
_inference_lock = threading.RLock()

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


def get_voice(voice_name: str) -> PiperVoice:
    """Load a voice once and keep recently used models resident in memory."""
    with _inference_lock:
        voice = _voice_cache.get(voice_name)
        if voice is not None:
            _voice_cache.move_to_end(voice_name)
            return voice

        model_path = VOICES[voice_name]
        voice = PiperVoice.load(str(model_path), use_cuda=False)
        _voice_cache[voice_name] = voice
        _voice_cache.move_to_end(voice_name)

        while len(_voice_cache) > MODEL_CACHE_SIZE:
            _voice_cache.popitem(last=False)

        return voice


@app.on_event("startup")
async def validate_installation():
    for voice_name, model_path in VOICES.items():
        config_path = Path(f"{model_path}.json")
        if not model_path.is_file():
            raise RuntimeError(f"Model for voice '{voice_name}' is missing: {model_path}")
        if not config_path.is_file():
            raise RuntimeError(f"Config for voice '{voice_name}' is missing: {config_path}")

    # Preload the default voice so the first normal request avoids model loading.
    # Run blocking model initialization off the event loop.
    await asyncio.to_thread(get_voice, "ryan")

@app.get("/", response_class=HTMLResponse)
async def root():
    return r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#080d1b">
<title>Kelku TTS</title>
<style>
:root{color-scheme:dark;--bg:#080d1b;--panel:#10192b;--panel-hi:#14213a;--line:#273652;--text:#f4f7ff;--muted:#91a1bf;--blue:#a5b4fc;--mint:#67e8d1;--red:#ff9ca8}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:radial-gradient(ellipse at 12% 0%,#1a2b50 0,transparent 38%),radial-gradient(ellipse at 100% 24%,#10343b 0,transparent 26%),var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;letter-spacing:-.01em}
button,select,textarea{font:inherit}
.shell{width:min(860px,calc(100% - 36px));margin:0 auto}
.topbar{height:86px;display:flex;align-items:center;justify-content:space-between;animation:fade-up .55s both}
.brand{display:flex;align-items:center;gap:11px;font-weight:780;font-size:19px;letter-spacing:-.6px}
.mark{display:grid;place-items:center;width:37px;height:37px;border-radius:12px;background:linear-gradient(140deg,var(--blue),var(--mint));color:#07111c;font-size:20px;box-shadow:0 7px 25px #67e8d122}
.api{font-size:12px;color:#aebce0;text-decoration:none;border:1px solid var(--line);padding:8px 11px;border-radius:10px;transition:background .2s,border-color .2s,color .2s}
.api:hover{background:#17243d;border-color:#52658a;color:white}
main{padding:38px 0 70px}
.workspace{display:grid;grid-template-columns:1fr;gap:16px;animation:fade-up .65s .06s both}
.card{background:linear-gradient(155deg,#121d31f5,#0d1525f7);border:1px solid #2a3955;border-radius:22px;padding:24px;box-shadow:0 25px 80px #0002;transition:border-color .25s,transform .25s,box-shadow .25s}
.card:focus-within{border-color:#536b98;box-shadow:0 25px 80px #0003,0 0 0 1px #8b9dff12}
.controls{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:end}
.field-label{display:block;font-size:12px;font-weight:700;color:#b6c4df;margin:0 0 9px 2px;letter-spacing:.04em}
select,textarea{width:100%;background:#090f1e;border:1px solid #2c3b58;border-radius:13px;color:var(--text);outline:none;transition:border-color .2s,box-shadow .2s,background .2s}
select{height:48px;padding:0 14px;cursor:pointer}
textarea{display:block;min-height:205px;resize:vertical;margin-top:15px;padding:17px 16px;font-size:15px;line-height:1.8;letter-spacing:0}
select:focus,textarea:focus{border-color:#8799e9;box-shadow:0 0 0 3px #8b9dff1a;background:#0b1324}
textarea::placeholder{color:#647491}
.text-meta{display:flex;justify-content:space-between;gap:12px;margin:9px 2px 0;color:#7585a3;font-size:11px}
.primary{height:48px;padding:0 19px;border:0;border-radius:13px;background:linear-gradient(110deg,#b4bfff,#6ce8d2);color:#07111d;font-weight:800;white-space:nowrap;cursor:pointer;box-shadow:0 8px 24px #8b9dff1c;transition:transform .2s,filter .2s,box-shadow .2s}
.primary:hover:not(:disabled){transform:translateY(-2px);filter:brightness(1.06);box-shadow:0 12px 28px #8b9dff30}
.primary:active:not(:disabled){transform:translateY(0) scale(.985)}
.primary:disabled{cursor:wait;opacity:.72}
.result{margin-top:17px;padding:16px;border:1px solid var(--line);border-radius:15px;background:#0a1120;animation:fade-up .35s both}
.result-top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}
.state{display:flex;align-items:center;gap:9px;font-size:13px;font-weight:700;color:#dce5fb}
.dot{width:7px;height:7px;border-radius:50%;background:var(--mint);box-shadow:0 0 13px #67e8d188}
.actions{display:flex;gap:8px;align-items:center}
.small-btn{display:inline-flex;align-items:center;justify-content:center;min-height:34px;padding:0 11px;border:1px solid #344563;border-radius:10px;background:#16223a;color:#eaf0ff;text-decoration:none;font-size:12px;font-weight:700;cursor:pointer;transition:transform .2s,background .2s,border-color .2s}
.small-btn:hover{transform:translateY(-1px);background:#202f4d;border-color:#5b6f96}
.wave{height:32px;display:flex;align-items:center;justify-content:center;gap:4px;margin:4px 0 12px}
.wave i{display:block;width:3px;height:7px;border-radius:4px;background:linear-gradient(var(--blue),var(--mint));opacity:.65;transform-origin:center;animation:wave 1s ease-in-out infinite;animation-play-state:paused}
.is-busy .wave i,.is-playing .wave i{animation-play-state:running}
.wave i:nth-child(3n){animation-delay:-.55s}.wave i:nth-child(3n + 1){animation-delay:-.25s}.wave i:nth-child(4n){animation-delay:-.75s}
.sentences{display:grid;gap:5px;max-height:180px;overflow:auto;padding:2px 2px 2px 0}
.sentence{border-radius:9px;padding:8px 10px;color:#7f90af;font-size:12px;line-height:1.55;border:1px solid transparent;transition:background .25s,color .25s,border-color .25s,transform .25s}
.sentence.active{color:#f4f7ff;background:#182640;border-color:#344a70;transform:translateX(2px)}
.sentence.done{color:#9eebdc}
.status{min-height:17px;margin:11px 2px 0;color:#8191ad;font-size:12px}
.status.error{color:var(--red)}
audio{display:none}
.hidden{display:none!important}
.footer{padding:0 0 28px;display:flex;justify-content:space-between;gap:10px;color:#647491;font-size:11px;animation:fade-up .7s .1s both}
@keyframes fade-up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}
@keyframes wave{0%,100%{height:6px;opacity:.5}50%{height:27px;opacity:1}}
@media(max-width:620px){.shell{width:min(100% - 22px,860px)}.topbar{height:72px}.brand{font-size:17px}.mark{width:34px;height:34px}main{padding:22px 0 48px}.card{padding:17px;border-radius:18px}.controls{grid-template-columns:1fr}.primary{width:100%}textarea{min-height:190px}.result-top{align-items:flex-start;flex-direction:column}.actions{width:100%}.small-btn{flex:1}.footer{flex-wrap:wrap}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important;transition-duration:.01ms!important}}
</style>
</head>
<body>
<div class="shell">
<header class="topbar">
  <div class="brand"><span class="mark">♫</span><span>Kelku TTS</span></div>
  <a class="api" href="/docs">API ↗</a>
</header>
<main>
<section class="workspace">
  <div class="card">
    <form id="ttsForm">
      <div class="controls">
        <div>
          <label class="field-label" for="voice">VOICE</label>
          <select id="voice">
            <option value="ryan">Ryan · English (US)</option>
            <option value="hfc_male">HFC Male · English (US)</option>
            <option value="libritts_r">LibriTTS R · English (US)</option>
            <option value="arjun">Arjun · Malayalam</option>
          </select>
        </div>
        <button class="primary" id="generate" type="submit">▶ &nbsp; Generate &amp; play</button>
      </div>
      <label class="field-label" for="text" style="margin-top:22px">TEXT</label>
      <textarea id="text" maxlength="2000" placeholder="Type or paste text…" required>Hello, welcome to Kelku TTS.</textarea>
      <div class="text-meta"><span id="count">0 / 2000</span><span>Sentence-by-sentence playback</span></div>
    </form>
    <div id="result" class="result hidden">
      <div class="result-top">
        <div class="state"><span class="dot"></span><span id="resultLabel">Ready to play</span></div>
        <div class="actions">
          <a id="download" class="small-btn" download="kelku-speech.wav">↓ Download current</a>
          <button id="clear" class="small-btn" type="button">Clear</button>
        </div>
      </div>
      <div class="wave" id="wave" aria-label="Audio activity animation"></div>
      <div id="sentences" class="sentences" aria-live="polite"></div>
      <audio id="audio" preload="auto"></audio>
    </div>
    <div id="status" class="status" role="status" aria-live="polite"></div>
  </div>
</section>
</main>
<footer class="footer"><span>Kelku TTS</span><span>Powered by Piper</span></footer>
</div>
<script>
const $=id=>document.getElementById(id);
const textEl=$('text'),voiceEl=$('voice'),button=$('generate'),statusEl=$('status');
const result=$('result'),audio=$('audio'),download=$('download'),sentencesEl=$('sentences'),wave=$('wave');
let runId=0,urls=[],chunks=[],activeIndex=-1,downloadUrl=null,isRunning=false;
for(let i=0;i<30;i++){const bar=document.createElement('i');wave.appendChild(bar)}
function updateCount(){$('count').textContent=`${textEl.value.length} / 2000`}
textEl.addEventListener('input',updateCount);updateCount();
function splitSentences(text){
  const lines=text.split(/
+/).map(s=>s.trim()).filter(Boolean);
  const result=[];
  for(const line of lines){
    const parts=line.match(/[^.!?。！？]+(?:[.!?。！？]+["'”’)\]]*|$)/g)||[line];
    for(const part of parts){const clean=part.trim();if(clean)result.push(clean)}
  }
  return result;
}
function cleanupUrls(){for(const url of urls)URL.revokeObjectURL(url);urls=[];if(downloadUrl){URL.revokeObjectURL(downloadUrl);downloadUrl=null}}
function stopPlayback(){audio.pause();audio.removeAttribute('src');audio.load();isRunning=false;result.classList.remove('is-busy','is-playing');}
function setActive(index){
  activeIndex=index;
  [...sentencesEl.children].forEach((node,i)=>{node.classList.toggle('active',i===index);if(i<index)node.classList.add('done');else node.classList.remove('done')});
  const current=chunks[index];
  if(current){$('resultLabel').textContent=`Sentence ${index+1} of ${chunks.length}`;if(current.url)download.href=current.url;sentencesEl.children[index]?.scrollIntoView({block:'nearest',behavior:'smooth'})}
}
function clearResult(){
  runId++;stopPlayback();cleanupUrls();chunks=[];activeIndex=-1;sentencesEl.replaceChildren();result.classList.add('hidden');statusEl.textContent='';statusEl.className='status';button.disabled=false;button.textContent='▶  Generate & play';
}
async function fetchChunk(text,voice,token){
  const params=new URLSearchParams({text,voice});
  const response=await fetch(`/generate?${params}`,{signal:controller.signal});
  if(!response.ok){let msg=`Generation failed (${response.status})`;try{msg=(await response.json()).detail||msg}catch{};throw new Error(msg)}
  const blob=await response.blob();if(!blob.size)throw new Error('Empty audio response');
  if(token!==runId)throw new DOMException('Cancelled','AbortError');
  const url=URL.createObjectURL(blob);urls.push(url);return url;
}
function ensureChunk(item,voice,token){
  if(item.url)return Promise.resolve(item.url);
  if(!item.promise)item.promise=fetchChunk(item.text,voice,token).then(url=>(item.url=url,url));
  return item.promise;
}
let controller=null;
async function playChunk(index,token){
  if(token!==runId)return;
  while(index<chunks.length&&token===runId){
    const item=chunks[index];
    if(!item.url){
      $('resultLabel').textContent=`Generating ${index+1} of ${chunks.length}…`;
      result.classList.add('is-busy');
      try{item.url=await ensureChunk(item,voiceEl.value,token)}
      catch(error){if(error.name==='AbortError')return;throw error}
    }
    if(token!==runId)return;
    setActive(index);result.classList.remove('is-busy');result.classList.add('is-playing');
    audio.src=item.url;download.href=item.url;download.download=`kelku-${voiceEl.value}-sentence-${index+1}.wav`;
    try{await audio.play()}catch(error){if(error.name==='NotAllowedError'){statusEl.textContent='Press play on the audio control to continue.';throw error}throw error}
    await new Promise((resolve,reject)=>{
      const ended=()=>{cleanup();resolve()},failed=()=>{cleanup();reject(new Error('Audio playback failed'))};
      const cleanup=()=>{audio.removeEventListener('ended',ended);audio.removeEventListener('error',failed);audio.removeEventListener('pause',paused)};
      const paused=()=>{if(!isRunning){cleanup();resolve()}};
      audio.addEventListener('ended',ended,{once:true});audio.addEventListener('error',failed,{once:true});audio.addEventListener('pause',paused,{once:true});
    });
    if(token!==runId)return;
    index++;
  }
  if(token===runId){result.classList.remove('is-busy','is-playing');$('resultLabel').textContent='Playback complete';statusEl.textContent='';button.disabled=false;button.textContent='▶  Play again'}
}
$('ttsForm').addEventListener('submit',async event=>{
  event.preventDefault();
  const token=++runId; if(controller)controller.abort();controller=new AbortController();stopPlayback();cleanupUrls();
  const text=textEl.value.trim(),voice=voiceEl.value;
  if(!text){statusEl.textContent='Enter text first.';statusEl.className='status error';return}
  chunks=splitSentences(text).map(text=>({text,url:null}));
  if(!chunks.length){statusEl.textContent='Enter text first.';statusEl.className='status error';return}
  sentencesEl.replaceChildren();
  chunks.forEach((item,index)=>{const node=document.createElement('div');node.className='sentence';node.textContent=item.text;node.dataset.index=index;sentencesEl.appendChild(node)});
  result.classList.remove('hidden');result.classList.add('is-busy');statusEl.className='status';statusEl.textContent='';
  button.disabled=true;button.textContent='Generating…';$('resultLabel').textContent=`Preparing ${chunks.length} sentence${chunks.length===1?'':'s'}…`;
  // Fetch the next chunk in the background while the current sentence plays.
  let producerError=null,producerDone=false;
  const producer=(async()=>{try{for(let i=0;i<chunks.length;i++){if(token!==runId)return;await ensureChunk(chunks[i],voice,token)}}catch(error){if(error.name!=='AbortError')producerError=error}finally{producerDone=true}})();
  try{
    // The first chunk is played as soon as it is ready; later chunks are prefetched concurrently.
    await playChunk(0,token);
    await producer;
    if(producerError&&token===runId)throw producerError;
  }catch(error){
    if(error.name!=='AbortError'&&token===runId){statusEl.textContent=error.message||'Could not generate speech.';statusEl.className='status error';$('resultLabel').textContent='Could not complete';result.classList.remove('is-busy','is-playing');button.disabled=false;button.textContent='↻ Try again'}
  }finally{
    if(token===runId){button.disabled=false;if($('resultLabel').textContent!=='Playback complete')button.textContent='▶  Play again'}
  }
});
audio.addEventListener('play',()=>result.classList.add('is-playing'));
audio.addEventListener('ended',()=>result.classList.remove('is-playing'));
$('clear').addEventListener('click',clearResult);
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

    started = time.perf_counter()

    try:
        # Piper's ONNX model stays loaded between requests. Audio is assembled
        # in memory, avoiding process startup and temporary-file disk I/O.
        wav_bytes = await asyncio.to_thread(synthesize_wav_bytes, text, voice)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Speech generation failed. Check the Render service logs.",
        ) from exc

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f'inline; filename="kelku-{voice}.wav"',
            "Cache-Control": "no-store",
            "X-TTS-Generation-Ms": str(elapsed_ms),
            "X-TTS-Voice": voice,
        },
    )


def synthesize_wav_bytes(text: str, voice_name: str) -> bytes:
    # Serialize inference to avoid CPU oversubscription on small free instances.
    # Model loading and synthesis share the lock so the cache cannot evict a
    # model while another request is using it.
    with _inference_lock:
        voice = get_voice(voice_name)
        output = io.BytesIO()
        with wave.open(output, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)
        return output.getvalue()

