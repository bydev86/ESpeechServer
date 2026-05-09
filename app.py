import os
import tempfile

from flask import Flask, jsonify, request
from flask_cors import CORS
from pydub import AudioSegment
import speech_recognition as sr

app = Flask(__name__)
CORS(
    app,
    resources={
        r"/uploadAudio": {
            "origins": "*",
            "methods": ["POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
        }
    },
)

MULTIPART_FIELD_NAMES = ("audio", "file", "recording", "upload")


def _json_error(message: str, status_code: int):
    return jsonify({"error": message}), status_code


def _content_type_to_format(content_type: str | None) -> tuple[str, str] | None:
    if not content_type:
        return None
    ct = content_type.split(";")[0].strip().lower()
    mapping = {
        "audio/wav": ("wav", ".wav"),
        "audio/x-wav": ("wav", ".wav"),
        "audio/wave": ("wav", ".wav"),
        "audio/webm": ("webm", ".webm"),
        "audio/x-webm": ("webm", ".webm"),
        "audio/ogg": ("ogg", ".ogg"),
        "audio/opus": ("opus", ".opus"),
        "application/ogg": ("ogg", ".ogg"),
    }
    return mapping.get(ct)


def _sniff_magic(data: bytes) -> tuple[str, str] | None:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ("wav", ".wav")
    if len(data) >= 4 and data[:4] == b"\x1a\x45\xdf\xa3":
        return ("webm", ".webm")
    if len(data) >= 4 and data[:4] == b"OggS":
        return ("ogg", ".ogg")
    return None


def resolve_audio_format(data: bytes, content_type: str | None) -> tuple[str, str] | None:
    """Prefer magic-byte sniffing, then Content-Type hint."""
    magic = _sniff_magic(data)
    if magic:
        return magic
    return _content_type_to_format(content_type)


def read_upload_payload():
    """Raw body or first matching multipart field."""
    for name in MULTIPART_FIELD_NAMES:
        if name not in request.files:
            continue
        storage = request.files[name]
        if not storage or not getattr(storage, "filename", None):
            continue
        data = storage.read()
        return data, storage.content_type
    data = request.get_data(cache=False, as_text=False)
    return data, request.content_type


def normalize_to_wav_16k_mono(raw_data: bytes, pydub_format: str, suffix: str) -> str:
    """
    Write input to a temp file under the default temp dir (e.g. /tmp on Render),
    transcode with pydub/ffmpeg to mono 16 kHz WAV, return path to WAV (caller must unlink).
    """
    fd_in, path_in = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd_in, "wb") as wf:
            wf.write(raw_data)
        fd_out, path_out = tempfile.mkstemp(suffix=".wav")
        os.close(fd_out)
        try:
            segment = AudioSegment.from_file(path_in, format=pydub_format)
            segment = segment.set_channels(1).set_frame_rate(16000)
            segment.export(path_out, format="wav")
            return path_out
        except Exception:
            try:
                os.unlink(path_out)
            except OSError:
                pass
            raise
    finally:
        try:
            os.unlink(path_in)
        except OSError:
            pass


def speech_to_text(wav_path: str) -> str:
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
    try:
        text = recognizer.recognize_google(audio_data)
        return text
    except sr.UnknownValueError:
        return "Google Speech Recognition could not understand audio"
    except sr.RequestError as e:
        return f"Could not request results from Google Speech Recognition service; {e}"


@app.route("/uploadAudio", methods=["POST", "OPTIONS"])
def upload_audio():
    if request.method == "OPTIONS":
        return "", 204

    path_wav = None
    try:
        raw, content_type = read_upload_payload()
        if not raw:
            return _json_error("Empty audio payload", 400)

        resolved = resolve_audio_format(raw, content_type)
        if not resolved:
            return _json_error(
                "Unsupported or unrecognized audio format; "
                "send a known Content-Type or WAV/WebM/OGG bytes",
                415,
            )

        pydub_format, suffix = resolved
        path_wav = normalize_to_wav_16k_mono(raw, pydub_format, suffix)
        transcription = speech_to_text(path_wav)
        return jsonify({"transcription": transcription}), 200

    except OSError as e:
        return _json_error(f"Audio processing failed: {e}", 500)
    except Exception as e:
        return _json_error(str(e), 500)
    finally:
        if path_wav:
            try:
                os.unlink(path_wav)
            except OSError:
                pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8888"))
    app.run(host="0.0.0.0", port=port)
