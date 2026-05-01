FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir --target=/deps \
    fastapi==0.115.0 \
    uvicorn==0.30.6 \
    sqlalchemy==2.0.35 \
    psycopg[binary]==3.2.2 \
    redis==5.0.8 \
    prometheus-client==0.21.0 \
    pydantic==2.9.2

FROM python:3.12-slim
RUN groupadd -g 1000 app && useradd -u 1000 -g 1000 -m -d /app app
WORKDIR /app
COPY --from=builder /deps /deps
COPY app/ ./app/
ENV PYTHONPATH=/deps \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER 1000
EXPOSE 8000
CMD ["python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
