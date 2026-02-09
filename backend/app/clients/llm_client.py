"""Wrapper around Anthropic Claude API for structured claim extraction."""

import json
import logging
import re
from typing import Any, List

import anthropic

from app.utils.retry import with_retry

logger = logging.getLogger(__name__)


class LLMClient:
    """Handles all LLM interactions.

    Responsibilities:
    - Send prompts with structured output expectations
    - Parse and validate JSON responses
    - Track token usage
    - Retry on transient failures
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        retry_max_attempts: int = 3,
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self._retry_max_attempts = retry_max_attempts

    @with_retry(
        max_attempts=3,
        initial_delay=2.0,  # Claude API is slower, start with 2s
        retry_on=(
            anthropic.APIError,
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
        ),
        reraise_on=(
            anthropic.BadRequestError,  # Invalid prompt - don't retry
            anthropic.AuthenticationError,  # Bad API key - don't retry
        ),
    )
    def extract_claims(
        self,
        transcript_text: str,
        ticker: str,
        quarter: int,
        year: int,
        system_prompt: str,
    ) -> List[dict]:
        """Send transcript to Claude and parse the structured claim response.

        Retries on:
        - API errors (5xx from Anthropic)
        - Timeouts
        - Rate limits
        - Network errors

        Does NOT retry on:
        - Bad request (invalid prompt)
        - Authentication errors
        """
        user_message = (
            f"Analyze this {ticker} Q{quarter} {year} earnings call transcript.\n\n"
            "Extract ALL quantitative claims made by management (CEO, CFO, etc.).\n\n"
            f"Transcript:\n{transcript_text}"
        )

        message = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        self.total_input_tokens += message.usage.input_tokens
        self.total_output_tokens += message.usage.output_tokens

        raw_text = message.content[0].text
        return self._parse_claims_response(raw_text)

    # ── Response parsing ─────────────────────────────────────────────

    @staticmethod
    def _parse_claims_response(text: str) -> List[dict]:
        """Extract a JSON array of claims from potentially messy LLM output.

        Handles:
        • Raw JSON array
        • JSON inside ```json … ``` fences
        • JSON buried in prose
        """
        # 1) Try markdown code block
        md = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
        if md:
            return json.loads(md.group(1))

        # 2) Direct JSON parse
        text_stripped = text.strip()
        if text_stripped.startswith("["):
            try:
                return json.loads(text_stripped)
            except json.JSONDecodeError:
                pass

        # 3) Find the first JSON array anywhere
        arr = re.search(r"\[[\s\S]*\]", text)
        if arr:
            try:
                return json.loads(arr.group(0))
            except json.JSONDecodeError:
                pass

        logger.error("Could not parse claims JSON from LLM response (first 300 chars): %s", text[:300])
        return []
