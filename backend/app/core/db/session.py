"""SQLite database session config.

DB path resolution:
  1. DATABASE_PATH env var
  2. Local fallback: a file next to the backend code (good for `python -m uvicorn` dev)
"""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

_LOCAL_DEFAULT = Path(__file__).parent.parent.parent.parent / "tender_analyst.db"
DB_PATH = Path(os.getenv("DATABASE_PATH", str(_LOCAL_DEFAULT)))

# Ensure parent directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
