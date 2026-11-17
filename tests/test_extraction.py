import io
import pytest
import pymupdf as fitz
import docx

from app.services.file_service import (
    FileService,
    CorruptedFileError,
    EmptyDocumentError,
    UnsupportedFileTypeError
)
from app.services.text_extractor import TextExtractorService, ExtractedDocument


def create_sample_pdf(text: str) -> bytes:
    """Helper to generate a valid PDF with embedded text."""
    doc = fitz.open()
    page = doc.new_page()
    rect = fitz.Rect(50, 50, 550, 750)
    page.insert_textbox(rect, text, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_sample_docx(text: str) -> bytes:
    """Helper to generate a valid DOCX document."""
    doc = docx.Document()
    doc.add_heading("Internal Project Update", level=1)
    doc.add_paragraph(text)
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Project Name"
    table.cell(0, 1).text = "FMS Summary Automation"
    table.cell(1, 0).text = "Status"
    table.cell(1, 1).text = "Active and Approved"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class TestTextExtraction:
    """Test suite for direct document text extraction."""

    def test_pdf_embedded_text_extraction(self):
        sample_text = (
            "This is an official correspondence regarding Project Apollo. "
            "The committee has approved the budget request on November 15, 2026. "
            "All department heads must submit their reports by Friday."
        )
        pdf_bytes = create_sample_pdf(sample_text)

        result = TextExtractorService.extract_text(pdf_bytes, ".pdf", "test.pdf")
        assert isinstance(result, ExtractedDocument)
        assert result.page_count == 1
        assert "Project Apollo" in result.text
        assert "November 15, 2026" in result.text
        assert result.word_count > 10

    def test_docx_extraction(self):
        sample_text = "The executive board met on October 10 to review performance benchmarks."
        docx_bytes = create_sample_docx(sample_text)

        result = TextExtractorService.extract_text(docx_bytes, ".docx", "update.docx")
        assert isinstance(result, ExtractedDocument)
        assert "Internal Project Update" in result.text
        assert "executive board met" in result.text
        assert "FMS Summary Automation" in result.text

    def test_doc_rtf_extraction(self):
        rtf_doc = (
            b"{\\rtf1\\ansi\\deff0 {\\fonttbl {\\f0 Arial;}}\n"
            b"\\f0\\fs24 MEMORANDUM: The request for software licenses has been reviewed and approved.\n"
            b"Action required: deploy by November 30.}"
        )
        result = TextExtractorService.extract_text(rtf_doc, ".doc", "memo.doc")
        assert isinstance(result, ExtractedDocument)
        assert "MEMORANDUM" in result.text
        assert "Action required" in result.text

    def test_txt_extraction(self):
        txt_content = b"Official correspondence: Please submit quarterly invoices before December 15."
        result = TextExtractorService.extract_text(txt_content, ".txt", "notice.txt")
        assert isinstance(result, ExtractedDocument)
        assert "quarterly invoices" in result.text

    def test_empty_document_raises_error(self):
        with pytest.raises(EmptyDocumentError):
            FileService.validate_file("empty.pdf", b"")

    def test_corrupted_file_raises_error(self):
        with pytest.raises(CorruptedFileError):
            FileService.validate_file("corrupt.pdf", b"Not a real PDF file bytes")
