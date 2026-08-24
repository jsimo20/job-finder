"""Loaders for the two per-user config layers.

config/pipeline.toml — gitignored. Filter geography, scoring weights, and
numeric knobs; preferences, never contact details. A fresh clone falls back
to the committed config/pipeline.example.toml.

profile/ — gitignored. Identity, EEO answers, and paths to the driving docs
(master resume, personal statement, standard answers). Only the local apply
workflow reads it; the pipeline never does. profile.example/ is the committed
template a new user copies to profile/ and fills in.
"""
from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib
from functools import cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_CONFIG_PATH = REPO_ROOT / "config" / "pipeline.toml"
PIPELINE_EXAMPLE_PATH = REPO_ROOT / "config" / "pipeline.example.toml"
PROFILE_DIR = REPO_ROOT / "profile"
PROFILE_EXAMPLE_DIR = REPO_ROOT / "profile.example"


@cache
def pipeline_config(path: Path | None = None) -> dict:
    """config/pipeline.toml (gitignored, the user's real search) when present,
    else the committed example — so a fresh clone runs out of the box."""
    p = path or (PIPELINE_CONFIG_PATH if PIPELINE_CONFIG_PATH.exists()
                 else PIPELINE_EXAMPLE_PATH)
    with p.open("rb") as f:
        return tomllib.load(f)


def profile_dir() -> Path:
    """The active profile directory: profile/ when configured, else the example.

    The example fallback keeps imports and tests working on a fresh clone. Code
    that would act on the values (filling a form, rendering a PDF) must go
    through require_profile() instead, so placeholder data never reaches a real
    application.
    """
    if (PROFILE_DIR / "profile.toml").exists():
        return PROFILE_DIR
    return PROFILE_EXAMPLE_DIR


def load_profile(path: Path | None = None) -> dict:
    p = path or (profile_dir() / "profile.toml")
    with p.open("rb") as f:
        return tomllib.load(f)


def require_profile() -> dict:
    """The user's real profile — refuses to fall back to the example."""
    real = PROFILE_DIR / "profile.toml"
    if not real.exists():
        raise FileNotFoundError(
            "profile/profile.toml not found. Copy profile.example/ to profile/ "
            "and fill in your details — see SETUP.md."
        )
    return load_profile(real)
