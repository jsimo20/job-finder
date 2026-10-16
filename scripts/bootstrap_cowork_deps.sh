#!/usr/bin/env sh
# Make job_finder runnable on a Cowork device VM. Idempotent; run from anywhere.
#
#     sh scripts/bootstrap_cowork_deps.sh
#
# The VM ships bare Python with no site-packages and cannot run the host's
# `.venv`, so this installs pyproject.toml's runtime dependencies into
# `.cowork-deps/`. After it, every Python call on the VM is:
#
#     sh scripts/py -m job_finder.<module>
#
# Keep runtime dependencies pure Python, so the folder survives a Python
# minor-version bump.
set -eu

cd "$(dirname "$0")/.."

# python3 where it exists; some Windows installs have only `python`.
PY=python3
"$PY" -c "" 2>/dev/null || PY=python

# Parsed by hand: tomllib is 3.11+, and the VM runs 3.10 with nothing installed.
"$PY" - <<'PYEOF'
import re
import subprocess
import sys
from pathlib import Path

text = Path("pyproject.toml").read_text(encoding="utf-8")
block = re.search(r"^dependencies = \[(.*?)^\]", text, re.M | re.S).group(1)
deps = re.findall(r'"([^"]+)"', block)
subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                "--disable-pip-version-check", "--target", ".cowork-deps", *deps],
               check=True)
PYEOF

# The path is set inside Python because PYTHONPATH's separator differs by OS.
"$PY" -c "
import sys; sys.path[:0] = ['.cowork-deps', 'src']
import job_finder.liveness, job_finder.letter_linter, job_finder.form_inventory
import job_finder.job_apply, job_finder.fill_grader, job_finder.weekly
import job_finder.builtin_discovery  # weekly.finish imports it lazily
import reportlab  # render() needs it, and an import-only check would miss that
print('.cowork-deps ready')
"
