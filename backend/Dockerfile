# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY backend ./backend
COPY agent ./agent
COPY mock-financial-service ./mock-financial-service

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --python 3.11

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
