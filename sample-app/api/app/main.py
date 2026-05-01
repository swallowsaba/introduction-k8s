"""Mini TODO API.

ローカル完結 K8s 教材のサンプル API。本番運用観点を意識した骨格になっています:
- /healthz : Liveness 用 (アプリ自身のみ確認)
- /readyz  : Readiness 用 (DB / Redis 到達確認)
- /metrics : Prometheus exporter
- 構造化ログ (JSON)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from .db import Base, Todo, engine_url

# --- logging (JSON structured) ---
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for k in ("request_id", "trace_id"):
            if hasattr(record, k):
                payload[k] = getattr(record, k)
        return json.dumps(payload, ensure_ascii=False)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), handlers=[_handler])
log = logging.getLogger("todo-api")

# --- DB / Redis ---
from sqlalchemy import create_engine

ENGINE = create_engine(engine_url(), pool_size=5, max_overflow=10, pool_pre_ping=True)
REDIS = redis.Redis(
    host=os.environ.get("REDIS_HOST", "redis"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    decode_responses=True,
)

# --- Prometheus ---
REQ = Counter("http_requests_total", "Total HTTP requests", ["method", "path", "code"])
LAT = Histogram("http_request_duration_seconds", "Request latency", ["method", "path"])


# --- Lifespan: テーブル作成 ---
@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(ENGINE)
    log.info("startup complete")
    yield
    log.info("shutdown complete")


app = FastAPI(title="Mini TODO API", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    try:
        response = await call_next(request)
        code = response.status_code
    except Exception:
        code = 500
        raise
    finally:
        elapsed = time.time() - start
        path = request.url.path
        REQ.labels(request.method, path, code).inc()
        LAT.labels(request.method, path).observe(elapsed)
    return response


# --- Schemas ---
class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class TodoUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    done: bool | None = None


class TodoOut(BaseModel):
    id: int
    title: str
    done: bool

    class Config:
        from_attributes = True


# --- Routes ---
@app.get("/healthz")
def healthz():
    """Liveness: 自身が動いているか。依存先は見ない。"""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness: 依存先 (DB, Redis) に到達できるか。"""
    try:
        with ENGINE.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:
        log.warning(f"db not ready: {e}")
        raise HTTPException(503, "db not ready")
    try:
        REDIS.ping()
    except Exception as e:
        log.warning(f"redis not ready: {e}")
        raise HTTPException(503, "redis not ready")
    return {"status": "ready"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/todos", response_model=list[TodoOut])
def list_todos():
    cached = REDIS.get("todos:all")
    if cached:
        return json.loads(cached)
    with Session(ENGINE) as s:
        rows = s.query(Todo).order_by(Todo.id).all()
        out = [TodoOut.model_validate(r).model_dump() for r in rows]
    REDIS.set("todos:all", json.dumps(out), ex=10)
    return out


@app.post("/todos", response_model=TodoOut, status_code=201)
def create_todo(body: TodoCreate):
    with Session(ENGINE) as s:
        t = Todo(title=body.title, done=False)
        s.add(t)
        s.commit()
        s.refresh(t)
        REDIS.delete("todos:all")
        return TodoOut.model_validate(t)


@app.patch("/todos/{todo_id}", response_model=TodoOut)
def update_todo(todo_id: int, body: TodoUpdate):
    with Session(ENGINE) as s:
        t = s.get(Todo, todo_id)
        if not t:
            raise HTTPException(404)
        if body.title is not None:
            t.title = body.title
        if body.done is not None:
            t.done = body.done
        s.commit()
        s.refresh(t)
        REDIS.delete("todos:all")
        return TodoOut.model_validate(t)


@app.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int):
    with Session(ENGINE) as s:
        t = s.get(Todo, todo_id)
        if not t:
            raise HTTPException(404)
        s.delete(t)
        s.commit()
        REDIS.delete("todos:all")
    return Response(status_code=204)
