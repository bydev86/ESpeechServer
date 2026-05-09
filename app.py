import os
import tempfile
import traceback

from flask import Flask, jsonify, request
from pydub import AudioSegment
import speech_recognition as sr

app = Flask(__name__)


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
        "audio/m4a": "m4a",
        "audio/x-m4a": "m4a",
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
    if fmt in ("m4a", "mp4"):
        return ".m4a"
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
                if ext in ("webm", "wav", "ogg", "opus", "mp3", "m4a", "mp4"):
                    pfmt = "ogg" if ext == "opus" else ext
            if not pfmt:
                pfmt = _sniff_pydub_format(data)
            return data, f.mimetype or ct, pfmt
    data = request.get_data(cache=False, as_text=False)
    pfmt = _pydub_format_from_content_type(ct)
    return data, ct, pfmt


def _export_wav_for_google_(src_path, pydub_format=None):
    """
    Decode with pydub (ffmpeg), normalize to mono 16kHz WAV for SpeechRecognition.
    Returns path to a new temp .wav file.
    """
    kwargs = {}
    if pydub_format:
        kwargs["format"] = pydub_format
    audio = AudioSegment.from_file(src_path, **kwargs)
    audio = audio.set_channels(1).set_frame_rate(16000)
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    audio.export(wav_path, format="wav")
    return wav_path


def speech_to_text(wav_path):
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
    try:
        text = recognizer.recognize_google(audio_data)
        print(f"Transcription: {text}")
        return text
    except sr.UnknownValueError:
        return "Google Speech Recognition could not understand audio"
    except sr.RequestError as e:
        return f"Could not request results from Google Speech Recognition service; {e}"


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
