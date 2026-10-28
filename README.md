# Kelku TTS

A Dockerized FastAPI text-to-speech API using Piper TTS. It supports four voices:

- `hfc_male` → `en_US-hfc_male-medium`
- `libritts_r` → `en_US-libritts_r-medium`
- `ryan` → `en_US-ryan-medium` (default)
- `arjun` → `ml_IN-arjun-medium` (Malayalam)

The Docker image downloads the Piper executable and exactly these four voice models during build.

## Web UI

The root URL (`/`) serves a responsive web interface where visitors can enter text, select one of the four voices, generate speech, play it, and download the WAV. API documentation remains available at `/docs`.

## API

- `GET /` service info
- `GET /health` health check
- `GET /docs` interactive API docs
- `GET /generate?text=Hello%20world&voice=ryan` returns WAV audio

Text is limited to 2,000 characters per request. This is a CPU-based service, not a guarantee of unlimited throughput.

## Deploy on Render

1. Create a GitHub repository named `kelku-tts`.
2. Upload the files from this folder to the repository root.
3. Open https://render.com and sign in.
4. Select **New + → Web Service** and connect the GitHub repository.
5. Set the service name to `kelku-tts`.
6. Set **Language/Runtime** to **Docker**. Keep the Dockerfile path as `./Dockerfile`.
7. Choose the Free plan if it is available for your account and region.
8. In Advanced settings, set the health check path to `/health`.
9. Create the Web Service and wait for the Docker build and deploy to finish.
10. Open the `onrender.com` URL Render assigns to your service.

The Dockerfile reads Render's `PORT` environment variable and listens on `0.0.0.0`.

## Test

Open these URLs, replacing `YOUR-SERVICE.onrender.com` with your Render hostname:

```text
https://YOUR-SERVICE.onrender.com/health
https://YOUR-SERVICE.onrender.com/generate?text=Hello%20world&voice=ryan
https://YOUR-SERVICE.onrender.com/generate?text=Hello%20world&voice=hfc_male
https://YOUR-SERVICE.onrender.com/generate?text=Hello%20world&voice=libritts_r
https://YOUR-SERVICE.onrender.com/generate?text=%E0%B4%A8%E0%B4%AE%E0%B4%B8%E0%B5%8D%E0%B4%95%E0%B4%BE%E0%B4%B0%E0%B4%82&voice=arjun
```

## Frontend JavaScript

```javascript
async function playKelkuTTS(text, voice = "ryan") {
  const baseUrl = "https://YOUR-SERVICE.onrender.com";
  const query = new URLSearchParams({ text, voice });
  const response = await fetch(`${baseUrl}/generate?${query}`);

  if (!response.ok) {
    throw new Error(`TTS request failed (${response.status}): ${await response.text()}`);
  }

  const audioBlob = await response.blob();
  const audioUrl = URL.createObjectURL(audioBlob);
  const audio = new Audio(audioUrl);

  audio.addEventListener("ended", () => URL.revokeObjectURL(audioUrl), { once: true });
  await audio.play();
}

playKelkuTTS("Hello from Kelku TTS", "ryan");
// Malayalam example: playKelkuTTS("നമസ്കാരം", "arjun");
```

## Local Docker test

```bash
docker build -t kelku-tts .
docker run --rm -p 10000:10000 -e PORT=10000 kelku-tts
```

Then open `http://localhost:10000/docs`.

## Important limitations

- Render Free web services spin down after 15 minutes without inbound traffic and can take around a minute to wake up.
- Free instances have usage limits and are not suitable for guaranteed unlimited or always-on production service.
- The service starts a Piper subprocess per request. It is a simple baseline, not a persistent-model ultra-low-latency implementation.
- Voice model licenses vary. Review each voice's model card before commercial use.
- The Docker build uses a versioned Piper release URL and the `main` branch of the voice repository. For reproducible builds, verify the release asset and pin the model repository to a specific commit.


## Speed-optimized version

This version uses Piper's Python API instead of starting a Piper subprocess for every request. It keeps recently used ONNX model sessions in an in-memory LRU cache, preloads Ryan at startup, synthesizes WAV data in memory, and returns `X-TTS-Generation-Ms` to help measure request generation time.

The cache defaults to two loaded voices to balance repeat-request speed against Render Free memory limits. If the service restarts or a voice is evicted from the cache, its next request must load that model again. To tune the cache, set `PIPER_MODEL_CACHE_SIZE` in the Dockerfile or Render environment. Do not set it to 4 on Render Free without checking memory usage; the instance may run out of RAM.

## Measuring performance

Check the `X-TTS-Generation-Ms` response header in browser developer tools or with curl. The first request to a voice can be slower than warm requests. Render Free also spins down after 15 minutes without inbound traffic, and wake-up delay is separate from speech synthesis.

This design removes repeated process creation and temporary WAV file I/O. It cannot guarantee instant speech: Piper still performs CPU inference, and Render Free has limited CPU/RAM. For consistently low latency, use a host with sufficient dedicated CPU/RAM and an always-on instance.

## UI behavior

The web UI is intentionally minimal. Text is split into sentences (newlines are also treated as boundaries), and each sentence is requested from the existing `/generate` endpoint. Audio chunks are prefetched in the background and played in order; the active sentence is highlighted as it plays. Download saves the currently selected sentence's WAV file.
