"""Idempotently load the synthetic demo tenant without deleting other tenants."""
from pathlib import Path
import logging
import pandas as pd
from app.db.connection import get_connection, initialize_schema
from app.services.data_quality import validate_transaction_csv

ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def main():
    schema_path = ROOT / "backend" / "sql" / "schema.sql"
    csv_path = ROOT / "data" / "transactions.csv"
    if not csv_path.exists():
        raise SystemExit("Generate data first: python -m scripts.generate_data")
    df, quality = validate_transaction_csv(csv_path)
    logger.info("Validated synthetic records=%d missing_values=%d duplicate_ids=%d", quality.record_count, quality.missing_values, quality.duplicate_transaction_ids)
    initialize_schema(schema_path)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT business_id FROM businesses WHERE business_name = %s ORDER BY business_id LIMIT 1", ("Demo Mobile Money Operator",))
        row = cur.fetchone()
        if row:
            business_id = row[0]
        else:
            cur.execute("INSERT INTO businesses (business_name, industry, country_code) VALUES (%s, %s, 'GH') RETURNING business_id", ("Demo Mobile Money Operator", "Financial Services"))
            business_id = cur.fetchone()[0]
        cur.execute("INSERT INTO workspaces (business_id, workspace_name, description) VALUES (%s, %s, %s) ON CONFLICT (business_id, workspace_name) DO NOTHING", (business_id, "Mobile Money Risk Analytics", "Synthetic transaction-risk demonstration workspace"))
        cur.execute("SELECT workspace_id FROM workspaces WHERE business_id = %s AND workspace_name = %s", (business_id, "Mobile Money Risk Analytics"))
        workspace_id = cur.fetchone()[0]
        cur.execute("INSERT INTO analytical_objectives (workspace_id, objective_name, objective_type, description) SELECT %s, 'Identify transaction risk patterns', 'classification', 'Establish a baseline for transaction-risk analytics' WHERE NOT EXISTS (SELECT 1 FROM analytical_objectives WHERE workspace_id = %s AND objective_type = 'classification')", (workspace_id, workspace_id))
        cur.execute("DELETE FROM transactions WHERE business_id = %s", (business_id,))
        cur.execute("DELETE FROM customers WHERE business_id = %s", (business_id,))
        cur.execute("DELETE FROM agents WHERE business_id = %s", (business_id,))
        cur.execute("INSERT INTO agents (agent_id, business_id, region, agent_tier) SELECT g, %s, 'Greater Accra', 'standard' FROM generate_series(5001,5200) g", (business_id,))
        cur.execute("INSERT INTO customers (customer_id, business_id, customer_segment, account_age_days) SELECT g, %s, 'retail', 365 FROM generate_series(10001,15000) g", (business_id,))
        df = df.copy()
        df["business_id"] = business_id
        with cur.copy("COPY transactions (transaction_id,business_id,customer_id,agent_id,transaction_ts,transaction_type,amount,channel,device_age_days,failed_attempts_24h,customer_tenure_days,hour_of_day,is_fraud,risk_reason) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)") as copy:
            import io
            copy.write(df.to_csv(index=False))
        cur.execute("DELETE FROM datasets WHERE workspace_id = %s AND dataset_name = %s", (workspace_id, "Synthetic mobile-money transactions"))
        cur.execute("INSERT INTO datasets (workspace_id, dataset_name, source_type, row_count, schema_version) VALUES (%s, %s, 'synthetic', %s, '1')", (workspace_id, "Synthetic mobile-money transactions", len(df)))
        cur.execute("SELECT COUNT(*) FROM transactions WHERE business_id = %s", (business_id,))
        loaded = cur.fetchone()[0]
        if loaded != len(df):
            raise RuntimeError(f"PostgreSQL validation failed: loaded={loaded}, expected={len(df)}")
    print(f"Loaded {loaded:,} synthetic transactions for demo business {business_id}; other businesses were not modified.")


if __name__ == "__main__":
    main()
