# agent/Dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY agent ./agent
COPY mock-financial-service/pyproject.toml ./mock-financial-service/pyproject.toml

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --package agent --python 3.11

EXPOSE 8001

CMD ["/app/.venv/bin/uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8001"]
