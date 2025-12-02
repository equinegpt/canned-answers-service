# db.py
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# Load .env in local dev (no effect on Render unless you add one there)
load_dotenv()

# Prefer explicit DATABASE_URL, then Render-style fallbacks.
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("EXTERNAL_DATABASE_URL")
)

use_sqlite_fallback = False

if not DATABASE_URL:
    # Local dev fallback – keeps things running even if you don't point at Postgres.
    # This is a separate file DB next to app.py and does NOT touch your Render Postgres.
    DATABASE_URL = "sqlite:///./canned_answers_dev.db"
    use_sqlite_fallback = True

if use_sqlite_fallback:
    # SQLite engine
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
else:
    # Postgres via psycopg3
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )

    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()
