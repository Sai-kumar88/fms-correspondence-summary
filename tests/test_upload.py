import io
import pytest
from fastapi.testclient import TestClient
import pymupdf as fitz

from app.main import app

client = TestClient(app)


def create_test_pdf(text: str = "Official Notice: Project review is scheduled for Monday.") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    rect = fitz.Rect(50, 50, 550, 750)
    page.insert_textbox(rect, text, fontsize=12)
    b = doc.tobytes()
    doc.close()
    return b


class TestUploadAPI:
    """Test suite for HTTP upload, validation, processing and download endpoints."""

    def test_root_ui_endpoint(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "FMS Summary" in response.text
        assert "Document Upload" in response.text

    def test_health_endpoints(self):
        resp_root = client.get("/health")
        assert resp_root.status_code == 200
        assert resp_root.json()["status"] == "healthy"

        resp_api = client.get("/api/v1/health")
        assert resp_api.status_code == 200
        data = resp_api.json()
        assert data["status"] == "healthy"
        assert "ai_model" in data
        assert "allowed_formats" in data

    def test_upload_valid_pdf_successful(self):
        pdf_bytes = create_test_pdf(
            "Notice of Decision: The contract renewal for vendor Acme Corp has been approved on 2026-11-17. "
            "Action required: sign the agreement and archive the correspondence."
        )
        response = client.post(
            "/api/v1/upload",
            files={"file": ("notice.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["filename"] == "notice.pdf"
        assert data["file_type"] == ".pdf"
        assert data["page_count"] == 1
        assert "summary" in data
        assert "document_summary" in data["summary"]
        assert "main_purpose" in data["summary"]
        assert isinstance(data["summary"]["key_highlights"], list)

    def test_upload_empty_file_rejected(self):
        response = client.post(
            "/api/v1/upload",
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")}
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_upload_unsupported_format_rejected(self):
        response = client.post(
            "/api/v1/upload",
            files={"file": ("script.exe", io.BytesIO(b"MZ\x90\x00binary"), "application/octet-stream")}
        )
        assert response.status_code == 415
        assert "unsupported" in response.json()["detail"].lower()

    def test_upload_corrupted_pdf_rejected(self):
        corrupted = b"%PDF-1.4\nInvalid broken PDF content with missing cross reference tables"
        response = client.post(
            "/api/v1/upload",
            files={"file": ("corrupt.pdf", io.BytesIO(corrupted), "application/pdf")}
        )
        assert response.status_code in {400, 422}

    def test_download_summary_formats(self):
        sample_payload = {
            "filename": "project_report.pdf",
            "format": "txt",
            "summary": {
                "document_summary": "Summary of the project report.",
                "main_purpose": "Review project progress.",
                "key_highlights": ["Milestone 1 is complete."]
            }
        }

        # Test TXT format
        sample_payload["format"] = "txt"
        resp_txt = client.post("/api/v1/download", json=sample_payload)
        assert resp_txt.status_code == 200
        assert "text/plain" in resp_txt.headers["content-type"]
        assert "1. DOCUMENT SUMMARY" in resp_txt.text
        assert "2. MAIN PURPOSE" in resp_txt.text
        assert "3. KEY HIGHLIGHTS" in resp_txt.text

        # Test Word Document (.doc) format
        sample_payload["format"] = "doc"
        resp_doc = client.post("/api/v1/download", json=sample_payload)
        assert resp_doc.status_code == 200
        assert "application/msword" in resp_doc.headers["content-type"]
        assert "<html" in resp_doc.text
        assert "project_report.pdf" in resp_doc.text

        # Test PDF Document (.pdf) format
        sample_payload["format"] = "pdf"
        resp_pdf = client.post("/api/v1/download", json=sample_payload)
        assert resp_pdf.status_code == 200
        assert "application/pdf" in resp_pdf.headers["content-type"]
        assert resp_pdf.content.startswith(b"%PDF-")

        # Test JSON format
        sample_payload["format"] = "json"
        resp_json = client.post("/api/v1/download", json=sample_payload)
        assert resp_json.status_code == 200
        assert "application/json" in resp_json.headers["content-type"]
        data = resp_json.json()
        assert data["filename"] == "project_report.pdf"
        assert "document_summary" in data["summary"]
