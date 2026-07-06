# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY backend ./backend
COPY agent ./agent

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --python 3.11

EXPOSE 8000

CMD ["sh", "-c", "uv run uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
