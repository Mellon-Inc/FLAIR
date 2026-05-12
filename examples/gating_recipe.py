"""Residual-gated forecasting recipe — per-origin routing around FLAIR.

このファイルは ``flair_autoprep`` 本体には含めず、recipe として ``examples/`` に
配置している。FLAIRforKISS のコアラッパは「明示指定された categorical を
one-hot して numpy で渡す」だけに絞り、ゲート系のロジックは利用者側で
組むパターンとして提示する。

When to use this recipe
-----------------------

Bike Sharing のように **年境界で trend が遷移する** データでは、auto_encode の
出力をそのまま FLAIR に投げると、月ダミー等が誤誘導するケースがある。
このレシピの ``residual_gate_forecast`` は origin ごとに

1. shift スコアで full / filt 特徴量集合を選び (``gated_forecast`` の v2 ロジック),
2. 訓練末尾で full vs vanilla の内部 MASE を比較し、full が劣化していれば
   vanilla に退避する

という 2 段ゲートを行う。Bike Sharing daily で MASE 1.058 (manual) → 0.846。
Jena のような numeric-only データでは効かない (Oracle = B なのでゲート無意味)。

Usage
-----

.. code-block:: python

    from flair_autoprep import auto_encode
    from examples.gating_recipe import residual_gate_forecast

    # Use auto_detect=True for object/string categoricals, OR pass
    # categorical_cols=["season", ...] for an explicit (recommended) list.
    out = auto_encode(df, target_col="cnt", datetime_col="dteday", auto_detect=True)
    y_full, X_full = out["y"], out["X"]
    y_hist, X_hist = y_full[:-h], X_full[:-h]
    X_future = X_full[-h:]

    samples, route = residual_gate_forecast(
        y_hist, h, "D",
        X_hist_full=X_hist, X_future_full=X_future,
        col_names_full=out["cols"],
        season_m=7,
    )

History
-------

実験 v2 (``gated_forecast``) と v4 (``type_gated_forecast``) は ablation
として残してある。本番に推奨するのは v5 = ``residual_gate_forecast``。

詳細は ``report/final_report_2026-04-28.md`` 参照。
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Distribution-shift detector (originally flair_autoprep.shift)
# ---------------------------------------------------------------------------


def detect_shift(
    X_hist: np.ndarray,
    X_future: np.ndarray,
    col_names: list[str],
    threshold_z: float = 2.0,
    exclude_cols: set[str] | None = None,
) -> list[tuple[str, float]]:
    """Per-column train→test mean shift in train-std units.

    Parameters
    ----------
    X_hist : (n_train, k) ndarray
        Training-window exog matrix.
    X_future : (horizon, k) ndarray
        Forecast-window exog matrix.
    col_names : list of str
        Column names corresponding to the k columns of ``X_hist`` / ``X_future``.
    threshold_z : float
        Absolute z-shift threshold. Default 2.0.
    exclude_cols : set of str, optional
        Columns to skip. Useful for monotone trend proxies (e.g. ``yr``,
        ``days_since_2011``) that always shift between train and the future
        horizon, so the returned list focuses on substantive distribution
        changes.

    Returns
    -------
    list of ``(col_name, z_shift)`` for columns whose absolute shift exceeds
    ``threshold_z``. Sorted by descending |z_shift|.
    """
    flagged: list[tuple[str, float]] = []
    skip = exclude_cols or set()
    for j, name in enumerate(col_names):
        if name in skip:
            continue
        h = X_hist[:, j]
        f = X_future[:, j]
        h = h[~np.isnan(h)]
        f = f[~np.isnan(f)]
        if len(h) == 0 or len(f) == 0:
            continue
        sd = float(np.std(h))
        if sd < 1e-12:
            continue
        z = (float(np.mean(f)) - float(np.mean(h))) / sd
        if abs(z) >= threshold_z:
            flagged.append((name, z))
    flagged.sort(key=lambda kv: -abs(kv[1]))
    return flagged


# ---------------------------------------------------------------------------
# Gating routes (originally flair_autoprep.gates)
# ---------------------------------------------------------------------------


def gated_forecast(
    y_hist: np.ndarray,
    horizon: int,
    freq: str,
    *,
    X_hist_full: np.ndarray,
    X_future_full: np.ndarray,
    col_names_full: list[str],
    X_hist_filt: np.ndarray | None = None,
    X_future_filt: np.ndarray | None = None,
    n_samples: int = 200,
    seed: int | None = None,
    shift_z: float = 2.0,
    n_shift_threshold: int = 2,
    n_shift_vanilla: int | None = None,
    invert: bool = True,
    exclude_cols: set[str] | None = None,
) -> tuple[np.ndarray, str]:
    """Per-origin gated forecast: choose feature set by shift score (実験 v2/v3).

    Computes ``n_shift = len(detect_shift(X_full, threshold=shift_z, exclude=…))``
    on the unfiltered feature set and routes:

    1. If ``n_shift_vanilla is not None`` and ``n_shift >= n_shift_vanilla``:
       use vanilla (no exog at all). This is for catastrophic shifts where
       no covariate set helps and the seasonal-baseline FLAIR is safer.
    2. Otherwise apply the B-vs-D gate:

           ``invert=True``  (default, Bike-data convention):
               n_shift >= n_shift_threshold  → full features (B)
               n_shift <  n_shift_threshold  → filtered features (D)

           ``invert=False`` (conventional intuition):
               n_shift >= n_shift_threshold  → filtered (simplify)
               n_shift <  n_shift_threshold  → full

    The inverted mode wins on Bike Sharing because the dominant shift
    drivers there are trend proxies (``yr``, ``days_since_2011``) that
    flag year-transition origins. At a year boundary the trend features
    are essential, so the model needs them — simplifying would discard
    information. In mid-period origins (low shift), the high-cardinality
    month dummies risk overfitting, so the simpler set is safer.

    Falls back to the full set when ``X_hist_filt`` is None (gate
    degenerates to vanilla-vs-full at that point).

    Returns ``(samples, route)`` where ``route ∈ {"full", "filt", "vanilla"}``.
    """
    from flaircast import forecast

    flagged = detect_shift(
        X_hist_full,
        X_future_full,
        col_names_full,
        threshold_z=shift_z,
        exclude_cols=exclude_cols,
    )
    n_shift = len(flagged)

    # Vanilla escape route — applied first so it can override B/D logic
    # under catastrophic shift.
    if n_shift_vanilla is not None and n_shift >= n_shift_vanilla:
        samples = forecast(
            y_hist,
            horizon,
            freq,
            n_samples=n_samples,
            seed=seed,
        )
        return samples, "vanilla"

    if X_hist_filt is None or X_future_filt is None:
        samples = forecast(
            y_hist,
            horizon,
            freq,
            n_samples=n_samples,
            seed=seed,
            X_hist=X_hist_full,
            X_future=X_future_full,
        )
        return samples, "full"

    use_full = (n_shift >= n_shift_threshold) if invert else (n_shift < n_shift_threshold)
    if use_full:
        samples = forecast(
            y_hist,
            horizon,
            freq,
            n_samples=n_samples,
            seed=seed,
            X_hist=X_hist_full,
            X_future=X_future_full,
        )
        return samples, "full"
    else:
        samples = forecast(
            y_hist,
            horizon,
            freq,
            n_samples=n_samples,
            seed=seed,
            X_hist=X_hist_filt,
            X_future=X_future_filt,
        )
        return samples, "filt"


def _inner_val_mase(
    y_train: np.ndarray,
    y_val: np.ndarray,
    freq: str,
    season_m: int,
    X_hist: np.ndarray | None = None,
    X_future: np.ndarray | None = None,
    n_samples: int = 50,
    seed: int | None = 0,
) -> float:
    """Inner-validation MASE: fit on y_train, predict horizon=len(y_val), compare.

    Used by ``residual_gate_forecast`` to compare how well full-features (B)
    and vanilla (A) fit the most recent window of training. If B's
    inner-MASE is worse than A's, the exog is degrading the fit and the
    gate routes to vanilla on the real forecast.

    Returns ``inf`` when training is too short to produce a meaningful
    seasonal baseline.
    """
    from flaircast import forecast

    if len(y_train) <= season_m + 1:
        return float("inf")
    h = len(y_val)
    s = forecast(
        y_train,
        h,
        freq,
        n_samples=n_samples,
        seed=seed,
        X_hist=X_hist,
        X_future=X_future,
    )
    pred = np.median(s, axis=0)
    naive_err = float(np.mean(np.abs(y_train[season_m:] - y_train[:-season_m])))
    if naive_err < 1e-12:
        return float("inf")
    return float(np.mean(np.abs(y_val - pred)) / naive_err)


def residual_gate_forecast(
    y_hist: np.ndarray,
    horizon: int,
    freq: str,
    *,
    X_hist_full: np.ndarray,
    X_future_full: np.ndarray,
    col_names_full: list[str],
    X_hist_filt: np.ndarray | None = None,
    X_future_filt: np.ndarray | None = None,
    n_samples: int = 200,
    seed: int | None = None,
    # Outer gate (gated_forecast v2 style)
    shift_z: float = 2.0,
    n_shift_threshold: int = 2,
    invert: bool = True,
    # Inner-validation residual gate
    inner_horizon: int | None = None,
    inner_n_samples: int = 50,
    season_m: int = 7,
    inner_ratio_threshold: float = 1.0,
) -> tuple[np.ndarray, str]:
    """v5: ``gated_forecast`` 候補 + 内部 validation で vanilla を確認するゲート.

    Pipeline:

    1. ``gated_forecast`` (v2) で full / filt のどちらが妥当かを決める
    2. 訓練の末尾 ``inner_horizon`` を hold-out し、full features (B) と
       vanilla (A) で予測。それぞれの内部 MASE を測る
    3. ``MASE_B > inner_ratio_threshold * MASE_A`` なら exog が直近データを
       損なっていると判断し、本番予測は vanilla で行う
    4. それ以外は v2 の判定 (full / filt) を採用する

    Cost: forecast() 呼び出し +2 回 (inner_n_samples を 50 など軽量にできる).

    Returns ``(samples, route)`` where ``route ∈ {"full", "filt", "vanilla"}``.
    """
    from flaircast import forecast

    if inner_horizon is None:
        inner_horizon = horizon

    # Step 1: outer gate candidate (gated_forecast v2 style)
    flagged = detect_shift(X_hist_full, X_future_full, col_names_full, threshold_z=shift_z)
    n_shift = len(flagged)
    use_full = (n_shift >= n_shift_threshold) if invert else (n_shift < n_shift_threshold)
    outer_route = "full" if use_full else "filt"

    # Step 2: Inner validation, only if there's enough history
    if len(y_hist) > inner_horizon * 2 + season_m:
        y_inner_train = y_hist[:-inner_horizon]
        y_inner_val = y_hist[-inner_horizon:]
        X_inner_train = X_hist_full[:-inner_horizon]
        X_inner_val = X_hist_full[-inner_horizon:]

        mase_b = _inner_val_mase(
            y_inner_train,
            y_inner_val,
            freq,
            season_m,
            X_hist=X_inner_train,
            X_future=X_inner_val,
            n_samples=inner_n_samples,
            seed=seed,
        )
        mase_a = _inner_val_mase(
            y_inner_train,
            y_inner_val,
            freq,
            season_m,
            n_samples=inner_n_samples,
            seed=seed,
        )

        if np.isfinite(mase_b) and np.isfinite(mase_a) and mase_b > inner_ratio_threshold * mase_a:
            samples = forecast(
                y_hist,
                horizon,
                freq,
                n_samples=n_samples,
                seed=seed,
            )
            return samples, "vanilla"

    # Step 3: Apply outer route
    if outer_route == "full" or X_hist_filt is None:
        samples = forecast(
            y_hist,
            horizon,
            freq,
            n_samples=n_samples,
            seed=seed,
            X_hist=X_hist_full,
            X_future=X_future_full,
        )
        return samples, "full"
    else:
        samples = forecast(
            y_hist,
            horizon,
            freq,
            n_samples=n_samples,
            seed=seed,
            X_hist=X_hist_filt,
            X_future=X_future_filt,
        )
        return samples, "filt"


def type_gated_forecast(
    y_hist: np.ndarray,
    horizon: int,
    freq: str,
    *,
    X_hist_full: np.ndarray,
    X_future_full: np.ndarray,
    col_names_full: list[str],
    X_hist_filt: np.ndarray | None = None,
    X_future_filt: np.ndarray | None = None,
    dummy_cols: set[str] | None = None,
    trend_cols: set[str] | None = None,
    n_samples: int = 200,
    seed: int | None = None,
    shift_z: float = 2.0,
) -> tuple[np.ndarray, str]:
    """実験 v4: シフト列の type で 3-way ルーティング.

    Decision tree (順番に評価):

    1. trend col のシフト (any) → full features (B)
       年遷移にはトレンド変数が必要
    2. dummy のみのシフト (trend / continuous なし) → vanilla (A)
       純粋な月ダミーの regime change は exog が誤誘導する典型例
    3. continuous のみのシフト (trend / dummy なし) → full (B)
       Coherent な物理量シフトは exog で吸収できる
    4. それ以外 (シフトなし or mixed) → filt (D) 利用可能なら filt、無ければ full

    Returns ``(samples, route)`` where ``route ∈ {"vanilla", "full", "filt"}``.

    Bike では failure recall 100% を達成するが、平均 MASE は v2 より悪化する
    (precision が低い)。v5 (``residual_gate_forecast``) で改善された。
    """
    from flaircast import forecast

    flagged = detect_shift(X_hist_full, X_future_full, col_names_full, threshold_z=shift_z)
    dummy = dummy_cols or set()
    trend = trend_cols or set()

    n_trend = sum(1 for c, _ in flagged if c in trend)
    n_dummy = sum(1 for c, _ in flagged if c in dummy)
    n_other = len(flagged) - n_trend - n_dummy

    if n_trend >= 1:
        route = "full"
    elif n_dummy >= 1 and n_other == 0:
        route = "vanilla"
    elif n_other >= 1 and n_trend == 0 and n_dummy == 0:
        route = "full"
    else:
        route = "filt" if X_hist_filt is not None else "full"

    if route == "vanilla":
        samples = forecast(y_hist, horizon, freq, n_samples=n_samples, seed=seed)
    elif route == "filt" and X_hist_filt is not None:
        samples = forecast(
            y_hist,
            horizon,
            freq,
            n_samples=n_samples,
            seed=seed,
            X_hist=X_hist_filt,
            X_future=X_future_filt,
        )
    else:  # full
        samples = forecast(
            y_hist,
            horizon,
            freq,
            n_samples=n_samples,
            seed=seed,
            X_hist=X_hist_full,
            X_future=X_future_full,
        )
    return samples, route
