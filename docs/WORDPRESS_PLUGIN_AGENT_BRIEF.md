# WordPress plugin integration — agent brief (ESpeechServer)

**Purpose:** One document so an implementing agent can integrate **https://yespeechserver.onrender.com** (or any deployed instance of [ESpeechServer](https://github.com/bydev86/ESpeechServer)) into the Liberation Lab **Study Guide Quick Teaser** flow **without** repeated clarification.

**Target page (context):** `https://theliberationlab.com/study-guide-quick-teaser/`

---

## 1. What this backend is good at

| Capability | Endpoint | Best when |
|------------|----------|-----------|
| **Mic / file / screen recording** | `POST /uploadAudio` | User’s browser has **audio or video bytes** (WebM, WAV, MP4, …). Most **reliable** end-to-end because **YouTube never sees the server’s datacenter IP** for the fetch. |
| **Paste a YouTube URL** | `POST /transcribeUrl` | Convenience path. Server tries **captions first**, then **download + STT**. Works great when captions exist **and** YouTube does not block the server IP. |

**Golden rule:** Prefer **browser-origin media** (`/uploadAudio`) for **maximum reliability** on controversial or restricted videos. Use **`/transcribeUrl`** when it works (often **instant** if `source: youtube_captions`).

---

## 2. API reference (exact contract)

**Base URL (configure per environment):**  
`https://yespeechserver.onrender.com`  
(No trailing slash required; avoid double slashes in paths.)

### 2.1 Health

```http
GET /
```

**200** JSON example: `{"ok":true,"service":"ESpeechServer"}`

Use for “is the service awake?” — remember **Render free tier cold starts** (~30–90s first hit).

---

### 2.2 Upload audio or video blob

```http
POST /uploadAudio
```

**CORS:** `OPTIONS` supported; responses include permissive CORS headers for browser use.

**Two supported modes:**

**A) Raw body**

- Set **`Content-Type`** to the **actual** format (`audio/wav`, `audio/webm`, `video/mp4`, …).  
- Body = **binary file bytes**.  
- **curl:** `--data-binary "@file.wav"` — the **`@`** is mandatory (otherwise curl sends the filename string, not the file).

**B) Multipart form**

- `multipart/form-data`  
- Prefer field name **`audio`** (aliases: **`file`**, **`recording`**, **`upload`**).  
- Example: `audio=@Screen-Recording.mp4;type=video/mp4`

**Success 200:**

```json
{ "transcription": "plain text" }
```

**Common failures:**

| Symptom | Likely cause |
|---------|----------------|
| Wrong text / SR garbage | Wrong **`Content-Type`** for raw POST (e.g. MP4 labeled `audio/wav`). |
| `413 Request Entity Too Large` | **Render proxy / platform** limit — file too big. Shorter clip, tighter encode, or multipart from browser with compression. |
| `500` + decode errors | Corrupt file, incomplete recording, or unsupported container. Retry multipart + correct MIME. |

---

### 2.3 YouTube URL → text (captions first, then STT fallback)

```http
POST /transcribeUrl
Content-Type: application/json
```

**Body:**

```json
{ "url": "https://www.youtube.com/watch?v=VIDEO_ID" }
```

Alternate key: `"video_url"` (same value).

**Success 200 — two shapes (check `source`):**

**1) Captions path (preferred — fast, no cookies, no ffmpeg download for audio):**

```json
{
  "transcription": "full plain text from subtitles",
  "source": "youtube_captions",
  "youtube_video_id": "VIDEO_ID",
  "caption_language_code": "en",
  "caption_language": "English",
  "caption_generated": true
}
```

**2) Audio + speech-to-text fallback:**

```json
{
  "transcription": "…",
  "source": "youtube_audio_stt",
  "youtube_video_id": "VIDEO_ID",
  "caption_fallback_reason": "IpBlocked"
}
```

`caption_fallback_reason` is **optional**; when present it is a **short** exception type name (e.g. `IpBlocked`, `NoTranscriptFound`), not a full stack trace.

**Client timeouts:**

- Cold start + work: use **`fetch` timeout ≥ 120s**; **≥ 900s** is safer for URL mode that falls through to download + STT.

**Operational realities:**

| Challenge | Effect | Mitigation in plugin |
|-----------|--------|----------------------|
| **Render cold start** | First request after idle is slow | Show spinner; retry once; warm-up ping optional |
| **YouTube blocks datacenter IP** | Caption fetch fails (`IpBlocked`) → fallback STT may also fail | **Primary mitigation:** capture audio client-side or use **official / licensed** flows; **secondary:** user retries later; **tertiary:** smaller clips |
| **No captions + STT fallback** | Needs yt-dlp + ffmpeg + optional cookies/Node on server | Ensure deployment uses **Dockerfile** path on Render for Node+EJS; cookies secret only for stubborn downloads |
| **Stale cookies** (STT path only) | yt-dlp auth errors | Operational — refresh secret `cookies.txt`; **not** needed when `source` is `youtube_captions` |

---

## 3. Optimal integration strategy (choose in this order)

### Tier 1 — Best reliability (recommended default path for “must work”)

1. User selects or plays video **in browser**.  
2. Plugin obtains **Blob** (e.g. **MediaRecorder**, **captureStream**, **downloaded segment**, or user-chosen file).  
3. **`POST /uploadAudio`** as **multipart** `audio` with correct `type=` **or** raw with correct `Content-Type`.  
4. Cache result in **`localStorage`** keyed by **`youtube_video_id`** or normalized URL.

**Why:** Avoids YouTube treating Render’s IP as a bot for **fetch** operations.

### Tier 2 — Best UX when it works (fast, no large upload)

1. User pastes **YouTube URL**.  
2. **`POST /transcribeUrl`** with JSON.  
3. If **`source === "youtube_captions"`** → done; cache text.  
4. If **`source === "youtube_audio_stt"`** → optionally show notice “generated from audio”; cache.  
5. If **500 / timeout / repeated failure** → **fallback to Tier 1** (offer “Record tab” / “Upload file” / “Try again from your network”).

### Tier 3 — Optional future (not required for v1)

- Client-side caption libraries calling YouTube **from the user’s IP** (maintenance burden; only if product demands zero server caption dependency).

---

## 4. Caching spec (required)

- **Key:** `ll_espeech_${youtube_video_id}` or hash of canonical URL.  
- **Value (JSON):** `{ transcription, source, fetchedAt, url }`  
- **TTL:** optional (e.g. 7 days) or manual clear button.  
- **Invalidate:** if user clicks “refresh transcript”.

---

## 5. WordPress implementation notes

- Enqueue **vanilla JS or bundled TS**; use **`fetch`** with **`AbortController`** for timeouts.  
- **Do not** bake secrets into the frontend; backend URL can be **wp_option** or constant.  
- If host uses strict **CORS** or **CSP**, allow **`https://yespeechserver.onrender.com`** for `connect-src`.  
- Show **explicit errors** from JSON `detail` when present (truncate for UI).  
- **Accessibility:** loading state + failure message + retry.

---

## 6. Legal / product (short)

YouTube ToS and copyright apply. The plugin should **not** encourage piracy; restrict to educational use aligned with site policy. Backend README links yt-dlp / transcript caveats.

---

## 7. Acceptance checklist (agent must satisfy)

- [ ] From teaser UI: user can get **plain text** for a video via **`/transcribeUrl`** **and** sees **`source`** (`youtube_captions` vs `youtube_audio_stt`).  
- [ ] Same UI offers **fallback** path using **`/uploadAudio`** (file or recorded blob) when URL path fails or times out.  
- [ ] **localStorage** cache prevents duplicate API calls for same video ID.  
- [ ] Handles **cold start** (long wait, no silent hang).  
- [ ] Handles **413** with user-facing guidance (file too large).  
- [ ] **`Content-Type` / multipart** documented in inline comments so future edits don’t regress.

---

## 8. Quick test commands (Windows `curl.exe`)

```bat
curl.exe -s "https://yespeechserver.onrender.com/"
```

```bat
curl.exe -s --max-time 900 -X POST "https://yespeechserver.onrender.com/transcribeUrl" -H "Content-Type: application/json" -d "{\"url\":\"https://www.youtube.com/watch?v=VIDEO_ID\"}"
```

```bat
curl.exe -s --max-time 300 -X POST "https://yespeechserver.onrender.com/uploadAudio" -H "Content-Type: audio/wav" --data-binary "@C:\path\to\sample.wav"
```

---

**End of brief.** Implement against **`main`** ESpeechServer; behavior described matches caption-first **`/transcribeUrl`** and resilient **`/uploadAudio`**.
