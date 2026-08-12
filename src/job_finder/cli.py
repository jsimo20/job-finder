"""CLI entrypoint. `run` drives the whole pipeline; the stage subcommands
(collect, extract, score, digest) run pieces of it, and the rest manage
durable state in data/state.db (companies, no-auto, applied, digest-archive,
outreach) or the working DB (review, mark-applied, dismiss, unmark)."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import applied, collect, db, digest, emailer, extract, outreach, review, score, state

load_dotenv(override=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _cmd_init_db(args: argparse.Namespace) -> int:
    db.init_db(Path(args.db) if args.db else db.DEFAULT_DB_PATH)
    print(f"initialized db at {args.db or db.DEFAULT_DB_PATH}")
    return 0


def _cmd_collect(args: argparse.Namespace) -> int:
    stats = collect.run(db_path=Path(args.db) if args.db else db.DEFAULT_DB_PATH)
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


def _cmd_review(args: argparse.Namespace) -> int:
    review.run(db_path=Path(args.db) if args.db else db.DEFAULT_DB_PATH)
    return 0


def _cmd_mark_applied(args: argparse.Namespace) -> int:
    db_path = Path(args.db) if args.db else db.DEFAULT_DB_PATH
    with db.connect(db_path) as conn:
        n = db.mark_applied(conn, external_id=args.external_id)
        # Also write to the durable applied-log so the role stays suppressed
        # after the DB is rebuilt. Pull company/title/url from the posting row.
        row = conn.execute(
            "SELECT p.title, p.url, c.name AS company FROM postings p "
            "JOIN companies c ON c.id = p.company_id WHERE p.external_id = ?",
            (args.external_id,),
        ).fetchone()
    if row:
        rec = applied.record_applied(args.external_id, company=row["company"],
                                     title=row["title"], url=row["url"], source="mark-applied")
        print(f"updated {n} posting(s); {'logged' if rec else 'already in'} applied-log")
        return 0
    # Ad-hoc role not in the (ephemeral) DB — nothing to update, and we can't
    # infer company/title. Tell the user to record it explicitly.
    print(f"updated {n} posting(s); no DB row for {args.external_id!r} — "
          f"use `applied add --external-id {args.external_id} --company ... --title ...` "
          f"to record it durably")
    return 0 if n else 1


def _cmd_applied_add(args: argparse.Namespace) -> int:
    rec = applied.record_applied(args.external_id, company=args.company, title=args.title,
                                 url=args.url, applied_on=args.date, source=args.source)
    if rec:
        print(f"logged: {rec['title']} @ {rec['company']} [{rec['external_id']}] ({rec['applied_at']})")
        return 0
    print(f"already logged: {args.external_id}")
    return 0


def _cmd_applied_list(args: argparse.Namespace) -> int:
    print(applied.format_applied(applied.list_applied(company=args.company)))
    return 0


def _cmd_applied_remove(args: argparse.Namespace) -> int:
    rec = applied.remove_applied(args.external_id)
    if rec:
        print(f"removed: {rec['company']} — {rec['title']} [{rec['external_id']}]")
        return 0
    print(f"no match for {args.external_id}")
    return 1


def _cmd_applied_check(args: argparse.Namespace) -> int:
    q = args.query.strip()
    # A URL if it looks like one; otherwise treat as an external_id.
    is_url = "/" in q or q.startswith("http")
    hit = applied.is_applied(url=q) if is_url else applied.is_applied(external_id=q)
    if hit:
        matches = [r for r in applied.list_applied()
                   if r.get("external_id") == q
                   or (r.get("url") and applied._norm_url(r["url"]) == applied._norm_url(q))]
        for r in matches:
            print(f"APPLIED: {r['company']} — {r['title']} [{r['external_id']}] ({r['applied_at']})")
        return 0
    print(f"not applied: {q}")
    return 1


def _cmd_dismiss(args: argparse.Namespace) -> int:
    db_path = Path(args.db) if args.db else db.DEFAULT_DB_PATH
    with db.connect(db_path) as conn:
        n = db.mark_dismissed(conn, external_id=args.external_id)
    print(f"updated {n} posting(s)")
    return 0 if n else 1


def _cmd_unmark(args: argparse.Namespace) -> int:
    db_path = Path(args.db) if args.db else db.DEFAULT_DB_PATH
    with db.connect(db_path) as conn:
        n = db.unmark(conn, external_id=args.external_id)
    print(f"updated {n} posting(s)")
    return 0 if n else 1


def _cmd_outreach_add(args: argparse.Namespace) -> int:
    rec = outreach.add_contact(
        args.name,
        args.company,
        role_context=args.role,
        message_type=args.type,
        notes=args.notes,
        on_date=args.date,
    )
    print(f"logged: {rec['name']} @ {rec['company']} ({rec['date']}, {rec['message_type']})")
    return 0


def _cmd_outreach_list(args: argparse.Namespace) -> int:
    print(outreach.format_contacts(outreach.list_contacts(company=args.company)))
    return 0


def _cmd_outreach_remove(args: argparse.Namespace) -> int:
    removed = outreach.remove_contact(args.name, args.company)
    for r in removed:
        print(f"removed: {r['name']} @ {r['company']} ({r['date']})")
    if not removed:
        print(f"no match for {args.name!r} @ {args.company!r}")
    return 0 if removed else 1


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
    out = digest.render(db_path=db_path)
    print(f"wrote {out}")
    if args.email:
        # The digest is already written and archived; a failed send loses
        # nothing but the notification.
        record = state.get_digest()
        try:
            emailer.send_digest(record["body"], record["date"])
            print(f"emailed digest {record['date']}")
        except Exception as exc:
            print(f"EMAIL FAILED: {exc}", file=sys.stderr)
            return 1
    return 0


def _cmd_companies(args: argparse.Namespace) -> int:
    cmd = args.companies_cmd
    if cmd == "list":
        rows = state.list_companies()
        for r in rows:
            label = r["ats_slug"] or r["careers_url"] or "?"
            print(f"{r['name']}  [{r['ats_provider']}:{label}]  "
                  f"{','.join(r['sector_tags'])}")
        print(f"{len(rows)} companies tracked")
    elif cmd == "add":
        if args.provider == "manual":
            if not args.careers_url:
                print("manual companies need --careers-url (that's all the digest can show)",
                      file=sys.stderr)
                return 2
        elif not args.slug:
            print(f"--slug is required for provider={args.provider}", file=sys.stderr)
            return 2
        state.upsert_company({
            "name": args.name, "ats_provider": args.provider, "ats_slug": args.slug,
            "careers_url": args.careers_url,
            "sector_tags": [t for t in (args.tags or "").split(",") if t],
            "size_band": args.size_band,
        })
        label = args.slug or args.careers_url
        print(f"tracked: {args.name} [{args.provider}:{label}]")
    elif cmd == "remove":
        ok = state.remove_company(args.name)
        print(f"removed: {args.name}" if ok else f"no match for {args.name!r}")
        return 0 if ok else 1
    elif cmd == "import":
        print(f"imported {state.import_companies(Path(args.path))} companies")
    elif cmd == "export":
        print(f"exported {state.export_companies(Path(args.path))} companies to {args.path}")
    return 0


def _cmd_no_auto(args: argparse.Namespace) -> int:
    cmd = args.no_auto_cmd
    if cmd == "list":
        rows = state.list_no_auto()
        for r in rows:
            print(f"{r['name']} — {r['reason'] or '(no reason recorded)'}")
        if not rows:
            print("no-auto-apply list is empty")
    elif cmd == "add":
        state.add_no_auto(args.name, args.reason or "")
        print(f"blocked from auto-apply: {args.name}")
    elif cmd == "remove":
        ok = state.remove_no_auto(args.name)
        print(f"unblocked: {args.name}" if ok else f"no match for {args.name!r}")
        return 0 if ok else 1
    return 0


def _cmd_digest_archive(args: argparse.Namespace) -> int:
    if args.archive_cmd == "list":
        dates = state.list_digests()
        for d in dates:
            print(d)
        print(f"{len(dates)} digests archived")
    else:
        record = state.get_digest(args.date)
        if not record:
            print("no digest found")
            return 1
        print(record["body"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job-finder")
    parser.add_argument("--db", help="path to sqlite db")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db").set_defaults(func=_cmd_init_db)

    p = sub.add_parser("collect")
    p.set_defaults(func=_cmd_collect)

    p = sub.add_parser("extract")
    p.add_argument("--limit", type=int, default=None)
    p.set_defaults(func=_cmd_extract)

    sub.add_parser("score").set_defaults(func=_cmd_score)

    p = sub.add_parser("digest")
    p.add_argument("--date", default=None, help="ISO date (default: today)")
    p.set_defaults(func=_cmd_digest)

    p = sub.add_parser("run")
    p.add_argument("--email", action="store_true",
                   help="email the digest after the run (the scheduled task passes this)")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("companies", help="the tracked-company list (data/state.db)")
    csub = p.add_subparsers(dest="companies_cmd", required=True)
    csub.add_parser("list").set_defaults(func=_cmd_companies)
    ca = csub.add_parser("add")
    ca.add_argument("--name", required=True)
    ca.add_argument("--provider", required=True,
                    choices=["greenhouse", "lever", "ashby", "workday", "manual"])
    ca.add_argument("--slug", default=None,
                    help="board slug; workday uses tenant/wdN/site; not used for manual")
    ca.add_argument("--careers-url", default=None, dest="careers_url")
    ca.add_argument("--tags", default="", help="comma-separated sector tags")
    ca.add_argument("--size-band", default=None, dest="size_band")
    ca.set_defaults(func=_cmd_companies)
    cr = csub.add_parser("remove")
    cr.add_argument("--name", required=True)
    cr.set_defaults(func=_cmd_companies)
    ci = csub.add_parser("import", help="merge companies from a JSON file")
    ci.add_argument("path")
    ci.set_defaults(func=_cmd_companies)
    ce = csub.add_parser("export", help="write the list to a JSON file")
    ce.add_argument("path")
    ce.set_defaults(func=_cmd_companies)

    p = sub.add_parser("no-auto", help="companies never auto-applied to")
    nsub = p.add_subparsers(dest="no_auto_cmd", required=True)
    nsub.add_parser("list").set_defaults(func=_cmd_no_auto)
    na = nsub.add_parser("add")
    na.add_argument("--name", required=True)
    na.add_argument("--reason", default="")
    na.set_defaults(func=_cmd_no_auto)
    nr = nsub.add_parser("remove")
    nr.add_argument("--name", required=True)
    nr.set_defaults(func=_cmd_no_auto)

    p = sub.add_parser("digest-archive", help="digests stored in data/state.db")
    dsub = p.add_subparsers(dest="archive_cmd", required=True)
    dsub.add_parser("list").set_defaults(func=_cmd_digest_archive)
    ds = dsub.add_parser("show", help="print a digest (latest by default)")
    ds.add_argument("--date", default=None)
    ds.set_defaults(func=_cmd_digest_archive)

    sub.add_parser("review").set_defaults(func=_cmd_review)

    p = sub.add_parser("mark-applied")
    p.add_argument("external_id", help="ATS posting id (the gh_jid number, etc.)")
    p.set_defaults(func=_cmd_mark_applied)

    p = sub.add_parser("applied", help="durable log of roles applied to (survives DB rebuilds)")
    asub = p.add_subparsers(dest="applied_cmd", required=True)
    aa = asub.add_parser("add", help="record an applied role (esp. ad-hoc ones not in the DB)")
    aa.add_argument("--external-id", required=True, dest="external_id")
    aa.add_argument("--company", required=True)
    aa.add_argument("--title", required=True)
    aa.add_argument("--url", default=None)
    aa.add_argument("--date", default=None, help="ISO date (default: today)")
    aa.add_argument("--source", default="manual")
    aa.set_defaults(func=_cmd_applied_add)
    al = asub.add_parser("list", help="list applied roles")
    al.add_argument("--company", default=None, help="filter by company (case-insensitive)")
    al.set_defaults(func=_cmd_applied_list)
    ac = asub.add_parser("check", help="have we applied to this? (external_id or URL)")
    ac.add_argument("query")
    ac.set_defaults(func=_cmd_applied_check)
    ar = asub.add_parser("remove", help="drop a role from the log (e.g. one you decided not to submit)")
    ar.add_argument("--external-id", required=True, dest="external_id")
    ar.set_defaults(func=_cmd_applied_remove)

    p = sub.add_parser("dismiss")
    p.add_argument("external_id")
    p.set_defaults(func=_cmd_dismiss)

    p = sub.add_parser("unmark")
    p.add_argument("external_id")
    p.set_defaults(func=_cmd_unmark)

    p = sub.add_parser("outreach", help="track people contacted on LinkedIn")
    osub = p.add_subparsers(dest="outreach_cmd", required=True)
    pa = osub.add_parser("add", help="log a person you reached out to")
    pa.add_argument("--name", required=True)
    pa.add_argument("--company", required=True)
    pa.add_argument("--role", default=None, help="role/reason for the outreach, if any")
    pa.add_argument("--type", default="connection-request", choices=outreach.MESSAGE_TYPES)
    pa.add_argument("--notes", default=None)
    pa.add_argument("--date", default=None, help="ISO date (default: today)")
    pa.set_defaults(func=_cmd_outreach_add)
    pl = osub.add_parser("list", help="list logged contacts")
    pl.add_argument("--company", default=None, help="filter by company (case-insensitive)")
    pl.set_defaults(func=_cmd_outreach_list)
    pr = osub.add_parser("remove", help="remove a logged contact by name + company")
    pr.add_argument("--name", required=True)
    pr.add_argument("--company", required=True)
    pr.set_defaults(func=_cmd_outreach_remove)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
