"""Shape estimation primitives.

Hosts the two Shape stages of the FLAIR pipeline:

- `_estimate_shape` — Shape₁ as a single frozen vector, the average of
  within-period proportions from the last ``_SHAPE_K`` periods.  An
  earlier version conditioned on a secondary period context via
  Dirichlet-Multinomial smoothing; the 97-configuration ablation
  showed this refinement is marginally harmful (−0.4 % relMASE,
  −0.9 % relCRPS) because the Prior-centered Ridge already captures
  weekly structure via cross-period lags, so FLAIR uses one global
  Shape with no context conditioning.

- `_compute_shape2` — Shape₂ (BIC-gated empirical Bayes shrinkage of a
  secondary periodic Level pattern, e.g. annual seasonality of a daily
  series).  Selects between a first-harmonic prior (2 params) and the
  flat prior (0 params) by the same MDL principle FLAIR uses for
  primary period selection.

- `_compute_cross_periods` — derives Ridge cross-period lag indices
  from the secondary period list returned by `_period._select_period`.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from ._constants import _EPS, _EPS_LOG, _EPS_SHAPE, _SHAPE_K


def _compute_shape2(
    L: NDArray[np.floating],
    cp: int,
    n_complete: int,
) -> NDArray[np.floating] | None:
    """Shape₂ with MDL-gated empirical Bayes shrinkage.

    Shape₂ = w × raw_proportions + (1−w) × prior
    w = nc₂ / (nc₂ + cp)

    The prior is selected by BIC (MDL): first harmonic (2 params) vs
    flat (0 params).  When the harmonic is not justified by data, the
    flat prior `S₂ = 1` keeps deseasonalization negligible — same MDL
    principle as BIC period selection.
    """
    nc2 = n_complete // cp
    if nc2 < 2:
        return None

    pos = np.arange(n_complete) % cp
    S2_raw = np.zeros(cp)
    for d in range(cp):
        vals = L[pos == d]
        S2_raw[d] = vals.mean() if len(vals) > 0 else 1.0
    raw_mean = S2_raw.mean()
    if raw_mean < _EPS:
        return None
    S2_raw = S2_raw / raw_mean

    # First harmonic fit
    t = np.arange(cp, dtype=float)
    cos_b = np.cos(2 * np.pi * t / cp)
    sin_b = np.sin(2 * np.pi * t / cp)
    S2_c = S2_raw - 1.0
    a = 2.0 * np.mean(S2_c * cos_b)
    b = 2.0 * np.mean(S2_c * sin_b)
    S2_harmonic = 1.0 + a * cos_b + b * sin_b

    # MDL gate: BIC selects harmonic (2 params) vs flat (0 params)
    RSS_flat: float = float(np.sum(S2_c**2))
    RSS_harmonic: float = float(np.sum((S2_raw - S2_harmonic) ** 2))
    bic_flat = cp * np.log(max(RSS_flat / cp, _EPS_LOG))
    bic_harmonic = cp * np.log(max(RSS_harmonic / cp, _EPS_LOG)) + 2 * np.log(cp)
    S2_prior = S2_harmonic if bic_harmonic < bic_flat else np.ones(cp)

    # Empirical Bayes weight
    w = nc2 / (nc2 + cp)
    S2 = w * S2_raw + (1 - w) * S2_prior

    S2 = np.maximum(S2, _EPS_SHAPE)
    S2 = S2 / S2.mean()
    return np.asarray(S2, dtype=np.float64)


def _estimate_shape(
    mat: NDArray[np.floating],
    n_complete: int,
    P: int,
    secondary: list[int],  # noqa: ARG001  # retained for API stability
    L: NDArray[np.floating],  # noqa: ARG001
    horizon: int,
) -> tuple[NDArray[np.floating], NDArray[np.floating], int]:
    """Frozen Shape: global average of within-period proportions.

    The Shape is a single fixed vector ``S ∈ Δ^{P−1}`` broadcast across
    all forecast and historical steps.  Earlier versions conditioned on a
    secondary period (e.g. day-of-week for hourly data) via
    Dirichlet-Multinomial smoothing; the 97-configuration ablation
    showed this refinement is marginally harmful (−0.4 % relMASE,
    −0.9 % relCRPS) because the Prior-centered Ridge already captures
    weekly structure through cross-period lags.  Removing it gives a
    purer "frozen Shape" method that is simpler, slightly better, and
    consistent with the BBP sub-criticality of the rank-1 residual's
    second singular vector.

    The ``secondary`` and ``L`` parameters are retained for API
    stability — the rest of the pipeline still uses ``secondary`` for
    Ridge cross-period lags via ``_compute_cross_periods``.

    Returns
    -------
    S_forecast : ndarray, shape (m, P)
        Per-block forecast Shape, where ``m = ceil(horizon / P)``.
    S_hist : ndarray, shape (n_complete, P)
        Per-period historical Shape used for the rank-1 reconstruction
        residual that drives the phase-noise sampler.
    m : int
        Number of period blocks the forecast horizon spans.
    """
    K = min(_SHAPE_K, n_complete)
    recent = mat[:, -K:]
    totals = recent.sum(axis=0, keepdims=True)
    S_global = np.where(totals > _EPS, recent / totals, 1.0 / P).mean(axis=1)
    S_global /= max(S_global.sum(), _EPS)

    m = int(np.ceil(horizon / P))
    S_forecast = np.tile(S_global, (m, 1))
    S_hist = np.tile(S_global, (n_complete, 1))
    return S_forecast, S_hist, m


def _compute_cross_periods(
    secondary: list[int],
    P: int,
    period: int,
    n_complete: int,
) -> tuple[list[int], int]:
    """Compute cross-period Ridge lag indices from the secondary period list.

    Returns `(cross_periods, max_cp)` where `max_cp` is the lag at which
    the Ridge will inject a per-period seasonal feature.
    """
    cross_periods: list[int] = []
    for sp in secondary:
        cp = sp // P if P >= 2 else sp
        if 2 <= cp <= n_complete // 2:
            cross_periods.append(cp)
    if P == 1 and period >= 2 and period <= n_complete // 2:
        cross_periods = sorted(set(cross_periods) | {period})
    max_cp = max(cross_periods) if cross_periods else 0
    return cross_periods, max_cp
