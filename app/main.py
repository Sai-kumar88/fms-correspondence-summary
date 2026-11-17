import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.upload import router as upload_router
from app.core.config import settings
from app.services.file_service import (
    FileValidationError,
    FileSizeExceededError,
    UnsupportedFileTypeError,
    CorruptedFileError,
    EmptyDocumentError,
)
from app.services.summary_generator import AIServiceError

# Setup structured logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("fms_summary")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    logger.info(f"NVIDIA Model: {settings.NVIDIA_MODEL}")
    logger.info(f"Max file upload size: {settings.MAX_FILE_SIZE_MB} MB")
    logger.info(f"Allowed formats: {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}")
    yield
    logger.info("Shutting down FMS Summary application.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Enterprise AI-Powered Correspondence Summarization System using NVIDIA Nemotron and FastAPI.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception Handlers
@app.exception_handler(FileValidationError)
async def file_validation_handler(request: Request, exc: FileValidationError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "detail": exc.message, "error_type": exc.__class__.__name__}
    )


@app.exception_handler(AIServiceError)
async def ai_service_handler(request: Request, exc: AIServiceError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "detail": exc.message, "error_type": "AIServiceError"}
    )


# Mount API Router (mount at standard prefix and Vercel serverless prefix)
app.include_router(upload_router, prefix=settings.API_PREFIX)
app.include_router(upload_router, prefix=f"/api{settings.API_PREFIX}", include_in_schema=False)


# Root UI Route (mapped to both root and Vercel serverless entry aliases)
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/api", response_class=HTMLResponse, include_in_schema=False)
@app.get("/api/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/api/index", response_class=HTMLResponse, include_in_schema=False)
@app.get("/api/index.py", response_class=HTMLResponse, include_in_schema=False)
async def get_index():
    """Serves the main application user interface."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if not template_path.exists():
        template_path = Path.cwd() / "app" / "templates" / "index.html"
    if not template_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="UI template not found."
        )
    return HTMLResponse(content=template_path.read_text(encoding="utf-8"))


# Global Health Route
@app.get("/health", tags=["System"])
@app.get("/api/health", tags=["System"], include_in_schema=False)
async def root_health():
    """System health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }
