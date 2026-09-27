# VoiceBox document upload API

## Configure

Copy `.env.example` to `.env` and set `PINECONE_API_KEY` and `PINECONE_INDEX_NAME`.
The index must use 384 dimensions for the `all-MiniLM-L6-v2` embedding model.

## Run

From this directory, install dependencies and start the API:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn api:app --reload --port 8000
```

The Vite frontend proxies `/api` to this server. It accepts TXT, MD, PDF, and DOCX files up to 10 MB. Scanned PDFs need OCR before upload.

Run the upload tests with:

```powershell
python -m unittest test_document_upload.py -v
```