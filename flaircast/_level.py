"""Level forecasting primitives.

This module hosts the per-period Level pipeline:

- Box-Cox transform (`_bc_lambda`, `_bc`, `_bc_inv`)
- Ridge regression with LOOCV soft-average and LWCP normalization
  (`_ridge_sa`)
- Gavish-Donoho 2014 optimal Frobenius shrinkage of the rank-1 singular
  value of the period-folded snapshot (`_optshrink_rank1`)
- Damped-trend coefficient estimator (`_estimate_phi`)

The Level itself (per-period sums of the period-folded matrix) is built
inside `_forecast`; this module provides the operators that act on it.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import quad
from scipy.optimize import brentq
from scipy.stats import boxcox as scipy_boxcox

from ._constants import (
    _ALPHA_LOG_MAX,
    _ALPHA_LOG_MIN,
    _BC_EXP_CLIP,
    _EPS,
    _EPS_BOXCOX,
    _EPS_WEIGHT,
    _MIN_POSITIVE_FOR_BC,
    _N_ALPHAS,
)

# ── Box-Cox ─────────────────────────────────────────────────────────────


def _bc_lambda(y: NDArray[np.floating]) -> float:
    """Estimate Box-Cox lambda, clipped to `[0, 1]` and falling back to 1.0.

    The clip keeps the recovered Level on a stable scale: `lam = 0` is
    log, `lam = 1` is identity, intermediate values smoothly interpolate.
    """
    yp = y[y > 0]
    if len(yp) < _MIN_POSITIVE_FOR_BC:
        return 1.0
    try:
        _, lam = scipy_boxcox(yp)
        return float(np.clip(lam, 0.0, 1.0))
    except (ValueError, RuntimeError):
        return 1.0


def _bc(y: NDArray[np.floating], lam: float) -> NDArray[np.floating]:
    """Forward Box-Cox with `lam = 0` short-circuited to `log`."""
    y = np.maximum(y, _EPS_BOXCOX)
    return np.log(y) if lam == 0.0 else (y**lam - 1) / lam


def _bc_inv(z: NDArray[np.floating], lam: float) -> NDArray[np.floating]:
    """Inverse Box-Cox; clips the `exp` argument when `lam = 0`."""
    if lam == 0.0:
        return np.exp(np.clip(z, -_BC_EXP_CLIP, _BC_EXP_CLIP))
    return np.maximum(z * lam + 1, _EPS) ** (1 / lam)


# ── Ridge with Soft-Average GCV ────────────────────────────────────────


def _ridge_sa(
    X: NDArray[np.floating],
    y: NDArray[np.floating],
) -> tuple[
    NDArray[np.floating],
    NDArray[np.floating],
    float,
    NDArray[np.floating],
    NDArray[np.floating],
    NDArray[np.floating],
]:
    """Ridge regression with LOOCV soft-average over 25 log-spaced alphas.

    Under the LSR1 model, this is local linear regression at the boundary
    `u = 1` with bandwidth `h = ∞` (global fit).  The regularization
    `alpha` is selected by LOOCV soft-averaging — a single SVD covers all
    alphas, so the cost is constant in the grid size.

    Returns
    -------
    beta : ndarray, shape (p,)
        Soft-averaged coefficient vector.
    loo : ndarray, shape (n,)
        LWCP-normalized LOO residuals: `e_i^LOO / sqrt(1 + h_ii)`.
        Under LWCP (Fadnavis et al., 2026), this normalization removes
        leverage-dependent heteroscedasticity, producing approximately
        exchangeable scores.  The test-point interval is then scaled by
        `sqrt(1 + h_test)` per horizon to restore the correct variance.
    gcv_min : float
        Minimum GCV across the alpha grid (used for the softmax temperature).
    Vt, s : ndarray
        Right singular vectors and singular values from the single SVD.
    d_avg : ndarray, shape (rank,)
        Soft-averaged spectral filter `s² / (s² + α)`; its sum is the
        effective Ridge degrees of freedom `tr(H)`.
    """
    U, s, Vt = np.linalg.svd(X, full_matrices=False)
    s2, Uty = s**2, U.T @ y
    alphas = np.logspace(_ALPHA_LOG_MIN, _ALPHA_LOG_MAX, _N_ALPHAS)

    # LOOCV for each alpha
    gcv = np.empty(len(alphas))
    for i, a in enumerate(alphas):
        d = s2 / (s2 + a)
        h = (U**2) @ d
        r = y - U @ (d * Uty)
        gcv[i] = np.mean((r / np.maximum(1 - h, _EPS)) ** 2)

    # Softmax weights (temperature = gcv_min)
    gcv_min = gcv.min()
    log_w = -(gcv - gcv_min) / max(gcv_min, _EPS)
    log_w -= log_w.max()
    w = np.exp(log_w)
    w /= w.sum()

    # Weighted-average beta and hat-matrix diagonal
    beta = np.zeros(X.shape[1])
    d_avg = np.zeros(len(s))
    for wi, a in zip(w, alphas):
        if wi < _EPS_WEIGHT:
            continue
        d = s2 / (s2 + a)
        beta += wi * (Vt.T @ (d * Uty / np.maximum(s, _EPS)))
        d_avg += wi * d

    # LWCP-normalized LOO residuals (see docstring above).
    residuals = y - X @ beta
    h_avg = (U**2) @ d_avg
    loo_raw = residuals / np.maximum(1 - h_avg, _EPS)
    loo = loo_raw / np.sqrt(np.maximum(1 + h_avg, _EPS))

    return beta, loo, gcv_min, Vt, s, d_avg


# ── Gavish-Donoho 2014 optimal Frobenius shrinkage ─────────────────────


@lru_cache(maxsize=128)
def _mp_median(beta: float) -> float:
    """Median of the Marchenko–Pastur distribution at aspect ratio ``β``.

    The MP density on ``[y_-, y_+]`` with ``y_± = (1 ± √β)²`` is

        ρ(y) = √((y_+ − y)(y − y_-)) / (2π β y),

    and the median ``μ_β`` is the unique value in ``(y_-, y_+)`` whose
    cumulative density equals ``0.5``.  No closed form exists; we solve
    the implicit equation numerically and cache the result per ``β``.

    Used by Gavish–Donoho's median-based noise estimator
    ``σ̂ = σ_med / √μ_β`` (see :func:`_optshrink_rank1`).
    """
    if beta <= _EPS:
        return 1.0
    b = min(beta, 1.0)
    y_minus = (1.0 - np.sqrt(b)) ** 2
    y_plus = (1.0 + np.sqrt(b)) ** 2

    def density(y: float) -> float:
        if y <= y_minus or y >= y_plus:
            return 0.0
        return float(np.sqrt((y_plus - y) * (y - y_minus)) / (2.0 * np.pi * b * y))

    def cdf_minus_half(m: float) -> float:
        c, _ = quad(density, y_minus, m, limit=100)
        return c - 0.5

    return float(brentq(cdf_minus_half, y_minus + _EPS, y_plus - _EPS, xtol=1e-8))


def _rank1_svd_summary(
    mat: NDArray[np.floating],
) -> tuple[float, float, NDArray[np.floating]]:
    """Single SVD pass that returns the three rank-1 quantities FLAIR uses.

    Returns
    -------
    factor : float
        Gavish-Donoho 2014 optimal Frobenius shrinkage factor in
        ``(0, 1]`` (or ``1.0`` for degenerate spectra).  Multiplying
        ``L`` by this factor yields the minimax-optimal rank-1
        reconstruction under the spiked rectangular model.
    sigma_noise : float
        Marchenko-Pastur median-based noise scale ``σ_med / √μ_β``.
        Used by the phase-noise sampler as the natural floor for the
        rank-1 magnitude denominator (replaces the legacy
        ``0.1 · median(|fitted|)`` clamp).
    rank1 : ndarray, shape (P, n_c)
        ``σ₁ u₁ v₁ᵀ`` — the rank-1 signal magnitude that defines the
        scale-invariant phase-noise denominator.

    All three quantities come from a single
    ``np.linalg.svd(mat, full_matrices=False)`` call so the SVD is
    computed exactly once per forecast.

    Returns the safe defaults ``(1.0, _EPS, S_proxy_zero)`` when ``mat``
    is degenerate (``min(P, n_c) < 2`` or ``σ₁ ≈ 0``); the call sites
    use these unconditionally as multiplicative factors / floors.
    """
    P, nc = mat.shape
    if min(P, nc) < 2:
        return 1.0, _EPS_BOXCOX, np.zeros_like(mat)
    U, s, Vt = np.linalg.svd(mat, full_matrices=False)
    sigma_1 = float(s[0])
    if sigma_1 < _EPS:
        return 1.0, _EPS_BOXCOX, np.zeros_like(mat)
    rank1 = sigma_1 * np.outer(U[:, 0], Vt[0, :])
    sigma_med = float(np.median(s))
    if sigma_med < _EPS:
        return 1.0, _EPS_BOXCOX, rank1
    beta = min(P, nc) / max(P, nc)
    mu_beta = _mp_median(round(beta, 4))
    sigma_noise = sigma_med / np.sqrt(mu_beta)
    # Gavish-Donoho 2014 Theorem 1: optimal Frobenius shrinker.
    threshold = (1.0 + np.sqrt(beta)) * sigma_noise
    if sigma_1 <= threshold:
        return 1.0, sigma_noise, rank1  # subcritical fallback (BIC
        # already guarantees rank-1 is present in the chosen P)
    inner = (sigma_1**2 - (1.0 + beta) * sigma_noise**2) ** 2 - 4.0 * beta * sigma_noise**4
    if inner <= 0.0:
        return 1.0, sigma_noise, rank1
    sigma_1_shrunk = float(np.sqrt(inner) / sigma_1)
    factor = float(np.clip(sigma_1_shrunk / sigma_1, _EPS, 1.0))
    return factor, sigma_noise, rank1


# ── Damped trend (LSR1 boundary extrapolation) ─────────────────────────


def _estimate_phi(L_bc: NDArray[np.floating]) -> float:
    """Estimate the trend damping factor from `lag-1 autocorr(diff(L_bc))`.

    Under the LSR1 model, `L ∈ Hölder(2)` so the trend change rate is
    bounded.  `phi = max(rho_1(ΔL), 0)` measures trend persistence:
    `phi > 0` means the trend is self-reinforcing; `phi = 0` means
    mean-reverting or noisy, warranting full damping of the linear
    extrapolation.
    """
    dL = np.diff(L_bc)
    if len(dL) < 5:
        return 0.0
    dL_c = dL - dL.mean()
    c0 = float(np.dot(dL_c, dL_c))
    if c0 < _EPS:
        return 0.0
    c1 = float(np.dot(dL_c[:-1], dL_c[1:]))
    return max(c1 / c0, 0.0)
