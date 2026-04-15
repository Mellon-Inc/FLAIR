"""MDL period selection.

`_select_period` chooses the primary period `P` for a series by
evaluating each candidate from the calendar table (`FREQ_TO_PERIODS`)
and picking the one whose period-folded matrix has the smallest residual
energy outside the leading singular triple, penalized by BIC.

Every candidate list implicitly includes ``P = 1`` (no periodicity).
The ``P = 1`` null model has ``RSS = Var(y) · T`` (total variance
around the mean) and ``k = 1`` parameter, while ``P ≥ 2`` has
``RSS = Σᵢ₌₂ σᵢ²`` (rank-1 residual) and ``k = P + n_c − 1``.
This unified BIC lets the MDL criterion reject periodicity when the
rank-1 fit improvement does not justify the extra Shape parameters.

Returns the chosen `P`, the list of plausible secondary periods, the
canonical primary period for the frequency string, and the raw calendar
candidate list (for use by `_compute_cross_periods`).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import svdvals

from ._constants import _EPS_LOG, _MAX_COMPLETE, _MIN_COMPLETE
from ._frequency import _get_period, _get_periods


def _select_period(
    y: NDArray[np.floating],
    n: int,
    freq: str,
) -> tuple[int, list[int], int, list[int], NDArray[np.floating], int]:
    """MDL period selection via BIC on the SVD spectrum.

    For each candidate period ``P ≥ 2`` the series is reshaped into a
    ``(P × n_c)`` matrix and the rank-1 residual energy is computed.
    The ``P = 1`` null model (mean + noise) is always evaluated as a
    baseline so that BIC can reject periodicity entirely.

    BIC for ``P ≥ 2``:
        ``T · log(RSS₁ / T) + (P + n_c − 1) · log(T)``
    BIC for ``P = 1``:
        ``T · log(Var(y_sel)) + log(T)``

    Returns ``(P, secondary, period, cal, svd_s, nc_svd)``.
    """
    period = _get_period(freq)
    cal = _get_periods(freq)
    candidates = [p for p in cal if p >= 2 and n // p >= _MIN_COMPLETE] if cal else []
    if not candidates:
        if max(period, 1) >= 2 and n // max(period, 1) >= _MIN_COMPLETE:
            candidates = [max(period, 1)]
        else:
            return 1, [], period, cal, np.zeros(1), 0

    T_max = min(n, _MAX_COMPLETE * min(candidates))
    y_sel = y[-T_max:]

    # P=1 null: mean + noise, 1 parameter.
    rss_null = float(np.var(y_sel) * T_max)
    bic_null = T_max * np.log(max(rss_null / T_max, _EPS_LOG)) + np.log(T_max)

    best_P, best_bic = 1, bic_null
    best_svd_s = np.zeros(1)
    nc_svd = 0
    for p_cand in candidates:
        nc = T_max // p_cand
        if nc < _MIN_COMPLETE:
            continue
        mat_c = y_sel[-(nc * p_cand) :].reshape(nc, p_cand).T
        s = svdvals(mat_c)
        rss1 = float(np.sum(s[1:] ** 2))
        T = nc * p_cand
        bic = T * np.log(max(rss1 / T, _EPS_LOG)) + (p_cand + nc - 1) * np.log(T)
        if bic < best_bic:
            best_P, best_bic = p_cand, bic
            best_svd_s = s
            nc_svd = nc
    P = best_P

    secondary = [p for p in cal if p != P and p > P] if cal else []
    return P, secondary, period, cal, best_svd_s, nc_svd
