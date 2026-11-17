import json
import logging
import time
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.file_service import (
    FileService,
    FileValidationError,
    FileSizeExceededError,
    UnsupportedFileTypeError,
    CorruptedFileError,
    EmptyDocumentError,
)
from app.services.text_extractor import TextExtractorService
from app.services.summary_generator import (
    SummaryGeneratorService,
    SummaryResult,
    AIServiceError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Correspondence Summary"])


# Pydantic Schemas for API Documentation & Response Validation
class SummaryDetailResponse(BaseModel):
    document_summary: str
    main_purpose: str
    key_highlights: List[str]


class ProcessDocumentResponse(BaseModel):
    success: bool
    filename: str
    file_size_bytes: int
    file_type: str
    page_count: int
    char_count: int
    word_count: int
    processing_time_seconds: float
    summary: SummaryDetailResponse
    warnings: List[str] = []


class DownloadRequest(BaseModel):
    filename: str = Field(default="summary")
    format: str = Field(default="txt", pattern="^(txt|doc|pdf|json)$")
    summary: SummaryDetailResponse
    metadata: Optional[Dict[str, Any]] = None


@router.post(
    "/upload",
    response_model=ProcessDocumentResponse,
    summary="Upload and summarize correspondence document",
    description="Validates file, extracts digital text, calls NVIDIA AI model, and returns clear summary."
)
async def upload_document(file: UploadFile = File(...)):
    """
    Primary processing pipeline:
    1. Validates file format, size, and magic bytes.
    2. Extracts digital text.
    3. Invokes NVIDIA Nemotron model to generate clear executive summary.
    4. Returns summary with processing metrics.
    """
    start_time = time.time()
    logger.info(f"Received upload request for: {file.filename}")

    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read upload stream: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read the uploaded file data."
        )

    # 1. Validation
    try:
        sanitized_name, ext = FileService.validate_file(file.filename or "", content)
    except UnsupportedFileTypeError as e:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=e.message)
    except FileSizeExceededError as e:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=e.message)
    except (CorruptedFileError, EmptyDocumentError, FileValidationError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

    # 2. Text Extraction
    try:
        extracted = TextExtractorService.extract_text(content, ext, sanitized_name)
    except EmptyDocumentError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message)
    except CorruptedFileError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except Exception as e:
        logger.error(f"Extraction error for {sanitized_name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document text extraction failed: {str(e)}"
        )

    # 3. AI Summarization via NVIDIA Model
    metadata_info = f"Pages: {extracted.page_count}"
    try:
        summary_result = await SummaryGeneratorService.generate_summary(
            document_text=extracted.text,
            filename=sanitized_name,
            metadata_info=metadata_info
        )
    except AIServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"AI summarization failure: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI Summarization service error: {str(e)}"
        )

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"Processed {sanitized_name} in {elapsed}s")

    return ProcessDocumentResponse(
        success=True,
        filename=sanitized_name,
        file_size_bytes=len(content),
        file_type=ext,
        page_count=extracted.page_count,
        char_count=extracted.char_count,
        word_count=extracted.word_count,
        processing_time_seconds=elapsed,
        summary=SummaryDetailResponse(
            document_summary=summary_result.document_summary,
            main_purpose=summary_result.main_purpose,
            key_highlights=summary_result.key_highlights,
        ),
        warnings=extracted.warnings
    )


@router.post(
    "/download",
    summary="Download formatted summary file",
    description="Exports summary as executive text (.txt), Word document (.doc), or structured JSON (.json)."
)
async def download_summary(payload: DownloadRequest):
    """Generates a downloadable file containing the structured summary."""
    base_name = payload.filename.rsplit(".", 1)[0]
    summary_obj = SummaryResult(
        document_summary=payload.summary.document_summary,
        main_purpose=payload.summary.main_purpose,
        key_highlights=payload.summary.key_highlights
    )

    fmt = payload.format.lower()
    if fmt == "pdf":
        content = summary_obj.to_pdf(filename=payload.filename, metadata=payload.metadata)
        media_type = "application/pdf"
        download_name = f"{base_name}_summary.pdf"
    elif fmt == "doc":
        content = summary_obj.to_word_doc(filename=payload.filename, metadata=payload.metadata)
        media_type = "application/msword; charset=utf-8"
        download_name = f"{base_name}_summary.doc"
    elif fmt == "json":
        data = {
            "filename": payload.filename,
            "metadata": payload.metadata or {},
            "summary": summary_obj.model_dump()
        }
        content = json.dumps(data, indent=2, ensure_ascii=False)
        media_type = "application/json; charset=utf-8"
        download_name = f"{base_name}_summary.json"
    else:  # txt default
        content = summary_obj.to_executive_text(filename=payload.filename, metadata=payload.metadata)
        media_type = "text/plain; charset=utf-8"
        download_name = f"{base_name}_summary.txt"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'}
    )


@router.get(
    "/health",
    summary="Health check and configuration inspection",
    description="Reports status of NVIDIA model configuration and allowed document formats."
)
async def health_check():
    """Returns application health and configuration readiness."""
    has_api_key = bool(settings.NVIDIA_API_KEY and len(settings.NVIDIA_API_KEY.strip()) > 5)

    return {
        "status": "healthy",
        "app_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "ai_model": {
            "model_id": settings.NVIDIA_MODEL,
            "api_key_configured": has_api_key,
            "base_url": settings.NVIDIA_BASE_URL
        },
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
        "allowed_formats": list(sorted(settings.ALLOWED_EXTENSIONS))
    }
