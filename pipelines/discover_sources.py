import datetime
import hashlib
import json
from pathlib import Path

import requests

root = Path(__file__).resolve().parents[1] / "data/raw/reference"
root.mkdir(parents=True, exist_ok=True)
probes = [
    (
        "eia",
        "https://api.eia.gov/v2/electricity/rto/region-data/data/",
        {
            "api_key": "DEMO_KEY",
            "frequency": "hourly",
            "data[0]": "value",
            "facets[respondent][]": "CISO",
            "facets[type][]": "D",
            "start": "2024-01-01T00",
            "end": "2024-01-02T23",
            "length": 48,
        },
    ),
    (
        "weather",
        "https://archive-api.open-meteo.com/v1/archive",
        {
            "latitude": 38.58,
            "longitude": -121.49,
            "start_date": "2024-01-01",
            "end_date": "2025-12-31",
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
            "timezone": "UTC",
        },
    ),
]
for name, url, params in probes:
    try:
        r = requests.get(url, params=params, timeout=120)
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise ValueError(data["error"])
        (root / f"{name}.json").write_bytes(r.content)
        (root / f"{name}.metadata.json").write_text(
            json.dumps(
                {
                    "url": r.url,
                    "acquired_at": datetime.datetime.now(datetime.UTC).isoformat(),
                    "sha256": hashlib.sha256(r.content).hexdigest(),
                },
                indent=2,
            )
        )
        print(name, "SUCCESS", len(r.content), flush=True)
    except (requests.RequestException, ValueError, OSError) as e:
        print(name, "FAILED", e, flush=True)
