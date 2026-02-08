"""Unit tests for ExtractionService — verifies orchestration and idempotency."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.engines.claim_extractor import ClaimExtractor
from app.models.claim import ClaimModel
from app.models.transcript import TranscriptModel
from app.repositories.claim_repo import ClaimRepository
from app.repositories.transcript_repo import TranscriptRepository
from app.services.extraction_service import ExtractionService
from tests.fixtures import load_fixture


class FakeLLMClient:
    """Deterministic LLM client that returns fixture data."""

    def __init__(self, response: list[dict]):
        self._response = response
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def extract_claims(self, **kwargs) -> list[dict]:
        return self._response


# ── Tests ────────────────────────────────────────────────────────────────


class TestExtractionServiceOrchestration:
    """Test the extract_all() method that drives the pipeline."""

    def test_processes_unprocessed_transcripts(self, db, sample_company, sample_transcript):
        """Transcripts with no claims should be processed."""
        fixture = load_fixture("llm_extraction_AAPL_Q3_2024.json")
        fake_llm = FakeLLMClient(fixture)
        extractor = ClaimExtractor(fake_llm)
        transcript_repo = TranscriptRepository(db)
        claim_repo = ClaimRepository(db)

        service = ExtractionService(extractor, transcript_repo, claim_repo)
        result = service.extract_all()

        assert result["transcripts_processed"] == 1
        assert result["claims_extracted"] > 0
        assert result["errors"] == 0

    def test_skips_already_processed_transcripts(self, db, sample_company, sample_transcript, sample_claim):
        """Transcripts that already have claims should be skipped."""
        fixture = load_fixture("llm_extraction_AAPL_Q3_2024.json")
        fake_llm = FakeLLMClient(fixture)
        extractor = ClaimExtractor(fake_llm)
        transcript_repo = TranscriptRepository(db)
        claim_repo = ClaimRepository(db)

        service = ExtractionService(extractor, transcript_repo, claim_repo)
        result = service.extract_all()

        # sample_claim was already attached to sample_transcript,
        # so the transcript is NOT unprocessed
        assert result["transcripts_processed"] == 0
        assert result["claims_extracted"] == 0

    def test_claims_have_correct_transcript_id(self, db, sample_company, sample_transcript):
        """Extracted claims should be linked to the correct transcript."""
        fixture = load_fixture("llm_extraction_AAPL_Q3_2024.json")
        fake_llm = FakeLLMClient(fixture)
        extractor = ClaimExtractor(fake_llm)
        transcript_repo = TranscriptRepository(db)
        claim_repo = ClaimRepository(db)

        service = ExtractionService(extractor, transcript_repo, claim_repo)
        service.extract_all()

        claims = claim_repo.get_for_transcript(sample_transcript.id)
        assert len(claims) > 0
        for c in claims:
            assert c.transcript_id == sample_transcript.id

    def test_handles_extraction_error_gracefully(self, db, sample_company, sample_transcript):
        """If LLM extraction raises, the service should log and continue."""

        class FailingLLMClient:
            total_input_tokens = 0
            total_output_tokens = 0

            def extract_claims(self, **kwargs):
                raise RuntimeError("LLM service unavailable")

        extractor = ClaimExtractor(FailingLLMClient())
        transcript_repo = TranscriptRepository(db)
        claim_repo = ClaimRepository(db)

        service = ExtractionService(extractor, transcript_repo, claim_repo)
        result = service.extract_all()

        assert result["errors"] == 1
        assert result["transcripts_processed"] == 0

    def test_deduplication_applied(self, db, sample_company, sample_transcript):
        """Duplicate claims from the LLM should be deduplicated."""
        # Create two identical claims
        duplicate_response = [
            {
                "speaker": "CEO",
                "speaker_role": "CEO",
                "claim_text": "Revenue was $85.8 billion",
                "metric": "revenue",
                "metric_type": "absolute",
                "stated_value": 85.8,
                "unit": "usd_billions",
                "comparison_period": "none",
                "is_gaap": True,
                "confidence": 0.95,
            },
            {
                "speaker": "CFO",
                "speaker_role": "CFO",
                "claim_text": "Total revenue $85.8 billion",
                "metric": "revenue",
                "metric_type": "absolute",
                "stated_value": 85.8,
                "unit": "usd_billions",
                "comparison_period": "none",
                "is_gaap": True,
                "confidence": 0.95,
            },
        ]
        fake_llm = FakeLLMClient(duplicate_response)
        extractor = ClaimExtractor(fake_llm)
        transcript_repo = TranscriptRepository(db)
        claim_repo = ClaimRepository(db)

        service = ExtractionService(extractor, transcript_repo, claim_repo)
        result = service.extract_all()

        # Only 1 should survive deduplication (same metric, value, unit, period)
        assert result["claims_extracted"] == 1
