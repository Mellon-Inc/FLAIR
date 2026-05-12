"""High-level ``FLAIRPipeline`` wrapper for KISS integration.

The simplest way to call FLAIR from KISS: hand a raw DataFrame and a
target column name, get probabilistic forecast samples back. The
pipeline handles encoding (one-hot of explicitly categorical columns)
and the forecast call in one shot.

Quick example
-------------

    from flair_autoprep import FLAIRPipeline

    pipe = FLAIRPipeline(
        target_col="Sales",
        datetime_col="Date",
        freq_hint="D",
    )
    result = pipe.fit_predict(history_df, horizon=28, future_X=future_df)
    samples = result.samples           # (n_samples, horizon)
    point   = result.point             # (horizon,) median
    lo, hi  = result.interval(0.10, 0.90)

The result is equivalent to calling the lower-level :func:`auto_encode`
directly (the pipeline forwards to it internally).

Per-origin routing such as residual gating lives outside this package
as ``examples/gating_recipe.py``. This module focuses on
pandas → numpy + one-hot encoding only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .encode import auto_encode


@dataclass
class PipelineResult:
    """Return value of :meth:`FLAIRPipeline.fit_predict`.

    Attributes
    ----------
    samples : ndarray (n_samples, horizon)
        Probabilistic forecast sample paths. Use :meth:`interval` for
        per-step quantile bounds, or take ``np.median`` along axis 0
        for a point forecast.
    point : ndarray (horizon,)
        ``np.median(samples, axis=0)``.
    encoded_cols : list of str
        Names of the exog columns produced by :func:`auto_encode`.
    freq : str
        FLAIR-compatible frequency string used for the forecast.
    leaky : list of str
        Columns removed by leakage detection. Mirrors
        ``auto_encode``'s ``"leaky"`` field.
    encode_elapsed : float
        Seconds spent inside :func:`auto_encode`.
    forecast_elapsed : float
        Seconds spent inside the FLAIR forecast call.
    encoded_X : ndarray (n_total, k)
        The full encoded exog matrix, useful for debugging.
    """

    samples: np.ndarray
    point: np.ndarray
    encoded_cols: list[str]
    freq: str
    leaky: list[str]
    encode_elapsed: float
    forecast_elapsed: float
    encoded_X: np.ndarray = field(repr=False)

    def interval(self, lo: float = 0.1, hi: float = 0.9) -> tuple[np.ndarray, np.ndarray]:
        """Return per-step ``(lo, hi)`` percentile bounds."""
        lo_arr = np.percentile(self.samples, lo * 100, axis=0)
        hi_arr = np.percentile(self.samples, hi * 100, axis=0)
        return lo_arr, hi_arr


class FLAIRPipeline:
    """High-level wrapper that takes a raw DataFrame and returns FLAIR samples.

    Parameters
    ----------
    target_col : str
        Name of the target column.
    datetime_col : str, optional
        Name of the datetime column. If omitted, the DataFrame index is
        used when it is a ``DatetimeIndex``.
    freq_hint : str, optional
        Explicit FLAIR frequency string (``"D"``, ``"H"``, ``"M"``, …).
        If omitted, ``pd.infer_freq`` is used.
    drop_cols : list of str, optional
        Columns to drop unconditionally (e.g. duplicate IDs).
    categorical_cols : list of str, optional
        Columns to one-hot encode regardless of dtype. Use this for
        numeric-typed identifiers that are semantically categorical
        (e.g. ``sku_id`` stored as int).
    auto_detect : bool
        Whether to dtype-classify object/string columns that are not in
        ``categorical_cols``. Default ``False`` (LightGBM
        ``categorical_feature='auto'`` style opt-in). See
        :func:`auto_encode` for details.
    leakage_threshold : float
        |corr| threshold for the algebraic-identity leakage check
        (default 0.99).
    min_class_support : int
        Drop categorical columns whose rarest class has fewer than this
        many samples. ``1`` keeps all categoricals (default).
    max_categorical_cols : int, optional
        Drop categorical columns whose one-hot expansion would exceed
        this many columns. ``None`` disables the filter.
    n_samples : int
        Number of forecast samples (default 200).
    seed : int, optional
        Random seed.
    verbose : bool
        Whether :func:`auto_encode` prints its classification summary
        (default ``False``).
    """

    def __init__(
        self,
        target_col: str,
        *,
        datetime_col: str | None = None,
        freq_hint: str | None = None,
        drop_cols: list[str] | None = None,
        categorical_cols: list[str] | None = None,
        auto_detect: bool = False,
        leakage_threshold: float = 0.99,
        min_class_support: int = 1,
        max_categorical_cols: int | None = None,
        n_samples: int = 200,
        seed: int | None = None,
        verbose: bool = False,
    ) -> None:
        self.target_col = target_col
        self.datetime_col = datetime_col
        self.freq_hint = freq_hint
        self.drop_cols = drop_cols
        self.categorical_cols = categorical_cols
        self.auto_detect = auto_detect
        self.leakage_threshold = leakage_threshold
        self.min_class_support = min_class_support
        self.max_categorical_cols = max_categorical_cols
        self.n_samples = n_samples
        self.seed = seed
        self.verbose = verbose

    def _combine_history_and_future(
        self,
        history_df: pd.DataFrame,
        future_X: pd.DataFrame | None,
        horizon: int,
    ) -> pd.DataFrame:
        """Stitch history + future_X into a single frame for :func:`auto_encode`.

        ``future_X`` must have exactly ``horizon`` rows and may omit the
        target column (the missing values are filled with NaN). Both
        frames are expected to share the same column set / dtypes.
        """
        if future_X is None:
            return history_df

        if len(future_X) != horizon:
            raise ValueError(
                f"future_X has {len(future_X)} rows but horizon={horizon}; "
                "they must match"
            )

        extra_cols = set(future_X.columns) - set(history_df.columns)
        if extra_cols:
            raise ValueError(
                f"future_X has columns not present in history_df: "
                f"{sorted(extra_cols)}. They would be silently dropped — "
                "align the column sets first (target may be omitted)."
            )

        # Fill NaN for any column missing in future_X (typically the target).
        future_X = future_X.copy()
        for col in history_df.columns:
            if col not in future_X.columns:
                future_X[col] = np.nan
        future_X = future_X[history_df.columns.tolist()]
        return pd.concat([history_df, future_X], axis=0)

    def fit_predict(
        self,
        history_df: pd.DataFrame,
        horizon: int,
        future_X: pd.DataFrame | None = None,
    ) -> PipelineResult:
        """Encode + forecast in a single call.

        Parameters
        ----------
        history_df : DataFrame
            Past data including the target column. When ``future_X`` is
            ``None``, the last ``horizon`` rows are treated as the
            forecast window (their target values are ignored).
        horizon : int
            Forecast horizon.
        future_X : DataFrame, optional
            Future exog values for the forecast window (target column
            may be missing — it will be NaN-filled). When ``None``,
            ``history_df``'s tail is reused as the known-exog window.

        Returns
        -------
        PipelineResult
        """
        full_df = self._combine_history_and_future(history_df, future_X, horizon)

        out = auto_encode(
            full_df,
            target_col=self.target_col,
            datetime_col=self.datetime_col,
            drop_cols=self.drop_cols,
            freq_hint=self.freq_hint,
            categorical_cols=self.categorical_cols,
            auto_detect=self.auto_detect,
            leakage_threshold=self.leakage_threshold,
            min_class_support=self.min_class_support,
            max_categorical_cols=self.max_categorical_cols,
            verbose=self.verbose,
        )
        y_full = out["y"]
        X_full = out["X"]
        freq = out["freq"]

        n_total = len(y_full)
        if horizon >= n_total:
            raise ValueError(
                f"horizon={horizon} >= total rows ({n_total}). "
                "Need at least 1 row of history."
            )
        n_hist = n_total - horizon
        y_hist = y_full[:n_hist]
        X_hist = X_full[:n_hist]
        X_future = X_full[n_hist:]

        from flaircast import forecast as _flair_forecast

        t = time.perf_counter()
        samples = _flair_forecast(
            y_hist, horizon, freq,
            n_samples=self.n_samples, seed=self.seed,
            X_hist=X_hist if X_hist.size else None,
            X_future=X_future if X_future.size else None,
        )
        forecast_elapsed = time.perf_counter() - t

        return PipelineResult(
            samples=samples,
            point=np.median(samples, axis=0),
            encoded_cols=list(out["cols"]),
            freq=freq,
            leaky=list(out["leaky"]),
            encode_elapsed=float(out["elapsed"]),
            forecast_elapsed=forecast_elapsed,
            encoded_X=X_full,
        )

    def encode_only(self, df: pd.DataFrame) -> dict[str, Any]:
        """Run :func:`auto_encode` directly without forecasting (debug helper)."""
        return auto_encode(
            df,
            target_col=self.target_col,
            datetime_col=self.datetime_col,
            drop_cols=self.drop_cols,
            freq_hint=self.freq_hint,
            categorical_cols=self.categorical_cols,
            auto_detect=self.auto_detect,
            leakage_threshold=self.leakage_threshold,
            min_class_support=self.min_class_support,
            max_categorical_cols=self.max_categorical_cols,
            verbose=self.verbose,
        )
