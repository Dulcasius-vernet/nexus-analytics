"""Opt-in live checks for PostgreSQL and Snwolley using the current environment."""
import asyncio
import os
from app.db.connection import get_connection, validate_schema
from app.services.snwolley import ask_snwolley

REQUIRED_TABLES = ("users", "businesses", "business_memberships", "workspaces", "analytical_objectives", "datasets", "customers", "agents", "transactions")


def main():
    if os.getenv("RUN_LIVE_INTEGRATION_CHECKS") != "1":
        raise SystemExit("Set RUN_LIVE_INTEGRATION_CHECKS=1 to enable live external integration checks.")
    validate_schema(REQUIRED_TABLES)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_database(), COUNT(*) FROM transactions")
        database_name, transaction_count = cur.fetchone()
    print(f"PostgreSQL: connected to {database_name}; transactions={transaction_count:,}; required schema present")
    result = asyncio.run(ask_snwolley("This is a connectivity test for the Nexus Analytics assignment. Reply with a short confirmation only."))
    print("Snwolley: request completed successfully")
    print("Provider response fields:", ", ".join(sorted(result.keys())) if isinstance(result, dict) else type(result).__name__)


if __name__ == "__main__":
    main()
