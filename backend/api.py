import re
from pathlib import PurePosixPath
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from document_parser import SUPPORTED_EXTENSIONS, extract_text


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
COMPANY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

app = FastAPI(title="VoiceBox Document API")


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


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