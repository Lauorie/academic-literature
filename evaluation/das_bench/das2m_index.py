#!/usr/bin/env python3
"""DAS-2M helpers for DAS-Bench evaluation.

build   : stream metadata/*.jsonl.zst into SQLite papers(arxiv_id, norm_title, metadata_json)
export  : write data/metadata/<arxiv_id>.json for every arXiv id named in eval_inputs/*/ref_*.json
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterator, Set

import zstandard

logger = logging.getLogger(__name__)


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def iter_records(shard: Path) -> Iterator[dict]:
    with shard.open("rb") as fh:
        reader = io.TextIOWrapper(zstandard.ZstdDecompressor().stream_reader(fh), encoding="utf-8")
        for line in reader:
            line = line.strip()
            if line:
                yield json.loads(line)


def build(shard_dir: Path, db_path: Path) -> None:
    db = sqlite3.connect(str(db_path))
    db.execute("CREATE TABLE IF NOT EXISTS papers(arxiv_id TEXT PRIMARY KEY, norm_title TEXT, metadata_json TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS done(shard TEXT PRIMARY KEY)")
    done = {r[0] for r in db.execute("SELECT shard FROM done")}
    for shard in sorted(shard_dir.glob("*.jsonl.zst")):
        if shard.name in done:
            continue
        rows = [
            (r["arxiv_id"], norm_title((r.get("basic_info") or {}).get("title", "")), json.dumps(r, ensure_ascii=False))
            for r in iter_records(shard)
        ]
        db.executemany("INSERT OR REPLACE INTO papers VALUES (?,?,?)", rows)
        db.execute("INSERT INTO done VALUES (?)", (shard.name,))
        db.commit()
        logger.info("%s: %d records", shard.name, len(rows))
    db.execute("CREATE INDEX IF NOT EXISTS idx_title ON papers(norm_title)")
    db.commit()
    logger.info("total records: %d", db.execute("SELECT COUNT(*) FROM papers").fetchone()[0])


def export(db_path: Path, eval_inputs: Path, out_dir: Path) -> None:
    ids: Set[str] = set()
    for ref in eval_inputs.glob("*/ref_*.json"):
        ids.update(json.loads(ref.read_text(encoding="utf-8")).values())
    out_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(db_path))
    hit = 0
    for arxiv_id in sorted(ids):
        row = db.execute("SELECT metadata_json FROM papers WHERE arxiv_id = ?", (arxiv_id,)).fetchone()
        if row:
            (out_dir / f"{arxiv_id}.json").write_text(row[0], encoding="utf-8")
            hit += 1
    logger.info("exported %d / %d cited arXiv ids found in DAS-2M", hit, len(ids))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--shards", type=Path, required=True)
    b.add_argument("--db", type=Path, required=True)
    e = sub.add_parser("export")
    e.add_argument("--db", type=Path, required=True)
    e.add_argument("--eval-inputs", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "build":
        build(args.shards, args.db)
    else:
        export(args.db, args.eval_inputs, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
