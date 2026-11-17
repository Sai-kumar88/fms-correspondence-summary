# FMS AI-Powered Correspondence Summary

A production-grade correspondence analysis and summarization system developed with **FastAPI**, **Python 3.11**, and the **NVIDIA AI Model (`nvidia/nemotron-3.5-lightning-30b-a3b`)**.

---

## Architecture Overview

```
                          [ Client / Web Browser ]
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │    FastAPI Application      │
                      │ (Security & File Validation)│
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │   Digital Text Extractor    │
                      │   (PyMuPDF, docx, olefile)  │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │ NVIDIA Nemotron 30B Model   │
                      │ (Concise Executive Summary, │
                      │  Strict Sentence Integrity) │
                      └──────────────┬──────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────────┐
                      │ Structured Summary Results  │
                      │ (Download: TXT / DOC / JSON)│
                      └─────────────────────────────┘
```

---

## Key Features

1. **Multi-Format Document Support**:
   - Supports **PDF, DOCX, DOC, and TXT** documents (Max 25MB).
   - Fast, direct digital text extraction without bulky external OCR dependencies.
   - Clean drag-and-drop web interface with live step-by-step progress tracking.

2. **Crystal-Clear Executive Summaries**:
   - Powered by `nvidia/nemotron-3.5-lightning-30b-a3b` via NVIDIA NIM API.
   - **Clutter-Free Output**: Displays an articulate, cohesive Executive Summary, Main Purpose, and Key Highlights.
   - **Zero Mid-Thought Truncation**: Strictly preserves complete, grammatically sound sentences.
   - **Zero Hallucination**: Preserves exact dates, numbers, figures, and facts verbatim.

3. **Enterprise Security & Reliability**:
   - **Magic Byte Verification**: Verifies true file header signatures to prevent extension spoofing.
   - **Path Traversal Protection**: Sanitizes filenames against directory traversal attacks.
   - **Enforced File Limits**: Configurable 25MB limit to prevent memory exhaustion.
   - **Docker Ready**: Lightweight, secure container with unprivileged user execution.

4. **Professional Summary Downloads**:
   - **PDF Document (.pdf)**: Beautifully styled executive PDF report with emerald branding.
   - **Word Document (.doc)**: Formatted Microsoft Word report with typography and cards.
   - **Text Document (.txt)**: Clean, formatted plain-text executive document.
   - **One-Click Copy**: Copies clean summary text directly to your clipboard.

---

## Project Structure

```
FMS_SUMMARY/
├── .env                       # Environment configuration and NVIDIA API key
├── .env.example               # Template environment file
├── .gitignore                 # Excludes virtual environments and cache
├── Dockerfile                 # Production lightweight Docker container
├── pytest.ini                 # Pytest runner configuration
├── README.md                  # System documentation
├── requirements.txt           # Production Python dependencies
├── app/
│   ├── main.py                # FastAPI entry point, exception handlers, and UI route
│   ├── api/
│   │   ├── __init__.py
│   │   └── upload.py          # API endpoints (/upload, /download, /health)
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py          # Pydantic BaseSettings loading from .env
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── summary_prompt.py  # Prompt engineering with strict JSON output format
│   ├── services/
│   │   ├── __init__.py
│   │   ├── file_service.py    # Magic bytes verification, size checks, and sanitization
│   │   ├── text_extractor.py  # Clean text extraction (PyMuPDF, docx, olefile, plain text)
│   │   └── summary_generator.py# NVIDIA NIM API client, response parser, and exporters
│   └── templates/
│       └── index.html         # Responsive frontend (Tailwind CSS, drag-and-drop, export)
└── tests/
    ├── test_extraction.py     # Extraction tests for PDF, DOCX, DOC, and TXT
    ├── test_summary.py        # Tests for prompt generation, anti-hallucination, and parsing
    └── test_upload.py         # HTTP endpoint tests (upload, error handling, downloads)
```

---

## Configuration (`.env`)

Create or edit your `.env` file in the root directory:

```env
# Application Settings
PROJECT_NAME="FMS AI Correspondence Summary"
ENVIRONMENT=development
DEBUG=false
HOST=127.0.0.1
PORT=8000
API_PREFIX=/api/v1

# NVIDIA AI Model Configuration
NVIDIA_API_KEY=your_nvidia_nim_api_key_here
NVIDIA_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_TIMEOUT_SECONDS=90.0
NVIDIA_MAX_RETRIES=3

# File Limits
MAX_FILE_SIZE_MB=25
```

> **Note**: To obtain an NVIDIA API Key, visit the [NVIDIA NIM Catalog](https://build.nvidia.com/). In development or test mode without an API key, the system provides a demonstration summary extracted from document facts.

---

## Getting Started

### 1. Prerequisites
- **Python 3.10+** (Python 3.11 recommended)
- Virtual environment (`venv`)

### 2. Setup Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the Development Server

To launch the server locally on Windows, macOS, or Linux:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

> **Important Note for Web Browsers**:
> Always navigate to **`http://127.0.0.1:8000`** or **`http://localhost:8000`**.
> *Do not type `http://0.0.0.0:8000` into your web browser*, as modern browsers on Windows reject `0.0.0.0` as an invalid destination address and will show `ERR_ADDRESS_INVALID`.

Open your browser to:
- **Interactive Web UI**: [http://127.0.0.1:8000](http://127.0.0.1:8000) or [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **System Health Check**: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

---

## Running with Docker

Build and run in a secure, lightweight Linux container:

```bash
# Build the Docker image
docker build -t fms-summary .

# Run the container
docker run -d -p 8000:8000 \
  -e NVIDIA_API_KEY="your_api_key" \
  --name fms-app fms-summary
```

Access the UI at `http://localhost:8000`.

---

## API Reference

### 1. Upload & Analyze Document
`POST /api/v1/upload` (multipart/form-data)

**Request**:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/upload" \
  -F "file=@sample_letter.pdf"
```

**Response (200 OK)**:
```json
{
  "success": true,
  "filename": "sample_letter.pdf",
  "file_size_bytes": 142050,
  "file_type": ".pdf",
  "page_count": 1,
  "char_count": 892,
  "word_count": 134,
  "processing_time_seconds": 1.25,
  "summary": {
    "document_summary": "This memorandum announces the finalized budget allocations for Fiscal Year 2027.",
    "main_purpose": "To communicate finalized budget allocations and specify submission deadlines.",
    "key_highlights": [
      "All department heads must submit operational expenditure revisions by December 5, 2026."
    ]
  },
  "warnings": []
}
```

### 2. Download Summary
`POST /api/v1/download` (application/json)

Formats: `"pdf"` (Executive PDF Report), `"doc"` (Microsoft Word), or `"txt"` (Text Document).

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/download" \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "memo.pdf",
    "format": "txt",
    "summary": {
      "document_summary": "Executive summary text...",
      "main_purpose": "Document purpose...",
      "key_highlights": ["Key takeaway..."]
    }
  }' \
  --output summary_report.txt
```

### 3. Health Check
`GET /api/v1/health`

```json
{
  "status": "healthy",
  "app_name": "FMS AI Correspondence Summary",
  "version": "1.0.0",
  "environment": "development",
  "ai_model": {
    "model_id": "nvidia/nemotron-3.5-lightning-30b-a3b",
    "api_key_configured": true,
    "base_url": "https://integrate.api.nvidia.com/v1"
  },
  "max_file_size_mb": 25,
  "allowed_formats": [".doc", ".docx", ".pdf", ".txt"]
}
```

---

## Running the Automated Test Suite

Run the full pytest suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

All 19 unit and integration tests run in ~2 seconds without external dependencies.

---

## Deployment to Vercel & Git

### 1. Push to GitHub / Git Remote

Initialize and push to your GitHub repository:

```bash
# Add your remote repository URL (replace with your repo link)
git remote add origin https://github.com/YOUR_USERNAME/FMS_SUMMARY.git

# Push the main branch
git push -u origin main
```

### 2. Deploy to Vercel

#### Method A: Via GitHub (Recommended)
1. Go to [vercel.com](https://vercel.com) and log in.
2. Click **Add New... > Project**.
3. Import your **`FMS_SUMMARY`** GitHub repository.
4. In the **Environment Variables** section, add:
   - **`NVIDIA_API_KEY`**: `your_actual_nvidia_nim_api_key`
   - **`NVIDIA_MODEL`**: `nvidia/nemotron-3.5-lightning-30b-a3b` *(optional, has default)*
5. Click **Deploy**. Vercel will install dependencies from `requirements.txt` and launch your serverless app.

#### Method B: Via Vercel CLI
```bash
# Install Vercel CLI globally
npm install -g vercel

# Deploy to preview
vercel

# Deploy to production
vercel --prod
```
When prompted, link your project and add `NVIDIA_API_KEY` in your Vercel Dashboard under **Settings > Environment Variables**.

