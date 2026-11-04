"""Create an ignored, immutable historical-replay bundle for public API hosting.

The bundle deliberately excludes raw CAISO downloads, model checkpoints and all
credentials. It contains only the processed observations and generated research
outputs used by GridCast's read-only historical endpoints.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "configs/default.yaml",
    "data/processed/demand.parquet",
    "data/processed/price.parquet",
    "experiments/results/summary.json",
    "experiments/results/predictions.parquet",
    "experiments/results/importance.csv",
    "experiments/results/segments.csv",
    "reports/gridcast_report.pdf",
)


def copy_release(destination: Path) -> None:
    missing = [relative for relative in REQUIRED if not (ROOT / relative).is_file()]
    if missing:
        joined = "\n  ".join(missing)
        raise SystemExit(f"Cannot create a replay release; required files are missing:\n  {joined}")

    if destination.exists():
        raise SystemExit(f"Destination already exists: {destination}")

    for relative in REQUIRED:
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    print(f"Created public historical-replay bundle at {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "release" / "gridcast-replay",
        help="Ignored destination directory (default: release/gridcast-replay)",
    )
    args = parser.parse_args()
    copy_release(args.output.resolve())


if __name__ == "__main__":
    main()
