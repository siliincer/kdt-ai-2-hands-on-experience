# mock-financial-service/Dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY agent/pyproject.toml ./agent/pyproject.toml
COPY mock-financial-service ./mock-financial-service

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --package financial-service --python 3.11

EXPOSE 8002

CMD ["/app/.venv/bin/uvicorn", "financial_service.app:app", "--host", "0.0.0.0", "--port", "8002"]
