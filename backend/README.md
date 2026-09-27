# VoiceBox backend (document API + voice loop)

## Configure

Copy `.env.example` to `.env` and set:

- `PINECONE_API_KEY`, `PINECONE_INDEX_NAME` (index must be 384 dims for `all-MiniLM-L6-v2`)
- `OLLAMA_CLIENT_HOST` (default `http://127.0.0.1:11434`, model `llama3.2:1b`)
- `STT_MODEL` (default `base`), `TTS_VOICE` (default `en-US-AriaNeural`)
- `COMPANY_MAP`, e.g. `1001:acme-corp,1002:globex` (Asterisk extension -> Pinecone namespace)

## Run (Windows host venv, GPU)

From the repo root:

```powershell
.\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
# Terminal 1: HTTP API (upload + voice-turn + audio)
.\venv\Scripts\python.exe -m uvicorn api:app --app-dir backend --port 8000
# Terminal 2: FastAGI server for Asterisk (port 4573)
.\venv\Scripts\python.exe backend\agi_server.py
```

Asterisk runs in Docker (`docker compose up -d asterisk`). After editing
`asterisk/config/extensions.conf`, reload without restarting:

```powershell
docker exec asterisk asterisk -rx "dialplan reload"
```

## Endpoints

- `GET /api/health` — status + stt model/voice/mapped extensions
- `POST /api/upload` — form `company_id` + file (txt/md/pdf/docx, 10 MB)
- `POST /api/voice-turn` — form `company_id` + audio (wav/mp3/m4a/flac/ogg/webm, 10 MB)
  → `{transcript, answer, audio_url}`. Same pipeline a phone caller hears.
- `GET /api/voice-audio/{name}` — serves generated `out_*.wav` replies.

## Call flow (extensions 1001/1002)

Answer → Record `sounds/in_<UNIQUEID>.wav` (12 s max) → FastAGI
`agi://host.docker.internal:4573/voice` → STT → RAG (`COMPANY_MAP`) → Ollama
→ edge-tts → 8 kHz wav `sounds/out_<UNIQUEID>.wav` → Playback → Hangup.
Every failure still plays a spoken fallback so callers never hear silence.

## Tests

```powershell
.\venv\Scripts\python.exe -m pytest backend\test_voice.py -v
.\venv\Scripts\python.exe -m unittest test_document_upload.py -v  # needs Pinecone key
```
