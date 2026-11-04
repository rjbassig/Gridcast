import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from gridcast.ingestion import parse_zip


def normalize(raw: pd.DataFrame, target: str, cfg: dict) -> pd.DataFrame:
    if target == "demand":
        raw = raw.loc[
            (raw.MARKET_RUN_ID == "ACTUAL") & (raw.TAC_AREA_NAME == cfg["data"]["demand_area"])
        ].copy()
    else:
        raw = raw.loc[
            (raw.MARKET_RUN_ID == "DAM") & (raw.LMP_TYPE == "LMP") & (raw.NODE == cfg["data"]["price_node"])
        ].copy()
    if raw.empty:
        raise ValueError(f"No matching observations for {target}")
    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(raw.INTERVALSTARTTIME_GMT, utc=True),
            "interval_end": pd.to_datetime(raw.INTERVALENDTIME_GMT, utc=True),
            "value": pd.to_numeric(raw.MW, errors="raise"),
        }
    )
    if not ((out.interval_end - out.timestamp) == pd.Timedelta(hours=1)).all():
        raise ValueError("Expected hourly source intervals")
    if not np.isfinite(out.value).all():
        raise ValueError("Nonfinite observations")
    if target == "demand" and (out.value <= 0).any():
        raise ValueError("Nonpositive demand")
    if out.duplicated("timestamp").any():
        raise ValueError("Duplicate target timestamps; resolve revisions explicitly")
    out = out.sort_values("timestamp").reset_index(drop=True)
    out["local_time"] = out.timestamp.dt.tz_convert("America/Los_Angeles").astype(str)
    out["available_at"] = out.timestamp + pd.Timedelta(hours=cfg["availability"][f"{target}_delay_hours"])
    out["target"] = target
    out["unit"] = "MW" if target == "demand" else "USD/MWh"
    out["market"] = "ACTUAL" if target == "demand" else "DAM"
    out["location"] = cfg["data"]["demand_area"] if target == "demand" else cfg["data"]["price_node"]
    return out


def prepare(root: Path, cfg: dict) -> dict:
    processed = root / "data/processed"
    processed.mkdir(parents=True, exist_ok=True)
    report = {"source": "CAISO OASIS", "targets": {}}
    for target in ["demand", "price"]:
        paths = sorted((root / "data/raw").glob(f"{target}_*.zip"))
        if not paths:
            raise FileNotFoundError(f"Run ingestion first: no {target} files")
        manifests = [json.loads(p.with_suffix(".json").read_text()) for p in paths]
        for p, m in zip(paths, manifests):
            if hashlib.sha256(p.read_bytes()).hexdigest() != m["sha256"]:
                raise ValueError(f"Checksum mismatch: {p}")
        frame = normalize(pd.concat([parse_zip(p.read_bytes()) for p in paths]), target, cfg)
        start = pd.Timestamp(cfg["data"]["start"], tz="UTC")
        end = pd.Timestamp(cfg["data"]["end"], tz="UTC")
        frame = frame[(frame.timestamp >= start) & (frame.timestamp < end)]
        expected = pd.date_range(start, end, freq="h", inclusive="left")
        missing = expected.difference(frame.timestamp)
        # Preserve gaps; do not backfill or manufacture target observations.
        frame.to_parquet(processed / f"{target}.parquet", index=False)
        values = frame.value
        q1, q3 = values.quantile([0.25, 0.75])
        report["targets"][target] = {
            "rows": len(frame),
            "expected_rows": len(expected),
            "missing_hours": len(missing),
            "missing_timestamps": missing.astype(str).tolist(),
            "duplicates": 0,
            "start": str(frame.timestamp.min()),
            "end": str(frame.timestamp.max()),
            "min": float(values.min()),
            "max": float(values.max()),
            "mean": float(values.mean()),
            "negative_observations": int((values < 0).sum()),
            "iqr_outlier_count": int(((values < q1 - 3 * (q3 - q1)) | (values > q3 + 3 * (q3 - q1))).sum()),
            "last_acquisition": max(m["acquired_at"] for m in manifests),
            "dataset_sha256": hashlib.sha256((processed / f"{target}.parquet").read_bytes()).hexdigest(),
        }
    (processed / "quality.json").write_text(json.dumps(report, indent=2))
    with duckdb.connect(str(processed / "gridcast.duckdb")) as conn:
        for target in ["demand", "price"]:
            path = str(processed / f"{target}.parquet").replace("'", "''")
            conn.execute(f"CREATE OR REPLACE TABLE {target} AS SELECT * FROM read_parquet('{path}')")
    return report


def series(root: Path, target: str) -> pd.Series:
    frame = pd.read_parquet(root / f"data/processed/{target}.parquet")
    result = frame.set_index("timestamp").value.sort_index()
    return result.asfreq("h")
