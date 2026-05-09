# 🗣️ ESpeechServer

**ESpeechServer** is a lightweight Flask-based backend server designed for speech-to-text conversion using the [ESpeech Library](https://github.com/yourusername/ESpeech). With support for audio uploads, it seamlessly transcribes speech using Google’s Speech Recognition engine. Deployed easily on platforms like Render, this project is perfect for integrating voice interfaces into web and IoT applications.

---

## ✨ Features

- 🔊 Accepts raw or multipart uploads (WebM, WAV, Ogg/Opus, MP3, M4A/MP4) with magic-byte sniffing and CORS
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

The server listens on `0.0.0.0` using the **`PORT`** environment variable, or **8888** if unset (local dev). **ffmpeg** must be installed (`ffmpeg -version`) for WebM/Opus via pydub.

---

## 🎯 Usage

### Endpoints

- `POST /uploadAudio` — transcribe uploaded audio (JSON `transcription` or JSON error body).
- `OPTIONS /uploadAudio` — CORS preflight.

Audio is decoded with **pydub**/**ffmpeg**, normalized to **mono 16 kHz WAV**, then sent to Google Speech Recognition.

### Request format

- **Raw body:** set `Content-Type` to match the blob (`audio/webm`, `audio/wav`, …). Magic-byte sniffing helps when the header is wrong or generic.
- **`multipart/form-data`:** field **`audio`** (also **`file`**, **`recording`**, **`upload`**).

### Example using `curl`

```bash
curl -s -X POST http://127.0.0.1:8888/uploadAudio -H "Content-Type: audio/wav" --data-binary "@path/to/sample.wav"
```

### Sample Response

```json
{
  "transcription": "Hello, how are you?"
}
```

---

## Deployment

- **Endpoints:** `POST /uploadAudio` and `OPTIONS /uploadAudio`.
- **Body:** raw audio bytes with the correct `Content-Type`, or `multipart/form-data` with field `audio` (also accepts `file`, `recording`, `upload`).
- **ffmpeg:** required on the server for WebM/Opus (pydub invokes ffmpeg).
- **Render (free tier):** instances sleep when idle—expect cold starts. Clients should use an HTTP timeout of **≥ 60 seconds**.

### Render (free Web Service)

Create a **Python** Web Service with the repo root as the application root. Use **temp files only** (Python’s default temp dir is `/tmp` on Render); do **not** rely on persistent disk.

1. **Buildpacks:** Dashboard → **Settings** → **Buildpacks** → add  
   `https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest`  
   If the build fails, put the ffmpeg buildpack **above** the Python buildpack or swap order per Render’s buildpack docs.
2. **Build command:** `pip install -r requirements.txt`
3. **Start command (free-tier safe):**  
   `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120`  
   **`--workers 1`** avoids parallel ffmpeg transcoding exhausting ~512MB RAM. **`--timeout 120`** allows cold start + decode + Google API (adjust only if your plan enforces a lower limit).

The `Procfile` matches this start command for convenience.

### Nori / browser client contract

- **Raw POST:** `Content-Type: audio/webm` (or the actual blob type) with body = blob bytes.
- **Multipart:** `FormData` append `audio`, blob, optional filename such as `.webm`.
- **Timeouts:** ≥ **60 seconds** because free Render sleeps after idle.

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
