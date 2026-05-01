"""SQLAlchemy ORM definitions."""
from __future__ import annotations

import os

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def engine_url() -> str:
    user = os.environ.get("DB_USER", "todo")
    password = os.environ["DB_PASSWORD"]
    host = os.environ.get("DB_HOST", "postgres")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "todo")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


class Base(DeclarativeBase):
    pass


class Todo(Base):
    __tablename__ = "todos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
