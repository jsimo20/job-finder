#!/bin/sh
# Overlay the latest main onto an install made by the setup skill.
#
#   sh scripts/self_update.sh
#
# Prints one status line. Exit 0 when updated or skipped, 1 when the update
# failed; on a failed download the folder is untouched. Personal state
# (profile/, data/, .env, config/pipeline.toml, .cowork-deps/) is gitignored,
# so the archive never carries it.
#
# The body is a function so the shell parses all of it before tar overwrites
# this file mid-run.

main() {
    cd "$(dirname "$0")/.." || { echo "update failed: no repo root"; return 1; }

    # A full checkout is the developer's; git owns it. Setup's own clone is
    # shallow, so it still updates here.
    if [ -d .git ] && [ ! -f .git/shallow ]; then
        echo "update skipped: developer checkout"
        return 0
    fi

    stamp=data/.engine_updated
    if [ -n "$(find "$stamp" -mmin -60 2>/dev/null)" ]; then
        echo "update skipped: already updated this hour"
        return 0
    fi

    tmp="${TMPDIR:-/tmp}/jf-main.$$.tar.gz"
    trap 'rm -f "$tmp"' EXIT
    if ! curl -fsSL --max-time 60 -o "$tmp" \
            https://github.com/jsimo20/job-finder/archive/refs/heads/main.tar.gz \
        || ! tar tzf "$tmp" > /dev/null 2>&1; then
        echo "update failed: download; still on the current version"
        return 1
    fi

    before=$(cksum < pyproject.toml)
    # --overwrite rewrites files in place. tar's default deletes and recreates,
    # and a Cowork folder mount blocks deletes.
    if ! tar xzf "$tmp" --strip-components=1 --overwrite; then
        echo "update failed: extract"
        return 1
    fi

    if [ "$before" != "$(cksum < pyproject.toml)" ] || [ ! -d .cowork-deps ]; then
        sh scripts/bootstrap_cowork_deps.sh > /dev/null \
            || { echo "update failed: dependency rebuild"; return 1; }
    fi

    mkdir -p data && touch "$stamp"
    echo "updated from main"
}

main
exit $?
