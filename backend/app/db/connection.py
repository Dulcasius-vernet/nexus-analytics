from pathlib import Path

import psycopg
from psycopg import OperationalError

from app.core.config import settings


class DatabaseConnectionError(RuntimeError):
    """Raised when PostgreSQL cannot be reached with the configured settings."""


def get_connection() -> psycopg.Connection:
    """Open a connection with psycopg commit, rollback, and close semantics."""
    try:
        return psycopg.connect(settings.database_url)
    except OperationalError as exc:
        raise DatabaseConnectionError("Unable to connect to PostgreSQL") from exc


def initialize_schema(schema_path: Path) -> None:
    """Apply the idempotent application schema in one transaction."""
    try:
        schema = schema_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Unable to read database schema: {schema_path}") from exc
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(schema)


def validate_schema(required_tables: tuple[str, ...]) -> None:
    """Fail explicitly when required application tables are not initialized."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            """,
            (list(required_tables),),
        )
        found = {row[0] for row in cur.fetchall()}
    missing = set(required_tables) - found
    if missing:
        names = ", ".join(sorted(missing))
        raise RuntimeError(f"Database schema is missing required tables: {names}")
