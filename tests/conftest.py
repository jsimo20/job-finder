"""Every test runs against the fictional fixture geography, so results are
identical whether or not a personal config/pipeline.toml exists locally."""
from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib
from pathlib import Path

import pytest

from job_finder import filter as filter_mod

FIXTURE = Path(__file__).parent / "fixtures" / "pipeline_test.toml"


@pytest.fixture(autouse=True, scope="session")
def _fixture_pipeline_config():
    with FIXTURE.open("rb") as f:
        filter_mod.configure(tomllib.load(f))
    yield
