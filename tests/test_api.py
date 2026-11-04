import pytest
from fastapi.testclient import TestClient

from api.main import app, predictions, summary

client = TestClient(app)


def test_health():
    assert client.get("/health").status_code == 200


def test_cors_allows_public_dashboard_origin_only():
    response = client.options(
        "/api/overview",
        headers={
            "Origin": "https://gridcast.rjbassig.dev",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://gridcast.rjbassig.dev"

    denied = client.options(
        "/api/overview",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"},
    )
    assert denied.headers.get("access-control-allow-origin") is None


def test_invalid_request_validation():
    assert (
        client.post("/api/forecast", json={"target": "fake", "horizon": -1, "issue_time": "bad"}).status_code
        == 422
    )
    assert client.get("/api/history/fake").status_code == 422
    assert client.get("/api/history/demand?start=2025-01-01").status_code == 422
    assert client.get("/api/history/demand?limit=1000000").status_code == 422


@pytest.fixture
def replay_row():
    p = predictions()
    return p[
        (p.target == "demand") & (p.horizon == 24) & (p.model == "ridge_100") & (p.split == "test")
    ].iloc[-1]


def test_forecast_reproduces_stored_prediction(replay_row):
    r = replay_row
    body = {"target": r.target, "horizon": int(r.horizon), "model": r.model, "issue_time": str(r.issue_time)}
    response = client.post("/api/forecast", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["prediction"] == pytest.approx(r.prediction)
    assert response.json()["mode"] == "historical_replay"
    assert client.post("/api/forecast", json={**body, "issue_time": "2024-01-01T00:00Z"}).status_code == 422


def test_scenario_runs_same_artifact(replay_row):
    r = replay_row
    body = {"target": r.target, "horizon": int(r.horizon), "model": r.model, "issue_time": str(r.issue_time)}
    zero = client.post("/api/scenario", json={**body, "historical_level_change_pct": 0})
    assert zero.status_code == 200, zero.text
    assert zero.json()["baseline"] == pytest.approx(r.prediction, rel=1e-6)
    assert zero.json()["delta"] == pytest.approx(0)
    shifted = client.post("/api/scenario", json={**body, "historical_level_change_pct": 10})
    assert shifted.status_code == 200
    assert abs(shifted.json()["delta"]) > 1
    assert client.post("/api/scenario", json={**body, "historical_level_change_pct": 100}).status_code == 422


def test_provenance_and_heldout_integrity():
    for m in summary()["registry"]:
        import pandas as pd

        assert pd.Timestamp(m["fit_labels_available_by"]) <= pd.Timestamp(m["calibration_start"])
        assert pd.Timestamp(m["calibration_labels_available_by"]) <= pd.Timestamp(m["eligible_start"])
        assert len(m["dataset_sha256"]) == 64


@pytest.mark.parametrize(
    "endpoint",
    ["overview", "quality", "models", "comparisons", "origins", "replay", "importance", "segments"],
)
def test_analytics_endpoints(endpoint):
    response = client.get(f"/api/{endpoint}")
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("horizon", [1, 6, 24, 48, 168])
def test_dashboard_query_parameters(horizon):
    for endpoint in ["comparisons", "origins", "replay", "importance", "segments"]:
        response = client.get(f"/api/{endpoint}?target=price&horizon={horizon}")
        assert response.status_code == 200, response.text
    assert client.get("/api/comparisons?target=price&horizon=2").status_code == 422


@pytest.mark.parametrize("target", ["demand", "price"])
@pytest.mark.parametrize(
    "name",
    [
        "persistence",
        "seasonal_naive",
        "historical_mean",
        "calendar_mean",
        "ridge_1",
        "ridge_100",
        "seasonal_ar",
        "xgboost",
        "lightgbm",
        "gru",
    ],
)
def test_all_model_inference_matches_experiment(target, name):
    p = predictions()
    r = p[(p.target == target) & (p.horizon == 24) & (p.model == name) & (p.split == "test")].iloc[-1]
    response = client.post(
        "/api/forecast",
        json={"target": target, "horizon": 24, "model": name, "issue_time": str(r.issue_time)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["prediction"] == pytest.approx(r.prediction, rel=1e-5, abs=0.01)
