#!/usr/bin/env sh
# Run the fresh-clone check in a python:3.10-slim container.
#
#     sh scripts/fresh_clone_docker.sh              # setup path, zero tokens
#     COLLECT=1 sh scripts/fresh_clone_docker.sh    # also poll the example boards
#
# The build context is the list of files git would commit (tracked plus
# untracked-but-not-ignored), not the working directory. That is what a clone
# receives, so a file that only exists locally cannot make the check pass, and a
# new file you forgot to `git add` still gets tested before you commit it.
set -eu

cd "$(dirname "$0")/.."

git ls-files -z --cached --others --exclude-standard \
    | tar --null -T - --ignore-failed-read -cf - \
    | docker build --quiet -t job-finder-fresh -f docker/Dockerfile - >/dev/null

exec docker run --rm -e COLLECT="${COLLECT:-0}" job-finder-fresh
