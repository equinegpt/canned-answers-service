import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Try to read DATABASE_URL from the environment (for Render / prod)
DATABASE_URL = os.getenv("DATABASE_URL")

# For local dev, fall back to a simple SQLite file if not set
if not DATABASE_URL:
    # This lives in the same folder as app.py / db.py
    DATABASE_URL = "sqlite:///./canned_answers.db"
    connect_args = {"check_same_thread": False}
else:
    # Postgres etc. don't need special connect_args
    connect_args = {}

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
