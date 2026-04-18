"""Unit tests for flaircast private helper functions."""

import numpy as np
import pytest

from flaircast import (
    FREQ_TO_PERIOD,
    FREQ_TO_PERIODS,
    _bc,
    _bc_inv,
    _bc_lambda,
    _compute_shape2,
    _get_period,
    _get_periods,
    _resolve_freq,
    _ridge_sa,
)
from flaircast._level import _mp_median, _optshrink_factor

# ── _resolve_freq ───────────────────────────────────────────────────────


class TestResolveFreq:
    def test_lowercase_to_uppercase(self):
        assert _resolve_freq("h") == "H"
        assert _resolve_freq("d") == "D"
        assert _resolve_freq("w") == "W"

    def test_min_to_t(self):
        assert _resolve_freq("min") == "T"
        assert _resolve_freq("5min") == "5T"
        assert _resolve_freq("15MIN") == "15T"

    def test_already_normalized(self):
        assert _resolve_freq("H") == "H"
        assert _resolve_freq("5T") == "5T"

    def test_mixed_case(self):
        assert _resolve_freq("Min") == "T"


# ── _get_period ─────────────────────────────────────────────────────────


class TestGetPeriod:
    @pytest.mark.parametrize("freq,expected", list(FREQ_TO_PERIOD.items()))
    def test_all_known_frequencies(self, freq, expected):
        assert _get_period(freq) == expected

    def test_suffix_matching(self):
        # '2H' should match 'H' suffix -> 24
        assert _get_period("2H") == 24

    def test_unknown_returns_1(self):
        assert _get_period("UNKNOWN") == 1

    def test_case_insensitive(self):
        assert _get_period("h") == 24
        assert _get_period("d") == 7


# ── _get_periods ────────────────────────────────────────────────────────


class TestGetPeriods:
    @pytest.mark.parametrize("freq,expected", list(FREQ_TO_PERIODS.items()))
    def test_all_known_frequencies(self, freq, expected):
        result = _get_periods(freq)
        assert result == expected
        # Must return a copy, not a reference to the dict value
        assert result is not FREQ_TO_PERIODS.get(freq)

    def test_unknown_returns_empty(self):
        assert _get_periods("UNKNOWN") == []

    def test_case_insensitive(self):
        assert _get_periods("h") == [24, 168]


# ── _bc_lambda ──────────────────────────────────────────────────────────


class TestBcLambda:
    def test_positive_array_returns_in_range(self):
        rng = np.random.RandomState(42)
        y = rng.exponential(10, 100)
        lam = _bc_lambda(y)
        assert 0.0 <= lam <= 1.0

    def test_few_positives_returns_1(self):
        y = np.array([1.0, 2.0, -5.0, -3.0, -1.0])
        assert _bc_lambda(y) == 1.0

    def test_all_negative_returns_1(self):
        y = np.array([-5.0, -3.0, -1.0, -10.0])
        assert _bc_lambda(y) == 1.0

    def test_constant_positive(self):
        # All identical values may cause scipy to fail -> fallback to 1.0
        y = np.full(100, 5.0)
        lam = _bc_lambda(y)
        assert 0.0 <= lam <= 1.0


# ── _bc / _bc_inv roundtrip ────────────────────────────────────────────


class TestBoxCox:
    @pytest.mark.parametrize("lam", [0.0, 0.25, 0.5, 0.75, 1.0])
    def test_roundtrip(self, lam):
        y = np.array([1.0, 2.0, 5.0, 10.0, 50.0])
        z = _bc(y, lam)
        y_back = _bc_inv(z, lam)
        np.testing.assert_allclose(y_back, y, rtol=1e-10)

    def test_bc_clamps_negatives(self):
        y = np.array([-5.0, 0.0, 1.0])
        z = _bc(y, 0.5)
        assert np.all(np.isfinite(z))

    def test_bc_inv_lam_zero_uses_exp(self):
        z = np.array([0.0, 1.0, 2.0])
        result = _bc_inv(z, 0.0)
        np.testing.assert_allclose(result, np.exp(z))

    def test_bc_inv_clips_extreme(self):
        z = np.array([100.0, -100.0])
        result = _bc_inv(z, 0.0)
        assert np.all(np.isfinite(result))


# ── _ridge_sa ───────────────────────────────────────────────────────────


class TestRidgeSA:
    def test_identity_system(self):
        X = np.eye(5)
        y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        beta, loo, gcv_min, Vt, s, d_avg, f_avg = _ridge_sa(X, y)
        assert beta.shape == (5,)
        assert loo.shape == (5,)
        assert isinstance(gcv_min, float)
        assert gcv_min >= 0
        assert Vt.shape[0] == s.shape[0] == d_avg.shape[0] == f_avg.shape[0]
        # f_avg = soft-averaged 1/(s²+α); must be positive and finite
        assert np.all(np.isfinite(f_avg)) and np.all(f_avg > 0)

    def test_simple_regression(self):
        rng = np.random.RandomState(42)
        n = 50
        X = np.column_stack([np.ones(n), np.arange(n, dtype=float) / n])
        true_beta = np.array([3.0, 2.0])
        y = X @ true_beta + rng.normal(0, 0.1, n)
        beta, _loo, _gcv_min, *_ = _ridge_sa(X, y)
        np.testing.assert_allclose(beta, true_beta, atol=0.5)

    def test_loo_residuals_reasonable(self):
        rng = np.random.RandomState(42)
        n = 30
        X = np.column_stack([np.ones(n), rng.randn(n)])
        y = 2 * X[:, 1] + rng.normal(0, 0.5, n)
        _, loo, _, *_ = _ridge_sa(X, y)
        assert np.all(np.isfinite(loo))
        # LOO residuals should be in a reasonable range
        assert np.std(loo) < 10 * np.std(y)


# ── _compute_shape2 ────────────────────────────────────────────────────


class TestComputeShape2:
    def test_uniform_level(self):
        L = np.ones(20)
        result = _compute_shape2(L, cp=7, n_complete=20)
        if result is not None:
            np.testing.assert_allclose(result.mean(), 1.0, atol=1e-5)

    def test_nc2_too_small_returns_none(self):
        L = np.ones(5)
        result = _compute_shape2(L, cp=7, n_complete=5)
        assert result is None  # nc2 = 5 // 7 = 0 < 2

    def test_periodic_level(self):
        rng = np.random.RandomState(42)
        # Create Level with clear day-of-week pattern
        cp = 7
        n_complete = 56  # 8 complete secondary periods
        base_pattern = np.array([1.2, 0.8, 1.0, 1.1, 0.9, 1.3, 0.7])
        L = np.tile(base_pattern, 8) + rng.normal(0, 0.05, n_complete)
        result = _compute_shape2(L, cp=cp, n_complete=n_complete)
        assert result is not None
        np.testing.assert_allclose(result.mean(), 1.0, atol=1e-5)
        assert result.shape == (cp,)

    def test_zero_level_returns_none(self):
        L = np.zeros(20)
        result = _compute_shape2(L, cp=7, n_complete=20)
        assert result is None


# ── Gavish-Donoho shrinkage tests ─────────────────────────────────────


class TestMpMedian:
    def test_returns_positive(self):
        for beta in [0.1, 0.5, 1.0]:
            assert _mp_median(beta) > 0

    def test_cached(self):
        v1 = _mp_median(0.24)
        v2 = _mp_median(0.24)
        assert v1 == v2

    def test_monotone_decreasing(self):
        # MP median decreases as beta increases (toward square matrix)
        m1 = _mp_median(0.1)
        m2 = _mp_median(0.5)
        m3 = _mp_median(1.0)
        assert m1 > m2 > m3


class TestOptShrinkFactor:
    def test_degenerate_returns_one(self):
        assert _optshrink_factor(np.zeros(1), P=1, n_complete=10) == 1.0
        assert _optshrink_factor(np.array([0.0, 0.0]), P=2, n_complete=2) == 1.0

    def test_strong_signal_near_one(self):
        # Strong rank-1: sigma_1 >> noise → factor close to 1
        svd_s = np.array([100.0, 1.0, 0.5, 0.3])
        f = _optshrink_factor(svd_s, P=4, n_complete=100)
        assert 0.95 < f <= 1.0

    def test_subcritical_returns_one(self):
        # All singular values equal → no spike → factor = 1.0
        svd_s = np.ones(5) * 0.1
        assert _optshrink_factor(svd_s, P=5, n_complete=5) == 1.0

    def test_in_zero_one_range(self):
        rng = np.random.RandomState(0)
        mat = rng.randn(12, 50)
        mat += np.outer(rng.randn(12) * 5, np.ones(50))  # add rank-1
        from scipy.linalg import svdvals

        s = svdvals(mat)
        f = _optshrink_factor(s, P=12, n_complete=50)
        assert 0 < f <= 1.0
