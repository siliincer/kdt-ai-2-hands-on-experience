FROM python:3.11-slim@sha256:842ba355f270883624adb44f8cabb8c55c5505e95db5fe76de413eb655666736 AS builder

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY agent/pyproject.toml ./agent/pyproject.toml
COPY mock-financial-service/pyproject.toml ./mock-financial-service/pyproject.toml

RUN pip install --no-cache-dir uv==0.11.6 \
    && uv sync --frozen --no-dev --package financial-service --no-install-package financial-service --python 3.11

COPY mock-financial-service/src ./mock-financial-service/src

RUN uv sync --frozen --no-dev --package financial-service --python 3.11

FROM python:3.11-slim@sha256:842ba355f270883624adb44f8cabb8c55c5505e95db5fe76de413eb655666736 AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN python -m pip uninstall --yes pip setuptools wheel \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown app:app /data

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/mock-financial-service/src /app/mock-financial-service/src

USER 10001:10001

EXPOSE 8002

CMD ["/app/.venv/bin/uvicorn", "financial_service.app:app", "--host", "0.0.0.0", "--port", "8002"]
