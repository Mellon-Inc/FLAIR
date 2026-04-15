"""Calendar tables and pandas-style frequency string resolution.

`FREQ_TO_PERIOD` and `FREQ_TO_PERIODS` are part of the public API and
get re-exported from the package root in `flaircast/__init__.py`.

`_resolve_freq`, `_get_period`, `_get_periods` are private helpers used
by `_period._select_period` and the test suite.
"""

from __future__ import annotations

# Primary period for each pandas-style frequency string.
FREQ_TO_PERIOD = {
    "S": 60,
    "T": 60,
    "5T": 12,
    "10T": 6,
    "15T": 4,
    "30T": 48,
    "10S": 6,
    "H": 24,
    "D": 7,
    "W": 52,
    "M": 12,
    "Q": 4,
    "A": 1,
    "Y": 1,
}

# MDL candidate periods (primary + plausible secondary periodicities).
# `_period._select_period` picks the best of these via BIC on the SVD
# spectrum of the period-folded matrix.
FREQ_TO_PERIODS = {
    "10S": [6, 360],
    "S": [60],
    "5T": [12, 288],
    "10T": [6, 144],
    "15T": [4, 96],
    "30T": [48, 336],
    "H": [24, 168],
    "D": [7, 365],
    "W": [52],
    "M": [12],
    "Q": [4],
    "A": [],
    "Y": [],
}


def _resolve_freq(freq: str) -> str:
    """Normalize a pandas-style frequency string for table lookup.

    Handles three classes of aliases that would otherwise miss the table:

    1. Modern ``MIN`` suffix → legacy ``T`` (e.g. ``30min`` → ``30T``).
    2. pandas 2.2+ end-of-period (``ME``, ``QE``, ``YE``) and
       start-of-period (``MS``, ``QS``, ``YS``, ``AS``, ``BMS`` etc.)
       aliases → their legacy single-letter equivalents.
    3. Offset anchors (``W-SUN``, ``Q-DEC``, ``QE-DEC``) → base letter.
    """
    f = freq.upper().replace("MIN", "T")
    # 1. Strip offset anchors first: "QE-DEC" → "QE", "W-SUN" → "W".
    if "-" in f:
        f = f.split("-")[0]
    # 2. Strip pandas 2.2+ end/start-of-period suffixes:
    #    "ME" → "M", "QE" → "Q", "MS" → "M", etc.
    for suffix, base in (("ME", "M"), ("QE", "Q"), ("YE", "Y"),
                         ("MS", "M"), ("QS", "Q"), ("YS", "Y"), ("AS", "A")):
        if f == suffix:
            return base
        if len(f) > len(suffix) and f.endswith(suffix):
            f = f[: -len(suffix)] + base
            break
    return f


def _get_period(freq: str) -> int:
    """Look up the primary period for a frequency string.

    Falls back to a longest-suffix match for compound frequencies (e.g.
    `2H` → matches the `H` entry).  Returns `1` when nothing matches.
    """
    f = _resolve_freq(freq)
    if f in FREQ_TO_PERIOD:
        return FREQ_TO_PERIOD[f]
    for k in sorted(FREQ_TO_PERIOD, key=len, reverse=True):
        if f.endswith(k):
            return FREQ_TO_PERIOD[k]
    return 1


def _get_periods(freq: str) -> list[int]:
    """Look up the MDL candidate period list for a frequency string."""
    f = _resolve_freq(freq)
    if f in FREQ_TO_PERIODS:
        return list(FREQ_TO_PERIODS[f])
    for k in sorted(FREQ_TO_PERIODS, key=len, reverse=True):
        if f.endswith(k):
            return list(FREQ_TO_PERIODS[k])
    return []
