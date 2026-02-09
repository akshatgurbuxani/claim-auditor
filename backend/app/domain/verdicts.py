"""Verdict assignment rules — the core business logic.

This module contains the logic for determining claim verdicts based on
accuracy scores and misleading flags.

Usage:
    from app.domain.verdicts import assign_verdict
    from app.schemas.verification import MisleadingFlag

    verdict = assign_verdict(
        accuracy_score=0.95,
        misleading_flags=[MisleadingFlag.ROUNDING_BIAS],
        tolerance_verified=0.02,
    )
"""

from app.schemas.verification import MisleadingFlag, Verdict


def assign_verdict(
    accuracy_score: float,
    misleading_flags: list[MisleadingFlag],
    tolerance_verified: float = 0.02,
    tolerance_approx: float = 0.10,
    tolerance_misleading: float = 0.25,
) -> Verdict:
    """Assign a verdict based on accuracy and misleading flags.

    Algorithm:
    1. Compute base verdict from accuracy score:
       - score >= 1 - 0.02  → VERIFIED
       - score >= 1 - 0.10  → APPROXIMATELY_CORRECT
       - score >= 1 - 0.25  → MISLEADING
       - score < 1 - 0.25   → INCORRECT

    2. Upgrade verdict if substantive flags present:
       - VERIFIED or APPROXIMATELY_CORRECT + substantive flags → MISLEADING

    Args:
        accuracy_score: Float in [0, 1] where 1.0 is perfect match
        misleading_flags: List of detected framing issues
        tolerance_verified: Threshold for VERIFIED (default: 2%)
        tolerance_approx: Threshold for APPROXIMATELY_CORRECT (default: 10%)
        tolerance_misleading: Threshold for MISLEADING (default: 25%)

    Returns:
        Verdict enum value

    Examples:
        >>> assign_verdict(0.99, [])
        <Verdict.VERIFIED: 'verified'>

        >>> assign_verdict(0.95, [])
        <Verdict.APPROXIMATELY_CORRECT: 'approximately_correct'>

        >>> assign_verdict(0.95, [MisleadingFlag.GAAP_NONGAAP_MISMATCH])
        <Verdict.MISLEADING: 'misleading'>

        >>> assign_verdict(0.50, [])
        <Verdict.INCORRECT: 'incorrect'>
    """
    # Step 1: Base verdict from accuracy score
    if accuracy_score >= 1 - tolerance_verified:  # >= 0.98
        verdict = Verdict.VERIFIED
    elif accuracy_score >= 1 - tolerance_approx:  # >= 0.90
        verdict = Verdict.APPROXIMATELY_CORRECT
    elif accuracy_score >= 1 - tolerance_misleading:  # >= 0.75
        verdict = Verdict.MISLEADING
    else:
        verdict = Verdict.INCORRECT

    # Step 2: Upgrade verdict if substantive flags present
    if misleading_flags and verdict in (Verdict.VERIFIED, Verdict.APPROXIMATELY_CORRECT):
        # Only upgrade if there are substantive flags (not just rounding)
        substantive = [
            f for f in misleading_flags if f != MisleadingFlag.ROUNDING_BIAS
        ]
        if substantive:
            verdict = Verdict.MISLEADING

    return verdict
