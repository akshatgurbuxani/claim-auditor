"""Shared verdict-counting, accuracy, and trust-score helpers.

Every place in the codebase that needs to tally verdicts, compute an
accuracy rate, or produce a trust score should import from here — never
duplicate the formulas.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.schemas.verification import Verdict


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def compute_verdict_counts(claims: Any) -> Dict[str, int]:
    """Count verdicts from a list of claim objects (ORM models or dicts).

    Works with both:
    - ORM ``ClaimModel`` instances (attribute access: ``c.verification``)
    - Plain dicts returned by the facade (key access: ``c["verification"]``)
    """
    v: Dict[str, int] = {e.value: 0 for e in Verdict}
    for c in claims:
        verification = (
            c.verification if hasattr(c, "verification") else c.get("verification")
        )
        if verification:
            verdict = (
                verification.verdict
                if hasattr(verification, "verdict")
                else verification.get("verdict")
            )
            if verdict and verdict in v:
                v[verdict] = v.get(verdict, 0) + 1
    return v


def compute_accuracy(verdict_counts: Dict[str, int]) -> float:
    """Return (verified + approximately_correct) / verifiable as a float in [0, 1]."""
    verifiable = sum(cnt for k, cnt in verdict_counts.items() if k != "unverifiable")
    if verifiable == 0:
        return 0.0
    return (
        verdict_counts.get("verified", 0)
        + verdict_counts.get("approximately_correct", 0)
    ) / verifiable


def compute_trust_score(verdict_counts: Dict[str, int]) -> float:
    """Weighted trust score on a 0-100 scale.

    Formula::

        raw = (verified*1.0 + approx*0.7 + misleading*-0.3 + incorrect*-1.0) / verifiable
        trust = clamp((raw + 1) * 50, 0, 100)

    Returns 50.0 when there are no verifiable claims.
    """
    verifiable = sum(cnt for k, cnt in verdict_counts.items() if k != "unverifiable")
    if verifiable == 0:
        return 50.0
    raw = (
        verdict_counts.get("verified", 0) * 1.0
        + verdict_counts.get("approximately_correct", 0) * 0.7
        + verdict_counts.get("misleading", 0) * -0.3
        + verdict_counts.get("incorrect", 0) * -1.0
    ) / verifiable
    return max(0.0, min(100.0, (raw + 1) * 50))


# ---------------------------------------------------------------------------
# Convenience wrapper (returns the 4-tuple many callers expect)
# ---------------------------------------------------------------------------

def compute_stats(claims: Any) -> Tuple[Dict[str, int], int, float, float]:
    """Return ``(verdict_counts, total_claims, accuracy, trust_score)``.

    This is a convenience wrapper so callers that previously destructured a
    4-tuple (Streamlit, facade, companies API) don't need to change their
    call-sites beyond swapping the import.
    """
    v = compute_verdict_counts(claims)
    return v, len(claims), compute_accuracy(v), compute_trust_score(v)
