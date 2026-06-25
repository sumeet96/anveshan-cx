"""
src/pipeline.py
===============
Run the whole prototype on the snapshot, in order:
    ingest -> enrich -> analyze -> brief

Each stage reads/writes data/processed/. ingest + enrich + brief need an
OPENAI_API_KEY (in .env); analyze is pure pandas. Re-runs reuse the enrich cache.

Run:  python -m src.pipeline
"""
from __future__ import annotations

import argparse

from . import analyze, brief, config, enrich, ingest


def run():
    from dotenv import load_dotenv
    load_dotenv(config.BASE_DIR / ".env")
    print("== ingest ==")
    ingest.main([])
    print("\n== enrich ==")
    enrich.main([])
    print("\n== analyze ==")
    analyze.main([])
    print("\n== brief ==")
    brief.main([])
    print(f"\nDone. Snapshot {config.SNAPSHOT_DATE}. Artifacts in {config.DATA_PROCESSED}")


def main(argv=None):
    argparse.ArgumentParser(description="Run ingest -> enrich -> analyze -> brief").parse_args(argv)
    run()


if __name__ == "__main__":
    main()
