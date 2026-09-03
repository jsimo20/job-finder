# A fresh clone on the Python floor. Built from `git ls-files`, never from the
# working tree, so nothing gitignored (profile/, .env, data/, .venv/) can leak in
# and mask a gap in SETUP.md. Run via scripts/fresh_clone_docker.sh.
#
# 3.10 on purpose: it is the floor pyproject declares and the version the Cowork
# device VM runs, and no Windows machine here has it installed.
FROM python:3.10-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /repo
COPY . .

CMD ["sh", "scripts/fresh_clone_check.sh"]
