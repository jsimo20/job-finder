"""Tests for the deterministic Greenhouse filler.

Browser-free: these cover argument pairing in batch mode. The fill itself is
exercised against live forms.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright", reason="fill_greenhouse needs the [apply] extra")

from boston_pm_tracker import fill_greenhouse as fg  # noqa: E402


def _main(argv, monkeypatch):
    monkeypatch.setattr("sys.argv", ["fill_greenhouse", *argv])
    return fg.main()


def test_mismatched_url_and_folder_counts_exit(monkeypatch, capsys):
    # Silent misalignment here would fill one role's form with another's PDFs.
    with pytest.raises(SystemExit):
        _main(["--url", "a", "--url", "b", "--folder", "x"], monkeypatch)
    assert "one --folder per --url" in capsys.readouterr().err


def test_slug_must_be_repeated_per_url(monkeypatch, capsys):
    with pytest.raises(SystemExit):
        _main(["--url", "a", "--url", "b", "--folder", "x", "--folder", "y",
               "--slug", "only-one"], monkeypatch)
    assert "repeated once per --url" in capsys.readouterr().err


def test_shot_rejected_in_batch_mode(monkeypatch, capsys):
    # --shot is a single file path, so it cannot mean anything for N tabs.
    with pytest.raises(SystemExit):
        _main(["--url", "a", "--url", "b", "--folder", "x", "--folder", "y",
               "--shot", "out.png"], monkeypatch)
    assert "omit it in batch mode" in capsys.readouterr().err
