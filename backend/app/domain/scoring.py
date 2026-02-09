"""All scoring formulas — accuracy, trust, percentage accuracy.

Consolidates scoring logic from:
- app/utils/financial_math.py::accuracy_score
- app/utils/scoring.py::compute_trust_score
- app/utils/scoring.py::compute_accuracy

Usage:
    from app.domain.scoring import accuracy_score, trust_score

    acc = accuracy_score(stated=15.0, actual=14.8)  # 0.987
    trust = trust_score({"verified": 10, "misleading": 2})  # 67.5
"""

from typing import Dict


def accuracy_score(stated: float, actual: float) -> float:
    """Compute how close stated is to actual.

    Returns a float in [0.0, 1.0] where 1.0 is a perfect match.

    Formula:
        accuracy = 1 - |stated - actual| / |actual|

    Special cases:
        - stated == actual == 0 → 1.0
        - stated != 0 and actual == 0 → 0.0

    Args:
        stated: The value claimed in the transcript
        actual: The true value from financial data

    Returns:
        Accuracy score in [0.0, 1.0]

    Examples:
        >>> accuracy_score(15.0, 15.0)
        1.0
        >>> accuracy_score(15.0, 14.0)
        0.933...
        >>> accuracy_score(15.0, 0.0)
        0.0
        >>> accuracy_score(0.0, 0.0)
        1.0
    """
    if actual == 0:
        return 0.0 if stated != 0 else 1.0
    return max(0.0, 1.0 - abs(stated - actual) / abs(actual))


def trust_score(verdict_counts: Dict[str, int]) -> float:
    """Weighted trust score on a 0-100 scale.

    Formula:
        raw = (verified*1.0 + approx*0.7 + misleading*-0.3 + incorrect*-1.0) / verifiable
        trust = clamp((raw + 1) * 50, 0, 100)

    Args:
        verdict_counts: Dict mapping verdict strings to counts
            e.g., {"verified": 10, "approximately_correct": 5, ...}

    Returns:
        Trust score in [0.0, 100.0]
        Returns 50.0 when no verifiable claims exist

    Examples:
        >>> trust_score({"verified": 10, "unverifiable": 2})
        100.0
        >>> trust_score({"verified": 5, "approximately_correct": 5})
        85.0
        >>> trust_score({"misleading": 10})
        35.0
        >>> trust_score({})
        50.0
    """
    verifiable = sum(
        cnt for k, cnt in verdict_counts.items() if k != "unverifiable"
    )
    if verifiable == 0:
        return 50.0

    raw = (
        verdict_counts.get("verified", 0) * 1.0
        + verdict_counts.get("approximately_correct", 0) * 0.7
        + verdict_counts.get("misleading", 0) * -0.3
        + verdict_counts.get("incorrect", 0) * -1.0
    ) / verifiable

    return max(0.0, min(100.0, (raw + 1) * 50))


def percentage_accuracy(verdict_counts: Dict[str, int]) -> float:
    """Percentage of verifiable claims that are correct (verified + approx).

    Returns value in [0.0, 1.0].

    Args:
        verdict_counts: Dict mapping verdict strings to counts

    Returns:
        Accuracy percentage in [0.0, 1.0]

    Examples:
        >>> percentage_accuracy({"verified": 8, "approximately_correct": 2})
        1.0
        >>> percentage_accuracy({"verified": 5, "misleading": 5})
        0.5
    """
    verifiable = sum(
        cnt for k, cnt in verdict_counts.items() if k != "unverifiable"
    )
    if verifiable == 0:
        return 0.0

    return (
        verdict_counts.get("verified", 0)
        + verdict_counts.get("approximately_correct", 0)
    ) / verifiable
