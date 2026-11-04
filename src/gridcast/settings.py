import os
from pathlib import Path

import yaml


def load(path: str | None = None) -> tuple[Path, dict]:
    p = Path(path or os.getenv("GRIDCAST_CONFIG", "configs/default.yaml")).resolve()
    return p.parent.parent, yaml.safe_load(p.read_text())
