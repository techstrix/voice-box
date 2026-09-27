"""Voice-loop tests. All heavy deps (Whisper, Pinecone, Ollama, Edge TTS)
are faked via monkeypatch; these run with only fastapi installed.
"""
import os
import wave

import voice


def _write_wav(path: str) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 800)


def test_company_map_parsing():
    assert voice.parse_company_map("1001:acme-corp, 1002:globex ") == {
        "1001": "acme-corp",
        "1002": "globex",
    }
    assert voice.parse_company_map("") == {}
    assert voice.parse_company_map("no-colon,1003:") == {}


def test_sanitize_call_id():
    assert voice.sanitize_call_id("../../etc") == ".._.._etc"
    assert len(voice.sanitize_call_id("x" * 100)) == 64
    assert voice.sanitize_call_id("") != ""


def test_process_voice_turn_happy_path(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "SOUNDS_DIR", str(tmp_path))
    src = tmp_path / "caller.wav"
    _write_wav(str(src))
    monkeypatch.setattr(voice, "transcribe_audio", lambda p, language="en": ("What are the hours?", "cuda/float16"))
    monkeypatch.setattr(voice, "answer_question", lambda c, q: ("We are open 9 to 5.", "ctx"))
    monkeypatch.setattr(voice, "synthesize_to_mp3", lambda t, p: open(p, "wb").write(b"mp3") or p)
    monkeypatch.setattr(
        voice, "convert_mp3_to_wav_8k", lambda mp3, wav: (_write_wav(wav), wav)[1]
    )

    result = voice.process_voice_turn("acme-corp", str(src), "abc123")
    assert result["transcript"] == "What are the hours?"
    assert result["answer"] == "We are open 9 to 5."
    assert result["wav_path"] and os.path.isfile(result["wav_path"])


def test_process_voice_turn_empty_transcript_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "SOUNDS_DIR", str(tmp_path))
    src = tmp_path / "silence.wav"
    _write_wav(str(src))
    monkeypatch.setattr(voice, "transcribe_audio", lambda p, language="en": ("   ", "cpu/int8"))
    monkeypatch.setattr(voice, "_speak_fallback", lambda t, c: None)

    result = voice.process_voice_turn("acme-corp", str(src), "abc123")
    assert result["transcript"] == ""
    assert result["answer"] == voice.FALLBACK_NO_SPEECH


def test_process_voice_turn_kb_error_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "SOUNDS_DIR", str(tmp_path))
    src = tmp_path / "caller.wav"
    _write_wav(str(src))
    monkeypatch.setattr(voice, "transcribe_audio", lambda p, language="en": ("Hello?", "cpu/int8"))

    def boom(company, question):
        raise RuntimeError("pinecone down")

    monkeypatch.setattr(voice, "answer_question", boom)
    monkeypatch.setattr(voice, "_speak_fallback", lambda t, c: None)

    result = voice.process_voice_turn("acme-corp", str(src), "abc123")
    assert result["transcript"] == "Hello?"
    assert result["answer"] == voice.FALLBACK_KB_ERROR


def test_process_voice_turn_unconfigured_company(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "SOUNDS_DIR", str(tmp_path))
    monkeypatch.setattr(voice, "_speak_fallback", lambda t, c: None)
    result = voice.process_voice_turn(None, "whatever.wav", "abc123")
    assert result["answer"] == voice.FALLBACK_UNCONFIGURED


def test_sweep_old_files(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "SOUNDS_DIR", str(tmp_path))
    old = tmp_path / "in_old.wav"
    _write_wav(str(old))
    old_ts = 0
    os.utime(str(old), (old_ts, old_ts))
    fresh = tmp_path / "out_new.wav"
    _write_wav(str(fresh))
    keep = tmp_path / "notes.txt"
    keep.write_text("do not touch")
    assert voice.sweep_old_files(max_age_seconds=60) == 1
    assert not old.exists()
    assert fresh.exists()
    assert keep.exists()


# --- API validation (no pipeline run) ---


def _client(monkeypatch):
    from fastapi.testclient import TestClient

    import api

    def fake_turn(company_id, in_path, call_id):
        return {"transcript": "hi", "answer": "hello", "context": "", "wav_path": None}

    monkeypatch.setattr(api.voice, "process_voice_turn", fake_turn)
    return TestClient(api.app)


def test_api_voice_turn_validation(monkeypatch):
    client = _client(monkeypatch)
    bad = client.post("/api/voice-turn", data={"company_id": "!!bad!!"}, files={"file": ("a.wav", b"data")})
    assert bad.status_code == 422
    wrong_ext = client.post(
        "/api/voice-turn", data={"company_id": "acme"}, files={"file": ("a.txt", b"data")}
    )
    assert wrong_ext.status_code == 415
    empty = client.post(
        "/api/voice-turn", data={"company_id": "acme"}, files={"file": ("a.wav", b"")}
    )
    assert empty.status_code == 422


def test_api_voice_turn_ok(monkeypatch):
    client = _client(monkeypatch)
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 800)
    resp = client.post(
        "/api/voice-turn", data={"company_id": "acme"}, files={"file": ("a.wav", buf.getvalue())}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["transcript"] == "hi"
    assert body["audio_url"] is None


def test_api_voice_audio_404(monkeypatch):
    from fastapi.testclient import TestClient

    import api

    client = TestClient(api.app)
    assert client.get("/api/voice-audio/nope.wav").status_code == 404
    assert client.get("/api/voice-audio/../api.py").status_code == 404
