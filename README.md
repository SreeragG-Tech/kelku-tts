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
