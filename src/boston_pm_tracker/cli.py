"""CLI entrypoint: init-db | collect | extract | score | digest | run."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import collect, db, digest, extract, score

load_dotenv(override=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _cmd_init_db(args: argparse.Namespace) -> int:
    db.init_db(Path(args.db) if args.db else db.DEFAULT_DB_PATH)
    print(f"initialized db at {args.db or db.DEFAULT_DB_PATH}")
    return 0


def _cmd_collect(args: argparse.Namespace) -> int:
    stats = collect.run(
        seeds_path=Path(args.seeds) if args.seeds else collect.DEFAULT_SEEDS,
        db_path=Path(args.db) if args.db else db.DEFAULT_DB_PATH,
    )
    print(json.dumps(stats, indent=2))
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    stats = extract.run(
        db_path=Path(args.db) if args.db else db.DEFAULT_DB_PATH,
        limit=args.limit,
    )
    print(json.dumps(stats, indent=2))
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    stats = score.run(db_path=Path(args.db) if args.db else db.DEFAULT_DB_PATH)
    print(json.dumps(stats, indent=2))
    return 0


def _cmd_digest(args: argparse.Namespace) -> int:
    out = digest.render(
        target_date=args.date,
        db_path=Path(args.db) if args.db else db.DEFAULT_DB_PATH,
    )
    print(f"wrote {out}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    db_path = Path(args.db) if args.db else db.DEFAULT_DB_PATH
    db.init_db(db_path)
    print("== collect ==")
    print(json.dumps(collect.run(db_path=db_path), indent=2))
    print("== extract ==")
    print(json.dumps(extract.run(db_path=db_path), indent=2))
    print("== score ==")
    print(json.dumps(score.run(db_path=db_path), indent=2))
    print("== digest ==")
    print(f"wrote {digest.render(db_path=db_path)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="boston-pm-tracker")
    parser.add_argument("--db", help="path to sqlite db")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db").set_defaults(func=_cmd_init_db)

    p = sub.add_parser("collect")
    p.add_argument("--seeds", help="path to seeds/companies.json")
    p.set_defaults(func=_cmd_collect)

    p = sub.add_parser("extract")
    p.add_argument("--limit", type=int, default=None)
    p.set_defaults(func=_cmd_extract)

    sub.add_parser("score").set_defaults(func=_cmd_score)

    p = sub.add_parser("digest")
    p.add_argument("--date", default=None, help="ISO date (default: today)")
    p.set_defaults(func=_cmd_digest)

    sub.add_parser("run").set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
