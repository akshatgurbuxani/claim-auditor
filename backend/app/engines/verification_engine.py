"""Core verification engine — compares claimed values to actual financial data.

This is the most important module in the system.  Every decision here is
deliberate and tested.
"""

import logging
from typing import Optional

from app.config import Settings
from app.engines.metric_mapper import MetricMapper
from app.models.claim import ClaimModel
from app.models.financial_data import FinancialDataModel
from app.repositories.financial_data_repo import FinancialDataRepository
from app.schemas.verification import MisleadingFlag, Verdict, VerificationCreate
from app.utils.financial_math import accuracy_score, normalize_to_unit, percentage_difference

logger = logging.getLogger(__name__)


class VerificationEngine:
    """Verifies a single claim against structured financial data.

    Pipeline per claim:
    1. Check metric is resolvable
    2. Fetch relevant financial data (current + comparison period)
    3. Compute actual value (growth rate, margin, absolute, per-share)
    4. Normalize units so stated and actual are comparable
    5. Score accuracy
    6. Detect misleading framing
    7. Assign verdict
    """

    def __init__(
        self,
        metric_mapper: MetricMapper,
        financial_repo: FinancialDataRepository,
        settings: Settings,
    ):
        self.mapper = metric_mapper
        self.repo = financial_repo
        self.tol_verified = settings.verification_tolerance  # 0.02
        self.tol_approx = settings.approximate_tolerance      # 0.10
        self.tol_misleading = settings.misleading_threshold   # 0.25

    # ── main entry point ─────────────────────────────────────────────

    def verify(
        self,
        claim: ClaimModel,
        company_id: int,
        transcript_year: int,
        transcript_quarter: int,
    ) -> VerificationCreate:
        # 1. Can we even resolve this metric?
        if not self.mapper.can_resolve(claim.metric):
            return self._unverifiable(
                claim.id,
                f"Metric '{claim.metric}' is not in our financial data mapping.",
            )

        # 2. Dispatch by metric type
        metric_type = claim.metric_type  # stored as enum string value
        try:
            if metric_type in ("growth_rate", "change"):
                # For margin metrics tagged as "change", check if the stated
                # value looks like an absolute margin (>10%).  LLMs sometimes
                # misclassify "gross margin was 48.2%, up from 46.9%" as a
                # *change* claim with stated_value=48.2 instead of 1.3.
                if claim.metric in self.mapper.DERIVED and claim.stated_value > 10:
                    result = self._verify_margin(claim, company_id, transcript_year, transcript_quarter)
                else:
                    result = self._verify_growth(claim, company_id, transcript_year, transcript_quarter)
            elif metric_type == "margin":
                result = self._verify_margin(claim, company_id, transcript_year, transcript_quarter)
            elif metric_type in ("absolute", "per_share"):
                result = self._verify_absolute(claim, company_id, transcript_year, transcript_quarter)
            else:
                result = None
        except Exception as exc:
            logger.exception("Verification error for claim %d: %s", claim.id, exc)
            result = None

        if result is None:
            return self._unverifiable(
                claim.id,
                "Could not find sufficient financial data to verify this claim.",
            )

        actual_value, fin_id, comp_id = result

        # 3. Normalize stated value to comparable form
        stated = self._stated_comparable(claim)

        # 4. Compute accuracy
        score = accuracy_score(stated, actual_value)

        # 5. Misleading framing checks
        flags = self._check_misleading(claim, stated, actual_value, score)

        # 6. Assign verdict (flags can upgrade severity)
        verdict = self._verdict(score, flags)

        # 7. Build human explanation
        explanation = self._explain(claim, stated, actual_value, score, verdict, flags)

        return VerificationCreate(
            claim_id=claim.id,
            actual_value=round(actual_value, 4),
            accuracy_score=round(score, 4),
            verdict=verdict,
            explanation=explanation,
            financial_data_id=fin_id,
            comparison_data_id=comp_id,
            financial_data_source=self._data_source_label(claim, transcript_year, transcript_quarter),
            misleading_flags=[f.value for f in flags],
            misleading_details=self._misleading_detail(flags) if flags else None,
        )

    # ── verification by type ─────────────────────────────────────────

    def _verify_growth(
        self, claim: ClaimModel, cid: int, year: int, quarter: int
    ) -> Optional[tuple[float, Optional[int], Optional[int]]]:
        """Verify a growth-rate claim (e.g. 'revenue grew 15% YoY')."""
        current, comparison = self.repo.get_comparison_pair(
            cid, year, quarter, claim.comparison_period,
        )
        if not current or not comparison:
            return None

        cur_val = self.mapper.resolve(claim.metric, current)
        comp_val = self.mapper.resolve(claim.metric, comparison)
        if cur_val is None or comp_val is None or comp_val == 0:
            return None

        actual_growth = ((cur_val - comp_val) / abs(comp_val)) * 100
        return actual_growth, current.id, comparison.id

    def _verify_margin(
        self, claim: ClaimModel, cid: int, year: int, quarter: int
    ) -> Optional[tuple[float, Optional[int], None]]:
        """Verify a margin claim (e.g. 'operating margin of 30%')."""
        data = self.repo.get_for_quarter(cid, year, quarter)
        if not data:
            return None
        val = self.mapper.resolve(claim.metric, data)
        if val is None:
            return None
        return val, data.id, None

    def _verify_absolute(
        self, claim: ClaimModel, cid: int, year: int, quarter: int
    ) -> Optional[tuple[float, Optional[int], None]]:
        """Verify an absolute value or per-share claim."""
        data = self.repo.get_for_quarter(cid, year, quarter)
        if not data:
            return None
        raw = self.mapper.resolve(claim.metric, data)
        if raw is None:
            return None

        # Financial data is in raw dollars; convert to claim's unit for comparison
        actual = normalize_to_unit(raw, claim.unit)
        return actual, data.id, None

    # ── helpers ──────────────────────────────────────────────────────

    def _stated_comparable(self, claim: ClaimModel) -> float:
        """Normalise the claim's stated_value for apples-to-apples comparison.

        Growth rates and margins are already in percentage points.
        Absolute values need unit conversion (billions → raw, etc.).
        """
        if claim.metric_type in ("growth_rate", "change", "margin"):
            if claim.unit == "basis_points":
                return claim.stated_value / 100  # bps → pct
            return claim.stated_value

        # absolute / per_share — stated is already in the claim's unit
        return claim.stated_value

    @staticmethod
    def _unverifiable(claim_id: int, reason: str) -> VerificationCreate:
        return VerificationCreate(
            claim_id=claim_id,
            verdict=Verdict.UNVERIFIABLE,
            explanation=reason,
        )

    def _verdict(self, score: float, flags: list[MisleadingFlag]) -> Verdict:
        if score >= 1 - self.tol_verified:        # ≥ 0.98
            v = Verdict.VERIFIED
        elif score >= 1 - self.tol_approx:         # ≥ 0.90
            v = Verdict.APPROXIMATELY_CORRECT
        elif score >= 1 - self.tol_misleading:     # ≥ 0.75
            v = Verdict.MISLEADING
        else:
            v = Verdict.INCORRECT

        # Non-numeric misleading flags can upgrade an otherwise-OK verdict
        if flags and v in (Verdict.VERIFIED, Verdict.APPROXIMATELY_CORRECT):
            # Only upgrade if there are substantive flags (not just rounding)
            substantive = [f for f in flags if f != MisleadingFlag.ROUNDING_BIAS]
            if substantive:
                v = Verdict.MISLEADING

        return v

    def _check_misleading(
        self,
        claim: ClaimModel,
        stated: float,
        actual: float,
        score: float,
    ) -> list[MisleadingFlag]:
        flags: list[MisleadingFlag] = []

        # Rounding bias: stated > actual and within approximate range
        if 0.90 <= score < 0.98:
            pct = percentage_difference(stated, actual)
            if pct is not None and pct > 0:
                flags.append(MisleadingFlag.ROUNDING_BIAS)

        # Non-GAAP without clear disclosure
        if not claim.is_gaap:
            flags.append(MisleadingFlag.GAAP_NONGAAP_MISMATCH)

        # Segment claim verified against total-company data
        if claim.segment:
            flags.append(MisleadingFlag.SEGMENT_VS_TOTAL)

        return flags

    @staticmethod
    def _explain(
        claim: ClaimModel,
        stated: float,
        actual: float,
        score: float,
        verdict: Verdict,
        flags: list[MisleadingFlag],
    ) -> str:
        pct = percentage_difference(stated, actual)
        pct_str = f"{pct:+.1f}%" if pct is not None else "N/A"

        base = {
            Verdict.VERIFIED: (
                f"✅ Verified. Stated {stated:.2f}, actual {actual:.2f} "
                f"(difference {pct_str}). Within acceptable tolerance."
            ),
            Verdict.APPROXIMATELY_CORRECT: (
                f"≈ Approximately correct. Stated {stated:.2f}, actual {actual:.2f} "
                f"(difference {pct_str})."
            ),
            Verdict.MISLEADING: (
                f"⚠️ Misleading. Stated {stated:.2f}, actual {actual:.2f} "
                f"(difference {pct_str}). The framing may create a false impression."
            ),
            Verdict.INCORRECT: (
                f"❌ Incorrect. Stated {stated:.2f}, actual {actual:.2f} "
                f"(difference {pct_str}). Materially inaccurate."
            ),
            Verdict.UNVERIFIABLE: "Cannot verify — insufficient data.",
        }[verdict]

        if flags:
            flag_names = ", ".join(f.value.replace("_", " ") for f in flags)
            base += f" Flags: {flag_names}."

        return base

    @staticmethod
    def _data_source_label(claim: ClaimModel, year: int, quarter: int) -> str:
        return f"{claim.metric} Q{quarter} {year}"

    @staticmethod
    def _misleading_detail(flags: list[MisleadingFlag]) -> str:
        parts = []
        for f in flags:
            if f == MisleadingFlag.ROUNDING_BIAS:
                parts.append("The stated figure rounds in a more favorable direction than the actual data.")
            elif f == MisleadingFlag.GAAP_NONGAAP_MISMATCH:
                parts.append("The claim uses non-GAAP / adjusted figures which may not match standard reporting.")
            elif f == MisleadingFlag.SEGMENT_VS_TOTAL:
                parts.append("The claim references a business segment; our verification uses total-company data.")
            elif f == MisleadingFlag.CHERRY_PICKED_PERIOD:
                parts.append("The comparison period may be selectively chosen.")
            elif f == MisleadingFlag.MISLEADING_COMPARISON:
                parts.append("The comparison basis is non-standard.")
            elif f == MisleadingFlag.OMITS_CONTEXT:
                parts.append("Important context is omitted from the claim.")
        return " ".join(parts)
