"""Extracts quantitative claims from earnings-call transcripts via LLM.

The prompts are managed by PromptManager and versioned separately.
"""

import logging
from typing import List

from app.clients.llm_client import LLMClient
from app.domain.metrics import normalize_metric_name
from app.prompts.manager import PromptManager
from app.schemas.claim import ClaimCreate, ComparisonPeriod, MetricType

logger = logging.getLogger(__name__)


class ClaimExtractor:
    """Two-step claim extraction: LLM → validate → deduplicate."""

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_version: str = "latest",
    ):
        """Initialize claim extractor with LLM client and prompt version.

        Args:
            llm_client: Anthropic API client
            prompt_version: Prompt version to use (e.g., "v1", "latest")
        """
        self.llm = llm_client
        self.prompt_manager = PromptManager()
        self.prompt_version = prompt_version

        # Load prompt on init (cached by PromptManager)
        self._system_prompt = self.prompt_manager.get(
            "claim_extraction", version=prompt_version
        )
        logger.info(
            "ClaimExtractor initialized with prompt version=%s (%d chars)",
            prompt_version,
            len(self._system_prompt),
        )

    def extract(
        self,
        transcript_text: str,
        ticker: str,
        quarter: int,
        year: int,
    ) -> List[ClaimCreate]:
        """Extract, validate, and deduplicate claims from a transcript."""
        raw_claims = self.llm.extract_claims(
            transcript_text=transcript_text,
            ticker=ticker,
            quarter=quarter,
            year=year,
            system_prompt=self._system_prompt,
        )

        valid: list[ClaimCreate] = []
        for raw in raw_claims:
            try:
                claim = self._validate(raw)
                valid.append(claim)
            except Exception as exc:
                logger.warning("Skipping invalid claim: %s — %s", exc, raw.get("claim_text", "")[:80])

        deduped = self._deduplicate(valid)
        logger.info(
            "%s Q%d %d: extracted %d raw → %d valid → %d unique claims",
            ticker, quarter, year, len(raw_claims), len(valid), len(deduped),
        )
        return deduped

    # ── internal ─────────────────────────────────────────────────────

    def _validate(self, raw: dict) -> ClaimCreate:
        """Turn a raw LLM dict into a validated ClaimCreate."""
        raw["metric"] = normalize_metric_name(raw.get("metric", "unknown"))

        # Coerce enums gracefully
        try:
            raw["metric_type"] = MetricType(raw.get("metric_type", "absolute"))
        except ValueError:
            raw["metric_type"] = MetricType.ABSOLUTE

        try:
            raw["comparison_period"] = ComparisonPeriod(raw.get("comparison_period", "none"))
        except ValueError:
            raw["comparison_period"] = ComparisonPeriod.NONE

        # Ensure required fields
        raw.setdefault("speaker", "Unknown")
        raw.setdefault("claim_text", "")
        raw.setdefault("stated_value", 0)
        raw.setdefault("unit", "usd")
        raw.setdefault("is_gaap", True)
        raw.setdefault("confidence", 0.5)

        # transcript_id will be set by the service layer
        raw.setdefault("transcript_id", 0)

        return ClaimCreate(**raw)

    @staticmethod
    def _deduplicate(claims: list[ClaimCreate]) -> list[ClaimCreate]:
        seen: set[tuple] = set()
        out: list[ClaimCreate] = []
        for c in claims:
            key = (c.metric, c.stated_value, c.comparison_period, c.unit)
            if key not in seen:
                seen.add(key)
                out.append(c)
        return out
