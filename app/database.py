import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR = Path(os.getenv("SCNGS_DATA_DIR", DEFAULT_DATA_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = f"sqlite:///{DATA_DIR}/novels.db"

_is_sqlite = DATABASE_URL.startswith("sqlite")
# First desktop launch runs long seeding/bootstrap write transactions while the
# background worker opens its first polling connections; installed-product storm
# conditions (WebView2 first-run, Defender scans) stretch single operations to
# 30-70s, so the busy timeout must cover that window instead of the 5s default.
_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 60_000

if _is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_connection_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()
else:
    engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)


def ensure_sqlite_wal_mode(db_engine: Engine = engine) -> None:
    if db_engine.dialect.name != "sqlite":
        return

    with db_engine.connect() as connection:
        current_mode = str(
            connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
        ).casefold()
        if current_mode == "wal":
            return

        configured_mode = str(
            connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one()
        ).casefold()
        if configured_mode != "wal":
            raise RuntimeError(
                "SQLite refused required WAL journal mode: "
                f"reported {configured_mode!r}."
            )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.config import get_settings

    ensure_sqlite_wal_mode()
    settings = get_settings()
    if not settings.db_auto_create:
        try:
            inspector = inspect(engine)
            tables = set(inspector.get_table_names())
            if "novels" in tables:
                return
            logging.getLogger(__name__).warning(
                "Database missing core tables; creating schema via metadata.create_all(). "
                "Consider running Alembic migrations or enabling DB_AUTO_CREATE."
            )
        except Exception:
            return

    Base.metadata.create_all(bind=engine)
