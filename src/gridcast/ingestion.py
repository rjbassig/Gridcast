"""Official CAISO OASIS acquisition with immutable response files and manifests."""

import hashlib
import io
import json
import logging
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)


def parse_zip(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if not names:
            messages = [archive.read(n).decode(errors="replace")[:1500] for n in archive.namelist()]
            raise ValueError(f"OASIS returned no CSV: {messages}")
        return pd.concat([pd.read_csv(archive.open(n)) for n in names], ignore_index=True)


def ingest(root: Path, cfg: dict) -> None:
    config = cfg["data"]
    raw = root / "data/raw"
    raw.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.mount(
        "https://",
        HTTPAdapter(max_retries=Retry(total=4, backoff_factor=3, status_forcelist=[429, 500, 502, 503, 504])),
    )
    start, end = pd.Timestamp(config["start"], tz="UTC"), pd.Timestamp(config["end"], tz="UTC")
    for target in ["demand", "price"]:
        t = start
        while t < end:
            until = min(t + pd.Timedelta(days=config["chunk_days"]), end)
            stem = f"{target}_{t:%Y%m%d}_{until:%Y%m%d}"
            output, meta = raw / f"{stem}.zip", raw / f"{stem}.json"
            if output.exists() and meta.exists():
                if hashlib.sha256(output.read_bytes()).hexdigest() != json.loads(meta.read_text())["sha256"]:
                    raise ValueError(f"Raw checksum mismatch: {output}")
                t = until
                continue
            params = {
                "queryname": "SLD_FCST" if target == "demand" else "PRC_LMP",
                "market_run_id": "ACTUAL" if target == "demand" else "DAM",
                "version": 1 if target == "demand" else 12,
                "resultformat": 6,
                "startdatetime": t.strftime("%Y%m%dT%H:%M-0000"),
                "enddatetime": until.strftime("%Y%m%dT%H:%M-0000"),
            }
            if target == "price":
                params["node"] = config["price_node"]
            response = session.get(config["endpoint"], params=params, timeout=180)
            response.raise_for_status()
            frame = parse_zip(response.content)
            if frame.empty:
                raise ValueError(f"Empty source response: {response.url}")
            temporary = output.with_suffix(".part")
            temporary.write_bytes(response.content)
            temporary.replace(output)
            meta.write_text(
                json.dumps(
                    {
                        "url": response.url,
                        "acquired_at": datetime.now(UTC).isoformat(),
                        "sha256": hashlib.sha256(response.content).hexdigest(),
                        "bytes": len(response.content),
                        "source_rows": len(frame),
                    },
                    indent=2,
                )
            )
            log.info("acquired %s: %s rows", stem, len(frame))
            t = until
            time.sleep(config["request_pause_seconds"])
