"""Read-only historical analytics and artifact-backed replay/scenario inference."""

import json
import logging
import os
import time
from enum import IntEnum
from functools import lru_cache
from typing import Literal

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from gridcast.data import series
from gridcast.features import features
from gridcast.settings import load

root, cfg = load()
app = FastAPI(
    title="GridCast",
    version="0.1.0",
    description="Historical CAISO research terminal; not a live dispatch service.",
)


def configured_origins():
    value = os.getenv(
        "GRIDCAST_CORS_ORIGINS",
        "https://gridcast.rjbassig.dev,https://rjbassig.dev,http://localhost:3000,http://127.0.0.1:3000",
    )
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


REPLAY_ONLY = os.getenv("GRIDCAST_REPLAY_ONLY", "false").lower() in {"1", "true", "yes"}
REPLAY_ARTIFACTS = (
    "configs/default.yaml",
    "data/processed/demand.parquet",
    "data/processed/price.parquet",
    "experiments/results/summary.json",
    "experiments/results/predictions.parquet",
    "experiments/results/importance.csv",
    "experiments/results/segments.csv",
    "reports/gridcast_report.pdf",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=600,
)
log = logging.getLogger("gridcast.api")
Target = Literal["demand", "price"]


class Horizon(IntEnum):
    one = 1
    six = 6
    day = 24
    two_days = 48
    week = 168


def artifact_path(relative: str):
    path = root / relative
    if not path.is_file():
        raise HTTPException(503, f"Required historical replay artifact is unavailable: {relative}")
    return path


def missing_replay_artifacts():
    return [relative for relative in REPLAY_ARTIFACTS if not (root / relative).is_file()]


@app.middleware("http")
async def request_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    log.info(
        json.dumps(
            {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            }
        )
    )
    return response


@lru_cache(maxsize=1)
def summary():
    path = artifact_path("experiments/results/summary.json")
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def predictions():
    summary()
    return pd.read_parquet(artifact_path("experiments/results/predictions.parquet"))


@lru_cache(maxsize=8)
def observations(target):
    return pd.read_parquet(artifact_path(f"data/processed/{target}.parquet"))


@lru_cache(maxsize=20)
def model(artifact):
    return joblib.load(root / f"artifacts/{artifact}.joblib")


def records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def timestamp(value):
    try:
        result = pd.Timestamp(value)
        if result.tzinfo is None:
            raise ValueError("Timezone required")
        return result.tz_convert("UTC")
    except (ValueError, TypeError):
        raise HTTPException(422, "Use an ISO 8601 timestamp with timezone")


class ForecastRequest(BaseModel):
    target: Target = "demand"
    horizon: Literal[1, 6, 24, 48, 168] = 24
    model: str | None = None
    issue_time: str


class ScenarioRequest(ForecastRequest):
    historical_level_change_pct: float = Field(default=0, ge=-20, le=20)


class ForecastResponse(BaseModel):
    issue_time: str
    target_time: str
    target: str
    horizon: int
    model: str
    prediction: float
    actual: float
    lower: float
    upper: float
    artifact_id: str
    mode: str = "historical_replay"


def resolve(req):
    name = req.model or summary()["selection"][f"{req.target}_{req.horizon}"]
    p = predictions()
    subset = p[
        (p.target == req.target)
        & (p.horizon == req.horizon)
        & (p.model == name)
        & (p.issue_time == timestamp(req.issue_time))
        & (p.split == "test")
    ]
    if len(subset) != 1:
        raise HTTPException(422, "No eligible held-out forecast for this origin/model/horizon")
    row = subset.iloc[0]
    meta = next(m for m in summary()["registry"] if m["id"] == row.artifact_id)
    return row, meta


def feature_row(req):
    y = series(root, req.target)
    frame = features(y, req.horizon, cfg["availability"][f"{req.target}_delay_hours"])
    t = timestamp(req.issue_time)
    if t not in frame.index:
        raise HTTPException(422, "Issue time unavailable")
    return frame.loc[[t]].drop(columns=["label", "label_time"])


@app.get("/health")
def health():
    missing = missing_replay_artifacts()
    if missing:
        raise HTTPException(
            503,
            {"status": "not_ready", "live": False, "replay_only": REPLAY_ONLY, "missing_artifacts": missing},
        )
    return {
        "status": "ready",
        "live": False,
        "replay_only": REPLAY_ONLY,
        "missing_artifacts": [],
    }


@app.get("/api/overview")
def overview():
    s = summary()
    return {
        "quality": s["quality"],
        "selection": s["selection"],
        "mode": "historical replay" if REPLAY_ONLY else "historical research",
        "replay_only": REPLAY_ONLY,
        "latest": {t: records(observations(t).tail(1))[0] for t in ["demand", "price"]},
    }


@app.get("/api/history/{target}")
def history(
    target: Target, start: str | None = None, end: str | None = None, limit: int = Query(1000, ge=1, le=20000)
):
    d = observations(target)
    if start:
        d = d[d.timestamp >= timestamp(start)]
    if end:
        d = d[d.timestamp < timestamp(end)]
    return {"target": target, "rows": records(d.tail(limit)), "source": "CAISO OASIS"}


@app.get("/api/comparisons")
def comparisons(target: Target = "demand", horizon: Horizon = 24):
    return [r for r in summary()["leaderboard"] if r["target"] == target and r["horizon"] == horizon]


@app.get("/api/models")
def models():
    return {"selection": summary()["selection"], "registry": summary()["registry"]}


@app.get("/api/origins")
def origins(target: Target = "demand", horizon: Horizon = 24):
    p = predictions()
    q = (
        p[(p.target == target) & (p.horizon == horizon) & (p.split == "test")]
        .issue_time.drop_duplicates()
        .sort_values()
    )
    return {"origins": q.astype(str).tolist(), "models": sorted(p.model.unique().tolist())}


@app.post("/api/forecast", response_model=ForecastResponse)
def forecast(req: ForecastRequest):
    if REPLAY_ONLY:
        raise HTTPException(503, "Forecast inference is disabled in the public historical replay release")
    row, meta = resolve(req)
    x = feature_row(req)
    if row.model == "persistence":
        delay = cfg["availability"][f"{req.target}_delay_hours"]
        value = float(x.iloc[0][f"lag_{delay}h"])
    elif row.model == "seasonal_naive":
        value = float(x.iloc[0].seasonal_anchor)
    elif row.model == "historical_mean":
        value = meta["baseline_mean"]
    elif row.model == "calendar_mean":
        local = row.target_time.tz_convert("America/Los_Angeles")
        value = meta["calendar"].get(f"{local.day_of_week}_{local.hour}", meta["baseline_mean"])
    else:
        value = float(model(row.artifact_id).predict(x)[0])
    row = row.copy()
    row["prediction"] = value
    return {
        k: str(row[k]) if k in ["issue_time", "target_time"] else row[k]
        for k in ForecastResponse.model_fields
        if k in row.index
    }


@app.post("/api/scenario")
def scenario(req: ScenarioRequest):
    if REPLAY_ONLY:
        raise HTTPException(503, "Scenario inference is disabled in the public historical replay release")
    row, meta = resolve(req)
    if row.model in ["persistence", "seasonal_naive", "historical_mean", "calendar_mean"]:
        raise HTTPException(422, "Select a fitted model for feature sensitivity scenarios")
    x = feature_row(req)
    changed = x.copy()
    multiplier = 1 + req.historical_level_change_pct / 100
    for col in x.columns:
        if col.startswith(("lag_", "mean_", "std_")) or col == "seasonal_anchor":
            changed[col] *= multiplier
    fitted = model(row.artifact_id)
    base = float(fitted.predict(x)[0])
    value = float(fitted.predict(changed)[0])
    return {
        "baseline": base,
        "scenario": value,
        "delta": value - base,
        "unit": "MW" if req.target == "demand" else "USD/MWh",
        "mode": "hypothetical historical feature sensitivity",
        "limitation": "Perturbs historical level features, not causal weather effects. Baseline intervals do not apply.",
        "artifact_id": meta["id"],
    }


@app.get("/api/importance")
def importance(target: Target = "demand", horizon: Horizon = 24, model_name: str | None = None):
    frame = pd.read_csv(artifact_path("experiments/results/importance.csv"))
    name = model_name or summary()["selection"][f"{target}_{horizon}"]
    frame = frame[(frame.target == target) & (frame.horizon == horizon) & (frame.model == name)]
    return {
        "method": "validation MAE permutation importance; correlated features share importance",
        "rows": records(frame.sort_values("mae_increase", ascending=False)),
        "model": name,
    }


@app.get("/api/quality")
def quality():
    return summary()["quality"]


@app.get("/api/segments")
def segments(target: Target = "demand", horizon: Horizon = 24, dimension: str = "season"):
    frame = pd.read_csv(artifact_path("experiments/results/segments.csv"))
    frame = frame[
        (frame.target == target)
        & (frame.horizon == horizon)
        & (frame.dimension == dimension)
        & (frame.split == "test")
    ]
    return records(frame)


@app.get("/api/replay")
def replay(
    target: Target = "demand",
    horizon: Horizon = 24,
    model_name: str | None = None,
    issue_time: str | None = None,
    limit: int = Query(168, ge=1, le=1500),
):
    p = predictions()
    name = model_name or summary()["selection"][f"{target}_{horizon}"]
    subset = p[(p.target == target) & (p.horizon == horizon) & (p.model == name) & (p.split == "test")]
    if issue_time:
        subset = subset[subset.issue_time == timestamp(issue_time)]
        if subset.empty:
            raise HTTPException(422, "No eligible held-out forecast for this origin/model/horizon")
    return records(subset.sort_values("issue_time").tail(limit))


@app.get("/api/report")
def report():
    path = artifact_path("reports/gridcast_report.pdf")
    return FileResponse(path, media_type="application/pdf")
