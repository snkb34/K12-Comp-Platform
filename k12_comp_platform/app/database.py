from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import os

DATA_DIR = os.environ.get('APP_DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(DATA_DIR, 'k12_comp.db')}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith('sqlite') else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    try:
        return column_name in [c["name"] for c in inspector.get_columns(table_name)]
    except Exception:
        return False


def _add_column_if_missing(table_name: str, column_name: str, column_type_sql: str):
    """
    Lightweight schema upgrade helper.

    SQLAlchemy create_all creates new tables, but it does not add new columns
    to existing tables. This helper adds safe nullable/default columns for the
    current prototype without requiring a full migration framework yet.
    """
    if _column_exists(table_name, column_name):
        return

    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type_sql}"))


def upgrade_schema():
    """
    Backward-compatible schema upgrades for Sprint 1.

    Later, we should move to Alembic migrations. For now, this lets Render
    upgrade the existing PostgreSQL database safely on startup.
    """
    # Source Manager columns added to existing sources table.
    _add_column_if_missing("sources", "employee_group", "VARCHAR(100)")
    _add_column_if_missing("sources", "employee_sub_group", "VARCHAR(200)")
    _add_column_if_missing("sources", "document_type", "VARCHAR(100)")
    _add_column_if_missing("sources", "school_year", "VARCHAR(50)")
    _add_column_if_missing("sources", "parser", "VARCHAR(100)")
    _add_column_if_missing("sources", "status", "VARCHAR(50)")
    _add_column_if_missing("sources", "priority", "INTEGER")
    _add_column_if_missing("sources", "notes", "TEXT")


def backfill_source_fields():
    """
    Populate new Source fields from the older category field where possible.
    """
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE sources
            SET employee_group = COALESCE(employee_group, category),
                employee_sub_group = COALESCE(employee_sub_group, category),
                document_type = COALESCE(document_type, 'Salary Schedule'),
                school_year = COALESCE(school_year, ''),
                status = COALESCE(status, 'Active'),
                priority = COALESCE(priority, 1),
                parser = COALESCE(
                    parser,
                    CASE
                        WHEN lower(COALESCE(category, '')) LIKE '%licensed%' THEN 'Teacher Schedule'
                        WHEN lower(COALESCE(category, '')) LIKE '%admin%' THEN 'Admin Range'
                        WHEN lower(COALESCE(category, '')) LIKE '%classified%' THEN 'Classified Range'
                        ELSE 'Generic'
                    END
                )
            WHERE employee_group IS NULL
               OR employee_sub_group IS NULL
               OR document_type IS NULL
               OR status IS NULL
               OR parser IS NULL
               OR priority IS NULL
        """))


def init_db():
    from app import models

    # Create any brand-new tables.
    Base.metadata.create_all(bind=engine)

    # Add Sprint 1 columns to existing tables.
    upgrade_schema()

    # Backfill new fields from old data.
    backfill_source_fields()
