import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from gridcast.data import normalize
from gridcast.evaluation import conformal_radius, metrics
from gridcast.features import features, training_mask
from gridcast.ingestion import parse_zip
from gridcast.models import build
from gridcast.settings import load


@pytest.fixture
def hourly():
    return pd.Series(
        np.arange(1000, dtype=float) + 100,
        index=pd.date_range("2024-01-01", periods=1000, freq="h", tz="UTC"),
    )


@pytest.mark.parametrize("horizon", [1, 6, 24, 48, 168])
@pytest.mark.parametrize("delay", [3, 48])
def test_every_feature_is_issuance_safe(hourly, horizon, delay):
    f = features(hourly, horizon, delay)
    origin = hourly.index[600]
    changed = hourly.copy()
    changed.loc[changed.index > origin - pd.Timedelta(hours=delay)] = 999999
    g = features(changed, horizon, delay)
    columns = [c for c in f if c not in ["label", "label_time"]]
    pd.testing.assert_series_equal(f.loc[origin, columns], g.loc[origin, columns])
    assert f.loc[origin, f"lag_{delay}h"] == hourly.loc[origin - pd.Timedelta(hours=delay)]
    assert f.loc[origin, "label"] == hourly.loc[origin + pd.Timedelta(hours=horizon)]
    assert f.loc[origin, "seasonal_anchor"] < f.loc[origin, "lag_3h"] if delay == 3 else True


def test_fit_labels_published_by_cutoff(hourly):
    f = features(hourly, 168, 3)
    origin = hourly.index[600]
    fit = f.loc[training_mask(f, origin, 3)]
    assert (fit.label_time + pd.Timedelta(hours=3)).max() <= origin
    assert fit.index.max() == origin - pd.Timedelta(hours=171)


def test_missing_value_stays_missing(hourly):
    hourly.iloc[500] = np.nan
    f = features(hourly, 24, 3)
    assert pd.isna(f.iloc[503].lag_3h)
    assert pd.isna(f.iloc[503].mean_24h)


def test_dst_spring_and_fall():
    spring = pd.date_range("2024-03-10T08:00Z", "2024-03-11T07:00Z", freq="h", inclusive="left")
    fall = pd.date_range("2024-11-03T07:00Z", "2024-11-04T08:00Z", freq="h", inclusive="left")
    assert len(spring) == 23 and len(fall) == 25
    local = fall.tz_convert("America/Los_Angeles")
    repeated = local[local.hour == 1]
    assert len(repeated) == 2 and repeated[0].utcoffset() != repeated[1].utcoffset()
    assert 2 not in spring.tz_convert("America/Los_Angeles").hour


def test_zip_rejects_oasis_xml_error():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("error.xml", "<ERR_CODE>1015</ERR_CODE>")
    with pytest.raises(ValueError, match="no CSV"):
        parse_zip(b.getvalue())


def test_actual_filter_and_duplicate_guard():
    _, cfg = load()
    raw = pd.DataFrame(
        {
            "INTERVALSTARTTIME_GMT": ["2024-01-01T00:00Z"] * 2,
            "INTERVALENDTIME_GMT": ["2024-01-01T01:00Z"] * 2,
            "MW": [20000, 90000],
            "MARKET_RUN_ID": ["ACTUAL", "DAM"],
            "TAC_AREA_NAME": ["CA ISO-TAC"] * 2,
        }
    )
    result = normalize(raw, "demand", cfg)
    assert result.value.tolist() == [20000]
    assert result.available_at.iloc[0] == pd.Timestamp("2024-01-01T03:00Z")
    with pytest.raises(ValueError, match="Duplicate"):
        normalize(pd.concat([raw, raw]), "demand", cfg)


def test_negative_prices_are_valid():
    _, cfg = load()
    raw = pd.DataFrame(
        {
            "INTERVALSTARTTIME_GMT": ["2024-01-01T00:00Z"],
            "INTERVALENDTIME_GMT": ["2024-01-01T01:00Z"],
            "MW": [-50.0],
            "MARKET_RUN_ID": ["DAM"],
            "NODE": [cfg["data"]["price_node"]],
            "LMP_TYPE": ["LMP"],
        }
    )
    assert normalize(raw, "price", cfg).value.iloc[0] == -50


def test_metrics_handle_zero_and_negative_prices():
    m = metrics([0, -10, 10], [0, -5, 5], 5)
    assert m["mae"] == pytest.approx(10 / 3)
    assert m["bias"] == 0
    assert np.isfinite(m["smape"])
    assert conformal_radius([-1, 2, -3, 4], 0.9) == 4


@pytest.mark.parametrize("name", ["ridge", "seasonal_ar", "xgboost", "lightgbm", "gru"])
def test_models_train_predict_and_serialize(hourly, name, tmp_path):
    import joblib

    _, cfg = load()
    cfg["experiment"]["gru_epochs"] = 1
    frame = features(hourly, 24, 3).dropna()
    x = frame.drop(columns=["label", "label_time"])
    m = build(name, cfg["experiment"]).fit(x.iloc[:300], frame.label.iloc[:300])
    predicted = m.predict(x.iloc[300:310])
    assert predicted.shape == (10,) and np.isfinite(predicted).all()
    joblib.dump(m, tmp_path / "model.joblib")
    loaded = joblib.load(tmp_path / "model.joblib")
    np.testing.assert_allclose(loaded.predict(x.iloc[300:310]), predicted)
