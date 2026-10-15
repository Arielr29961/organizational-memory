from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_columns(columns: dict[str, dict[str, str]]):
    """Add columns missing from existing tables ({table: {column: sql_type}}); create_all only creates new tables."""
    existing_tables = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        for table, cols in columns.items():
            if table not in existing_tables:
                continue
            present = {c["name"] for c in inspect(conn).get_columns(table)}
            for name, sql_type in cols.items():
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
