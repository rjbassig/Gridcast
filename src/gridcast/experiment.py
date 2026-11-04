"""Quarterly expanding-origin evaluation with purged calibration and held-out test."""

import hashlib
import json
import logging
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from gridcast.data import series
from gridcast.evaluation import block_interval, conformal_radius, metrics
from gridcast.features import features, training_mask
from gridcast.models import build

log = logging.getLogger(__name__)
BASELINES = ["persistence", "seasonal_naive", "historical_mean", "calendar_mean"]


def run(root: Path, cfg: dict) -> dict:
    c = cfg["experiment"]
    folder = root / "artifacts"
    folder.mkdir(exist_ok=True)
    results = root / "experiments/results"
    results.mkdir(parents=True, exist_ok=True)
    config_hash = hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()
    quality = json.loads((root / "data/processed/quality.json").read_text())
    scores, registry, prediction_frames, importances, choices = [], [], [], [], {}
    validation_start = pd.Timestamp(c["validation_start"], tz="UTC")
    test_start = pd.Timestamp(c["test_start"], tz="UTC")
    folds = pd.date_range(validation_start, pd.Timestamp(cfg["data"]["end"], tz="UTC"), freq="3MS")
    for target in ["demand", "price"]:
        y = series(root, target)
        delay = cfg["availability"][f"{target}_delay_hours"]
        for horizon in c["horizons"]:
            complete = features(y, horizon, delay).dropna()
            columns = [col for col in complete if col not in ["label", "label_time"]]
            models = BASELINES + ["ridge_1", "ridge_100"] + [n for n in c["models"] if n != "ridge"]
            key = f"{target}_{horizon}"
            validation_scores = []
            for fold_index, begin in enumerate(folds[:-1]):
                end = folds[fold_index + 1]
                split = "validation" if begin < test_start else "test"
                if split == "test" and key not in choices:
                    selection = pd.DataFrame(validation_scores).groupby("model").mae.mean().sort_values()
                    choices[key] = selection.index[0]
                    (results / "selection_frozen.json").write_text(
                        json.dumps({"selection": choices, "config_sha256": config_hash}, indent=2)
                    )
                calibration_start = begin - pd.Timedelta(hours=c["calibration_hours"] + horizon + delay)
                calibration_end = begin - pd.Timedelta(hours=horizon + delay)
                # Labels used to fit are published before calibration starts; calibration labels before fold starts.
                fit = complete.loc[training_mask(complete, calibration_start, delay)].iloc[
                    :: c["train_stride"]
                ]
                calibration = complete.loc[
                    (complete.index >= calibration_start) & (complete.index < calibration_end)
                ]
                test = complete.loc[
                    (complete.index >= begin) & (complete.index < end) & (complete.label_time < end)
                ]
                if (
                    len(fit) * c["train_stride"] < c["minimum_train_hours"]
                    or len(calibration) < 100
                    or test.empty
                ):
                    raise ValueError("Insufficient fit/calibration/evaluation data")
                assert (fit.label_time + pd.Timedelta(hours=delay)).max() <= calibration.index.min()
                assert (calibration.label_time + pd.Timedelta(hours=delay)).max() <= begin
                # MASE denominator uses only pre-fold observations and never test labels.
                past = y.loc[y.index + pd.Timedelta(hours=delay) <= begin]
                scale = float((past - past.shift(168)).abs().mean())
                peak_threshold = float(past.quantile(0.95))
                volatility_threshold = float(past.diff().abs().quantile(0.95))
                local = fit.label_time.dt.tz_convert("America/Los_Angeles")
                calendar = fit.groupby([local.dt.day_of_week, local.dt.hour]).label.mean().to_dict()
                for name in models:
                    started = time.perf_counter()
                    model = None

                    def baseline(frame, name=name, delay=delay, fit=fit, calendar=calendar):
                        if name == "persistence":
                            return frame[f"lag_{delay}h"].to_numpy()
                        if name == "seasonal_naive":
                            return frame.seasonal_anchor.to_numpy()
                        if name == "historical_mean":
                            return np.full(len(frame), fit.label.mean())
                        lt = frame.label_time.dt.tz_convert("America/Los_Angeles")
                        return np.array(
                            [
                                calendar.get((d, h), fit.label.mean())
                                for d, h in zip(lt.dt.day_of_week, lt.dt.hour)
                            ]
                        )

                    if name in BASELINES:
                        cp, predictions = baseline(calibration), baseline(test)
                    else:
                        alpha = float(name.split("_")[-1]) if name.startswith("ridge_") else 100
                        model = build("ridge" if name.startswith("ridge_") else name, c, alpha)
                        model.fit(fit[columns], fit.label)
                        cp = model.predict(calibration[columns])
                        predictions = model.predict(test[columns])
                    seconds = time.perf_counter() - started
                    radius = conformal_radius(calibration.label.to_numpy() - cp, c["coverage"])
                    row = {
                        "target": target,
                        "horizon": horizon,
                        "model": name,
                        "fold": str(begin),
                        "split": split,
                        "training_seconds": seconds,
                        "coverage": float((np.abs(test.label.to_numpy() - predictions) <= radius).mean()),
                        "interval_radius": radius,
                        **metrics(test.label, predictions, scale),
                    }
                    scores.append(row)
                    if split == "validation":
                        validation_scores.append(row)
                    artifact_name = f"{key}_{begin:%Y%m%d}_{name}"
                    metadata = {
                        **row,
                        "id": artifact_name,
                        "feature_names": columns,
                        "fit_labels_available_by": str((fit.label_time + pd.Timedelta(hours=delay)).max()),
                        "calibration_start": str(calibration.index.min()),
                        "calibration_labels_available_by": str(
                            (calibration.label_time + pd.Timedelta(hours=delay)).max()
                        ),
                        "eligible_start": str(begin),
                        "eligible_end": str(end),
                        "dataset_sha256": quality["targets"][target]["dataset_sha256"],
                        "config_sha256": config_hash,
                        "train_samples": len(fit),
                        "calibration_samples": len(calibration),
                        "seed": c["seed"],
                        "parameters": json.loads(
                            json.dumps(model.get_params(), default=str), parse_constant=lambda _: None
                        )
                        if hasattr(model, "get_params")
                        else {},
                        "baseline_mean": float(fit.label.mean()),
                        "calendar": {f"{d}_{h}": float(v) for (d, h), v in calendar.items()},
                    }
                    # Save inference state for every replayable test fold, no browser access to artifacts.
                    if model is not None and split == "test":
                        joblib.dump(model, folder / f"{artifact_name}.joblib")
                    registry.append(metadata)
                    p = pd.DataFrame(
                        {
                            "issue_time": test.index,
                            "target_time": test.label_time,
                            "actual": test.label,
                            "prediction": predictions,
                            "lower": predictions - radius,
                            "upper": predictions + radius,
                            "target": target,
                            "horizon": horizon,
                            "model": name,
                            "fold": str(begin),
                            "split": split,
                            "artifact_id": artifact_name,
                            "peak": test.label.to_numpy() >= peak_threshold,
                            "spike": (
                                y.diff().abs().reindex(pd.DatetimeIndex(test.label_time)).to_numpy()
                                >= volatility_threshold
                            ),
                        }
                    )
                    prediction_frames.append(p.reset_index(drop=True))
                    if model is not None and split == "validation" and fold_index == 1:
                        sample = calibration[columns].iloc[::12]
                        importance = permutation_importance(
                            model,
                            sample,
                            calibration.label.iloc[::12],
                            scoring="neg_mean_absolute_error",
                            n_repeats=3,
                            random_state=c["seed"],
                            n_jobs=1,
                        )
                        importances.extend(
                            {
                                "target": target,
                                "horizon": horizon,
                                "model": name,
                                "feature": f,
                                "mae_increase": float(v),
                                "std": float(s),
                            }
                            for f, v, s in zip(
                                columns, importance.importances_mean, importance.importances_std
                            )
                        )
                    log.info(
                        "%s %sh %s %s %s MAE %.3f", target, horizon, begin.date(), split, name, row["mae"]
                    )
            # Persist each completed target/horizon for crash recovery and inspection.
            pd.DataFrame(scores).to_csv(results / "fold_metrics.csv", index=False)
    all_predictions = pd.concat(prediction_frames, ignore_index=True)
    all_predictions.to_parquet(results / "predictions.parquet", index=False)
    pd.DataFrame(importances).to_csv(results / "importance.csv", index=False)
    leaderboard, segments = [], []
    for (target, horizon, name, split), p in all_predictions.groupby(["target", "horizon", "model", "split"]):
        y = series(root, target)
        training = y.loc[y.index < (validation_start if split == "validation" else test_start)]
        scale = float((training - training.shift(168)).abs().mean())
        result = {
            "target": target,
            "horizon": int(horizon),
            "model": name,
            "split": split,
            "selected_on_validation": choices[f"{target}_{horizon}"] == name,
            **metrics(p.actual, p.prediction, scale),
            "coverage": float(((p.actual >= p.lower) & (p.actual <= p.upper)).mean()),
            "mean_interval_width": float((p.upper - p.lower).mean()),
            "mae_ci95": block_interval(p.prediction - p.actual),
            "training_seconds": sum(
                r["training_seconds"]
                for r in scores
                if r["target"] == target
                and r["horizon"] == horizon
                and r["model"] == name
                and r["split"] == split
            ),
        }
        leaderboard.append(result)
        local = p.target_time.dt.tz_convert("America/Los_Angeles")
        season = local.dt.month.map(
            {
                12: "winter",
                1: "winter",
                2: "winter",
                3: "spring",
                4: "spring",
                5: "spring",
                6: "summer",
                7: "summer",
                8: "summer",
                9: "fall",
                10: "fall",
                11: "fall",
            }
        )
        groups = {
            "season": season,
            "hour": local.dt.hour.astype(str),
            "day_type": np.where(local.dt.day_of_week >= 5, "weekend", "weekday"),
            "event": np.where(p.peak, "high_value", "ordinary"),
            "volatility": np.where(p.spike, "large_hourly_change", "ordinary"),
        }
        for dimension, values in groups.items():
            for label in np.unique(values):
                subset = p[np.asarray(values) == label]
                segments.append(
                    {
                        "target": target,
                        "horizon": int(horizon),
                        "model": name,
                        "split": split,
                        "dimension": dimension,
                        "segment": str(label),
                        **metrics(subset.actual, subset.prediction, scale),
                        "coverage": float(
                            ((subset.actual >= subset.lower) & (subset.actual <= subset.upper)).mean()
                        ),
                    }
                )
    summary = {
        "config": cfg,
        "config_sha256": config_hash,
        "selection": choices,
        "leaderboard": leaderboard,
        "registry": registry,
        "quality": quality,
    }
    (results / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    pd.DataFrame(segments).to_csv(results / "segments.csv", index=False)
    log.info("Finished: %s evaluated forecasts", len(all_predictions))
    return summary
