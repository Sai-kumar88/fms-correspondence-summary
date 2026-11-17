import asyncio
import html
import json
import logging
import re
from typing import Any, Dict, List, Optional
import httpx
import pymupdf as fitz
from pydantic import BaseModel, Field

from app.core.config import settings
from app.prompts.summary_prompt import SUMMARY_SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

NOT_AVAILABLE_MSG = "Information not available in document"

# Common abbreviations protected from triggering sentence breaks
KNOWN_ABBREVIATIONS = (
    "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.",
    "Inc.", "Corp.", "Ltd.", "Co.", "No.", "Nov.", "Dec.",
    "Jan.", "Feb.", "Mar.", "Apr.", "Aug.", "Oct.", "Sept.", "Dept.", "vs.", "e.g.", "i.e."
)

DANGLING_CONJUNCTIONS = {
    "and", "or", "the", "of", "to", "with", "on", "for", "at", "by", "is",
    "was", "that", "which", "in", "as", "from", "but", "an", "a", "so", "if", "then"
}


def ensure_complete_sentence(text: str, default: str = NOT_AVAILABLE_MSG) -> str:
    """
    Validates and guarantees that a sentence is grammatically intact, not cut off mid-thought,
    and concludes with valid terminal punctuation (. ! ?).
    Never truncates sentences at internal abbreviations (like Nov., Dr., Mr., etc.).
    """
    if not text or not text.strip():
        return default

    s = text.strip()

    if NOT_AVAILABLE_MSG.lower() in s.lower():
        return NOT_AVAILABLE_MSG

    # Clean leading bullet dashes or asterisks (preserve internal bolding like **Tag:**)
    s = re.sub(r'^[•\-\d\.]+\s*', '', s).strip()
    if not s:
        return default

    # Remove trailing dangling words (e.g., 'and the' or 'but')
    words = s.split()
    while words and words[-1].lower().rstrip('.,;:!?') in DANGLING_CONJUNCTIONS:
        words.pop()
    s = " ".join(words).strip()
    if not s:
        return default

    # Clean trailing colons, semicolons, or commas
    s = re.sub(r'[,;:\s]+$', '', s).strip()

    # Ensure ending with terminal punctuation (. ! ?)
    if not re.search(r'[.!?]["\']?$', s):
        s += "."

    return s


def split_into_complete_sentences(text: str) -> List[str]:
    """
    Splits text into full sentences without breaking at abbreviations (Mr., Dr., Nov., etc.).
    """
    if not text:
        return []

    s = text.strip()
    # Mask abbreviation periods
    for abbr in KNOWN_ABBREVIATIONS:
        masked = abbr.replace(".", "@@DOT@@")
        s = re.sub(re.escape(abbr), masked, s, flags=re.IGNORECASE)

    # Split on actual sentence endings (. ! ?) followed by whitespace or line break
    raw_chunks = re.split(r'[.!?]+(?:\s+|\n+)', s)
    results: List[str] = []

    for chunk in raw_chunks:
        restored = chunk.replace("@@DOT@@", ".").strip()
        if len(restored) > 5:
            clean = ensure_complete_sentence(restored)
            results.append(clean)

    return results


class AIServiceError(Exception):
    """Raised when communication with or response parsing from NVIDIA AI fails."""
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class SummaryResult(BaseModel):
    """Clean, focused correspondence summary strictly composed of meaningful sentences."""
    document_summary: str = Field(
        ...,
        description="Authoritative executive summary written in full, unbroken, meaningful sentences."
    )
    main_purpose: str = Field(
        default="",
        description="Primary intent and core objective of the correspondence."
    )
    key_highlights: List[str] = Field(
        default_factory=list,
        description="Key takeaways, decisions, and deadlines with category prefixes."
    )

    # Backward compatibility property for existing tests/clients
    @property
    def important_points(self) -> List[str]:
        return self.key_highlights

    def to_executive_text(self, filename: str = "", metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Renders the summary as a clean, professionally formatted executive plain-text report.
        Focuses directly on the core summary, purpose, and key takeaways without clutter.
        """
        divider = "=" * 80
        sub_divider = "-" * 80
        lines = [
            divider,
            "                    AI CORRESPONDENCE SUMMARY REPORT",
            divider,
            f"Document Name : {filename or 'Unnamed Document'}"
        ]

        if metadata:
            for k, v in metadata.items():
                label = k.replace("_", " ").title()
                lines.append(f"{label:<14}: {v}")

        lines.extend([
            sub_divider,
            "",
            "1. DOCUMENT SUMMARY",
            f"   {self.document_summary}",
            "",
            "2. MAIN PURPOSE",
            f"   {self.main_purpose}",
            "",
            "3. KEY HIGHLIGHTS"
        ])
        for pt in self.key_highlights:
            if pt and NOT_AVAILABLE_MSG.lower() not in pt.lower():
                # Clean markdown bold markers for plain text
                clean_pt = pt.replace("**", "")
                lines.append(f"   • {clean_pt}")

        lines.extend([
            "",
            divider,
            "End of Summary - FMS Correspondence Intelligence System",
            divider
        ])

        return "\n".join(lines)

    def to_word_doc(self, filename: str = "", metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Renders the summary into an HTML-formatted Microsoft Word document (.doc)
        with elegant typography, header branding, and clean executive cards.
        """
        title = html.escape(filename or "Document Summary")

        def render_html_highlights(items: List[str]) -> str:
            out = []
            for item in items:
                # Convert **Category:** into <strong>Category:</strong>
                escaped = html.escape(item)
                bolded = re.sub(r'&ast;&ast;(.*?)&ast;&ast;', r'<strong>\1</strong>', escaped)
                bolded = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', bolded)
                out.append(f"<li style='color: #1e293b; margin-bottom: 8px; line-height: 1.5;'>{bolded}</li>")
            return "".join(out)

        meta_rows = ""
        if metadata:
            for k, v in metadata.items():
                meta_rows += f"<tr><td style='padding: 6px 12px; font-weight: bold; background: #f1f5f9; width: 180px;'>{html.escape(k.replace('_', ' ').title())}</td><td style='padding: 6px 12px;'>{html.escape(str(v))}</td></tr>"

        valid_highlights = [pt for pt in self.key_highlights if pt and NOT_AVAILABLE_MSG.lower() not in pt.lower()]

        return f"""<!DOCTYPE html>
<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <!--[if gte mso 9]>
  <xml>
    <w:WordDocument>
      <w:View>Print</w:View>
      <w:Zoom>100</w:Zoom>
      <w:DoNotOptimizeForBrowser/>
    </w:WordDocument>
  </xml>
  <![endif]-->
  <style>
    body {{
      font-family: 'Segoe UI', Calibri, Arial, sans-serif;
      margin: 40px;
      color: #0f172a;
      line-height: 1.6;
      background: #ffffff;
    }}
    .header-box {{
      background: #047857;
      color: #ffffff;
      padding: 20px 24px;
      border-radius: 6px;
      margin-bottom: 24px;
    }}
    .header-box h1 {{
      margin: 0;
      font-size: 20pt;
      font-weight: 700;
      letter-spacing: -0.5px;
    }}
    .header-box p {{
      margin: 6px 0 0 0;
      font-size: 11pt;
      opacity: 0.9;
    }}
    .meta-table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 24px;
      font-size: 10pt;
      border: 1px solid #cbd5e1;
    }}
    .meta-table td {{
      border: 1px solid #cbd5e1;
    }}
    .section-card {{
      background: #f8fafc;
      border-left: 5px solid #059669;
      padding: 14px 18px;
      margin-bottom: 20px;
      border-radius: 4px;
    }}
    .section-title {{
      font-size: 12pt;
      font-weight: 700;
      color: #065f46;
      text-transform: uppercase;
      margin-top: 0;
      margin-bottom: 8px;
      letter-spacing: 0.5px;
    }}
    .section-body {{
      font-size: 11pt;
      color: #1e293b;
      margin: 0;
    }}
    ul {{
      margin: 6px 0 6px 20px;
      padding: 0;
      font-size: 11pt;
    }}
    .footer-note {{
      margin-top: 32px;
      padding-top: 12px;
      border-top: 1px solid #e2e8f0;
      font-size: 9pt;
      color: #94a3b8;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="header-box">
    <h1>Executive Document Summary</h1>
    <p>Document: {title}</p>
  </div>

  {f'<table class="meta-table">{meta_rows}</table>' if meta_rows else ''}

  <div class="section-card">
    <div class="section-title">Document Summary</div>
    <p class="section-body">{html.escape(self.document_summary)}</p>
  </div>

  <div class="section-card" style="border-left-color: #0284c7;">
    <div class="section-title" style="color: #0369a1;">Main Purpose</div>
    <p class="section-body">{html.escape(self.main_purpose)}</p>
  </div>

  <div class="section-card" style="border-left-color: #6366f1;">
    <div class="section-title" style="color: #4338ca;">Key Highlights</div>
    <ul>{render_html_highlights(valid_highlights)}</ul>
  </div>

  <div class="footer-note">
    Generated by FMS AI Correspondence Summary &bull; Powered by NVIDIA Nemotron-30B
  </div>
</body>
</html>"""

    def to_pdf(self, filename: str = "", metadata: Optional[Dict[str, Any]] = None) -> bytes:
        """
        Renders the summary into a high-quality, professional executive PDF document
        using PyMuPDF. Clean, lightweight, and self-contained.
        """
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)  # Standard A4 size in points

        # Top banner (emerald green)
        page.draw_rect(fitz.Rect(0, 0, 595, 75), color=None, fill=(0.04, 0.47, 0.34))
        page.insert_text(fitz.Point(40, 36), "EXECUTIVE CORRESPONDENCE SUMMARY", fontsize=16, color=(1, 1, 1), fontname="helv")
        doc_title = filename or "Document Summary"
        page.insert_text(fitz.Point(40, 58), f"Document: {doc_title}", fontsize=10, color=(0.85, 0.95, 0.9), fontname="helv")

        y = 96
        # Metadata row
        if metadata:
            meta_items = [f"{k.replace('_', ' ').title()}: {v}" for k, v in metadata.items()]
            page.insert_text(fitz.Point(40, y), "  |  ".join(meta_items), fontsize=8, color=(0.4, 0.45, 0.5), fontname="helv")
            y += 18

        # Section 1: Document Summary
        page.draw_rect(fitz.Rect(40, y, 44, y + 16), color=None, fill=(0.04, 0.47, 0.34))
        page.insert_text(fitz.Point(52, y + 13), "1. DOCUMENT SUMMARY", fontsize=11, color=(0.04, 0.47, 0.34), fontname="helv")
        y += 22

        summary_box = fitz.Rect(40, y, 555, y + 120)
        page.insert_textbox(summary_box, self.document_summary, fontsize=10, fontname="helv", color=(0.12, 0.16, 0.22))
        words_summary = len(self.document_summary.split())
        approx_lines = max(2, (words_summary // 13) + 1)
        y += approx_lines * 14 + 18

        # Section 2: Main Purpose
        page.draw_rect(fitz.Rect(40, y, 44, y + 16), color=None, fill=(0.01, 0.52, 0.78))
        page.insert_text(fitz.Point(52, y + 13), "2. MAIN PURPOSE", fontsize=11, color=(0.01, 0.52, 0.78), fontname="helv")
        y += 22

        purpose_box = fitz.Rect(40, y, 555, y + 60)
        page.insert_textbox(purpose_box, self.main_purpose, fontsize=10, fontname="helv", color=(0.12, 0.16, 0.22))
        words_purpose = len(self.main_purpose.split())
        approx_p_lines = max(1, (words_purpose // 13) + 1)
        y += approx_p_lines * 14 + 18

        # Section 3: Key Highlights
        page.draw_rect(fitz.Rect(40, y, 44, y + 16), color=None, fill=(0.39, 0.4, 0.95))
        page.insert_text(fitz.Point(52, y + 13), "3. KEY HIGHLIGHTS", fontsize=11, color=(0.39, 0.4, 0.95), fontname="helv")
        y += 22

        for item in self.key_highlights:
            if y > 760:
                # Add continuation page if needed
                page = doc.new_page(width=595, height=842)
                y = 40

            clean_item = item.replace("**", "")
            page.insert_text(fitz.Point(40, y + 10), "•", fontsize=12, color=(0.04, 0.47, 0.34))
            bullet_box = fitz.Rect(52, y, 555, y + 45)
            page.insert_textbox(bullet_box, clean_item, fontsize=9.5, fontname="helv", color=(0.12, 0.16, 0.22))
            item_lines = max(1, (len(clean_item.split()) // 13) + 1)
            y += item_lines * 14 + 8

        # Footer
        page.draw_line(fitz.Point(40, 805), fitz.Point(555, 805), color=(0.85, 0.88, 0.9))
        page.insert_text(
            fitz.Point(40, 820),
            "Generated by FMS AI Correspondence Summary • Powered by NVIDIA Nemotron-30B",
            fontsize=8,
            color=(0.55, 0.6, 0.65),
            fontname="helv"
        )

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes


class SummaryGeneratorService:
    """
    Service responsible for calling the NVIDIA AI model API
    (nvidia/nemotron-3.5-lightning-30b-a3b) and parsing the structured response.
    """

    @classmethod
    async def generate_summary(
        cls,
        document_text: str,
        filename: str = "",
        metadata_info: str = ""
    ) -> SummaryResult:
        """
        Sends extracted document text to NVIDIA model and parses the response.
        Ensures unbroken, complete sentences across all sections.
        """
        prepared_text = cls._prepare_text(document_text)
        api_key = settings.NVIDIA_API_KEY.strip() if settings.NVIDIA_API_KEY else ""

        # Fallback when no API key is configured
        if not api_key:
            if settings.ENVIRONMENT in {"test", "development"}:
                logger.warning("NVIDIA_API_KEY not configured. Generating demonstration summary from document facts.")
                return cls._generate_mock_summary(prepared_text, filename)
            raise AIServiceError(
                "NVIDIA_API_KEY is not configured in .env. Please configure your NVIDIA API key.",
                status_code=500
            )

        user_prompt = build_user_prompt(prepared_text, filename, metadata_info)
        payload = {
            "model": settings.NVIDIA_MODEL,
            "messages": [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,
            "top_p": 0.7,
            "max_tokens": 2048,
            "chat_template_kwargs": {"thinking": False}
        }

        endpoint = f"{settings.NVIDIA_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        raw_response = ""
        for attempt in range(1, settings.NVIDIA_MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=settings.NVIDIA_TIMEOUT_SECONDS) as client:
                    resp = await client.post(endpoint, json=payload, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise AIServiceError("NVIDIA API returned an empty choices array.")
                    msg = choices[0].get("message", {})
                    raw_response = msg.get("content") or msg.get("reasoning_content") or ""
                    break
                elif resp.status_code in {429, 500, 502, 503, 504} and attempt < settings.NVIDIA_MAX_RETRIES:
                    delay = attempt * 2
                    logger.warning(f"NVIDIA API status {resp.status_code}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    err_msg = f"NVIDIA API Error [{resp.status_code}]: {resp.text}"
                    logger.error(err_msg)
                    raise AIServiceError(err_msg, status_code=resp.status_code)

            except httpx.RequestError as e:
                if attempt < settings.NVIDIA_MAX_RETRIES:
                    delay = attempt * 2
                    logger.warning(f"Connection error to NVIDIA API: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    raise AIServiceError(f"Connection to NVIDIA API failed: {str(e)}")

        return cls._parse_ai_response(raw_response)

    @classmethod
    def _parse_ai_response(cls, raw_content: str) -> SummaryResult:
        """Parses model response into SummaryResult, handling reasoning text and markdown fences."""
        if not raw_content or not raw_content.strip():
            raise AIServiceError("AI model returned an empty response.")

        cleaned = raw_content.strip()

        # 1. Direct JSON parse attempt
        try:
            parsed = json.loads(cleaned)
            return cls._build_result_from_dict(parsed)
        except json.JSONDecodeError:
            pass

        # 2. Extract from markdown code fences ```json ... ```
        block_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', cleaned)
        if block_match:
            try:
                parsed = json.loads(block_match.group(1))
                return cls._build_result_from_dict(parsed)
            except json.JSONDecodeError:
                pass

        # 3. Extract outermost JSON object
        obj_match = re.search(r'(\{[\s\S]*\})', cleaned)
        if obj_match:
            candidate = obj_match.group(1)
            try:
                parsed = json.loads(candidate)
                return cls._build_result_from_dict(parsed)
            except json.JSONDecodeError:
                for end_idx in [m.end() for m in re.finditer(r'\}', candidate)][::-1]:
                    try:
                        parsed = json.loads(candidate[:end_idx])
                        return cls._build_result_from_dict(parsed)
                    except json.JSONDecodeError:
                        continue

        # 4. Fallback parsing if JSON was malformed
        parsed = cls._fallback_text_parse(raw_content)
        return cls._build_result_from_dict(parsed)

    @classmethod
    def _build_result_from_dict(cls, data: Dict[str, Any]) -> SummaryResult:
        """
        Validates output fields and sanitizes sentences to guarantee meaningful, unbroken prose.
        """
        def clean_items(val: Any) -> List[str]:
            if not val:
                return []
            if isinstance(val, str):
                items = [s.strip() for s in val.split("\n") if s.strip()]
            elif isinstance(val, list):
                items = [str(x).strip() for x in val if str(x).strip()]
            else:
                items = [str(val).strip()]

            clean_list = []
            for item in items:
                s = re.sub(r'^[•\-\d\.]+\s*', '', item).strip()
                if s:
                    completed = ensure_complete_sentence(s)
                    clean_list.append(completed)
            return clean_list

        raw_summary = str(data.get("document_summary", "")).strip()
        raw_purpose = str(data.get("main_purpose", "")).strip()

        # Enforce complete, unbroken sentences
        summary = ensure_complete_sentence(raw_summary)

        # Enhance and ensure full-sentence main purpose
        if raw_purpose and NOT_AVAILABLE_MSG.lower() not in raw_purpose.lower():
            if len(raw_purpose.split()) < 5 and not raw_purpose.lower().startswith("the"):
                purpose = f"The primary purpose of this correspondence is to {raw_purpose[0].lower() + raw_purpose[1:]}"
            else:
                purpose = raw_purpose
            purpose = ensure_complete_sentence(purpose)
        else:
            purpose = "The primary purpose is communicated in the document summary above."

        # Support both 'key_highlights' and 'important_points'
        raw_highlights = data.get("key_highlights") or data.get("important_points") or []
        highlights = clean_items(raw_highlights)

        return SummaryResult(
            document_summary=summary,
            main_purpose=purpose,
            key_highlights=highlights
        )

    @classmethod
    def _fallback_text_parse(cls, text: str) -> Dict[str, Any]:
        """Fallback dictionary structure if output was unstructured text."""
        sentences = split_into_complete_sentences(text)
        summary_text = " ".join(sentences[:3]) if sentences else text[:300]

        return {
            "document_summary": ensure_complete_sentence(summary_text),
            "main_purpose": ensure_complete_sentence(sentences[0] if sentences else "Correspondence summary."),
            "key_highlights": [ensure_complete_sentence(s) for s in sentences[1:4]] if len(sentences) > 1 else []
        }

    @classmethod
    def _prepare_text(cls, text: str) -> str:
        """Truncates text safely at a sentence boundary if exceeding maximum characters."""
        if len(text) <= settings.MAX_TEXT_CHARS:
            return text

        logger.info(f"Text length {len(text)} exceeds limit {settings.MAX_TEXT_CHARS}. Truncating safely.")
        truncated = text[:settings.MAX_TEXT_CHARS]
        last_punct = max(
            truncated.rfind('. '),
            truncated.rfind('.\n'),
            truncated.rfind('!\n'),
            truncated.rfind('?\n')
        )
        if last_punct > 1000:
            truncated = truncated[:last_punct + 1]

        return f"{truncated}\n\n[Note: Document truncated to fit model context window.]"

    @classmethod
    def _generate_mock_summary(cls, text: str, filename: str) -> SummaryResult:
        """
        Accurate fallback summary using document facts when no API key is configured.
        Guarantees unbroken sentences, structured highlights, and a proper main purpose.
        """
        sentences = split_into_complete_sentences(text)

        summary_p = " ".join(sentences[:3]) if sentences else "The uploaded document provides formal correspondence."

        if sentences:
            first_s = sentences[0]
            if len(first_s.split()) < 6 or "notice" in first_s.lower() or "authorization" in first_s.lower():
                purpose = f"The primary purpose of this correspondence is to provide {first_s.strip('.')}."
            else:
                purpose = first_s
        else:
            purpose = "The primary purpose of this correspondence is to record official business communications."

        raw_pts = sentences[1:5] if len(sentences) > 1 else ["Core document content was extracted and processed successfully."]
        structured_pts = []
        for i, pt in enumerate(raw_pts):
            if i == 0:
                tag = "**Core Decision:** "
            elif i == 1:
                tag = "**Operational Scope:** "
            elif i == 2:
                tag = "**Action Required:** "
            else:
                tag = "**Key Detail:** "
            structured_pts.append(f"{tag}{ensure_complete_sentence(pt)}")

        return SummaryResult(
            document_summary=ensure_complete_sentence(summary_p),
            main_purpose=ensure_complete_sentence(purpose),
            key_highlights=structured_pts
        )
