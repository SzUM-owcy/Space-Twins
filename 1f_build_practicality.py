"""Practicality side table (cost / access / constraints), separate from the scientific analog score.

Usage:
  uv run --frozen python 1f_build_practicality.py init       # create data/practicality_earth.csv (all patches, nothing measured)
  uv run --frozen python 1f_build_practicality.py finalize   # recompute derived scores/classes from the raw columns present

Later phases add steps that fill raw columns (buildability, population, travel time, ...) and then call finalize.
Existing raw values are kept across ``init`` reruns only through ``finalize``; ``init`` never overwrites an existing table.
"""

from __future__ import annotations

import argparse
import logging

import pandas as pd

from config import EARTH_INDEX_PATH, PRACTICALITY_PATH
from src.practicality import empty_table, score_table

log = logging.getLogger("practicality")


def cmd_init(force: bool) -> None:
    if PRACTICALITY_PATH.exists() and not force:
        log.info("%s exists; use --force to recreate", PRACTICALITY_PATH)
        return
    ids = pd.read_csv(EARTH_INDEX_PATH, usecols=["patch_id"])["patch_id"]
    cmd_write(score_table(empty_table(ids)))


def cmd_write(df: pd.DataFrame) -> None:
    PRACTICALITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PRACTICALITY_PATH, index=False)
    log.info("wrote %s (%d rows)", PRACTICALITY_PATH, len(df))


def cmd_finalize() -> None:
    cmd_write(score_table(pd.read_csv(PRACTICALITY_PATH)))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["init", "finalize"])
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    cmd_init(args.force) if args.step == "init" else cmd_finalize()


if __name__ == "__main__":
    main()
