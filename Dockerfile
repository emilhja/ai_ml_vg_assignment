FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md MODEL_CONFIG.md PROMPTS.md ./
COPY specs ./specs
COPY scripts ./scripts
COPY tests ./tests
COPY src ./src
COPY fixtures ./fixtures

RUN python scripts/generate_project.py --clean

CMD ["python", "-m", "pytest"]
