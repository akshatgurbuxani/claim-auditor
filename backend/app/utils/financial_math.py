"""Pure financial calculation utilities.

Every function here is stateless and thoroughly tested.
Used by the verification engine and analysis service.
"""

from typing import Optional


def growth_rate(current: float, previous: float) -> Optional[float]:
    """Calculate percentage growth rate.

    Returns None when previous is zero (undefined growth).

    >>> growth_rate(115, 100)
    15.0
    >>> growth_rate(85, 100)
    -15.0
    >>> growth_rate(100, 0) is None
    True
    """
    if previous == 0:
        return None
    return ((current - previous) / abs(previous)) * 100


def margin(numerator: float, denominator: float) -> Optional[float]:
    """Calculate a margin / ratio expressed as a percentage.

    >>> margin(30, 100)
    30.0
    >>> margin(0, 100)
    0.0
    >>> margin(10, 0) is None
    True
    """
    if denominator == 0:
        return None
    return (numerator / denominator) * 100


def basis_points_to_percentage(bps: float) -> float:
    """Convert basis points to percentage points.

    >>> basis_points_to_percentage(200)
    2.0
    >>> basis_points_to_percentage(50)
    0.5
    """
    return bps / 100


def percentage_to_basis_points(pct: float) -> float:
    """Convert percentage points to basis points.

    >>> percentage_to_basis_points(2.0)
    200.0
    """
    return pct * 100


def normalize_to_unit(value: float, unit: str) -> float:
    """Convert a raw dollar value to the named unit.

    >>> normalize_to_unit(5_000_000_000, "usd_billions")
    5.0
    >>> normalize_to_unit(5_000_000, "usd_millions")
    5.0
    >>> normalize_to_unit(5, "usd")
    5
    """
    if unit == "usd_billions":
        return value / 1_000_000_000
    if unit == "usd_millions":
        return value / 1_000_000
    return value


def denormalize_from_unit(value: float, unit: str) -> float:
    """Convert a value in the named unit back to raw dollars.

    >>> denormalize_from_unit(5.0, "usd_billions")
    5000000000.0
    >>> denormalize_from_unit(5.0, "usd_millions")
    5000000.0
    """
    if unit == "usd_billions":
        return value * 1_000_000_000
    if unit == "usd_millions":
        return value * 1_000_000
    return value


def accuracy_score(stated: float, actual: float) -> float:
    """Compute how close a stated value is to the actual value.

    Returns a float in [0.0, 1.0] where 1.0 is a perfect match.

    >>> accuracy_score(15.0, 15.0)
    1.0
    >>> 0.92 < accuracy_score(15.0, 14.0) < 0.94
    True
    >>> accuracy_score(15.0, 0.0)
    0.0
    >>> accuracy_score(0.0, 0.0)
    1.0
    """
    if actual == 0:
        return 0.0 if stated != 0 else 1.0
    return max(0.0, 1.0 - abs(stated - actual) / abs(actual))


def percentage_difference(stated: float, actual: float) -> Optional[float]:
    """Return how far off *stated* is from *actual* as a signed percentage.

    Positive means the stated value overshoots the actual.

    >>> percentage_difference(115, 100)
    15.0
    >>> percentage_difference(85, 100)
    -15.0
    >>> percentage_difference(10, 0) is None
    True
    """
    if actual == 0:
        return None
    return ((stated - actual) / abs(actual)) * 100
