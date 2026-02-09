"""Unit tests for domain.scoring module."""

import pytest

from app.domain.scoring import accuracy_score, trust_score, percentage_accuracy


class TestAccuracyScore:
    """Test accuracy score calculation."""

    def test_perfect_match(self):
        """Perfect match returns 1.0."""
        assert accuracy_score(15.0, 15.0) == 1.0
        assert accuracy_score(0.0, 0.0) == 1.0
        assert accuracy_score(100.0, 100.0) == 1.0

    def test_close_match(self):
        """Close matches return high accuracy."""
        # 15.0 vs 14.8 = 1.35% error → 0.9865 accuracy
        score = accuracy_score(15.0, 14.8)
        assert 0.98 <= score < 0.99

        # 100.0 vs 99.0 = 1% error → 0.989... accuracy
        score = accuracy_score(100.0, 99.0)
        assert score == pytest.approx(0.989899, abs=0.001)

    def test_stated_higher_than_actual(self):
        """Overstating reduces accuracy."""
        # Stated 20, actual 15 = 33% error → 0.67 accuracy
        score = accuracy_score(20.0, 15.0)
        assert score == pytest.approx(0.666667, abs=0.01)

    def test_stated_lower_than_actual(self):
        """Understating reduces accuracy."""
        # Stated 10, actual 15 = 33% error → 0.67 accuracy
        score = accuracy_score(10.0, 15.0)
        assert score == pytest.approx(0.666667, abs=0.01)

    def test_zero_actual_nonzero_stated(self):
        """Stated != 0 and actual == 0 returns 0.0."""
        assert accuracy_score(10.0, 0.0) == 0.0
        assert accuracy_score(0.01, 0.0) == 0.0
        assert accuracy_score(-5.0, 0.0) == 0.0

    def test_both_zero(self):
        """Both zero returns 1.0 (perfect match)."""
        assert accuracy_score(0.0, 0.0) == 1.0

    def test_negative_values(self):
        """Handles negative values correctly."""
        # Loss: stated -10, actual -10 = perfect
        assert accuracy_score(-10.0, -10.0) == 1.0

        # Loss: stated -10, actual -12 = 16.67% error
        score = accuracy_score(-10.0, -12.0)
        assert score == pytest.approx(0.8333, abs=0.01)

    def test_very_small_differences(self):
        """Very small differences yield high accuracy."""
        score = accuracy_score(1000.0, 1001.0)
        assert score > 0.999

    def test_large_error(self):
        """Large errors yield low accuracy, clamped at 0."""
        # Stated 100, actual 10 = 900% error → 0.0
        score = accuracy_score(100.0, 10.0)
        assert score == 0.0

    def test_never_negative(self):
        """Accuracy score is clamped at 0.0."""
        assert accuracy_score(1000.0, 1.0) == 0.0
        assert accuracy_score(50.0, 5.0) == 0.0


class TestTrustScore:
    """Test trust score calculation."""

    def test_all_verified(self):
        """All verified claims = 100 trust score."""
        assert trust_score({"verified": 10}) == 100.0

    def test_all_approximately_correct(self):
        """All approximately correct = 85 trust score."""
        score = trust_score({"approximately_correct": 10})
        assert score == 85.0

    def test_all_misleading(self):
        """All misleading = 35 trust score."""
        score = trust_score({"misleading": 10})
        assert score == 35.0

    def test_all_incorrect(self):
        """All incorrect = 0 trust score."""
        assert trust_score({"incorrect": 10}) == 0.0

    def test_mixed_verdicts(self):
        """Mixed verdicts are weighted correctly."""
        # 10 verified + 0 others = 100
        # 5 verified + 5 approx = (5*1.0 + 5*0.7) / 10 = 0.85 → 92.5
        score = trust_score({"verified": 5, "approximately_correct": 5})
        assert score == 92.5

    def test_unverifiable_ignored(self):
        """Unverifiable claims don't affect score."""
        score = trust_score({"verified": 10, "unverifiable": 5})
        assert score == 100.0

    def test_no_verifiable_claims(self):
        """No verifiable claims returns neutral 50.0."""
        assert trust_score({}) == 50.0
        assert trust_score({"unverifiable": 10}) == 50.0

    def test_weights(self):
        """Verify exact weighting formula."""
        # verified=1.0, approx=0.7, misleading=-0.3, incorrect=-1.0
        # 1 of each verifiable = (1.0 + 0.7 - 0.3 - 1.0) / 4 = 0.4 / 4 = 0.1
        # trust = (0.1 + 1) * 50 = 55
        counts = {
            "verified": 1,
            "approximately_correct": 1,
            "misleading": 1,
            "incorrect": 1,
        }
        score = trust_score(counts)
        assert score == pytest.approx(55.0)

    def test_clamped_at_zero(self):
        """Trust score is clamped at 0."""
        # All incorrect = raw -1.0 → trust 0.0
        assert trust_score({"incorrect": 100}) == 0.0

    def test_clamped_at_hundred(self):
        """Trust score is clamped at 100."""
        # All verified = raw 1.0 → trust 100.0
        assert trust_score({"verified": 100}) == 100.0

    def test_realistic_scenario(self):
        """Realistic mixed scenario."""
        counts = {
            "verified": 15,
            "approximately_correct": 3,
            "misleading": 1,
            "incorrect": 1,
            "unverifiable": 5,  # Ignored
        }
        # verifiable = 15 + 3 + 1 + 1 = 20
        # raw = (15*1.0 + 3*0.7 + 1*-0.3 + 1*-1.0) / 20
        #     = (15 + 2.1 - 0.3 - 1.0) / 20
        #     = 15.8 / 20 = 0.79
        # trust = (0.79 + 1) * 50 = 89.5
        score = trust_score(counts)
        assert score == pytest.approx(89.5)


class TestPercentageAccuracy:
    """Test percentage accuracy calculation."""

    def test_all_correct(self):
        """All verified = 100% accuracy."""
        assert percentage_accuracy({"verified": 10}) == 1.0

    def test_all_approximately_correct(self):
        """All approximately correct = 100% accuracy."""
        assert percentage_accuracy({"approximately_correct": 10}) == 1.0

    def test_mixed_correct(self):
        """Mix of verified + approximately correct = 100%."""
        acc = percentage_accuracy({"verified": 5, "approximately_correct": 5})
        assert acc == 1.0

    def test_half_correct(self):
        """Half correct, half incorrect = 50%."""
        acc = percentage_accuracy({"verified": 5, "incorrect": 5})
        assert acc == 0.5

    def test_all_incorrect(self):
        """All incorrect = 0%."""
        assert percentage_accuracy({"incorrect": 10}) == 0.0

    def test_all_misleading(self):
        """All misleading = 0%."""
        assert percentage_accuracy({"misleading": 10}) == 0.0

    def test_unverifiable_ignored(self):
        """Unverifiable claims don't affect percentage."""
        acc = percentage_accuracy({"verified": 10, "unverifiable": 10})
        assert acc == 1.0

    def test_no_verifiable_claims(self):
        """No verifiable claims returns 0.0."""
        assert percentage_accuracy({}) == 0.0
        assert percentage_accuracy({"unverifiable": 10}) == 0.0

    def test_realistic_scenario(self):
        """Realistic mixed scenario."""
        counts = {
            "verified": 15,
            "approximately_correct": 3,
            "misleading": 1,
            "incorrect": 1,
            "unverifiable": 5,  # Ignored
        }
        # correct = 15 + 3 = 18
        # verifiable = 15 + 3 + 1 + 1 = 20
        # accuracy = 18 / 20 = 0.9
        acc = percentage_accuracy(counts)
        assert acc == 0.9

    def test_counts_treated_as_integers(self):
        """Integer counts work correctly."""
        acc = percentage_accuracy({"verified": 7, "incorrect": 3})
        assert acc == 0.7
