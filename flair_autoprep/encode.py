"""Rule-based DataFrame → FLAIR-ready encoder.

Depends only on pandas and numpy; never touches ``flaircast`` itself.

Public functions
----------------

* :func:`auto_encode` — convert a raw DataFrame into ``(y, X, freq, ...)``
  in one shot.
* :func:`infer_freq` — derive a FLAIR-compatible freq string from a
  DatetimeIndex.

Categorical handling is two-stage:

1. Columns listed in ``categorical_cols`` are **explicitly** one-hot
   encoded regardless of dtype. Use this when a column is numeric-typed
   but semantically categorical (e.g. ``sku_id`` stored as int).
2. Columns *not* listed are governed by the ``auto_detect`` flag:

   ==================  ====================================================
   ``auto_detect``     Behavior
   ==================  ====================================================
   ``False`` (default)  numeric/bool → kept as numeric exog, datetime →
                        used for freq inference only, object/cat → dropped
                        with a warning.
   ``True``             dtype-based auto-classification: numeric/bool →
                        numeric, object/cat → one-hot, datetime → freq.
   ==================  ====================================================

This mirrors LightGBM's ``categorical_feature='auto'`` convention: nothing
magical happens by default — auto-detection is opt-in.

Leakage detection is always on and runs in three passes:

1. Name heuristic (target tokens, ``_lag``, ``_bfr``, etc. suffixes).
2. High correlation (|corr(col, target)| ≥ ``leakage_threshold``).
3. Sum-decomposition (``target ≈ a + b`` detected via residual std).

Categorical control:

* ``min_class_support`` drops categoricals whose rarest class is too small.
* ``max_categorical_cols`` drops categoricals whose one-hot expansion is
  too wide.
"""

from __future__ import annotations

import re
import time
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

# Common token suffixes/substrings that indicate a temporally-shifted target.
_LEAK_TOKENS = (
    "_lag",
    "_bfr",
    "_before",
    "_lead",
    "_ahead",
    "_prev",
    "_next",
    "_yesterday",
    "_tomorrow",
    "_t-1",
    "_t+1",
    "_lookback",
    "_future",
)

# pandas freq alias → FLAIR-compatible freq string.
_PANDAS_TO_FLAIR_FREQ = {
    "H": "H",
    "h": "H",
    "D": "D",
    "W": "W",
    "W-SUN": "W",
    "W-MON": "W",
    "M": "M",
    "MS": "M",
    "ME": "M",
    "Q": "Q",
    "QS": "Q",
    "QE": "Q",
    "Y": "Y",
    "A": "Y",
    "YS": "Y",
    "YE": "Y",
    "AS": "Y",
    "T": "T",
    "min": "T",
    "S": "S",
}


def infer_freq(idx: pd.DatetimeIndex, hint: str | None = None) -> str:
    """Infer FLAIR-compatible freq string from a DatetimeIndex.

    Priority: explicit hint > pandas inferred freq > median diff heuristic > 'D'.
    """
    if hint:
        return hint
    try:
        f = pd.infer_freq(idx)
    except (ValueError, TypeError):
        f = None
    if f:
        # Strip multipliers ("3H" → "H"). FLAIR's _get_period also handles this,
        # but normalizing here keeps logs clean.
        base = "".join(ch for ch in f if not ch.isdigit() and ch != "-")
        # Remove anchors like "W-SUN" -> "W".
        base = base.split("-")[0]
        return _PANDAS_TO_FLAIR_FREQ.get(base, base[:1].upper() if base else "D")

    # Heuristic fallback by median delta.
    if len(idx) < 2:
        return "D"
    delta = (idx[1:] - idx[:-1]).to_series().median()
    seconds = delta.total_seconds()
    if seconds < 90:
        return "T"
    if seconds < 90 * 60:
        return "H"
    if seconds < 36 * 3600:
        return "D"
    if seconds < 9 * 86400:
        return "W"
    if seconds < 35 * 86400:
        return "M"
    if seconds < 100 * 86400:
        return "Q"
    return "Y"


def _classify_column(series: pd.Series) -> str:
    """Return one of: 'numeric', 'binary', 'categorical', 'datetime', 'drop'."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_bool_dtype(series):
        return "binary"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if isinstance(series.dtype, pd.CategoricalDtype) or pd.api.types.is_string_dtype(series):
        nunique = series.nunique(dropna=True)
        if nunique <= 1:
            return "drop"  # constant or all-NaN string
        return "categorical"
    return "drop"


def _is_leak_by_name(col: str, target: str) -> bool:
    """Heuristic: column name contains target as a token, or has time-shift suffix."""
    col_l = col.lower()
    tgt_l = target.lower()
    if col_l == tgt_l:
        return False
    if re.search(rf"\b{re.escape(tgt_l)}\b", col_l):
        return True
    return any(tok in col_l for tok in _LEAK_TOKENS)


def _detect_leakage(
    df: pd.DataFrame,
    target_col: str,
    candidate_cols: list[str],
    threshold: float = 0.99,
    sum_identity_tol: float = 0.01,
    max_pair_check: int = 30,
) -> tuple[list[str], list[str]]:
    """Detect three classes of leakage. Returns ``(leaky_cols, reasons)``.

    1. Algebraic identity        : |corr(col, target)| ≥ threshold
    2. Name-based heuristic      : column name contains target token,
                                   or has _lag/_bfr/_lead/_ahead/... suffix
    3. Sum-decomposition identity: target ≈ a + b for some pair
                                   (residual std / target std < tol)

    The pair check is O(k²) but capped at ``max_pair_check`` columns
    sorted by |corr| with target to keep cost bounded for wide frames.
    """
    leaky: list[str] = []
    reasons: list[str] = []

    y = df[target_col]
    y_is_numeric = pd.api.types.is_numeric_dtype(y)
    y_num = pd.to_numeric(y, errors="coerce") if y_is_numeric else None

    # Pass 1: name heuristic (works on any dtype).
    for col in candidate_cols:
        if _is_leak_by_name(col, target_col):
            leaky.append(col)
            reasons.append(f"{col} (name)")

    # Pass 2: |corr| ≥ threshold.
    if y_is_numeric:
        corrs: list[tuple[str, float]] = []
        for col in candidate_cols:
            if col in leaky:
                continue
            s = df[col]
            if not pd.api.types.is_numeric_dtype(s):
                continue
            try:
                r = float(pd.to_numeric(s, errors="coerce").corr(y_num))
            except (ValueError, TypeError):
                continue
            if np.isfinite(r):
                corrs.append((col, r))
                if abs(r) >= threshold:
                    leaky.append(col)
                    reasons.append(f"{col} (|r|={abs(r):.3f})")

        # Pass 3: pair sum identity. Restrict to top-K by |corr| for speed.
        candidates_for_pair = sorted(corrs, key=lambda kv: -abs(kv[1]))[:max_pair_check]
        cand_names = [c for c, _ in candidates_for_pair if c not in leaky]
        y_std = float(y_num.std())
        if y_std > 0 and len(cand_names) >= 2:
            for a, b in combinations(cand_names, 2):
                if a in leaky or b in leaky:
                    continue
                resid = y_num - (df[a].astype(float) + df[b].astype(float))
                if not np.isfinite(resid).any():
                    continue
                rel = float(resid.std()) / y_std
                if rel < sum_identity_tol:
                    leaky.extend([a, b])
                    reasons.extend([f"{a} (sum-id with {b})", f"{b} (sum-id with {a})"])

    # De-duplicate while preserving order.
    seen: set[str] = set()
    leaky_unique: list[str] = []
    reasons_unique: list[str] = []
    for col, why in zip(leaky, reasons):
        if col not in seen:
            seen.add(col)
            leaky_unique.append(col)
            reasons_unique.append(why)
    return leaky_unique, reasons_unique


def auto_encode(
    df: pd.DataFrame,
    target_col: str,
    datetime_col: str | None = None,
    drop_cols: list[str] | None = None,
    freq_hint: str | None = None,
    categorical_cols: list[str] | None = None,
    auto_detect: bool = False,
    leakage_threshold: float = 0.99,
    min_class_support: int = 1,
    max_categorical_cols: int | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Encode a raw DataFrame into FLAIR-ready arrays.

    Parameters
    ----------
    df : pandas DataFrame
        Raw input (any column dtypes).
    target_col : str
        Name of the target series.
    datetime_col : str, optional
        Name of the datetime column. If None, attempts to use the
        DataFrame index when it's a DatetimeIndex.
    drop_cols : list[str], optional
        Columns to drop unconditionally (e.g. duplicate IDs). If a column
        appears in both ``drop_cols`` and ``categorical_cols``, drop wins.
    freq_hint : str, optional
        Explicit freq override ('H', 'D', etc.).
    categorical_cols : list[str], optional
        Columns to **explicitly** treat as categorical (one-hot encoded)
        regardless of dtype. Use this when a column is numeric-typed but
        semantically categorical (e.g. ``sku_id`` stored as int). Unknown
        column names raise ``KeyError``; the target column is not allowed.
    auto_detect : bool
        When ``True``, columns *not* listed in ``categorical_cols`` are
        classified by dtype (numeric → numeric, object/cat → one-hot).
        When ``False`` (default), only ``categorical_cols`` are one-hot
        encoded; object/string columns not in the list are dropped with
        a warning. Mirrors LightGBM's ``categorical_feature='auto'`` opt-in.
    leakage_threshold : float
        |corr| threshold for the algebraic-identity leakage check.
    min_class_support : int
        Drop categorical columns whose rarest class has fewer than this many
        samples. ``1`` keeps all categoricals (default).
    max_categorical_cols : int, optional
        Drop categorical columns whose one-hot expansion would exceed this
        many columns. None disables the filter.
    verbose : bool
        Print a one-line classification summary (default ``False``).

    Returns
    -------
    dict with keys:
        ``y``       : (n,) float ndarray, target series (NaN preserved for
                      downstream FLAIR interpolation).
        ``X``       : (n, k) float ndarray of encoded exog. NaN preserved.
        ``freq``    : FLAIR-compatible freq string.
        ``cols``    : list of encoded column names (length k).
        ``report``  : dict with per-column classification.
        ``leaky``   : list of columns dropped for high target correlation.
        ``leak_reasons`` : list of reason strings, parallel to ``leaky``.
        ``filtered_low_support`` : list of columns dropped because the
                      minimum per-class count was below ``min_class_support``.
        ``filtered_high_cardinality`` : list of columns dropped because
                      their one-hot expansion would exceed ``max_categorical_cols``.
        ``filtered_unspecified_str`` : list of object/string columns dropped
                      because they were not in ``categorical_cols`` and
                      ``auto_detect=False``.
        ``dummy_cols``  : set of one-hot column names (for type-aware gating).
        ``numeric_cols`` : set of numeric/binary column names.
        ``elapsed`` : seconds spent in this function.

    Notes
    -----
    The failure-case analysis on Bike Sharing showed that high-cardinality
    calendar dummies (e.g. monthly with 11 dummy columns and only ~30
    training samples per class) cause regime-shift forecasting failures.
    Setting ``max_categorical_cols=10`` drops these while preserving
    lower-cardinality dummies (weekday=6, season=3, weather=2).
    """
    t0 = time.perf_counter()
    drop_cols = list(drop_cols or [])
    categorical_cols_set = set(categorical_cols or [])

    unknown_cat = categorical_cols_set - set(df.columns)
    if unknown_cat:
        raise KeyError(
            f"categorical_cols contains columns not in DataFrame: {sorted(unknown_cat)}"
        )
    if target_col in categorical_cols_set:
        raise KeyError(f"categorical_cols cannot include the target column '{target_col}'")

    # 1. Establish a datetime index if possible.
    if datetime_col is not None and datetime_col in df.columns:
        df = df.copy()
        df[datetime_col] = pd.to_datetime(df[datetime_col], errors="coerce")
        df = df.set_index(datetime_col).sort_index()
    elif isinstance(df.index, pd.DatetimeIndex):
        df = df.sort_index()

    # 2. Frequency inference.
    if isinstance(df.index, pd.DatetimeIndex):
        freq = infer_freq(df.index, hint=freq_hint)
    else:
        freq = freq_hint or "D"

    # 3. Target.
    if target_col not in df.columns:
        raise KeyError(f"target_col '{target_col}' not found in DataFrame")
    y = df[target_col].astype(float).to_numpy()

    # 3a. Leakage detection (name heuristic + corr + sum identity).
    candidate_cols = [c for c in df.columns if c != target_col and c not in drop_cols]
    leaky_cols, leak_reasons = _detect_leakage(
        df, target_col, candidate_cols, threshold=leakage_threshold
    )
    drop_cols = list(drop_cols) + leaky_cols

    # 4. Classify and encode every remaining column.
    encoded: list[np.ndarray] = []
    encoded_names: list[str] = []
    report: dict[str, str] = {}
    filtered_low_support: list[str] = []
    filtered_high_cardinality: list[str] = []
    filtered_unspecified_str: list[str] = []
    dummy_cols: set[str] = set()
    numeric_cols: set[str] = set()
    for col in df.columns:
        if col == target_col or col in drop_cols:
            continue

        if col in categorical_cols_set:
            # Explicit override: force categorical regardless of dtype.
            kind = "categorical"
        else:
            dtype_kind = _classify_column(df[col])
            if not auto_detect and dtype_kind == "categorical":
                # Default mode: object/str columns must be opt-in via
                # categorical_cols. Drop and report.
                filtered_unspecified_str.append(col)
                report[col] = "filtered_unspecified_str"
                continue
            kind = dtype_kind
        report[col] = kind

        if kind == "drop" or kind == "datetime":
            continue

        if kind in ("numeric", "binary"):
            encoded.append(df[col].astype(float).to_numpy()[:, None])
            encoded_names.append(col)
            numeric_cols.add(col)
        elif kind == "categorical":
            # Filter A: drop categoricals where the rarest class has < N samples.
            counts = df[col].value_counts(dropna=True)
            if len(counts) and int(counts.min()) < min_class_support:
                filtered_low_support.append(col)
                report[col] = "filtered_low_support"
                continue
            # drop_first=True handles binary categoricals economically
            # (a 2-value column becomes 1 indicator).
            dummies = pd.get_dummies(df[col], prefix=col, drop_first=True, dummy_na=False)
            if dummies.shape[1] == 0:
                continue
            # Filter B: drop categoricals whose one-hot expansion is too wide.
            if max_categorical_cols is not None and dummies.shape[1] > max_categorical_cols:
                filtered_high_cardinality.append(col)
                report[col] = "filtered_high_cardinality"
                continue
            encoded.append(dummies.astype(float).to_numpy())
            encoded_names.extend(dummies.columns.tolist())
            dummy_cols.update(dummies.columns.tolist())

    X = np.column_stack(encoded) if encoded else np.zeros((len(y), 0))

    elapsed = time.perf_counter() - t0

    if verbose:
        print(
            f"[auto_encode] freq={freq}  rows={len(y)}  "
            f"target={target_col}  exog_cols={len(encoded_names)}  "
            f"elapsed={elapsed * 1000:.1f}ms"
        )
        kind_counts: dict[str, int] = {}
        for k in report.values():
            kind_counts[k] = kind_counts.get(k, 0) + 1
        print(f"[auto_encode] column kinds: {kind_counts}")
        if leaky_cols:
            print("[auto_encode] dropped (leakage):")
            for r in leak_reasons:
                print(f"    - {r}")
        if filtered_low_support:
            print(
                f"[auto_encode] dropped (min_class_support<{min_class_support}): "
                f"{filtered_low_support}"
            )
        if filtered_high_cardinality:
            print(
                f"[auto_encode] dropped (one-hot expansion > {max_categorical_cols}): "
                f"{filtered_high_cardinality}"
            )
        if filtered_unspecified_str:
            print(
                "[auto_encode] dropped (object/str cols not in categorical_cols, "
                f"auto_detect=False): {filtered_unspecified_str}"
            )

    return {
        "y": y,
        "X": X,
        "freq": freq,
        "cols": encoded_names,
        "report": report,
        "leaky": leaky_cols,
        "leak_reasons": leak_reasons,
        "filtered_low_support": filtered_low_support,
        "filtered_high_cardinality": filtered_high_cardinality,
        "filtered_unspecified_str": filtered_unspecified_str,
        "dummy_cols": dummy_cols,
        "numeric_cols": numeric_cols,
        "elapsed": elapsed,
    }
