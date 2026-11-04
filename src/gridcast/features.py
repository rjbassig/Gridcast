"""Direct-horizon features aligned to forecast issue time, never target time."""

import numpy as np
import pandas as pd

LAGS = (0, 1, 2, 3, 6, 12, 24, 48, 72, 168)


def features(y: pd.Series, horizon: int, delay: int) -> pd.DataFrame:
    if horizon < 1 or delay < 1:
        raise ValueError("Positive horizon and availability delay required")
    issue = y.index
    target_time = issue + pd.Timedelta(hours=horizon)
    local = target_time.tz_convert("America/Los_Angeles")
    out = pd.DataFrame(index=issue)
    for lag in LAGS:
        out[f"lag_{delay + lag}h"] = y.shift(delay + lag)
    observed = y.shift(delay)
    for window in [24, 168]:
        out[f"mean_{window}h"] = observed.rolling(window, min_periods=window).mean()
        out[f"std_{window}h"] = observed.rolling(window, min_periods=window).std()
    for name, value, period in [
        ("hour", local.hour, 24),
        ("weekday", local.day_of_week, 7),
        ("year", local.day_of_year, 365.25),
    ]:
        out[f"{name}_sin"] = np.sin(2 * np.pi * value / period)
        out[f"{name}_cos"] = np.cos(2 * np.pi * value / period)
    out["weekend"] = (local.day_of_week >= 5).astype(int)
    # Repeat the latest available UTC weekly profile; DST shifts are explicit limitations.
    cycle = int(np.ceil((horizon + delay) / 168)) * 168
    out["seasonal_anchor"] = y.shift(cycle - horizon)
    out["label"] = y.shift(-horizon)
    out["label_time"] = target_time
    return out


def training_mask(frame: pd.DataFrame, issue: pd.Timestamp, delay: int) -> pd.Series:
    return frame.label_time + pd.Timedelta(hours=delay) <= issue
