"""SQLite engine + session setup for the Phase 2 platform backend.

Per docs/phase2/INFRA_STACK.md §2/§4: SQLite as a local file at
platform/data/platform.db, accessed via SQLAlchemy. Fully separate from
the public showcase site's data/ (JSON content) and build.py.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../platform
DATA_DIR = os.path.join(PLATFORM_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_DB_PATH = os.path.join(DATA_DIR, "platform.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session, always closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
