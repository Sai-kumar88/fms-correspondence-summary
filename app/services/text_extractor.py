import io
import logging
import re
from dataclasses import dataclass, field
from typing import List

import docx
import olefile
import pymupdf as fitz

from app.services.file_service import CorruptedFileError, EmptyDocumentError

logger = logging.getLogger(__name__)


@dataclass
class ExtractedDocument:
    """Container holding extracted document text and processing metrics."""
    text: str
    page_count: int
    char_count: int
    word_count: int
    file_type: str
    warnings: List[str] = field(default_factory=list)


class TextExtractorService:
    """
    Direct, fast text extraction service supporting PDF, DOCX, DOC, and TXT files.
    Extracts digital text cleanly without requiring external OCR engines.
    """

    @classmethod
    def extract_text(cls, content: bytes, file_ext: str, filename: str = "") -> ExtractedDocument:
        """
        Extracts readable text from file content based on file extension.

        Args:
            content: Raw file content in bytes
            file_ext: File extension including leading dot (e.g., '.pdf')
            filename: Original file name for logging context

        Returns:
            ExtractedDocument containing cleaned text and extraction metadata.

        Raises:
            EmptyDocumentError: If document contains no readable characters.
            CorruptedFileError: If file structure cannot be read or parsed.
        """
        ext = file_ext.lower()

        try:
            if ext == ".pdf":
                doc = cls._extract_from_pdf(content)
            elif ext == ".docx":
                doc = cls._extract_from_docx(content)
            elif ext == ".doc":
                doc = cls._extract_from_doc(content)
            elif ext == ".txt":
                doc = cls._extract_from_txt(content)
            else:
                raise CorruptedFileError(f"Unsupported extraction format: {ext}")
        except (EmptyDocumentError, CorruptedFileError):
            raise
        except Exception as e:
            logger.error(f"Text extraction failed for {filename} ({ext}): {e}", exc_info=True)
            raise CorruptedFileError(f"Failed to read or parse file '{filename}': {str(e)}")

        # Clean text while strictly preserving sentence structure
        cleaned = cls._clean_text(doc.text)
        if not cleaned or len(cleaned.strip()) == 0:
            raise EmptyDocumentError("The document contains no readable text or characters.")

        doc.text = cleaned
        doc.char_count = len(cleaned)
        doc.word_count = len(cleaned.split())
        return doc

    @classmethod
    def _extract_from_pdf(cls, content: bytes) -> ExtractedDocument:
        """Extracts digital text from PDF pages."""
        try:
            pdf_doc = fitz.open(stream=content, filetype="pdf")
        except Exception as e:
            raise CorruptedFileError(f"Invalid or corrupted PDF file: {str(e)}")

        total_pages = len(pdf_doc)
        if total_pages == 0:
            pdf_doc.close()
            raise EmptyDocumentError("The PDF document contains 0 pages.")

        page_texts: List[str] = []
        for idx in range(total_pages):
            page = pdf_doc[idx]
            extracted = page.get_text("text").strip()
            if extracted:
                page_texts.append(f"--- Page {idx + 1} ---\n{extracted}")

        pdf_doc.close()

        full_text = "\n\n".join(page_texts)
        if not full_text.strip():
            raise EmptyDocumentError("The PDF document contains no readable digital text.")

        return ExtractedDocument(
            text=full_text,
            page_count=total_pages,
            char_count=len(full_text),
            word_count=len(full_text.split()),
            file_type="application/pdf"
        )

    @classmethod
    def _extract_from_docx(cls, content: bytes) -> ExtractedDocument:
        """Extracts text from DOCX paragraphs and tables."""
        try:
            doc = docx.Document(io.BytesIO(content))
        except Exception as e:
            raise CorruptedFileError(f"Invalid or corrupted DOCX document: {str(e)}")

        parts: List[str] = []

        # Extract text from all paragraphs
        for p in doc.paragraphs:
            val = p.text.strip()
            if val:
                parts.append(val)

        # Extract text from tables
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(dict.fromkeys(cells)))

        full_text = "\n\n".join(parts)
        if not full_text.strip():
            raise EmptyDocumentError("The DOCX document contains no readable text.")

        return ExtractedDocument(
            text=full_text,
            page_count=1,
            char_count=len(full_text),
            word_count=len(full_text.split()),
            file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    @classmethod
    def _extract_from_doc(cls, content: bytes) -> ExtractedDocument:
        """Extracts text from legacy binary DOC files via RTF or OLE Compound File streams."""
        extracted = ""

        # Check for Rich Text Format (RTF)
        if content.startswith(b"{\\rtf"):
            extracted = cls._extract_from_rtf(content)
        # Check for OLE compound binary document
        elif olefile.isOleFile(io.BytesIO(content)):
            try:
                with olefile.OleFileIO(io.BytesIO(content)) as ole:
                    if ole.exists("WordDocument"):
                        stream = ole.openstream("WordDocument").read()
                        extracted = cls._extract_printable_strings(stream)
            except Exception as e:
                logger.warning(f"OleFile parsing warning: {e}")

        # Fallback for binary text streams
        if not extracted:
            extracted = cls._extract_printable_strings(content)

        if not extracted.strip():
            raise EmptyDocumentError("No readable text found in this DOC file.")

        return ExtractedDocument(
            text=extracted,
            page_count=1,
            char_count=len(extracted),
            word_count=len(extracted.split()),
            file_type="application/msword"
        )

    @classmethod
    def _extract_from_txt(cls, content: bytes) -> ExtractedDocument:
        """Extracts text directly from plain text files."""
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                text = content.decode(enc)
                if text.strip():
                    return ExtractedDocument(
                        text=text.strip(),
                        page_count=1,
                        char_count=len(text),
                        word_count=len(text.split()),
                        file_type="text/plain"
                    )
            except UnicodeDecodeError:
                continue

        raise CorruptedFileError("Failed to decode text file. Unsupported character encoding.")

    @staticmethod
    def _extract_from_rtf(content: bytes) -> str:
        """Decodes RTF and removes control commands."""
        try:
            text = content.decode("latin-1", errors="ignore")
            text = re.sub(r'\\([a-z]{1,32})(-?\d+)? ?', ' ', text)
            text = re.sub(r'[\{\}]', '', text)
            return text.strip()
        except Exception:
            return ""

    @staticmethod
    def _extract_printable_strings(stream: bytes) -> str:
        """Extracts readable ASCII and UTF-16LE text runs from binary streams."""
        lines = []

        # ASCII character runs (at least 5 printable characters)
        ascii_runs = re.findall(b'[\x20-\x7E\t\r\n]{5,}', stream)
        for run in ascii_runs:
            try:
                decoded = run.decode('ascii', errors='ignore').strip()
                if len(decoded) > 5 and not decoded.startswith('\x00'):
                    lines.append(decoded)
            except Exception:
                continue

        # UTF-16LE character runs (common in WordDocument streams)
        utf16_runs = re.findall(b'(?:[\x20-\x7E]\x00){4,}', stream)
        for run in utf16_runs:
            try:
                decoded = run.decode('utf-16le', errors='ignore').strip()
                if len(decoded) > 4:
                    lines.append(decoded)
            except Exception:
                continue

        return "\n".join(lines)

    @staticmethod
    def _clean_text(raw_text: str) -> str:
        """
        Cleans extracted text without breaking sentences or words.
        Normalizes line endings and removes non-printable noise.
        """
        if not raw_text:
            return ""

        # Normalize line endings
        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

        # Strip non-printable control characters
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

        # Collapse excess empty lines (max 2)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Collapse excessive inline spaces
        text = re.sub(r'[ \t]{2,}', ' ', text)

        return text.strip()
