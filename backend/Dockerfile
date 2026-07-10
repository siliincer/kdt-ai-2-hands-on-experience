# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY backend ./backend
COPY agent/pyproject.toml ./agent/pyproject.toml
COPY mock-financial-service/pyproject.toml ./mock-financial-service/pyproject.toml

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --package backend --python 3.11

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
