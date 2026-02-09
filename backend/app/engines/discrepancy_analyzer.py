"""Quarter-to-quarter discrepancy pattern detection (bonus feature).

Analyses a company's claims across multiple quarters to find systematic
patterns of misleading communication.
"""

import logging
from typing import List

from app.models.claim import ClaimModel
from app.schemas.discrepancy import DiscrepancyPattern, PatternType

logger = logging.getLogger(__name__)


class DiscrepancyAnalyzer:
    """Detect cross-quarter patterns of misleading behaviour."""

    def analyze_company(
        self,
        company_id: int,
        claims_by_quarter: dict[str, list[ClaimModel]],
    ) -> List[DiscrepancyPattern]:
        patterns: list[DiscrepancyPattern] = []
        patterns.extend(self._detect_rounding_bias(company_id, claims_by_quarter))
        patterns.extend(self._detect_metric_switching(company_id, claims_by_quarter))
        patterns.extend(self._detect_increasing_inaccuracy(company_id, claims_by_quarter))
        patterns.extend(self._detect_gaap_shifting(company_id, claims_by_quarter))
        patterns.extend(self._detect_selective_emphasis(company_id, claims_by_quarter))
        return patterns

    # ── detectors ────────────────────────────────────────────────────

    def _detect_rounding_bias(
        self, cid: int, cbq: dict[str, list[ClaimModel]]
    ) -> list[DiscrepancyPattern]:
        """Flag if >70% of inexact claims round in a favourable direction."""
        favourable = 0
        total = 0
        affected: list[str] = []

        for quarter, claims in cbq.items():
            for c in claims:
                v = c.verification
                if v and v.actual_value is not None and v.accuracy_score is not None and v.accuracy_score < 1.0:
                    total += 1
                    if c.stated_value > v.actual_value:
                        favourable += 1
                        affected.append(quarter)

        if total >= 4 and favourable / total > 0.7:
            return [DiscrepancyPattern(
                company_id=cid,
                pattern_type=PatternType.CONSISTENT_ROUNDING_UP,
                description=(
                    f"Management consistently rounds in a favorable direction. "
                    f"{favourable}/{total} inexact claims overshoot the actual figure."
                ),
                affected_quarters=sorted(set(affected)),
                severity=round(favourable / total, 2),
                evidence=[f"{favourable}/{total} favorable roundings"],
            )]
        return []

    def _detect_metric_switching(
        self, cid: int, cbq: dict[str, list[ClaimModel]]
    ) -> list[DiscrepancyPattern]:
        """Flag when the most-emphasised metric changes each quarter."""
        top_by_q: dict[str, str] = {}
        for quarter, claims in cbq.items():
            counts: dict[str, int] = {}
            for c in claims:
                counts[c.metric] = counts.get(c.metric, 0) + 1
            if counts:
                top_by_q[quarter] = max(counts, key=counts.get)  # type: ignore[arg-type]

        unique = set(top_by_q.values())
        if len(unique) >= 3 and len(top_by_q) >= 3:
            desc = "; ".join(f"{q}: {m}" for q, m in sorted(top_by_q.items()))
            return [DiscrepancyPattern(
                company_id=cid,
                pattern_type=PatternType.METRIC_SWITCHING,
                description=f"Most-emphasised metric shifts across quarters ({desc}). Possible selective emphasis.",
                affected_quarters=sorted(top_by_q),
                severity=0.5,
                evidence=[f"Top metrics: {top_by_q}"],
            )]
        return []

    def _detect_increasing_inaccuracy(
        self, cid: int, cbq: dict[str, list[ClaimModel]]
    ) -> list[DiscrepancyPattern]:
        """Flag when average accuracy declines over time."""
        q_acc: dict[str, float] = {}
        for quarter, claims in sorted(cbq.items()):
            scores = [
                c.verification.accuracy_score
                for c in claims
                if c.verification and c.verification.accuracy_score is not None
            ]
            if scores:
                q_acc[quarter] = sum(scores) / len(scores)

        vals = list(q_acc.values())
        if len(vals) >= 3 and vals[-1] < vals[0] - 0.05:
            trend = "; ".join(f"{q}: {v:.1%}" for q, v in q_acc.items())
            # Round accuracy values for clean display
            q_acc_rounded = {q: round(v, 4) for q, v in q_acc.items()}
            return [DiscrepancyPattern(
                company_id=cid,
                pattern_type=PatternType.INCREASING_INACCURACY,
                description=f"Claim accuracy declining over time ({trend}).",
                affected_quarters=sorted(q_acc),
                severity=round(abs(vals[-1] - vals[0]), 2),
                evidence=[f"Accuracy trend: {q_acc_rounded}"],
            )]
        return []

    def _detect_gaap_shifting(
        self, cid: int, cbq: dict[str, list[ClaimModel]]
    ) -> list[DiscrepancyPattern]:
        """Flag when the GAAP vs non-GAAP mix changes significantly."""
        ratios: dict[str, float] = {}
        for quarter, claims in cbq.items():
            if claims:
                ratios[quarter] = sum(1 for c in claims if c.is_gaap) / len(claims)

        vals = list(ratios.values())
        if len(vals) >= 2 and max(vals) - min(vals) > 0.3:
            return [DiscrepancyPattern(
                company_id=cid,
                pattern_type=PatternType.GAAP_NONGAAP_SHIFTING,
                description=f"Company shifts between GAAP and non-GAAP emphasis. GAAP ratios: {ratios}",
                affected_quarters=sorted(ratios),
                severity=round(max(vals) - min(vals), 2),
                evidence=[f"GAAP ratios: {ratios}"],
            )]
        return []

    def _detect_selective_emphasis(
        self, cid: int, cbq: dict[str, list[ClaimModel]]
    ) -> list[DiscrepancyPattern]:
        """Flag when management almost never mentions negative growth."""
        biased_qs: list[str] = []
        for quarter, claims in cbq.items():
            pos = sum(1 for c in claims if c.metric_type == "growth_rate" and c.stated_value > 0)
            neg = sum(1 for c in claims if c.metric_type == "growth_rate" and c.stated_value < 0)
            total = pos + neg
            if total > 2 and pos / total > 0.9:
                biased_qs.append(quarter)

        if len(biased_qs) >= 2:
            return [DiscrepancyPattern(
                company_id=cid,
                pattern_type=PatternType.SELECTIVE_EMPHASIS,
                description=(
                    f"Management overwhelmingly highlights positive growth metrics "
                    f"in {len(biased_qs)} quarters while avoiding negative trends."
                ),
                affected_quarters=sorted(biased_qs),
                severity=0.6,
                evidence=[f"Quarters with >90% positive growth claims: {biased_qs}"],
            )]
        return []
