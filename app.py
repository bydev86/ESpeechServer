import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from urllib.parse import parse_qs, urlparse

from flask import Flask, jsonify, request
from pydub import AudioSegment
import speech_recognition as sr

app = Flask(__name__)


@app.route("/")
def root_health():
    return jsonify({"ok": True, "service": "ESpeechServer"}), 200


def _cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.after_request
def _after(resp):
    return _cors_headers(resp)


@app.route("/uploadAudio", methods=["OPTIONS"])
def upload_audio_options():
    return "", 204


def _normalize_content_type(ct):
    if not ct:
        return ""
    return ct.split(";", 1)[0].strip().lower()


def _pydub_format_from_content_type(ct):
    ct = _normalize_content_type(ct)
    return {
        "audio/webm": "webm",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/wave": "wav",
        "audio/ogg": "ogg",
        "audio/opus": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/mp4": "mp4",
        "video/mp4": "mp4",
        "audio/m4a": "m4a",
        "audio/x-m4a": "m4a",
        "video/quicktime": "mov",
    }.get(ct)


def _sniff_pydub_format(data):
    if not data or len(data) < 12:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"OggS":
        return "ogg"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    # ISO BMFF (MP4 / M4A / MOV) — typical for iPhone Voice Memos / AAC
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return "mp4"
    if data[:3] == b"ID3" or (len(data) >= 2 and data[0:1] == b"\xff" and (data[1] & 0xE0) == 0xE0):
        return "mp3"
    return None


def _suffix_for_format(fmt):
    if fmt == "webm":
        return ".webm"
    if fmt in ("ogg", "opus"):
        return ".ogg"
    if fmt == "mp3":
        return ".mp3"
    if fmt == "mp4":
        return ".mp4"
    if fmt == "m4a":
        return ".m4a"
    if fmt == "mov":
        return ".mov"
    if fmt == "wav":
        return ".wav"
    return ".bin"


def _read_upload_bytes_and_meta():
    """
    Returns (raw_bytes, content_type_hint, pydub_format or None).
    Supports raw body POSTs and multipart file fields (audio, file, recording).
    """
    ct = request.headers.get("Content-Type", "")
    if request.files:
        for key in ("audio", "file", "recording", "upload"):
            f = request.files.get(key)
            if not f:
                continue
            data = f.read()
            if not data:
                continue
            pfmt = _pydub_format_from_content_type(f.mimetype or "")
            if not pfmt and f.filename:
                ext = os.path.splitext(f.filename)[1].lower().lstrip(".")
                if ext in ("webm", "wav", "ogg", "opus", "mp3", "m4a", "mp4", "mov"):
                    pfmt = "ogg" if ext == "opus" else ext
            if not pfmt:
                pfmt = _sniff_pydub_format(data)
            return data, f.mimetype or ct, pfmt
    data = request.get_data(cache=False, as_text=False)
    pfmt = _pydub_format_from_content_type(ct)
    return data, ct, pfmt


def _decode_audio_segment(src_path, format_hint=None):
    """
    Load media with pydub/ffmpeg using several strategies (wrong MIME/extension happens often).
    Larger probes help MP4/MOV where moov/metadata is late in the file.
    """
    _, ext = os.path.splitext(src_path)
    ext = ext.lower()

    attempts = []
    seen = set()

    def add_attempt(kwargs):
        key = repr(kwargs)
        if key not in seen:
            seen.add(key)
            attempts.append(kwargs)

    meaningful_ext = ext in (
        ".wav",
        ".webm",
        ".ogg",
        ".opus",
        ".mp3",
        ".mp4",
        ".m4a",
        ".mov",
    )
    if meaningful_ext:
        add_attempt({})
    if format_hint:
        add_attempt({"format": format_hint})

    if format_hint in ("mp4", "m4a", "mov") or ext in (".mp4", ".m4a", ".mov"):
        for fmt in ("mp4", "m4a", "mov"):
            add_attempt({"format": fmt})

    if format_hint == "webm" or ext == ".webm":
        add_attempt({"format": "webm"})
        add_attempt({"format": "matroska"})

    if format_hint in ("ogg", "opus") or ext in (".ogg", ".opus"):
        for fmt in ("ogg", "opus"):
            add_attempt({"format": fmt})

    if not attempts and format_hint:
        add_attempt({"format": format_hint})
    if not attempts:
        add_attempt({})

    heavy_params = ["-probesize", "100M", "-analyzeduration", "100M", "-fflags", "+genpts+discardcorrupt"]

    last_err = None
    for kwargs in attempts:
        for extra in (None, heavy_params):
            kw = dict(kwargs)
            if extra:
                kw["parameters"] = list(extra)
            try:
                return AudioSegment.from_file(src_path, **kw)
            except Exception as e:
                last_err = e
                continue
    if last_err:
        raise last_err
    raise RuntimeError("Unable to decode audio")


def _ffmpeg_direct_wav(src_path, wav_path):
    """Extract first audio stream to mono 16 kHz PCM WAV (handles many video containers)."""
    ffmpeg_bin = os.environ.get("FFMPEG_BINARY", "ffmpeg")
    cmd = [
        ffmpeg_bin,
        "-nostdin",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-probesize",
        "100M",
        "-analyzeduration",
        "100M",
        "-fflags",
        "+genpts+discardcorrupt",
        "-i",
        src_path,
        "-vn",
        "-map_metadata",
        "-1",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        wav_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip() or "ffmpeg CLI decode failed"
        raise RuntimeError(msg)


def _export_wav_for_google_(src_path, pydub_format=None):
    """
    Decode with pydub (ffmpeg), normalize to mono 16 kHz WAV for SpeechRecognition.
    Falls back to ffmpeg CLI for stubborn MP4/MOV/screen captures.
    Returns path to a new temp .wav file.
    """
    pydub_err = None
    try:
        audio = _decode_audio_segment(src_path, format_hint=pydub_format)
        audio = audio.set_channels(1).set_frame_rate(16000)
        fd, wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        audio.export(wav_path, format="wav")
        return wav_path
    except Exception as e:
        pydub_err = e

    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        _ffmpeg_direct_wav(src_path, wav_path)
        return wav_path
    except Exception as ff_err:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
        raise RuntimeError(
            f"Decode failed (pydub/ffmpeg): {pydub_err}; CLI fallback: {ff_err}"
        ) from ff_err


def _url_host_allowed(hostname: str) -> bool:
    if not hostname:
        return False
    h = hostname.lower().rstrip(".")
    if os.environ.get("TRANSCRIBE_URL_ANY_HOST", "").lower() in ("1", "true", "yes"):
        return True
    if h == "youtu.be":
        return True
    if h == "youtube.com" or h.endswith(".youtube.com"):
        return True
    extra = os.environ.get("TRANSCRIBE_URL_EXTRA_HOSTS", "")
    for part in extra.split(","):
        p = part.strip().lower().rstrip(".")
        if p and (h == p or h.endswith("." + p)):
            return True
    return False


def _validate_transcribe_url(url: str) -> tuple[bool, str]:
    url = (url or "").strip()
    if not url:
        return False, "missing url"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "only http(s) URLs are allowed"
    host = parsed.hostname
    if not host:
        return False, "invalid URL"
    if not _url_host_allowed(host):
        return (
            False,
            "host not allowed for URL transcribe (YouTube only by default; "
            "set TRANSCRIBE_URL_EXTRA_HOSTS or TRANSCRIBE_URL_ANY_HOST=true with care)",
        )
    return True, ""


def _is_youtube_url(url: str) -> bool:
    try:
        h = (urlparse(url).hostname or "").lower().rstrip(".")
    except Exception:
        return False
    return h == "youtu.be" or h == "youtube.com" or h.endswith(".youtube.com")


def _youtube_video_id_from_url(url: str) -> str | None:
    """Extract 11-char video id from common YouTube URL shapes."""
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    parts = [p for p in parsed.path.split("/") if p]

    if host == "youtu.be" and parts:
        vid = parts[0].split("?")[0]
        return vid if len(vid) >= 6 else None

    if host in ("youtube.com", "m.youtube.com", "music.youtube.com") or host.endswith(".youtube.com"):
        qs = parse_qs(parsed.query)
        if qs.get("v") and qs["v"][0]:
            return qs["v"][0]
        if len(parts) >= 2 and parts[0] in ("shorts", "embed", "live"):
            return parts[1]

    return None


def _try_youtube_caption_transcript(video_id: str) -> tuple[str | None, dict]:
    """
    Use youtube-transcript-api (undocumented timedtext API; no API key).
    May fail on datacenter IPs (IpBlocked) — same class of issue as yt-dlp.
    """
    if os.environ.get("SKIP_YOUTUBE_CAPTIONS", "").lower() in ("1", "true", "yes"):
        return None, {}
    raw = os.environ.get("YOUTUBE_TRANSCRIPT_LANGS", "en,en-US,en-GB").strip()
    languages = [x.strip() for x in raw.split(",") if x.strip()] or ["en"]
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=languages)
        pieces = [snippet.text for snippet in fetched]
        text = " ".join(pieces).strip()
        meta = {
            "caption_language_code": getattr(fetched, "language_code", None),
            "caption_language": getattr(fetched, "language", None),
            "caption_generated": getattr(fetched, "is_generated", None),
        }
        return (text or None), meta
    except Exception as e:
        return None, {"caption_error": type(e).__name__, "caption_detail": (str(e) or "")[:300]}


def _writable_cookies_copy_for_ytdlp(cookies_src: str | None) -> str | None:
    """
    yt-dlp calls save_cookies() on shutdown and opens the cookiejar for writing.
    Render secret files under /etc/secrets are read-only — feed yt-dlp a /tmp copy.
    """
    if not cookies_src or not os.path.isfile(cookies_src):
        return None
    fd, tmp = tempfile.mkstemp(prefix="yt_cookies_", suffix=".txt")
    os.close(fd)
    shutil.copyfile(cookies_src, tmp)
    return tmp


def _yt_dlp_download_best_audio(url: str) -> tuple[str, str]:
    """
    Download best audio with yt-dlp into a fresh temp directory.
    Returns (work_dir, media_path).

    YouTube often blocks datacenter IPs unless a non-web client is used; we try
    android/ios InnerTube variants before falling back to defaults.
    See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#youtube-sign-in-confirm-youre-not-a-bot
    """
    max_sec = int(os.environ.get("MAX_URL_AUDIO_SECONDS", "300"))
    max_mb = int(os.environ.get("MAX_URL_DOWNLOAD_MB", "120"))

    work_dir = tempfile.mkdtemp(prefix="ytdl_")
    out_tmpl = os.path.join(work_dir, "src.%(ext)s")

    cookies_src = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if not cookies_src:
        for candidate in ("/etc/secrets/cookies.txt", "/etc/secrets/yt_cookies.txt"):
            if os.path.isfile(candidate):
                cookies_src = candidate
                break

    cookies_writable: str | None = None
    try:
        cookies_writable = _writable_cookies_copy_for_ytdlp(cookies_src or None)

        base_cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "-f",
            "bestaudio/best",
            "--max-filesize",
            f"{max_mb}M",
            "-o",
            out_tmpl,
            "--retries",
            "2",
            "--fragment-retries",
            "2",
            "--socket-timeout",
            "30",
        ]
        if cookies_writable:
            base_cmd.extend(["--cookies", cookies_writable])

        # YouTube EJS / PO-token paths often need a JS runtime (Node ≥20, Deno ≥2, …).
        # Docker sets YTDLP_JS_RUNTIMES=node; on hosts where `node` exists we default to it.
        js_runtimes = os.environ.get("YTDLP_JS_RUNTIMES", "").strip()
        if not js_runtimes and shutil.which("node"):
            js_runtimes = "node"
        if js_runtimes:
            base_cmd.extend(["--js-runtimes", js_runtimes])

        # Fetch challenge solver scripts (required for many YouTube formats since ~2025).
        # https://github.com/yt-dlp/yt-dlp/wiki/EJS
        if "YTDLP_REMOTE_COMPONENTS" in os.environ:
            remote_components = os.environ["YTDLP_REMOTE_COMPONENTS"].strip()
        else:
            remote_components = "ejs:github" if _is_youtube_url(url) else ""
        if remote_components:
            base_cmd.extend(["--remote-components", remote_components])

        if max_sec > 0:
            base_cmd.extend(["--download-sections", f"*0-{max_sec}"])

        override = os.environ.get("YTDLP_EXTRACTOR_ARGS", "").strip()
        youtube_attempt_extras: list[list[str]] = []
        if override:
            youtube_attempt_extras.append(["--extractor-args", override])
        youtube_attempt_extras.extend(
            [
                ["--extractor-args", "youtube:player_client=android;player_skip=webpage"],
                ["--extractor-args", "youtube:player_client=ios;player_skip=webpage"],
                ["--extractor-args", "youtube:player_client=android"],
                ["--extractor-args", "youtube:player_client=ios"],
                [],
            ]
        )

        attempts = youtube_attempt_extras if _is_youtube_url(url) else [[]]

        last_msg = ""
        for extras in attempts:
            for fname in os.listdir(work_dir):
                fp = os.path.join(work_dir, fname)
                try:
                    if os.path.isfile(fp):
                        os.unlink(fp)
                except OSError:
                    pass

            cmd = list(base_cmd)
            cmd.extend(extras)
            cmd.append(url)

            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                last_msg = (proc.stderr or proc.stdout or "yt-dlp failed").strip()
                continue

            files = [
                os.path.join(work_dir, f)
                for f in os.listdir(work_dir)
                if os.path.isfile(os.path.join(work_dir, f))
            ]
            if not files:
                last_msg = "yt-dlp produced no file"
                continue

            media_path = max(files, key=os.path.getmtime)
            return work_dir, media_path

        shutil.rmtree(work_dir, ignore_errors=True)
        raise RuntimeError((last_msg or "yt-dlp failed")[:8000])
    finally:
        if cookies_writable:
            try:
                os.unlink(cookies_writable)
            except OSError:
                pass


def _recognize_google_safe(recognizer, audio_data):
    try:
        text = recognizer.recognize_google(audio_data)
        print(f"Transcription chunk: {text[:120]!r}...")
        return text
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        return f"[Google SR error: {e}]"


def speech_to_text(wav_path):
    """
    Google SpeechRecognition has practical limits on clip length; long WAVs are chunked.
    """
    recognizer = sr.Recognizer()
    chunk_ms = int(os.environ.get("SR_CHUNK_MS", "45000"))
    max_single_ms = int(os.environ.get("SR_MAX_SINGLE_MS", "55000"))
    chunk_sleep = float(os.environ.get("SR_CHUNK_SLEEP_SEC", "0.25"))

    seg = AudioSegment.from_file(wav_path, format="wav")
    total_ms = len(seg)

    if total_ms <= max_single_ms:
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
        text = _recognize_google_safe(recognizer, audio_data)
        return text or "Google Speech Recognition could not understand audio"

    parts = []
    for start in range(0, total_ms, chunk_ms):
        chunk = seg[start : start + chunk_ms]
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            chunk.export(tmp, format="wav")
            with sr.AudioFile(tmp) as source:
                audio_data = recognizer.record(source)
            piece = _recognize_google_safe(recognizer, audio_data)
            if piece:
                parts.append(piece)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        if chunk_sleep > 0:
            time.sleep(chunk_sleep)

    joined = " ".join(parts).strip()
    return joined or "Google Speech Recognition could not understand audio"


@app.route("/transcribeUrl", methods=["OPTIONS"])
def transcribe_url_options():
    return "", 204


@app.route("/transcribeUrl", methods=["POST"])
def transcribe_url():
    """
    JSON body: {"url": "https://www.youtube.com/watch?v=..."}

    For YouTube: tries existing captions/subtitles first (no cookies), then falls back
    to yt-dlp audio + speech-to-text. Non-YouTube URLs use audio download only.
    """
    work_dir = None
    wav_path = None
    video_id = None
    cap_meta: dict = {}
    try:
        body = request.get_json(silent=True) or {}
        url = body.get("url") or body.get("video_url") or ""
        ok, reason = _validate_transcribe_url(url)
        if not ok:
            return jsonify({"error": "bad_request", "detail": reason}), 400

        video_id = _youtube_video_id_from_url(url) if _is_youtube_url(url) else None
        if video_id:
            cap_text, cap_meta = _try_youtube_caption_transcript(video_id)
            if cap_text:
                out = {
                    "transcription": cap_text,
                    "source": "youtube_captions",
                    "youtube_video_id": video_id,
                }
                for k, v in cap_meta.items():
                    if v is not None:
                        out[k] = v
                return jsonify(out), 200

        # Consumer-facing hosts: skip yt-dlp (cookies/bot wall) when captions failed — fail fast for UI upload path.
        if (
            video_id
            and _is_youtube_url(url)
            and os.environ.get("SKIP_YTDLP_FALLBACK", "").lower() in ("1", "true", "yes")
        ):
            return jsonify(
                {
                    "error": "client_upload_required",
                    "youtube_video_id": video_id,
                    "caption_attempt": {
                        k: cap_meta[k]
                        for k in ("caption_error", "caption_detail")
                        if k in cap_meta and cap_meta[k]
                    },
                    "message": (
                        "This server cannot download YouTube audio without captions. "
                        "Use POST /uploadAudio with audio or video from the viewer's device "
                        "(file pick, screen/tab recording, or exported clip)."
                    ),
                    "next_step": "upload_audio",
                }
            ), 422

        work_dir, media_path = _yt_dlp_download_best_audio(url)
        wav_path = _export_wav_for_google_(media_path, pydub_format=None)
        transcription = speech_to_text(wav_path)
        out = {
            "transcription": transcription,
            "source": "youtube_audio_stt",
        }
        if video_id:
            out["youtube_video_id"] = video_id
            err = cap_meta.get("caption_error") if cap_meta else None
            if err:
                out["caption_fallback_reason"] = err
        return jsonify(out), 200
    except Exception as e:
        err = {
            "error": "transcription_failed",
            "detail": str(e),
            "trace": traceback.format_exc() if app.debug else None,
        }
        if video_id:
            err["youtube_video_id"] = video_id
        if cap_meta:
            err["caption_attempt"] = {
                k: cap_meta[k]
                for k in ("caption_error", "caption_detail")
                if k in cap_meta and cap_meta[k]
            }
        err["hint"] = (
            "Captions may have failed from a datacenter IP; yt-dlp then hit a bot check. "
            "Refresh Render cookies.txt if using STT fallback, or upload audio via POST /uploadAudio from the user browser."
        )
        return jsonify(err), 500
    finally:
        if wav_path:
            try:
                if os.path.exists(wav_path):
                    os.remove(wav_path)
            except OSError:
                pass
        if work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)


@app.route("/uploadAudio", methods=["POST"])
def upload_audio():
    tmp_paths = []
    try:
        raw, ct_header, pfmt = _read_upload_bytes_and_meta()
        if not raw:
            return jsonify({"error": "empty_body", "detail": "No audio bytes received"}), 400
        if not pfmt:
            pfmt = _pydub_format_from_content_type(ct_header)
        if not pfmt:
            pfmt = _sniff_pydub_format(raw)
        suffix = _suffix_for_format(pfmt) if pfmt else ".bin"
        fd_in, in_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd_in)
        tmp_paths.append(in_path)
        with open(in_path, "wb") as f:
            f.write(raw)
        wav_path = _export_wav_for_google_(in_path, pydub_format=pfmt)
        tmp_paths.append(wav_path)
        transcription = speech_to_text(wav_path)
        return jsonify({"transcription": transcription}), 200
    except Exception as e:
        err = {
            "error": "transcription_failed",
            "detail": str(e),
            "trace": traceback.format_exc() if app.debug else None,
        }
        return jsonify(err), 500
    finally:
        for p in tmp_paths:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8888"))
    app.run(host="0.0.0.0", port=port)
    print(f"Listening at {port}")
