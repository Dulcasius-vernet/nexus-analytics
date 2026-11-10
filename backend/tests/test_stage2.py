import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.core.security import create_session, hash_password, read_session, verify_password
from app.main import app
from app.services.snwolley import SnwolleyConfigurationError, ask_snwolley
from app.core.config import settings

client = TestClient(app)
DEMO_USER = {"user_id": 9, "full_name": "Test User", "email": "test@example.com", "business_id": 77, "role": "owner"}


class FakeCursor:
    def __init__(self):
        self.row = None
        self.rows = []

    def __enter__(self): return self
    def __exit__(self, *args): return False

    def execute(self, query, params=None):
        sql = " ".join(query.lower().split())
        if "count(*)" in sql and "failed_attempts_24h" in sql:
            self.row = (30000, 1250000.50, 41.68, 125, 720)
        elif "select transaction_type" in sql:
            self.rows = [("transfer", 12000, 650000.0), ("cash_out", 9000, 400000.0)]
        elif "select coalesce(nullif(btrim(channel)" in sql:
            self.rows = [("USSD", 15000, 60), ("APP", 9000, 50)]
        elif "select count(*)" in sql and "coalesce(sum(amount)" in sql:
            self.row = (30000, 1250000.50, 125, 41.68)
        else:
            self.row = (1,)
            self.rows = []

    def fetchone(self): return self.row
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self): self._cursor = FakeCursor()
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self._cursor


class FakeAuthCursor:
    def __init__(self): self.row = None
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, query, params=None):
        sql = " ".join(query.lower().split())
        if sql.startswith("select 1 from users"):
            self.row = None
        elif "insert into users" in sql:
            self.row = (101,)
        elif "insert into businesses" in sql:
            self.row = (77,)
        elif "insert into workspaces" in sql:
            self.row = (301,)
        elif "select u.user_id" in sql:
            self.row = (101, "Integration Test", "integration@example.com", 77, "owner")
    def fetchone(self): return self.row


class FakeAuthConnection:
    def __init__(self): self._cursor = FakeAuthCursor()
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self._cursor


class Stage2SecurityTests(unittest.TestCase):
    def test_password_hash_and_verification(self):
        encoded = hash_password("Nexus-Strong-Password-2026")
        self.assertTrue(verify_password("Nexus-Strong-Password-2026", encoded))
        self.assertFalse(verify_password("incorrect", encoded))

    def test_signed_session_expiry_and_integrity(self):
        token = create_session(10, 20)
        claims = read_session(token)
        self.assertEqual(claims["uid"], 10)
        self.assertEqual(claims["bid"], 20)
        self.assertIsNone(read_session(token + "tampered"))

    def test_public_health_and_protected_analytics(self):
        self.assertEqual(client.get("/api/v1/health").status_code, 200)
        self.assertEqual(client.get("/api/v1/analytics/overview").status_code, 401)

    def test_snwolley_request_uses_server_key_and_non_streaming_payload(self):
        from app.services import snwolley
        captured = {}
        class FakeResponse:
            status_code = 200
            headers = {}
            def raise_for_status(self): pass
            def json(self): return {"content": "Verified synthetic insight"}
        class FakeClient:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def post(self, url, headers, json):
                captured.update({"url": url, "headers": headers, "json": json})
                return FakeResponse()
        old_key, old_url = settings.snwolley_api_key, settings.snwolley_api_url
        settings.snwolley_api_key = "test-key-not-a-real-credential"
        settings.snwolley_api_url = "https://example.invalid/test"
        try:
            with patch("app.services.snwolley.httpx.AsyncClient", return_value=FakeClient()):
                result = asyncio.run(ask_snwolley("Summarise supplied metrics"))
        finally:
            settings.snwolley_api_key, settings.snwolley_api_url = old_key, old_url
        self.assertEqual(result["content"], "Verified synthetic insight")
        self.assertEqual(captured["headers"]["X-API-Key"], "test-key-not-a-real-credential")
        self.assertEqual(captured["json"], {"message": "Summarise supplied metrics", "stream": False})

    def test_snwolley_requires_a_configured_key(self):
        original = settings.snwolley_api_key
        settings.snwolley_api_key = ""
        try:
            with self.assertRaises(SnwolleyConfigurationError):
                asyncio.run(ask_snwolley("test request"))
        finally:
            settings.snwolley_api_key = original


class Stage2ApplicationTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[get_current_user] = lambda: DEMO_USER

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_business_registration_creates_session_cookie(self):
        client.cookies.clear()
        payload = {"full_name": "Integration Test", "email": "integration@example.com", "password": "Nexus-Strong-Password-2026",
                   "business_name": "Example Analytics Ltd", "industry": "Financial Services",
                   "workspace_name": "Risk Workspace", "objective_type": "fraud-risk"}
        with patch("app.api.auth.get_connection", return_value=FakeAuthConnection()):
            response = client.post("/api/v1/auth/register", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["business_id"], 77)
        self.assertIn("nexus_session", response.headers.get("set-cookie", ""))
        self.assertIn("httponly", response.headers.get("set-cookie", "").lower())
        client.cookies.clear()

    def test_prediction_endpoint_uses_saved_pipeline(self):
        payload = {"transactions": [{"amount": 250, "hour_of_day": 22, "device_age_days": 3,
                                    "failed_attempts_24h": 2, "customer_tenure_days": 12,
                                    "transaction_type": "transfer", "channel": "APP"}]}
        response = client.post("/api/v1/models/predict", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body["results"]), 1)
        self.assertIn("risk_score", body["results"][0])
        self.assertIn("flagged_for_review", body["results"][0])
        self.assertIn("Synthetic-data demonstration", body["disclaimer"])

    def test_prediction_validates_input(self):
        response = client.post("/api/v1/models/predict", json={"transactions": [{"amount": -1, "hour_of_day": 40}]})
        self.assertEqual(response.status_code, 422)

    def test_ai_report_uses_aggregate_context_and_returns_narrative(self):
        with patch("app.api.routes.get_connection", return_value=FakeConnection()), patch(
            "app.api.routes.ask_snwolley", new=AsyncMock(return_value={"content": "Summary\n- Review unusual activity."})
        ) as mocked:
            response = client.post("/api/v1/reports/ai", json={"question": "Summarise the business risk"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Summary", response.json()["narrative"])
        prompt = mocked.await_args.args[0]
        self.assertIn("observed_database_metrics", prompt)
        self.assertIn("Do not describe labelled fraud as confirmed fraud", prompt)

    def test_ai_report_respects_provider_rate_limit(self):
        from app.services.snwolley import SnwolleyRateLimitError
        with patch("app.api.routes.get_connection", return_value=FakeConnection()), patch(
            "app.api.routes.ask_snwolley", new=AsyncMock(side_effect=SnwolleyRateLimitError("17"))
        ):
            response = client.post("/api/v1/reports/ai", json={"question": "Summarise the business risk"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers.get("retry-after"), "17")

    def test_ai_report_pdf_is_valid_pdf_response(self):
        with patch("app.api.routes.get_connection", return_value=FakeConnection()), patch(
            "app.api.routes.ask_snwolley", new=AsyncMock(return_value={"content": "Executive summary.\nReview the flagged activity."})
        ):
            response = client.post("/api/v1/reports/ai.pdf", json={"question": "Prepare the management report"})
        self.assertEqual(response.status_code, 200, response.text[:200])
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_tenant_scope_rejects_other_business_id(self):
        response = client.get("/api/v1/analytics/overview?business_id=999")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
