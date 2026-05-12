"""Auto-preprocessing layer for FLAIR forecast.

A thin pandas wrapper that takes raw DataFrames and produces FLAIR-ready
arrays. The package focuses on three things:

* :class:`FLAIRPipeline` — pass a raw DataFrame plus the target column
  name, get probabilistic forecast samples back. Handles one-hot
  encoding, frequency inference, and leakage detection internally.
* :func:`auto_encode` — the lower-level encoder used by the pipeline.
  Returns ``{"y": ndarray, "X": ndarray, "cols": [...], "freq": str, ...}``.
* :func:`infer_freq` — derive a FLAIR-compatible frequency string from
  a DatetimeIndex.

Per-origin gating and residual correction (formerly
``residual_gate_forecast`` and friends) live outside the package as a
recipe in ``examples/gating_recipe.py``. They are useful for datasets
with year-on-year regime shifts (e.g. Bike Sharing) but are not part
of the core API.
"""

from __future__ import annotations

from .encode import auto_encode, infer_freq
from .pipeline import FLAIRPipeline, PipelineResult

__all__ = [
    "FLAIRPipeline",
    "PipelineResult",
    "auto_encode",
    "infer_freq",
]

__version__ = "0.1.0"
