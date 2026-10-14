"""Every test runs against the fixture config, so results are identical
whether or not a personal config/pipeline.toml exists locally."""
from __future__ import annotations

import os
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "pipeline_test.toml"
# Set before any job_finder import: taxonomy reads the config at import time.
os.environ["JOB_FINDER_PIPELINE_CONFIG"] = str(FIXTURE)

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib
import pytest  # noqa: E402  (after the env var above)

from job_finder import filter as filter_mod  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _fixture_pipeline_config():
    with FIXTURE.open("rb") as f:
        filter_mod.configure(tomllib.load(f))
    yield
