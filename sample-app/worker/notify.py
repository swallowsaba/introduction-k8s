"""期限切れ TODO の通知バッチ。

CronJob から実行される想定。実際の通知先(Slack 等)は設定によるが、本サンプルでは
Redis のリストに件名を push するだけの簡易実装。
"""
from __future__ import annotations

import json
import os
import sys
import time

import redis
from sqlalchemy import create_engine, text


def main() -> int:
    user = os.environ.get("DB_USER", "todo")
    password = os.environ["DB_PASSWORD"]
    host = os.environ.get("DB_HOST", "postgres")
    port = os.environ.get("DB_PORT", "5432")
    db = os.environ.get("DB_NAME", "todo")
    url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
    engine = create_engine(url, pool_pre_ping=True)

    r = redis.Redis(
        host=os.environ.get("REDIS_HOST", "redis"),
        port=int(os.environ.get("REDIS_PORT", "6379")),
        decode_responses=True,
    )

    with engine.connect() as c:
        rows = c.execute(text("SELECT id, title FROM todos WHERE done = FALSE")).all()

    sent = 0
    for row in rows:
        msg = {"id": row.id, "title": row.title, "ts": time.time()}
        r.lpush("notifications", json.dumps(msg, ensure_ascii=False))
        sent += 1

    print(json.dumps({"event": "notify_run", "sent": sent}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
