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
MOCK_DB_PATH = os.path.join(DATA_DIR, "platform-mock.db")


def _resolve_database_url() -> str:
    """Elige la base según el modo de datos (DESIGN.md §9.1, candado 1).

    En modo simulación se usa `platform-mock.db`, **nunca** `platform.db`.
    `platform.db` contiene los propietarios reales del CEO; si los inquilinos
    de prueba se guardaran ahí quedarían mezclados con datos reales y
    separarlos después sería trabajo manual y arriesgado. Con dos archivos, la
    purga de pruebas es borrar uno.

    Un `DATABASE_URL` explícito siempre gana: es lo que usan las pruebas
    automatizadas para trabajar sobre una base desechable.
    """
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    mode = os.environ.get("DATA_MODE", "mock").strip().lower()
    path = DEFAULT_DB_PATH if mode == "live" else MOCK_DB_PATH
    return f"sqlite:///{path}"


DATABASE_URL = _resolve_database_url()

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
