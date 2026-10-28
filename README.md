# Piper TTS API on Render

FastAPI + Piper TTS with four voices:
- `hfc_male` -> `en_US-hfc_male-medium`
- `libritts_r` -> `en_US-libritts_r-medium`
- `ryan` -> `en_US-ryan-medium` (default)
- `arjun` -> `ml_IN-arjun-medium`

The Docker build downloads the Piper Linux x86-64 executable and only the four selected ONNX models plus their JSON configuration files.

## Deploy to Render

1. Download and unzip this project.
2. Create a new GitHub repository, for example `piper-tts-api`.
3. Upload the files from this folder to the repository root. Do not upload ONNX models; the Docker build downloads them.
4. Sign in to Render and choose **New + → Web Service**.
5. Connect your GitHub repository.
6. Select the **Docker** runtime if asked. The repository's `Dockerfile` is used automatically.
7. Choose the Free plan if it is available for your account and service.
8. Set health check path to `/health` if Render does not pick it up from `render.yaml`.
9. Click **Create Web Service** and monitor the build and deploy logs. The first build downloads several hundred MB and can take a while.
10. When deployment is live, open `https://YOUR-SERVICE-NAME.onrender.com/health`.

Render supplies the `PORT` environment variable. The Docker command listens on that port, defaulting to `10000` for local use.

## Test endpoints

Replace `YOUR-SERVICE-NAME` with the actual Render service hostname.

- `https://YOUR-SERVICE-NAME.onrender.com/`
- `https://YOUR-SERVICE-NAME.onrender.com/health`
- `https://YOUR-SERVICE-NAME.onrender.com/generate?text=Hello%20world&voice=ryan`
- `https://YOUR-SERVICE-NAME.onrender.com/generate?text=%E0%B4%A8%E0%B4%AE%E0%B4%B8%E0%B5%8D%E0%B4%95%E0%B4%BE%E0%B4%B0%E0%B4%82&voice=arjun`

The `/generate` endpoint returns `audio/wav`.

## JavaScript example

```javascript
async function speakText(text, voice = "ryan") {
  const baseUrl = "https://YOUR-SERVICE-NAME.onrender.com/generate";
  const params = new URLSearchParams({ text, voice });
  const response = await fetch(`${baseUrl}?${params}`);

  if (!response.ok) {
    throw new Error(`TTS request failed (${response.status}): ${await response.text()}`);
  }

  const audioBlob = await response.blob();
  const objectUrl = URL.createObjectURL(audioBlob);
  const audio = new Audio(objectUrl);

  audio.addEventListener("ended", () => URL.revokeObjectURL(objectUrl), { once: true });
  await audio.play();
}

speakText("Hello from Piper", "ryan");
// speakText("നമസ്കാരം", "arjun");
```

## Local Docker test

Build:
```bash
docker build -t piper-tts-api .
```

Run:
```bash
docker run --rm -p 10000:10000 -e PORT=10000 piper-tts-api
```

Then open `http://localhost:10000/health`.

## Important limitations

- This is not unlimited hosting. Free services have CPU, memory, usage, and availability constraints, and may spin down when idle.
- A cold request after spin-down may be slow.
- This version launches a Piper process for each request, so it is a straightforward starter implementation, not the lowest possible latency architecture.
- The endpoint is public and CORS is open by request. CORS is not access control. Add authentication and rate limiting before exposing it to untrusted users.
- The Piper executable URL targets Linux x86-64. If your deployment uses a different CPU architecture, use the matching Piper release asset.
- Model URLs currently use the repository's `main` branch. For strict reproducibility, pin them to a verified commit.
- Check the Piper and voice-model licenses for your intended usage.
