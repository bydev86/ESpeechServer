# ESpeechServer — agent brain (master context)

**Use this file when:** you are a new agent, a different tool, or a human pasting context into a **private** repo where other agents’ histories are invisible.

**How to use:** copy this entire file into your session, or commit/sync `docs/AGENT_BRAIN.md` from the **ESpeechServer** repo. For **WordPress-only** repos, paste this file (or the sections you need) into that project so agents there still understand the backend.

**Companion doc (WordPress UI integration):** `docs/WORDPRESS_PLUGIN_AGENT_BRIEF.md` — API contract, tiered strategy, caching, acceptance checklist.

---

## 1. Project identity

| Item | Value |
|------|--------|
| **Name** | ESpeechServer |
| **Purpose** | HTTP API: audio/video → normalized WAV → **Google Speech Recognition** text; optional **YouTube URL** → captions **or** download + STT |
| **Stack** | Flask, pydub, ffmpeg (CLI), SpeechRecognition, yt-dlp, youtube-transcript-api, gunicorn |
| **Production example** | `https://yespeechserver.onrender.com` (Render; name may vary per deploy) |
| **Upstream repo (reference)** | `bydev86/ESpeechServer` — treat as canonical implementation |

---

## 2. What was built (feature chronology — high level)

Use this to avoid “re-discovering” decisions:

1. **Replaced** naive `recording.wav` + raw-only uploads with **temp files**, **multipart**, **magic-byte + MIME** detection, **mono 16 kHz WAV** via pydub/ffmpeg before SR.
2. **CORS + OPTIONS** on `/uploadAudio` (manual headers; no Flask-Cors dependency in final lean requirements).
3. **Resilient decode:** multi-strategy pydub + **ffmpeg CLI fallback** (`-vn`, mono 16 kHz); correct **`.mp4` vs `.m4a`** suffixes; ISO BMFF (`ftyp`) sniff; `video/mp4`, `video/quicktime`.
4. **Render constraints:** gunicorn **`--workers 1`**, **`--timeout 900`** for long `/transcribeUrl` jobs; **`Procfile`** tracks start command.
5. **`POST /transcribeUrl`:** JSON `{ "url" }` → **youtube-transcript-api first** (captions, no API key) → on failure **yt-dlp** best audio → decode → chunked SR for long WAVs.
6. **yt-dlp hardening:** `--remote-components ejs:github` default for YouTube; auto **`--js-runtimes node`** if `node` on PATH; cookie file **copied to `/tmp`** (Render secrets are read-only — yt-dlp must write cookiejar).
7. **Dockerfile** path for Render when **no buildpack UI**: installs **ffmpeg**, **Node 22**, Python deps; sets **`YTDLP_JS_RUNTIMES=node`**.
8. **`GET /`** health JSON (avoids bare `/` 404 on probes).
9. **Docs:** WordPress agent brief, this brain file.

---

## 3. Architecture (mental model)

```
Client
  ├─ POST /uploadAudio (bytes | multipart)
  │     → temp file → pydub/ffmpeg → mono 16 kHz WAV → Google SR → JSON { transcription }
  │
  └─ POST /transcribeUrl { url }
        → if YouTube: youtube_transcript_api.fetch (captions) → success? return source=youtube_captions
        → else: yt-dlp → temp media → same decode/STT pipeline → source=youtube_audio_stt
```

**Important:** YouTube **caption** fetch and **yt-dlp** both run **from the server IP**. Datacenter IPs can see **`IpBlocked`** / bot challenges — **browser → `/uploadAudio`** remains the most reliable path for stubborn videos.

---

## 4. API specification (must implement clients against this)

### 4.1 `GET /`

- **200:** `{"ok": true, "service": "ESpeechServer"}` (shape may vary slightly; `ok` is the signal).

### 4.2 `OPTIONS /uploadAudio` / `OPTIONS /transcribeUrl`

- **204** empty — CORS preflight.

### 4.3 `POST /uploadAudio`

- **Raw:** `Content-Type` must match bytes (`audio/wav`, `audio/webm`, `video/mp4`, …). Use `@file` in curl for file bytes.
- **Multipart:** fields `audio`, `file`, `recording`, `upload` (first non-empty wins).
- **200:** `{ "transcription": "<string>" }`
- **Errors:** JSON with `error` / `detail` where applicable.
- **413** may come from **Render edge** (payload too large) — not fixable only in Flask.

### 4.4 `POST /transcribeUrl`

- **Headers:** `Content-Type: application/json`
- **Body:** `{ "url": "<https://...>" }` or `{ "video_url": "..." }`
- **200 success — inspect `source`:**
  - **`youtube_captions`** — text from existing YouTube subtitles/captions (fast path).
  - **`youtube_audio_stt`** — captions unavailable or failed; audio downloaded + STT. May include `youtube_video_id`, `caption_fallback_reason` (short error class).
- **Timeouts:** clients should allow **≥ 120s**, preferably **900s** (cold start + yt-dlp + SR).

### 4.5 Host allowlist (URL mode)

- Default: **YouTube** hosts only (`youtube.com`, `youtu.be`, subdomains).
- **`TRANSCRIBE_URL_EXTRA_HOSTS`**, **`TRANSCRIBE_URL_ANY_HOST`** (dangerous SSRF) — see README.

---

## 5. Environment variables (operations)

| Variable | Role |
|----------|------|
| `PORT` | Bind port (Render sets this). |
| `MAX_URL_AUDIO_SECONDS` | yt-dlp segment cap (default 300; `0` = no section limit). |
| `MAX_URL_DOWNLOAD_MB` | yt-dlp max filesize. |
| `SR_CHUNK_MS` / `SR_MAX_SINGLE_MS` / `SR_CHUNK_SLEEP_SEC` | Long-audio SR chunking. |
| `SKIP_YOUTUBE_CAPTIONS` | Skip caption API; go straight to yt-dlp. |
| `YOUTUBE_TRANSCRIPT_LANGS` | Caption language preference list. |
| `YTDLP_COOKIES_FILE` | Optional; auto `/etc/secrets/cookies.txt` on Render if present. |
| `YTDLP_JS_RUNTIMES` | e.g. `node` — auto if `node` on PATH. |
| `YTDLP_REMOTE_COMPONENTS` | Default `ejs:github` for YouTube when unset. |
| `YTDLP_EXTRACTOR_ARGS` | Advanced yt-dlp override. |

---

## 6. Deployment (Render)

- **Native Python:** no Heroku buildpack UI in typical flow; ffmpeg often available per Render native tooling — **Node may be missing** → YouTube download/challenge path weaker.
- **Docker (recommended for `/transcribeUrl`):** root **`Dockerfile`** — Python + ffmpeg + NodeSource Node 22 + pip deps + **`YTDLP_JS_RUNTIMES=node`** + gunicorn timeout **900**.
- **Start command:** must match **`--timeout 900`** for URL jobs (avoid gunicorn **WORKER TIMEOUT**).
- **Secrets:** `cookies.txt` → `/etc/secrets/cookies.txt`; app **copies** to `/tmp` for yt-dlp writes.
- **Free tier:** cold starts, ~512MB RAM, single worker; **413** limits on large uploads.

---

## 7. Known limitations & mitigations

| Issue | Mitigation |
|-------|------------|
| YouTube blocks server IP (captions or yt-dlp) | Tier 1: **browser blob → `/uploadAudio`** |
| Cookies expire (yt-dlp only) | Refresh secret `cookies.txt`; irrelevant when `youtube_captions` succeeds |
| No JS runtime on server | Use **Dockerfile** with Node; `ejs:github` for challenge scripts |
| Worker timeout | gunicorn `--timeout 900`; client `--max-time 900` |
| Legal / ToS | User/content policy; backend README has disclaimer |

---

## 8. WordPress / Liberation Lab

- **Product page (context):** `https://theliberationlab.com/study-guide-quick-teaser/`
- **Integration spec:** `docs/WORDPRESS_PLUGIN_AGENT_BRIEF.md`
- **Strategy:** URL convenience (`/transcribeUrl`) + **mandatory fallback** to `/uploadAudio` from browser; **localStorage** cache by `youtube_video_id`.

---

## 9. Verification checklist (any agent can run)

- [ ] `GET /` → 200 JSON  
- [ ] `POST /uploadAudio` with small real WAV + `Content-Type: audio/wav` → `transcription`  
- [ ] `POST /uploadAudio` multipart MP4 + `type=video/mp4` → `transcription`  
- [ ] `POST /transcribeUrl` with video that has captions → `source: youtube_captions`  
- [ ] Same with long timeout on cold instance  
- [ ] After deploy: Docker image includes `node` (`node -v` in container shell if available)

---

## 10. Feedback & handoff log (append only)

*Instructions for future agents/humans: append a new dated block below when behavior, URLs, or product decisions change. Keep entries short.*

```
### YYYY-MM-DD — <author / agent id>
- Change:
- Verified:
- Open issues:
```

---

## 11. File map (repo root)

| Path | Role |
|------|------|
| `app.py` | All routes, decode, SR, yt-dlp, captions |
| `requirements.txt` | Python deps |
| `Procfile` | gunicorn line for non-Docker |
| `Dockerfile` | Render Docker path with Node + ffmpeg |
| `.dockerignore` | Docker build scope |
| `package.json` | Engine hint for Node tooling (minimal) |
| `docs/WORDPRESS_PLUGIN_AGENT_BRIEF.md` | WordPress integration contract |
| `docs/AGENT_BRAIN.md` | **This file** |

---

**End of agent brain.** Update §10 when reality drifts; keep §2–§7 aligned with `README.md` when changing the service.
