# Procurement audit harness (Part B). Targets Render's free web service (512 MB RAM).
FROM python:3.12-slim

# poppler-utils: pdftotext/pdfinfo used by the skills. jq: used by the agents to inspect JSON.
# bubblewrap: the Claude CLI needs it for CLAUDE_CODE_SUBPROCESS_ENV_SCRUB (it may still fail inside
# Render's container; runner.py then retries once with the scrub off).
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils jq bubblewrap \
 && rm -rf /var/lib/apt/lists/*

# The skills and agents call ".venv/bin/python", so the dependencies live in /app/.venv.
WORKDIR /app
COPY requirements-server.txt .
RUN python -m venv .venv \
 && .venv/bin/pip install --no-cache-dir -r requirements-server.txt

COPY CLAUDE.md ./
COPY .claude ./.claude
COPY scripts ./scripts
COPY data ./data
COPY outputs ./outputs
COPY app ./app

# Run unprivileged. live/ (working copy, ledger) is written at runtime and is ephemeral.
RUN useradd --create-home app && mkdir -p live && chown -R app:app /app/live
USER app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/home/app

# One worker: the job lock and cost ledger assume a single process.
CMD ["sh", "-c", ".venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
