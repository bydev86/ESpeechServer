# 🗣️ ESpeechServer

**ESpeechServer** is a lightweight Flask-based backend server designed for speech-to-text conversion using the [ESpeech Library](https://github.com/yourusername/ESpeech). With support for audio uploads, it seamlessly transcribes speech using Google’s Speech Recognition engine. Deployed easily on platforms like Render, this project is perfect for integrating voice interfaces into web and IoT applications.

---

## ✨ Features

- 🔊 Accepts raw audio (`audio/wav`, `audio/webm`, etc.) or multipart uploads (`audio`, `file`, `recording`, `upload` fields)
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

The server listens on `0.0.0.0` using the **`PORT`** environment variable, or **8888** if unset (local dev).

---

## 🎯 Usage

### Endpoint

```
POST /uploadAudio
```

### Description

Uploads audio and returns JSON with transcribed text. Non-audio errors use `{"error":"..."}`.

Input is normalized with **pydub** to **mono, 16 kHz WAV** before Google Speech Recognition.

### Request format

- **Raw body**: set `Content-Type` appropriately (`audio/wav`, `audio/webm`, …). Magic-byte sniffing (RIFF/WAVE, WebM EBML, Ogg) is used when the body is recognizable.
- **Multipart**: first non-empty file among fields `audio`, `file`, `recording`, `upload`.

### Examples using `curl`

```bash
curl -X POST http://localhost:8888/uploadAudio -H "Content-Type: audio/wav" --data-binary "@yourfile.wav"
curl -X POST http://localhost:8888/uploadAudio -H "Content-Type: audio/webm" --data-binary "@clip.webm"
```

### Sample Response

```json
{
  "transcription": "Hello, how are you?"
}
```

---

## 🌐 Deployment on Render (free Web Service)

Render’s free tier has **cold starts** (first request after sleep often **10–30+ seconds**), **512MB RAM**, and **no persistent disk** (only **`/tmp`** is writable). This app keeps temp audio under the default temp directory and uses **one Gunicorn worker** so transcoding stays within those limits.

### FFmpeg (required for WebM / Opus)

**pydub** shells out to **ffmpeg**. On Render’s Python runtime, add a secondary **buildpack** (order may matter; if the build fails, try ffmpeg **first**):

- [jonathanong/heroku-buildpack-ffmpeg-latest](https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest)

Use **`pip install -r requirements.txt`** as the build command (do not rely on `apt-get` unless you switch to a Docker deploy).

### Commands

- **Build Command**: `pip install -r requirements.txt`
- **Start Command** (matches `Procfile`):  
  `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120`  

Use **`--workers 1`** on the free instance. Avoid **`--timeout 0`**; **120** is a reasonable upper bound for short speech blobs.

### Smoke tests after deploy

```bash
curl -X POST "$SERVICE_URL/uploadAudio" -H "Content-Type: audio/wav" --data-binary "@small.wav"
curl -X POST "$SERVICE_URL/uploadAudio" -H "Content-Type: audio/webm" --data-binary "@clip.webm"
```

From the browser on another origin: **OPTIONS** then **POST** should succeed without CORS blocking (`Access-Control-Allow-Origin` is set for `/uploadAudio`).

### Clients (e.g. Nori)

POST the raw blob with the correct `Content-Type`, or use multipart with one of the fields above. Use a **fetch timeout ≥ 60s** to tolerate cold starts on the free tier.

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
