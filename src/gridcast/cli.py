import argparse
import json
import logging

from gridcast.settings import load


def main():
    parser = argparse.ArgumentParser(description="GridCast reproducible pipelines")
    parser.add_argument("command", choices=["ingest", "prepare", "train", "report", "all"])
    parser.add_argument("--config", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root, cfg = load(args.config)
    if args.command in ["ingest", "all"]:
        from gridcast.ingestion import ingest

        ingest(root, cfg)
    if args.command in ["prepare", "all"]:
        from gridcast.data import prepare

        print(json.dumps(prepare(root, cfg), indent=2))
    if args.command in ["train", "all"]:
        from gridcast.experiment import run

        run(root, cfg)
    if args.command in ["report", "all"]:
        from gridcast.reporting import report

        report(root, cfg)


if __name__ == "__main__":
    main()
