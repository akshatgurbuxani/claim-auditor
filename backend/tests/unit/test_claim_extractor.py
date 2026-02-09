"""Unit tests for ClaimExtractor — validate parsing, normalization, dedup."""

import pytest

from app.engines.claim_extractor import ClaimExtractor
from app.domain.metrics import normalize_metric_name
from app.clients.llm_client import LLMClient


class FakeLLMClient:
    """Deterministic stand-in for the real LLM client."""

    def __init__(self, response: list[dict]):
        self._response = response

    def extract_claims(self, **kwargs) -> list[dict]:
        return self._response


class TestNormalizeMetric:
    def test_common_aliases(self):
        assert normalize_metric_name("total revenue") == "revenue"
        assert normalize_metric_name("earnings per share") == "eps"
        assert normalize_metric_name("FCF") == "free_cash_flow"
        assert normalize_metric_name("op margin") == "operating_margin"
        assert normalize_metric_name("Net Revenue") == "revenue"
        assert normalize_metric_name("SG&A") == "selling_general_admin"

    def test_already_canonical(self):
        assert normalize_metric_name("revenue") == "revenue"
        assert normalize_metric_name("operating_income") == "operating_income"

    def test_unknown_passthrough(self):
        assert normalize_metric_name("subscriber_count") == "subscriber_count"


class TestDedup:
    def test_removes_exact_dupes(self):
        from app.schemas.claim import ClaimCreate, MetricType, ComparisonPeriod

        claims = [
            ClaimCreate(
                transcript_id=0, speaker="CEO", claim_text="rev grew 10%",
                metric="revenue", metric_type=MetricType.GROWTH_RATE,
                stated_value=10.0, unit="percent",
                comparison_period=ComparisonPeriod.YOY,
            ),
            ClaimCreate(
                transcript_id=0, speaker="CFO", claim_text="revenue up 10% yoy",
                metric="revenue", metric_type=MetricType.GROWTH_RATE,
                stated_value=10.0, unit="percent",
                comparison_period=ComparisonPeriod.YOY,
            ),
        ]
        result = ClaimExtractor._deduplicate(claims)
        assert len(result) == 1

    def test_keeps_different_metrics(self):
        from app.schemas.claim import ClaimCreate, MetricType, ComparisonPeriod

        claims = [
            ClaimCreate(
                transcript_id=0, speaker="CEO", claim_text="rev grew 10%",
                metric="revenue", metric_type=MetricType.GROWTH_RATE,
                stated_value=10.0, unit="percent",
                comparison_period=ComparisonPeriod.YOY,
            ),
            ClaimCreate(
                transcript_id=0, speaker="CEO", claim_text="EPS was $1.46",
                metric="eps", metric_type=MetricType.PER_SHARE,
                stated_value=1.46, unit="usd",
                comparison_period=ComparisonPeriod.NONE,
            ),
        ]
        result = ClaimExtractor._deduplicate(claims)
        assert len(result) == 2


class TestExtractEndToEnd:
    def test_valid_extraction(self):
        fake_response = [
            {
                "speaker": "Tim Cook, CEO",
                "speaker_role": "CEO",
                "claim_text": "Revenue grew approximately 10.7% year over year",
                "metric": "total revenue",
                "metric_type": "growth_rate",
                "stated_value": 10.7,
                "unit": "percent",
                "comparison_period": "year_over_year",
                "comparison_basis": "Q3 2025 vs Q3 2024",
                "is_gaap": True,
                "segment": None,
                "confidence": 0.95,
                "context_snippet": "Total revenue was up about 10.7 percent.",
            }
        ]
        extractor = ClaimExtractor(FakeLLMClient(fake_response))
        claims = extractor.extract("...", "AAPL", 3, 2025)

        assert len(claims) == 1
        assert claims[0].metric == "revenue"  # alias normalized
        assert claims[0].stated_value == 10.7

    def test_invalid_claim_skipped(self):
        """Malformed claims should be skipped, not crash."""
        fake_response = [
            {"speaker": "CEO"},  # missing required fields
            {
                "speaker": "CFO",
                "claim_text": "EPS was $1.46",
                "metric": "eps",
                "metric_type": "per_share",
                "stated_value": 1.46,
                "unit": "usd",
            },
        ]
        extractor = ClaimExtractor(FakeLLMClient(fake_response))
        claims = extractor.extract("...", "AAPL", 3, 2025)
        # At least the valid one should survive
        assert len(claims) >= 1


class TestLLMClientParsing:
    def test_parse_raw_json(self):
        text = '[{"speaker": "CEO", "metric": "revenue"}]'
        result = LLMClient._parse_claims_response(text)
        assert len(result) == 1

    def test_parse_markdown_fenced(self):
        text = '```json\n[{"speaker": "CEO"}]\n```'
        result = LLMClient._parse_claims_response(text)
        assert len(result) == 1

    def test_parse_json_in_prose(self):
        text = 'Here are the claims:\n[{"speaker": "CEO"}]\nDone.'
        result = LLMClient._parse_claims_response(text)
        assert len(result) == 1

    def test_unparseable_returns_empty(self):
        result = LLMClient._parse_claims_response("This is not JSON at all")
        assert result == []
