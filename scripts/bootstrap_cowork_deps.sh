#!/usr/bin/env sh
# Make job_finder runnable on a Cowork device VM. Idempotent; run from anywhere.
#
#     sh scripts/bootstrap_cowork_deps.sh          # what the batch needs
#     sh scripts/bootstrap_cowork_deps.sh --cli    # also the job-finder console script
#
# Why this exists. `job_finder` lives under `src/`, and the only editable install
# is a .pth file inside the Windows `.venv`, which the Linux VM Cowork mounts
# cannot see. The first Python call of the batch therefore dies on
# `ModuleNotFoundError: No module named 'job_finder'` before any dependency
# question arises. `PYTHONPATH=src` fixes that import; this directory fixes the
# third-party imports behind it, because the VM ships bare Python with no
# site-packages.
#
# After running this, every Python call on that VM is:
#
#     PYTHONPATH=".cowork-deps:src" python3 -m job_finder.<module>
#
# `python3`, not `python`. Both exist on the VM; be explicit.
#
# The default set is pure Python with zero compiled extensions, so it survives a
# Python minor-version bump:
#
#   httpx      liveness, and every ATS adapter
#   tomli      settings, on 3.10 where tomllib does not exist
#   reportlab  job_apply.render(). Not needed to import job_apply, only to call
#              it, which is why an import-only check passes without it and the
#              batch then fails at the render step.
#
# --cli adds anthropic and python-dotenv, which `job_finder.cli` imports at module
# level. That is the only way to reach `job-finder digest-archive list` and
# `job-finder applications archive` on a machine with no console script:
#
#     PYTHONPATH=".cowork-deps:src" python3 -m job_finder.cli applications archive
#
# It is not the default because anthropic pulls
# `jiter.cpython-310-x86_64-linux-gnu.so`, which locks this directory to CPython
# 3.10 on linux/x86_64 and makes it a rebuild rather than a copy after an upgrade.
# Prefer running the CLI on Windows, where the editable install already works.
set -eu

cd "$(dirname "$0")/.."

PACKAGES="httpx tomli reportlab"
if [ "${1:-}" = "--cli" ]; then
    PACKAGES="$PACKAGES anthropic python-dotenv"
fi

# shellcheck disable=SC2086
python3 -m pip install --quiet --disable-pip-version-check --target .cowork-deps $PACKAGES

PYTHONPATH=".cowork-deps:src" python3 -c "
import job_finder.liveness, job_finder.letter_linter, job_finder.form_inventory
import job_finder.job_apply, job_finder.fill_grader
import reportlab  # render() needs it, and an import-only check would miss that
print('.cowork-deps ready')
"
