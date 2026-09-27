"""Shared voice-turn pipeline: STT -> RAG -> LLM -> TTS.

Used by both the HTTP API (`/api/voice-turn`, frontend Call tester) and the
Asterisk FastAGI server (`agi_server.py`). Telephony callers must always hear
* something, so `process_voice_turn` never raises for pipeline failures --
it falls back to a spoken apology instead.

Only stdlib imports at module top so `api.py` stays importable even when
optional heavy dependencies (torch, pinecone, whisper) are missing. All
third-party imports are lazy inside functions.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
import uuid

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUNDS_DIR = os.path.join(REPO_ROOT, "asterisk", "sounds")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

STT_MODEL = os.environ.get("STT_MODEL", "base")
TTS_VOICE = os.environ.get("TTS_VOICE", "en-US-AriaNeural")

FALLBACK_NO_AUDIO = "Sorry, I didn't hear anything. Please try again."
FALLBACK_NO_SPEECH = "Sorry, I couldn't make out what you said. Please try again."
FALLBACK_KB_ERROR = "Sorry, I'm having trouble reaching the knowledge base right now. Please try again later."
FALLBACK_UNCONFIGURED = "Sorry, this line is not configured yet. Please contact support."

_model_lock = threading.Lock()
_cached_model: dict = {}


def parse_company_map(raw: str | None = None) -> dict[str, str]:
    """Parse 'COMPANY_MAP' like '1001:acme-corp,1002:globex' into {extension: company_id}."""
    raw = raw if raw is not None else os.environ.get("COMPANY_MAP", "")
    mapping: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        ext, company = item.split(":", 1)
        ext, company = ext.strip(), company.strip()
        if ext and company:
            mapping[ext] = company
    return mapping


def company_for_extension(extension: str) -> str | None:
    return parse_company_map().get((extension or "").strip())


def sanitize_call_id(call_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", call_id or "")
    return cleaned[:64] or uuid.uuid4().hex


def in_wav_path(call_id: str) -> str:
    return os.path.join(SOUNDS_DIR, f"in_{sanitize_call_id(call_id)}.wav")


def out_wav_path(call_id: str) -> str:
    return os.path.join(SOUNDS_DIR, f"out_{sanitize_call_id(call_id)}.wav")


def _get_whisper_model():
    """Load (once) and cache the faster-whisper model for the configured STT_MODEL."""
    import stt as stt_mod

    with _model_lock:
        entry = _cached_model.get(STT_MODEL)
        if entry is None:
            device = stt_mod.resolve_device("auto")
            compute = stt_mod.default_compute_type(device)
            model, used_device, used_compute = stt_mod.load_model_with_fallback(
                STT_MODEL, device, compute
            )
            entry = (model, used_device, used_compute)
            _cached_model[STT_MODEL] = entry
        return entry


def transcribe_audio(audio_path: str, language: str = "en") -> tuple[str, str]:
    """Transcribe with the cached GPU model. Returns (text, 'device/compute')."""
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if os.path.getsize(audio_path) == 0:
        raise ValueError(f"Audio file is empty (0 bytes): {audio_path}")
    model, used_device, used_compute = _get_whisper_model()
    try:
        segments, _info = model.transcribe(audio_path, language=language, beam_size=5)
        text = " ".join(s.text.strip() for s in segments if s.text.strip())
    except Exception as error:
        raise RuntimeError(f"STT decode failed: {error}") from error
    return text, f"{used_device}/{used_compute}"


def synthesize_to_mp3(text: str, mp3_path: str) -> str:
    import tts as tts_mod

    return tts_mod.synthesize(text, mp3_path, voice=TTS_VOICE)


def convert_mp3_to_wav_8k(mp3_path: str, wav_path: str) -> str:
    """Convert edge-tts mp3 output to 8 kHz mono 16-bit wav for Asterisk Playback."""
    import av

    os.makedirs(os.path.dirname(os.path.abspath(wav_path)), exist_ok=True)
    with av.open(mp3_path) as container:
        stream = next(s for s in container.streams if s.type == "audio")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=8000)
        out = av.open(wav_path, "w")
        out_stream = out.add_stream("pcm_s16le", rate=8000)
        out_stream.layout = "mono"

        def _write(frame):
            for resampled in resampler.resample(frame):
                for packet in out_stream.encode(resampled):
                    out.mux(packet)

        for frame in container.decode(stream):
            _write(frame)
        _write(None)  # flush resampler
        for packet in out_stream.encode(None):  # flush encoder
            out.mux(packet)
        out.close()
    return wav_path


def answer_question(company_id: str, question: str) -> tuple[str, str]:
    """RAG + LLM. Returns (answer, context). Lets errors propagate to caller."""
    from rag import retrieve_context
    from llm import generate_answer

    context = retrieve_context(company_id=company_id, question=question)
    answer = generate_answer(
        company_name=company_id, context=context, question=question
    )
    return answer, context


def _speak_fallback(text: str, call_id: str) -> str | None:
    """Best-effort TTS for fallback audio. Returns wav path or None."""
    try:
        tmp_mp3 = os.path.join(SOUNDS_DIR, f"tmp_{sanitize_call_id(call_id)}.mp3")
        synthesize_to_mp3(text, tmp_mp3)
        wav = convert_mp3_to_wav_8k(tmp_mp3, out_wav_path(call_id))
        try:
            os.remove(tmp_mp3)
        except OSError:
            pass
        return wav
    except Exception:
        return None


def process_voice_turn(
    company_id: str | None, in_path: str, call_id: str
) -> dict[str, str | None]:
    """Full loop for one caller utterance. Never raises -- always returns audio if possible."""
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    call_id = sanitize_call_id(call_id)

    if not company_id:
        wav = _speak_fallback(FALLBACK_UNCONFIGURED, call_id)
        return {
            "transcript": "",
            "answer": FALLBACK_UNCONFIGURED,
            "context": "",
            "wav_path": wav,
        }

    try:
        transcript, _engine = transcribe_audio(in_path)
    except (FileNotFoundError, ValueError):
        wav = _speak_fallback(FALLBACK_NO_AUDIO, call_id)
        return {"transcript": "", "answer": FALLBACK_NO_AUDIO, "context": "", "wav_path": wav}
    except Exception:
        wav = _speak_fallback(FALLBACK_NO_SPEECH, call_id)
        return {"transcript": "", "answer": FALLBACK_NO_SPEECH, "context": "", "wav_path": wav}

    if not transcript.strip():
        wav = _speak_fallback(FALLBACK_NO_SPEECH, call_id)
        return {"transcript": "", "answer": FALLBACK_NO_SPEECH, "context": "", "wav_path": wav}

    try:
        answer, context = answer_question(company_id, transcript)
    except Exception:
        wav = _speak_fallback(FALLBACK_KB_ERROR, call_id)
        return {"transcript": transcript, "answer": FALLBACK_KB_ERROR, "context": "", "wav_path": wav}
    if not (answer or "").strip():
        answer = FALLBACK_KB_ERROR

    wav: str | None
    try:
        tmp_mp3 = os.path.join(SOUNDS_DIR, f"tmp_{call_id}.mp3")
        synthesize_to_mp3(answer, tmp_mp3)
        wav = convert_mp3_to_wav_8k(tmp_mp3, out_wav_path(call_id))
        try:
            os.remove(tmp_mp3)
        except OSError:
            pass
    except Exception:
        wav = None
    return {"transcript": transcript, "answer": answer, "context": context, "wav_path": wav}


def sweep_old_files(max_age_seconds: int = 3600) -> int:
    """Delete stale in_/out_/tmp_ wav/mp3 files from the shared sounds dir."""
    now = time.time()
    removed = 0
    try:
        names = os.listdir(SOUNDS_DIR)
    except OSError:
        return 0
    for name in names:
        if not (name.startswith(("in_", "out_", "tmp_")) and name.endswith((".wav", ".mp3"))):
            continue
        path = os.path.join(SOUNDS_DIR, name)
        try:
            if now - os.path.getmtime(path) > max_age_seconds:
                os.remove(path)
                removed += 1
        except OSError:
            pass
    return removed
