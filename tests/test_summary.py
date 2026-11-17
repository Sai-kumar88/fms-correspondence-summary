import pytest
from app.prompts.summary_prompt import build_user_prompt, SUMMARY_SYSTEM_PROMPT
from app.services.summary_generator import (
    SummaryGeneratorService,
    SummaryResult,
    AIServiceError,
    ensure_complete_sentence,
    split_into_complete_sentences
)


class TestSummaryGeneration:
    """Test suite for AI prompt engineering and structured summary generation."""

    def test_summary_prompt_structure(self):
        doc_text = "The committee convened on December 1, 2026 to discuss procurement."
        prompt = build_user_prompt(doc_text, filename="procurement.pdf", metadata_info="Pages: 1")
        assert "procurement.pdf" in prompt
        assert "Pages: 1" in prompt
        assert doc_text in prompt
        assert "DOCUMENT TEXT:" in prompt

    def test_parse_ai_valid_json_response(self):
        raw_ai_json = """
        {
          "document_summary": "The correspondence confirms approval for the procurement of cloud infrastructure assets. The budget of $50,000 was officially allocated.",
          "main_purpose": "The primary purpose of this correspondence is to notify the finance team of the procurement decision and allocate required capital.",
          "key_highlights": [
            "Total allocated budget is fifty thousand dollars.",
            "All vendors must be certified cloud service partners."
          ]
        }
        """
        result = SummaryGeneratorService._parse_ai_response(raw_ai_json)
        assert isinstance(result, SummaryResult)
        assert "cloud infrastructure" in result.document_summary
        assert result.main_purpose.startswith("The primary purpose")
        assert len(result.key_highlights) == 2

    def test_parse_markdown_fenced_json(self):
        fenced_json = """```json
        {
          "document_summary": "Official memo announcing the quarterly board meeting agenda.",
          "main_purpose": "The purpose is to announce the quarterly meeting schedule.",
          "key_highlights": ["Meeting will be held at headquarters on October 24."]
        }
        ```"""
        result = SummaryGeneratorService._parse_ai_response(fenced_json)
        assert isinstance(result, SummaryResult)
        assert "quarterly board meeting" in result.document_summary
        assert len(result.key_highlights) == 1

    def test_unbroken_sentence_sanitization(self):
        # Truncated sentence with dangling preposition at the end
        fragment = "The executive committee decided to approve the capital allocation and the"
        sanitized = ensure_complete_sentence(fragment)
        assert not sanitized.endswith("and the.")
        assert not sanitized.endswith("and.")
        assert sanitized.endswith(".")
        assert "capital allocation" in sanitized

        # Already complete sentence
        complete = "This is a complete sentence."
        assert ensure_complete_sentence(complete) == complete

    def test_abbreviation_aware_sentence_splitting(self):
        text = (
            "Project Authorization: Mr. John Smith has signed off on the agreement dated Nov. 10, 2026. "
            "Action required: deploy to production."
        )
        sentences = split_into_complete_sentences(text)
        assert len(sentences) == 2
        assert "Mr. John Smith" in sentences[0]
        assert "Nov. 10, 2026" in sentences[0]
        assert "deploy to production" in sentences[1]

    def test_executive_text_and_word_doc_export(self):
        summary = SummaryResult(
            document_summary="The team approved the migration timeline.",
            main_purpose="The primary purpose is to coordinate server migration.",
            key_highlights=["Phase 1 will start next month."]
        )
        
        # Test executive text
        txt = summary.to_executive_text("migration.pdf", {"pages": 2})
        assert "AI CORRESPONDENCE SUMMARY REPORT" in txt
        assert "1. DOCUMENT SUMMARY" in txt
        assert "2. MAIN PURPOSE" in txt
        assert "3. KEY HIGHLIGHTS" in txt
        assert "#" not in txt
        assert "**" not in txt

        # Test Word Document
        doc = summary.to_word_doc("migration.pdf", {"pages": 2})
        assert "<html" in doc
        assert "w:WordDocument" in doc
        assert "migration.pdf" in doc
        assert "migration timeline" in doc

        # Test PDF Document
        pdf_bytes = summary.to_pdf("migration.pdf", {"pages": 2})
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 500
