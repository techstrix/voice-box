import sys
import types
import unittest
from io import BytesIO
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient

from document_parser import extract_text
from api import app


class DocumentParserTests(unittest.TestCase):
    def test_extracts_plain_text(self):
        self.assertEqual(extract_text("faq.txt", b"  Return within 30 days.  "), "Return within 30 days.")

    def test_extracts_docx_paragraph(self):
        document = Document()
        document.add_paragraph("Office hours are 9 to 5.")
        content = BytesIO()
        document.save(content)

        self.assertEqual(
            extract_text("hours.docx", content.getvalue()),
            "Office hours are 9 to 5.",
        )

    def test_rejects_unsupported_extension(self):
        with self.assertRaises(ValueError):
            extract_text("manual.exe", b"not a document")


class UploadEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.rag_stub = types.ModuleType("rag")
        self.rag_stub.upsert_company_doc = lambda company_id, text, source_name: 2
        self.rag_patch = patch.dict(sys.modules, {"rag": self.rag_stub})
        self.rag_patch.start()
        self.addCleanup(self.rag_patch.stop)

    def test_upload_indexes_supported_text_document(self):
        response = self.client.post(
            "/api/upload",
            data={"company_id": "acme-corp"},
            files={"file": ("faq.txt", b"Returns within 30 days.", "text/plain")},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "indexed")
        self.assertEqual(response.json()["chunks"], 2)

    def test_rejects_unsupported_document(self):
        response = self.client.post(
            "/api/upload",
            data={"company_id": "acme-corp"},
            files={"file": ("program.exe", b"not a document", "application/octet-stream")},
        )

        self.assertEqual(response.status_code, 415)

    def test_rejects_invalid_company_id(self):
        response = self.client.post(
            "/api/upload",
            data={"company_id": "../other-company"},
            files={"file": ("faq.txt", b"content", "text/plain")},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()