# mock-financial-service/Dockerfile
# TODO: 멀티스테이지 빌드로 변경하기!
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
COPY mock-financial-service ./

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --python 3.11

EXPOSE 8002

CMD ["uv", "run", "uvicorn", "src.financial_service.app:app", "--host", "0.0.0.0", "--port", "8002"]
