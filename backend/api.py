import os
import re
import tempfile
from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from document_parser import SUPPORTED_EXTENSIONS, extract_text

import voice


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 10 * 1024 * 1024
COMPANY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".webm"}

app = FastAPI(title="VoiceBox Document API")


@app.get("/api/health")
def health_check() -> dict[str, str | int]:
    return {
        "status": "ok",
        "stt_model": voice.STT_MODEL,
        "tts_voice": voice.TTS_VOICE,
        "mapped_extensions": len(voice.parse_company_map()),
    }


@app.post("/api/upload")
async def upload_document(
    company_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, str | int]:
    company_id = company_id.strip()
    if not COMPANY_ID_PATTERN.fullmatch(company_id):
        raise HTTPException(
            status_code=422,
            detail="Company ID must be 1-63 letters, numbers, dots, underscores, or hyphens.",
        )

    filename = (file.filename or "").replace("\\", "/").split("/")[-1]
    if not filename or PurePosixPath(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Upload a TXT, MD, PDF, or DOCX file.")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB upload limit.")

    try:
        text = extract_text(filename, content)
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=422, detail="The document could not be read.") from error

    if not text:
        raise HTTPException(
            status_code=422,
            detail="No readable text was found. Scanned PDFs need OCR before upload.",
        )

    from rag import upsert_company_doc

    source_id = f"{uuid4().hex}-{filename}"
    try:
        chunk_count = upsert_company_doc(company_id, text, source_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail="Document indexing failed.") from error

    return {
        "status": "indexed",
        "company_id": company_id,
        "filename": filename,
        "chunks": chunk_count,
    }


@app.get("/api/voice-audio/{name}")
def get_voice_audio(name: str):
    safe = (name or "").replace("\\", "/").split("/")[-1]
    if not re.fullmatch(r"out_[A-Za-z0-9_.-]{1,64}\.wav", safe):
        raise HTTPException(status_code=404, detail="Audio not found.")
    path = os.path.join(voice.SOUNDS_DIR, safe)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Audio not found.")
    return FileResponse(path, media_type="audio/wav", filename=safe)


@app.post("/api/voice-turn")
async def voice_turn(
    company_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, str | None]:
    company_id = (company_id or "").strip()
    if not COMPANY_ID_PATTERN.fullmatch(company_id):
        raise HTTPException(
            status_code=422,
            detail="Company ID must be 1-63 letters, numbers, dots, underscores, or hyphens.",
        )

    filename = (file.filename or "audio.webm").replace("\\", "/").split("/")[-1]
    suffix = PurePosixPath(filename).suffix.lower() or ".webm"
    if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Upload a WAV, MP3, M4A, FLAC, OGG, or WebM file.")

    content = await file.read(MAX_AUDIO_BYTES + 1)
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio exceeds the 10 MB limit.")
    if not content:
        raise HTTPException(status_code=422, detail="Audio file is empty.")

    call_id = uuid4().hex
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        result = voice.process_voice_turn(company_id, tmp_path, call_id)
    except Exception as error:
        raise HTTPException(status_code=502, detail="Voice turn failed.") from error
    finally:
        try:
            if tmp_path:
                os.remove(tmp_path)
        except OSError:
            pass

    audio_url = None
    if result.get("wav_path"):
        audio_url = f"/api/voice-audio/{os.path.basename(result['wav_path'])}"
    return {
        "transcript": result.get("transcript") or "",
        "answer": result.get("answer") or "",
        "audio_url": audio_url,
    }