from django.test import SimpleTestCase

from core import views


class SampleSizeCalculatorTests(SimpleTestCase):
    def test_proportion_estimate_applies_fpc(self) -> None:
        """Finite population correction should reduce the required n."""

        result = views._calculate_sample_size(
            population=10_000,
            confidence=95,
            margin=0.05,
            proportion=0.5,
            tail='two-sided',
        )
        self.assertEqual(result, 370)

    def test_mean_estimate_uses_absolute_error(self) -> None:
        result = views._calculate_mean_sample_size(
            population=None,
            confidence=95,
            std_dev=10,
            margin=1,
            tail='two-sided',
        )
        self.assertEqual(result, 385)

    def test_ab_proportion_powered_design(self) -> None:
        result = views._calculate_ab_proportions(
            confidence=95,
            power=0.8,
            baseline=0.2,
            detectable_diff=0.05,
            tail='two-sided',
        )
        self.assertEqual(result, 1094)

    def test_ab_mean_powered_design(self) -> None:
        result = views._calculate_ab_means(
            confidence=95,
            power=0.8,
            std_dev=12,
            detectable_diff=2,
            tail='two-sided',
        )
        self.assertEqual(result, 566)
