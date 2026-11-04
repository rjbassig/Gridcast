import numpy as np


def metrics(actual, predicted, scale: float) -> dict:
    actual, predicted = np.asarray(actual), np.asarray(predicted)
    error = predicted - actual
    denominator = np.abs(actual) + np.abs(predicted)
    smape = np.divide(
        200 * np.abs(error), denominator, out=np.zeros_like(error, dtype=float), where=denominator > 0
    )
    return {
        "n": len(error),
        "mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "bias": float(error.mean()),
        "smape": float(smape.mean()),
        "mase": float(np.abs(error).mean() / scale) if scale > 0 else None,
        "p95_absolute_error": float(np.quantile(np.abs(error), 0.95)),
    }


def conformal_radius(errors, coverage=0.9) -> float:
    errors = np.abs(np.asarray(errors))
    if not len(errors) or not np.isfinite(errors).all():
        raise ValueError("Finite calibration residuals required")
    level = min(np.ceil((len(errors) + 1) * coverage) / len(errors), 1)
    return float(np.quantile(errors, level, method="higher"))


def block_interval(errors, seed=42, repetitions=500, block=168) -> list[float]:
    """Block-bootstrap MAE interval; preserves within-week dependence approximately."""
    errors = np.abs(np.asarray(errors))
    groups = [errors[i : i + block] for i in range(0, len(errors), block)]
    rng = np.random.default_rng(seed)
    values = [
        np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))]).mean()
        for _ in range(repetitions)
    ]
    return [float(v) for v in np.quantile(values, [0.025, 0.975])]
