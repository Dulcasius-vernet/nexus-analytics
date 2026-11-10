import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.db.connection import DatabaseConnectionError, get_connection, initialize_schema, validate_schema
from app.main import app
from app.services.data_quality import validate_transaction_csv

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "backend" / "sql" / "schema.sql"
client = TestClient(app)


def database_available() -> bool:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


@unittest.skipUnless(database_available(), "PostgreSQL is not available")
class Stage1DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_schema(SCHEMA)
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO businesses (business_name, industry, country_code) VALUES ('Nexus Automated Test Business', 'Testing', 'GH') RETURNING business_id")
            cls.business_id = cur.fetchone()[0]
            cur.execute("INSERT INTO workspaces (business_id, workspace_name, description) VALUES (%s, 'Automated Test Workspace', 'Temporary integration-test workspace') RETURNING workspace_id", (cls.business_id,))
            cls.workspace_id = cur.fetchone()[0]

    @classmethod
    def tearDownClass(cls):
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM businesses WHERE business_id = %s", (cls.business_id,))

    def setUp(self):
        app.dependency_overrides[get_current_user] = lambda: {"user_id": 1, "full_name": "Integration Test", "email": "integration@example.com", "business_id": self.business_id, "role": "owner"}

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_database_initialization_is_idempotent(self):
        initialize_schema(SCHEMA)
        initialize_schema(SCHEMA)
        validate_schema(("users", "businesses", "business_memberships", "workspaces", "transactions"))

    def test_health_and_overview(self):
        self.assertEqual(client.get("/api/v1/health").status_code, 200)
        response = client.get("/api/v1/analytics/overview")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertGreaterEqual(response.json()["transaction_count"], 0)

    def test_pagination_and_filtering(self):
        response = client.get("/api/v1/analytics/transactions?page=1&page_size=5&fraud_status=true")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertLessEqual(len(body["items"]), 5)
        self.assertTrue(all(item["is_fraud"] for item in body["items"]))

    def test_data_quality_and_datasets(self):
        quality = client.get("/api/v1/data-quality")
        datasets = client.get("/api/v1/datasets")
        self.assertEqual(quality.status_code, 200, quality.text)
        self.assertEqual(datasets.status_code, 200, datasets.text)
        self.assertGreaterEqual(quality.json()["total_records"], 0)
        self.assertIsInstance(datasets.json(), list)

    def test_analytics_endpoints(self):
        for path in (
            "/api/v1/analytics/transactions?page_size=2",
            "/api/v1/analytics/fraud-trends",
            "/api/v1/analytics/transaction-types",
            "/api/v1/analytics/regions",
            "/api/v1/analytics/channels",
        ):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIsInstance(response.json(), list if "transactions" not in path else dict)

    def test_demo_dataset_ingestion_is_tenant_scoped_and_idempotent(self):
        response = client.post("/api/v1/datasets/demo")
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["row_count"], 30000)
        repeated = client.post("/api/v1/datasets/demo")
        self.assertEqual(repeated.status_code, 409)


class Stage1ValidationTests(unittest.TestCase):
    def test_generated_csv_validates(self):
        frame, summary = validate_transaction_csv(ROOT / "data" / "transactions.csv")
        self.assertEqual(len(frame), 30000)
        self.assertEqual(summary.duplicate_transaction_ids, 0)

    def test_invalid_request_and_database_failure(self):
        app.dependency_overrides[get_current_user] = lambda: {"user_id": 1, "full_name": "Test", "email": "test@example.com", "business_id": 1, "role": "owner"}
        try:
            self.assertEqual(client.get("/api/v1/analytics/transactions?page_size=0").status_code, 422)
            with patch("app.api.routes.get_connection", side_effect=DatabaseConnectionError("offline")):
                self.assertEqual(client.get("/api/v1/health/database").status_code, 503)
        finally:
            app.dependency_overrides.clear()
