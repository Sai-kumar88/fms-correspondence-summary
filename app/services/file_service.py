import re
from pathlib import Path
from typing import Tuple
from app.core.config import settings


class FileValidationError(Exception):
    """Base exception for file validation errors."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class FileSizeExceededError(FileValidationError):
    """Raised when file size exceeds the configured maximum allowed limit."""
    pass


class UnsupportedFileTypeError(FileValidationError):
    """Raised when the uploaded file extension is not supported."""
    pass


class CorruptedFileError(FileValidationError):
    """Raised when file magic bytes or internal structure indicate corruption."""
    pass


class EmptyDocumentError(FileValidationError):
    """Raised when the uploaded file contains 0 bytes or no extractable text."""
    pass


# Magic bytes signatures for supported document formats (prevents extension spoofing)
FILE_SIGNATURES = {
    ".pdf": [b"%PDF-"],
    ".docx": [b"PK\x03\x04"],  # Standard ZIP container used by DOCX
    ".doc": [
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",  # OLE compound binary format
        b"{\\rtf",                             # Rich Text Format (RTF)
        b"<\\?xml",                            # Word XML document
    ],
}


class FileService:
    """
    Validates file properties, enforces size limits, prevents directory traversal,
    and verifies binary magic bytes before text extraction.
    """

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitizes input filename to prevent directory traversal or unsafe characters."""
        if not filename:
            return "unnamed_document"
        clean = Path(filename).name
        clean = re.sub(r'[^a-zA-Z0-9_.-]', '_', clean)
        return clean or "document"

    @classmethod
    def validate_file(cls, filename: str, content: bytes) -> Tuple[str, str]:
        """
        Validates the uploaded file name, extension, size, and header signature.

        Returns:
            Tuple of (sanitized_filename, normalized_extension)

        Raises:
            FileValidationError: When any validation check fails.
        """
        if not filename or not filename.strip():
            raise FileValidationError("File name is missing or empty.")

        sanitized_name = cls.sanitize_filename(filename)
        ext = Path(sanitized_name).suffix.lower()

        # 1. Extension check
        if not ext or ext not in settings.ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(settings.ALLOWED_EXTENSIONS))
            raise UnsupportedFileTypeError(
                f"Unsupported file format '{ext}'. Allowed formats are: {allowed}"
            )

        # 2. Empty file check
        if not content or len(content) == 0:
            raise EmptyDocumentError("The uploaded file is empty (0 bytes).")

        # 3. File size check
        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if len(content) > max_bytes:
            size_mb = len(content) / (1024 * 1024)
            raise FileSizeExceededError(
                f"File size ({size_mb:.2f} MB) exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB} MB."
            )

        # 4. Binary signature verification (for binary formats)
        cls._verify_magic_bytes(ext, content)

        return sanitized_name, ext

    @staticmethod
    def _verify_magic_bytes(ext: str, content: bytes) -> None:
        """Verifies that file header bytes match the expected format for its extension."""
        signatures = FILE_SIGNATURES.get(ext)
        if not signatures:
            return

        header = content[:32]
        matched = any(header.startswith(sig) for sig in signatures)
        if not matched:
            raise CorruptedFileError(
                f"The file header does not match the expected format for '{ext}'. "
                "The file may be corrupted, truncated, or misnamed."
            )
