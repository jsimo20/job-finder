"""Neither database may need to unlink a file in order to commit.

A Cowork device-bridge mount blocks unlink. SQLite's default DELETE journal mode
removes the rollback journal on every commit, so a write from there fails and
leaves a hot journal behind, which then wedges the database for the next reader:
rollback also requires deleting it. This happened to jobs.db on 2026-08-28.
"""
from __future__ import annotations

import sqlite3

import pytest

from job_finder import db as jobs_db, state

DATABASES = [(jobs_db, "jobs.db"), (state, "state.db")]


def sidecars(db_path):
    """Journal, WAL and shared-memory files sitting beside the database."""
    return {p.name for p in db_path.parent.iterdir() if p.name != db_path.name}


@pytest.mark.parametrize("module,name", DATABASES)
def test_committing_never_unlinks_a_file(tmp_path, module, name):
    """The property, not the pragma: any unlink-free mode passes this."""
    db_path = tmp_path / name
    with module.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS probe (x INTEGER)")
        conn.execute("INSERT INTO probe VALUES (1)")
        during = sidecars(db_path)
    after = sidecars(db_path)

    vanished = during - after
    assert not vanished, (
        f"{sorted(vanished)} was deleted on commit or close. A mount that blocks "
        "unlink fails that write and leaves the database wedged for the next reader")


@pytest.mark.parametrize("module,name", DATABASES)
def test_the_journal_mode_is_one_we_chose(tmp_path, module, name):
    """Two reasons to reject a mode, and only the first one is mechanical.

    delete unlinks per commit and wal unlinks on close, so both need the syscall
    the bridge blocks. memory and off need no file at all and would satisfy the
    property above, but they give up crash recovery: a process killed
    mid-transaction can leave the database corrupt. state.db holds the applied
    ledger and the tracked-company list, is gitignored, and is backed up nowhere,
    so that is not a trade to make quietly. No test can catch it either, since
    proving it needs a process killed mid-write, which is why it is pinned here.
    """
    with module.connect(tmp_path / name) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode not in ("delete", "wal", "off", "memory")


@pytest.mark.parametrize("module,name", DATABASES)
def test_the_mode_is_per_connection_and_does_not_persist(tmp_path, module, name):
    """Which is why both connect() functions set it, rather than one migration.

    Only WAL is recorded in the database header. Everything else reverts to the
    default on the next connection, so a helper that opens sqlite3 directly and
    skips the pragma reintroduces the bug.
    """
    db_path = tmp_path / name
    with module.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS probe (x INTEGER)")

    bare = sqlite3.connect(db_path)
    assert bare.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    bare.close()


def test_a_leftover_journal_does_not_wedge_the_next_reader(tmp_path):
    db_path = tmp_path / "jobs.db"
    with jobs_db.connect(db_path) as conn:
        conn.execute("CREATE TABLE probe (x INTEGER)")
        conn.execute("INSERT INTO probe VALUES (1)")

    leftovers = sidecars(db_path)
    with jobs_db.connect(db_path) as conn:
        assert [tuple(r) for r in conn.execute("SELECT x FROM probe")] == [(1,)]
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        conn.execute("INSERT INTO probe VALUES (2)")

    with jobs_db.connect(db_path) as conn:
        assert [tuple(r) for r in conn.execute("SELECT x FROM probe")] == [(1,), (2,)]
    assert sidecars(db_path) == leftovers


def test_rollback_still_works(tmp_path):
    """The guarantee MEMORY would have traded away, exercised in the shipped mode."""
    db_path = tmp_path / "jobs.db"
    with jobs_db.connect(db_path) as conn:
        conn.execute("CREATE TABLE probe (x INTEGER)")
        conn.execute("INSERT INTO probe VALUES (1)")

    with pytest.raises(RuntimeError):
        with jobs_db.connect(db_path) as conn:
            conn.execute("INSERT INTO probe VALUES (99)")
            raise RuntimeError("caller blew up mid-transaction")

    with jobs_db.connect(db_path) as conn:
        assert [tuple(r) for r in conn.execute("SELECT x FROM probe")] == [(1,)]
