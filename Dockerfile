FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:0.5.31 /uv /usr/local/bin/uv

RUN useradd --create-home --uid 1000 vg

WORKDIR /app

COPY pyproject.toml uv.lock README.md MODEL_CONFIG.md PROMPTS.md ./
COPY specs ./specs
COPY scripts ./scripts
COPY src ./src
COPY fixtures ./fixtures

RUN uv sync --frozen --no-dev && python scripts/generate_project.py --clean

WORKDIR /workspace
USER vg

ENTRYPOINT ["/app/.venv/bin/python", "-m", "vg_agent"]
CMD []
