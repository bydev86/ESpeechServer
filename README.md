# 🗣️ ESpeechServer

**ESpeechServer** is a lightweight Flask-based backend server designed for speech-to-text conversion using the [ESpeech Library](https://github.com/yourusername/ESpeech). With support for audio uploads, it seamlessly transcribes speech using Google’s Speech Recognition engine. Deployed easily on platforms like Render, this project is perfect for integrating voice interfaces into web and IoT applications.

---

## ✨ Features

- 🔊 **Live / mic:** `POST /uploadAudio` — raw or multipart (WebM, WAV, Ogg/Opus, MP3, M4A/MP4) with sniffing + CORS  
- 🔗 **URL (YouTube default):** `POST /transcribeUrl` — JSON `{ "url": "..." }`; **yt-dlp** + same STT pipeline  
- 🧠 Uses Google Speech Recognition for high-accuracy transcription
- ⚙️ Built with Flask and SpeechRecognition library
- ☁️ Easily deployable on [Render](https://render.com/) or similar cloud platforms
- 🔁 Simple API endpoint for quick integration
- 🎧 Ready to integrate with [ESpeech](https://github.com/yourusername/ESpeech) client libraries or custom ESP32 IoT devices

---

## 📦 Tech Stack

- **Flask** – Lightweight WSGI web application framework  
- **SpeechRecognition** – Python library for performing speech recognition  
- **Pydub** – Audio handling made easy  
- **yt-dlp** – Fetch audio from YouTube (and optional other hosts) by URL  
- **Gunicorn** – Production WSGI server for Python apps  

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/ESpeechServer.git
cd ESpeechServer
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Server Locally

```bash
python app.py
```

The server listens on `0.0.0.0` using the **`PORT`** environment variable, or **8888** if unset (local dev). **ffmpeg** must be installed (`ffmpeg -version`) for WebM/Opus and for yt-dlp merging/extraction where needed.

---

## 🎯 Usage

### Endpoints

| Method | Path | Purpose |
|--------|------|--------|
| `POST` | `/uploadAudio` | Upload audio/video blob (body or multipart); returns `{ "transcription": "..." }`. |
| `OPTIONS` | `/uploadAudio` | CORS preflight. |
| `POST` | `/transcribeUrl` | JSON body with a **`url`** (YouTube by default); downloads audio, transcribes; returns `{ "transcription": "...", "source": "url" }`. |
| `OPTIONS` | `/transcribeUrl` | CORS preflight. |

Audio is decoded with **pydub**/**ffmpeg**, normalized to **mono 16 kHz WAV**, then sent to Google Speech Recognition. Long clips are **chunked** automatically for the URL path (and for long uploads).

### Request format — live audio (`/uploadAudio`)

- **Raw body:** set `Content-Type` to match the blob (`audio/webm`, `audio/wav`, …). Magic-byte sniffing helps when the header is wrong or generic.
- **`multipart/form-data`:** field **`audio`** (also **`file`**, **`recording`**, **`upload`**).

### Request format — URL (`/transcribeUrl`)

`Content-Type: application/json`

```json
{ "url": "https://www.youtube.com/watch?v=VIDEO_ID" }
```

Optional alternate key: `"video_url"`.

### Example using `curl`

Live upload:

```bash
curl -s -X POST http://127.0.0.1:8888/uploadAudio -H "Content-Type: audio/wav" --data-binary "@path/to/sample.wav"
```

YouTube (or allowed host):

```bash
curl -s -X POST http://127.0.0.1:8888/transcribeUrl -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://www.youtube.com/watch?v=dQw4w9WgXcQ\"}"
```

(PowerShell: escape quotes or use single quotes around the `-d` string in `curl.exe`.)

### Legal / policy

Automated download/transcription of third-party videos may be restricted by **YouTube’s Terms of Service** and copyright. Use only for content you have rights to process, or route users through official APIs where appropriate.

### Sample Response

```json
{
  "transcription": "Hello, how are you?"
}
```

---

## Deployment

- **Endpoints:** `POST /uploadAudio`, `OPTIONS /uploadAudio`, **`POST /transcribeUrl`**, **`OPTIONS /transcribeUrl`**.
- **Live audio:** raw bytes or `multipart/form-data` with field `audio` (also `file`, `recording`, `upload`).
- **URL audio:** JSON `{ "url": "https://..." }` — **YouTube-only by default** (host allowlist); optional env for other hosts (see below).
- **ffmpeg:** required on the server (pydub + yt-dlp).
- **Render (free tier):** cold starts; live clients should use **≥ 60 s** timeout. **`/transcribeUrl`** needs **much longer** wall time (yt-dlp + ffmpeg + chunked SR): use **`gunicorn --timeout 900`** (see `Procfile`). If the dashboard **Start Command** still uses **`300`**, you get **WORKER TIMEOUT** mid-download.
- **YouTube from cloud hosts:** Datacenter IPs often hit **bot checks**. Use a **fresh** Netscape **`cookies.txt`** secret (`cookies.txt` → `/etc/secrets/cookies.txt`, copied to `/tmp` at runtime). For **“No supported JavaScript runtime”**, add **Node** on the server and set **`YTDLP_JS_RUNTIMES=node`** (see below). If URL mode still fails, use **`POST /uploadAudio`** from the client.

### Environment variables (optional)

| Variable | Default | Meaning |
|----------|---------|---------|
| `MAX_URL_AUDIO_SECONDS` | `300` | Only the first *N* seconds of audio are downloaded (caps RAM/time on small instances). Set `0` to disable section limiting (risky on free tier). |
| `MAX_URL_DOWNLOAD_MB` | `120` | yt-dlp `--max-filesize` cap. |
| `SR_CHUNK_MS` | `45000` | Google SR chunk size for long audio (ms). |
| `SR_MAX_SINGLE_MS` | `55000` | Below this length, one SR request is used. |
| `SR_CHUNK_SLEEP_SEC` | `0.25` | Pause between chunks to reduce rate-limit issues. |
| `TRANSCRIBE_URL_EXTRA_HOSTS` | _(empty)_ | Comma-separated extra allowed hostnames (e.g. `vimeo.com`). |
| `YTDLP_COOKIES_FILE` | _(auto)_ | Path to Netscape **`cookies.txt`**. If unset but **`/etc/secrets/cookies.txt`** exists (Render secret filename), it is used automatically. The server **copies** it to `/tmp` before yt-dlp runs because secret files are **read-only** on Render (yt-dlp must be able to update its cookie jar on disk during the run). |
| `YTDLP_JS_RUNTIMES` | _(empty)_ | Passed to yt-dlp **`--js-runtimes`** (e.g. **`node`** after installing Node on the host). Needed for full YouTube support with recent yt-dlp; without it you may see **“No supported JavaScript runtime”**. |
| `YTDLP_REMOTE_COMPONENTS` | _(empty)_ | Optional yt-dlp **`--remote-components`** value (see [EJS wiki](https://github.com/yt-dlp/yt-dlp/wiki/EJS)). |
| `YTDLP_EXTRACTOR_ARGS` | _(empty)_ | Override **`--extractor-args`** for yt-dlp (advanced). |

### Render (free Web Service)

Create a **Python** Web Service with the repo root as the application root. Use **temp files only** (Python’s default temp dir is `/tmp` on Render); do **not** rely on persistent disk.

1. **Buildpacks:** Dashboard → **Settings** → **Buildpacks**  
   - **`https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest`** (ffmpeg for pydub / merges).  
   - **`https://github.com/heroku/heroku-buildpack-nodejs`** (recommended for **`/transcribeUrl`**) — provides **Node ≥20** for yt-dlp’s JS/EJS path.  
   - Render’s **Python** buildpack (or native Python).  
   **Order:** try **ffmpeg → node → python**; if the build fails, swap ffmpeg/node order per Render’s docs.  
2. **Environment:** set **`NODE_VERSION=22`** (or **20**) when using the Node buildpack. For YouTube URL mode, also set **`YTDLP_JS_RUNTIMES=node`**.  
3. **Build command:** `pip install -r requirements.txt`  
4. **Start command:** Must stay in sync with `Procfile` (or paste the same flags in the dashboard). **`--timeout 900`** gives `/transcribeUrl` room for yt-dlp + decode + chunked SR; if the dashboard still has **`300`**, workers die with **WORKER TIMEOUT**. Example:  
   `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 900`

The `Procfile` matches this start command for convenience.

### Nori / browser client contract

- **Live — raw POST:** `Content-Type: audio/webm` (or the actual blob type) with body = blob bytes.
- **Live — multipart:** `FormData` append `audio`, blob, optional filename such as `.webm`.
- **Video URL:** `POST /transcribeUrl` with `Content-Type: application/json` and `{ "url": "..." }`.
- **Timeouts:** ≥ **60 s** for live requests on free Render; **URL jobs** often need **≥ 120–300 s** (download + chunked SR).

---

## 🛠️ Customization

You can modify the `speech_to_text()` function in `app.py` to use other engines like:

- **Sphinx** (Offline)
- **Azure Speech**
- **IBM Speech to Text**

---

## 📹 Tutorial

Need a visual walkthrough?

> 🎥 Coming soon: [Watch the Tutorial Video](https://github.com/yourusername/ESpeechServer/wiki)

---

## 🤝 Contributing

Have suggestions or improvements? Feel free to [open an issue](https://github.com/yourusername/ESpeechServer/issues) or submit a PR!

---

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
