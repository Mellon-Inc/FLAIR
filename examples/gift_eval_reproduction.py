#!/usr/bin/env python3
"""Reproduce FLAIR results on the GIFT-Eval benchmark (97 configurations).

Requirements:
    pip install flaircast gift-eval gluonts

Usage:
    # Set GIFT_EVAL to the dataset directory (download from HuggingFace)
    export GIFT_EVAL=/path/to/gift-eval-data
    python examples/gift_eval_reproduction.py

    # Or specify the path directly:
    python examples/gift_eval_reproduction.py --data-dir /path/to/gift-eval-data

Output:
    results/gift_eval_flair.csv — per-configuration MASE and CRPS.
    The final block prints:
      * MASE_gm / CRPS_gm : geometric mean of raw per-config metrics
      * relMASE / relCRPS : geometric mean of (model_metric / SN_metric),
        using the Seasonal Naive baseline fetched from the gift-eval
        repo (results/seasonal_naive/all_results.csv).

Expected results (flaircast v0.6.0, N_SAMPLES=200):
    relMASE = 0.8384, relCRPS = 0.5871
"""

import argparse
import hashlib
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd
from gift_eval.data import Dataset
from gluonts.ev.metrics import MASE, MeanWeightedSumQuantileLoss
from gluonts.model.forecast import SampleForecast
from gluonts.model.predictor import RepresentablePredictor

from flaircast import forecast

warnings.filterwarnings("ignore")

N_SAMPLES = 200

METRICS = [
    MASE(forecast_type=0.5),
    MeanWeightedSumQuantileLoss(
        quantile_levels=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    ),
]

DATASET_CONFIGS = [
    ("bitbrains_fast_storage", "5T", ["short", "medium", "long"]),
    ("bitbrains_fast_storage", "H", ["short"]),
    ("bitbrains_rnd", "5T", ["short", "medium", "long"]),
    ("bitbrains_rnd", "H", ["short"]),
    ("bizitobs_application", "10S", ["short", "medium", "long"]),
    ("bizitobs_l2c", "5T", ["short", "medium", "long"]),
    ("bizitobs_l2c", "H", ["short", "medium", "long"]),
    ("bizitobs_service", "10S", ["short", "medium", "long"]),
    ("car_parts", "M", ["short"]),
    ("covid_deaths", "D", ["short"]),
    ("electricity", "15T", ["short", "medium", "long"]),
    ("electricity", "D", ["short"]),
    ("electricity", "H", ["short", "medium", "long"]),
    ("electricity", "W", ["short"]),
    ("ett1", "15T", ["short", "medium", "long"]),
    ("ett1", "D", ["short"]),
    ("ett1", "H", ["short", "medium", "long"]),
    ("ett1", "W", ["short"]),
    ("ett2", "15T", ["short", "medium", "long"]),
    ("ett2", "D", ["short"]),
    ("ett2", "H", ["short", "medium", "long"]),
    ("ett2", "W", ["short"]),
    ("hierarchical_sales", "D", ["short"]),
    ("hierarchical_sales", "W", ["short"]),
    ("hospital", "M", ["short"]),
    ("jena_weather", "10T", ["short", "medium", "long"]),
    ("jena_weather", "D", ["short"]),
    ("jena_weather", "H", ["short", "medium", "long"]),
    ("kdd_cup_2018", "D", ["short"]),
    ("kdd_cup_2018", "H", ["short", "medium", "long"]),
    ("loop_seattle", "5T", ["short", "medium", "long"]),
    ("loop_seattle", "D", ["short"]),
    ("loop_seattle", "H", ["short", "medium", "long"]),
    ("m4_daily", "D", ["short"]),
    ("m4_hourly", "H", ["short"]),
    ("m4_monthly", "M", ["short"]),
    ("m4_quarterly", "Q", ["short"]),
    ("m4_weekly", "W", ["short"]),
    ("m4_yearly", "A", ["short"]),
    ("m_dense", "D", ["short"]),
    ("m_dense", "H", ["short", "medium", "long"]),
    ("restaurant", "D", ["short"]),
    ("saugeen", "D", ["short"]),
    ("saugeen", "M", ["short"]),
    ("saugeen", "W", ["short"]),
    ("solar", "10T", ["short", "medium", "long"]),
    ("solar", "D", ["short"]),
    ("solar", "H", ["short", "medium", "long"]),
    ("solar", "W", ["short"]),
    ("sz_taxi", "15T", ["short", "medium", "long"]),
    ("sz_taxi", "H", ["short"]),
    ("temperature_rain", "D", ["short"]),
    ("us_births", "D", ["short"]),
    ("us_births", "M", ["short"]),
    ("us_births", "W", ["short"]),
]

NAME_MAP = {
    "kdd_cup_2018": "kdd_cup_2018_with_missing",
    "car_parts": "car_parts_with_missing",
    "temperature_rain": "temperature_rain_with_missing",
    "loop_seattle": "LOOP_SEATTLE",
    "m_dense": "M_DENSE",
    "sz_taxi": "SZ_TAXI",
    "saugeen": "saugeenday",
}


class FLAIRPredictor(RepresentablePredictor):
    def __init__(self, prediction_length, freq_str, n_samples):
        super().__init__(prediction_length=prediction_length)
        self.freq_str = freq_str
        self.n_samples = n_samples

    def predict_item(self, item):
        target = item["target"]
        sid = int(
            hashlib.md5(str(item.get("item_id", "")).encode()).hexdigest()[:8], 16
        )
        if target.ndim == 2:
            nv, T = target.shape
            samples = np.zeros((self.n_samples, self.prediction_length, nv))
            for v in range(nv):
                samples[:, :, v] = forecast(
                    target[v],
                    self.prediction_length,
                    self.freq_str,
                    self.n_samples,
                    seed=sid + v,
                )
            start = item["start"] + T
        else:
            samples = forecast(
                target,
                self.prediction_length,
                self.freq_str,
                self.n_samples,
                seed=sid,
            )
            start = item["start"] + len(target)
        return SampleForecast(
            samples=samples,
            start_date=start,
            item_id=item.get("item_id", "unknown"),
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=None, help="Path to GIFT-Eval dataset")
    parser.add_argument(
        "--output", default="results/gift_eval_flair.csv", help="Output CSV path"
    )
    args = parser.parse_args()

    if args.data_dir:
        os.environ["GIFT_EVAL"] = args.data_dir
    if "GIFT_EVAL" not in os.environ:
        print("Set GIFT_EVAL env var or use --data-dir", file=sys.stderr)
        sys.exit(1)

    from gluonts.model import evaluate_model

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    n_total = sum(len(terms) for _, _, terms in DATASET_CONFIGS)
    results = []
    done = 0
    total_start = time.perf_counter()

    for ds_name, freq, terms in DATASET_CONFIGS:
        for term in terms:
            done += 1
            cid = f"{ds_name}/{freq}/{term}"
            load_name = NAME_MAP.get(ds_name, ds_name)
            dp = os.path.join(os.environ["GIFT_EVAL"], load_name)
            if os.path.isdir(os.path.join(dp, freq)):
                load_name = f"{load_name}/{freq}"
            try:
                dataset = Dataset(name=load_name, term=term, to_univariate=False)
            except Exception as e:
                print(f"  [{done:>3}/{n_total}] {cid:45s} SKIP ({e})")
                sys.stdout.flush()
                continue

            pred = FLAIRPredictor(dataset.prediction_length, dataset.freq, N_SAMPLES)
            t0 = time.perf_counter()
            try:
                res = evaluate_model(
                    pred,
                    test_data=dataset.test_data,
                    metrics=METRICS,
                    batch_size=5000,
                    axis=None,
                    mask_invalid_label=True,
                    allow_nan_forecast=False,
                    seasonality=None,
                )
                mase = float(res["MASE[0.5]"].iloc[0])
                crps = float(res["mean_weighted_sum_quantile_loss"].iloc[0])
            except Exception as e:
                elapsed = time.perf_counter() - t0
                print(
                    f"  [{done:>3}/{n_total}] {cid:45s} ERROR ({e}) ({elapsed:.0f}s)"
                )
                sys.stdout.flush()
                continue

            elapsed = time.perf_counter() - t0
            print(
                f"  [{done:>3}/{n_total}] {cid:45s} "
                f"MASE={mase:.4f} CRPS={crps:.4f} ({elapsed:.0f}s)"
            )
            sys.stdout.flush()
            results.append(
                {
                    "config": cid,
                    "mase": mase,
                    "crps": crps,
                    "time": elapsed,
                    "term": term,
                }
            )

    dt = time.perf_counter() - total_start
    df = pd.DataFrame(results)
    df.to_csv(args.output, index=False)
    print(f"\nSaved {args.output} ({len(df)} configs, {dt:.0f}s)")

    if len(df) > 0:
        gm = lambda x: float(np.exp(np.log(np.clip(x, 1e-10, None)).mean()))
        print(f"\nAggregate (geometric mean of raw metrics):")
        print(f"  MASE_gm = {gm(df.mase):.4f}")
        print(f"  CRPS_gm = {gm(df.crps):.4f}")

        # Fetch Seasonal Naive baseline from gift-eval repo for relMASE/relCRPS.
        # relMASE/relCRPS = geometric mean of per-config (model_metric / sn_metric).
        SN_URL = (
            "https://raw.githubusercontent.com/SalesforceAIResearch/"
            "gift-eval/main/results/seasonal_naive/all_results.csv"
        )
        try:
            sn = pd.read_csv(SN_URL)
            sn_m = dict(zip(sn["dataset"], sn["eval_metrics/MASE[0.5]"]))
            sn_c = dict(
                zip(sn["dataset"], sn["eval_metrics/mean_weighted_sum_quantile_loss"])
            )
            df["rel_mase"] = df["mase"] / df["config"].map(sn_m)
            df["rel_crps"] = df["crps"] / df["config"].map(sn_c)
            n_ok = df[["rel_mase", "rel_crps"]].notna().all(axis=1).sum()
            print(
                f"\nAggregate normalized by Seasonal Naive "
                f"(matched {n_ok}/{len(df)} configs):"
            )
            print(f"  relMASE = {gm(df.rel_mase.dropna()):.4f}")
            print(f"  relCRPS = {gm(df.rel_crps.dropna()):.4f}")
        except Exception as e:
            print(f"\n[warn] could not fetch Seasonal Naive baseline: {e}")
            print(
                "       relMASE/relCRPS require dividing each row by "
                "gift-eval/results/seasonal_naive/all_results.csv, "
                "then taking the geometric mean."
            )


if __name__ == "__main__":
    main()
