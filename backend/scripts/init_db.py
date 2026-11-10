from pathlib import Path

from app.db.connection import initialize_schema, validate_schema


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "backend" / "sql" / "schema.sql"
REQUIRED_TABLES = (
    "users",
    "businesses",
    "business_memberships",
    "workspaces",
    "analytical_objectives",
    "datasets",
    "customers",
    "agents",
    "transactions",
)


def main() -> None:
    initialize_schema(SCHEMA_PATH)
    validate_schema(REQUIRED_TABLES)
    print(f"Database schema is ready ({len(REQUIRED_TABLES)} tables validated)")


if __name__ == "__main__":
    main()
