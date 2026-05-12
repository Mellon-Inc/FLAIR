"""Unit tests for the ``flair_autoprep`` package.

Covers the public API surface that ships with KISS / OSS: explicit
categorical handling, auto_detect opt-in, leakage detection, the
class-support / cardinality filters, frequency inference, and the
high-level FLAIRPipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from flair_autoprep import FLAIRPipeline, auto_encode, infer_freq


@pytest.fixture
def sample_df():
    """60 daily rows with mixed dtypes: numeric id, str, numeric, target."""
    rng = np.random.default_rng(0)
    n = 60
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="D"),
            "sku_id": rng.integers(10000, 10005, n),  # numeric-typed id
            "region": rng.choice(["JP", "US", "EU"], n),  # string
            "price": rng.standard_normal(n),  # numeric
            "sales": rng.standard_normal(n).cumsum() + 50.0,
        }
    )


# --------------------------------------------------------------------------
# Categorical handling
# --------------------------------------------------------------------------


class TestCategoricalCols:
    def test_explicit_numeric_id_forced_to_onehot(self, sample_df):
        out = auto_encode(
            sample_df,
            target_col="sales",
            datetime_col="date",
            categorical_cols=["sku_id"],
            verbose=False,
        )
        assert any(c.startswith("sku_id_") for c in out["cols"])
        assert "price" in out["numeric_cols"]
        assert "sku_id" not in out["numeric_cols"]

    def test_auto_detect_false_drops_str(self, sample_df):
        out = auto_encode(
            sample_df, target_col="sales", datetime_col="date", verbose=False
        )
        assert "region" in out["filtered_unspecified_str"]
        assert not any(c.startswith("region_") for c in out["cols"])

    def test_auto_detect_true_onehots_str(self, sample_df):
        out = auto_encode(
            sample_df,
            target_col="sales",
            datetime_col="date",
            auto_detect=True,
            verbose=False,
        )
        assert any(c.startswith("region_") for c in out["cols"])
        assert "region" not in out["filtered_unspecified_str"]

    def test_unknown_categorical_col_raises(self, sample_df):
        with pytest.raises(KeyError, match="categorical_cols"):
            auto_encode(
                sample_df,
                target_col="sales",
                datetime_col="date",
                categorical_cols=["sku_id_typo"],
                verbose=False,
            )

    def test_target_in_categorical_cols_raises(self, sample_df):
        with pytest.raises(KeyError, match="target"):
            auto_encode(
                sample_df,
                target_col="sales",
                datetime_col="date",
                categorical_cols=["sales"],
                verbose=False,
            )

    def test_drop_cols_wins_over_categorical_cols(self, sample_df):
        out = auto_encode(
            sample_df,
            target_col="sales",
            datetime_col="date",
            drop_cols=["sku_id"],
            categorical_cols=["sku_id"],
            verbose=False,
        )
        assert not any(c.startswith("sku_id") for c in out["cols"])


# --------------------------------------------------------------------------
# Leakage detection
# --------------------------------------------------------------------------


class TestLeakage:
    def test_high_correlation_dropped(self):
        rng = np.random.default_rng(0)
        n = 60
        sales = rng.standard_normal(n).cumsum() + 50.0
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=n, freq="D"),
                "sales": sales,
                "near_copy": sales + rng.standard_normal(n) * 1e-6,
                "noise": rng.standard_normal(n),
            }
        )
        out = auto_encode(
            df, target_col="sales", datetime_col="date", verbose=False
        )
        assert "near_copy" in out["leaky"]
        assert "noise" not in out["leaky"]

    def test_name_based_leak(self, sample_df):
        df = sample_df.assign(sales_lag=sample_df["sales"].shift(1).fillna(0))
        out = auto_encode(
            df, target_col="sales", datetime_col="date", verbose=False
        )
        assert "sales_lag" in out["leaky"]

    def test_sum_identity_leak(self):
        rng = np.random.default_rng(0)
        n = 60
        a = rng.standard_normal(n)
        b = rng.standard_normal(n)
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=n, freq="D"),
                "a": a,
                "b": b,
                "y": a + b,
            }
        )
        out = auto_encode(df, target_col="y", datetime_col="date", verbose=False)
        assert "a" in out["leaky"] and "b" in out["leaky"]


# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------


class TestFilters:
    def test_min_class_support_drops_rare(self):
        n = 60
        regions = ["JP"] * (n - 1) + ["RARE"]
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=n, freq="D"),
                "region": regions,
                "y": np.arange(n, dtype=float),
            }
        )
        out = auto_encode(
            df,
            target_col="y",
            datetime_col="date",
            auto_detect=True,
            min_class_support=2,
            verbose=False,
        )
        assert "region" in out["filtered_low_support"]

    def test_max_categorical_cols_drops_wide(self):
        n = 120
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=n, freq="D"),
                "month": [str(i % 12) for i in range(n)],
                "y": np.arange(n, dtype=float),
            }
        )
        out = auto_encode(
            df,
            target_col="y",
            datetime_col="date",
            auto_detect=True,
            max_categorical_cols=5,
            verbose=False,
        )
        assert "month" in out["filtered_high_cardinality"]


# --------------------------------------------------------------------------
# Frequency inference
# --------------------------------------------------------------------------


class TestFreqInference:
    @pytest.mark.parametrize(
        "freq_in,freq_out",
        [("D", "D"), ("h", "H"), ("W", "W"), ("MS", "M"), ("ME", "M")],
    )
    def test_basic_freqs_via_auto_encode(self, freq_in, freq_out):
        n = 30
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=n, freq=freq_in),
                "y": np.arange(n, dtype=float),
            }
        )
        out = auto_encode(
            df, target_col="y", datetime_col="date", verbose=False
        )
        assert out["freq"] == freq_out

    def test_infer_freq_falls_back_to_hint(self):
        idx = pd.DatetimeIndex(["2024-01-01"])
        assert infer_freq(idx, hint="D") == "D"

    def test_infer_freq_heuristic_on_irregular_index(self):
        # pandas cannot infer a regular freq from irregular gaps,
        # so the median-delta heuristic kicks in. Median ~1h → "H".
        idx = pd.DatetimeIndex(
            [
                "2024-01-01 00:00",
                "2024-01-01 01:00",
                "2024-01-01 02:30",
                "2024-01-01 03:30",
            ]
        )
        assert infer_freq(idx) == "H"


# --------------------------------------------------------------------------
# FLAIRPipeline E2E
# --------------------------------------------------------------------------


class TestPipeline:
    def test_fit_predict_basic(self, sample_df):
        pipe = FLAIRPipeline(
            target_col="sales",
            datetime_col="date",
            n_samples=10,
            seed=0,
            verbose=False,
        )
        res = pipe.fit_predict(sample_df, horizon=7)
        assert res.samples.shape == (10, 7)
        assert res.point.shape == (7,)
        assert res.freq == "D"

    def test_fit_predict_with_categorical(self, sample_df):
        pipe = FLAIRPipeline(
            target_col="sales",
            datetime_col="date",
            categorical_cols=["sku_id"],
            n_samples=10,
            seed=0,
            verbose=False,
        )
        res = pipe.fit_predict(sample_df, horizon=7)
        assert any(c.startswith("sku_id_") for c in res.encoded_cols)

    def test_fit_predict_with_future_x(self, sample_df):
        n_hist = 50
        history = sample_df.iloc[:n_hist].copy()
        future_X = sample_df.iloc[n_hist : n_hist + 7].drop(columns=["sales"])
        pipe = FLAIRPipeline(
            target_col="sales",
            datetime_col="date",
            n_samples=10,
            seed=0,
            verbose=False,
        )
        res = pipe.fit_predict(history, horizon=7, future_X=future_X)
        assert res.samples.shape == (10, 7)

    def test_encode_only(self, sample_df):
        pipe = FLAIRPipeline(
            target_col="sales",
            datetime_col="date",
            categorical_cols=["sku_id"],
            verbose=False,
        )
        out = pipe.encode_only(sample_df)
        assert {"y", "X", "freq", "cols"}.issubset(out.keys())
        assert out["y"].shape == (60,)


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------


class TestEdgeCases:
    def test_missing_target_col(self, sample_df):
        with pytest.raises(KeyError, match="target_col"):
            auto_encode(sample_df, target_col="nonexistent", verbose=False)

    def test_horizon_too_large(self, sample_df):
        pipe = FLAIRPipeline(
            target_col="sales",
            datetime_col="date",
            n_samples=10,
            seed=0,
            verbose=False,
        )
        with pytest.raises(ValueError, match="horizon"):
            pipe.fit_predict(sample_df, horizon=100)

    def test_future_x_extra_column_raises(self, sample_df):
        n_hist = 50
        history = sample_df.iloc[:n_hist].copy()
        future_X = (
            sample_df.iloc[n_hist : n_hist + 7]
            .drop(columns=["sales"])
            .assign(unexpected_col=0.0)
        )
        pipe = FLAIRPipeline(
            target_col="sales",
            datetime_col="date",
            n_samples=10,
            seed=0,
            verbose=False,
        )
        with pytest.raises(ValueError, match="unexpected_col"):
            pipe.fit_predict(history, horizon=7, future_X=future_X)

    def test_empty_df_returns_empty_arrays(self):
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(pd.Series([], dtype="object")),
                "y": pd.Series([], dtype=float),
            }
        )
        out = auto_encode(df, target_col="y", datetime_col="date", verbose=False)
        assert out["y"].shape == (0,)
        assert out["X"].shape == (0, 0)

    def test_all_nan_target_does_not_crash(self):
        n = 30
        df = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=n, freq="D"),
                "x": np.arange(n, dtype=float),
                "y": np.full(n, np.nan),
            }
        )
        out = auto_encode(df, target_col="y", datetime_col="date", verbose=False)
        assert out["y"].shape == (n,)
        assert np.all(np.isnan(out["y"]))
        assert "x" in out["numeric_cols"]
