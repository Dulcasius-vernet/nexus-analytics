import logging
import io
import json
from pathlib import Path
from datetime import datetime
from decimal import Decimal

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from psycopg import Error as PsycopgError
from pydantic import BaseModel, Field
from fastapi.responses import Response as FastAPIResponse
from functools import lru_cache
from io import BytesIO
import joblib
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

from app.api.auth import get_business_id, get_current_user
from app.api.models import (
    DataQualityResponse,
    DatabaseHealthResponse,
    DatasetResponse,
    HealthResponse,
    OverviewResponse,
    PaginatedTransactions,
    ReportResponse,
    RegionSummary,
    TransactionRecord,
    TransactionTypeSummary,
    TrendPoint,
)
from app.db.connection import DatabaseConnectionError, get_connection, validate_schema
from app.services.snwolley import SnwolleyConfigurationError, SnwolleyRateLimitError, SnwolleyResponseError, ask_snwolley
from app.services.data_quality import validate_transaction_csv

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])

REQUIRED_TABLES = (
    "users", "businesses", "business_memberships", "workspaces", "analytical_objectives", "datasets",
    "customers", "agents", "transactions",
)


class InsightRequest(BaseModel):
    question: str = Field(min_length=8, max_length=2000)
    business_id: int | None = Field(default=None, ge=1)


def _database_error(exc: Exception, detail: str) -> HTTPException:
    logger.exception("Database operation failed", exc_info=exc)
    return HTTPException(status_code=503, detail=detail)


@router.get("/health/database", response_model=DatabaseHealthResponse)
@router.get("/health/ready", response_model=DatabaseHealthResponse, include_in_schema=False)
def database_health() -> DatabaseHealthResponse:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        validate_schema(REQUIRED_TABLES)
    except (DatabaseConnectionError, PsycopgError, RuntimeError) as exc:
        raise _database_error(exc, "Database is unavailable or not initialized") from exc
    return DatabaseHealthResponse(status="ready", service="nexus-analytics-api", database="ok")


@router.get("/analytics/overview", response_model=OverviewResponse)
def analytics_overview(business_id: int = Depends(get_business_id)) -> OverviewResponse:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(t.*), COALESCE(SUM(t.amount), 0), COALESCE(AVG(t.amount), 0),
                       COUNT(*) FILTER (WHERE t.is_fraud), COUNT(DISTINCT c.customer_id),
                       COUNT(DISTINCT a.agent_id)
                FROM transactions t
                LEFT JOIN customers c ON c.customer_id = t.customer_id AND c.business_id = t.business_id
                LEFT JOIN agents a ON a.agent_id = t.agent_id AND a.business_id = t.business_id
                WHERE t.business_id = %s
                """,
                (business_id,),
            )
            count, value, average, fraud_count, customer_count, agent_count = cur.fetchone()
        rate = Decimal(fraud_count * 100) / Decimal(count) if count else Decimal("0")
        return OverviewResponse(
            business_id=business_id, transaction_count=count, transaction_value=value,
            average_transaction_value=average, labelled_fraud_count=fraud_count,
            labelled_fraud_rate_pct=rate, customer_count=customer_count, agent_count=agent_count,
        )
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "Analytics database is unavailable or not initialized") from exc


@router.get("/analytics/transactions", response_model=PaginatedTransactions)
def transactions(
    business_id: int = Depends(get_business_id),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    transaction_type: str | None = Query(default=None, min_length=1, max_length=30),
    channel: str | None = Query(default=None, min_length=1, max_length=30),
    fraud_status: bool | None = None,
) -> PaginatedTransactions:
    where = ["business_id = %s"]
    params: list[object] = [business_id]
    if start_date:
        where.append("transaction_ts >= %s")
        params.append(start_date)
    if end_date:
        where.append("transaction_ts < %s")
        params.append(end_date)
    if transaction_type:
        where.append("transaction_type = %s")
        params.append(transaction_type)
    if channel:
        where.append("channel = %s")
        params.append(channel)
    if fraud_status is not None:
        where.append("is_fraud = %s")
        params.append(fraud_status)
    clause = " AND ".join(where)
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM transactions WHERE {clause}", params)
            total = cur.fetchone()[0]
            cur.execute(
                f"""
                SELECT transaction_id, customer_id, agent_id, transaction_ts,
                       transaction_type, amount, channel, is_fraud, risk_reason
                FROM transactions WHERE {clause}
                ORDER BY transaction_ts DESC, transaction_id DESC
                LIMIT %s OFFSET %s
                """,
                [*params, page_size, (page - 1) * page_size],
            )
            items = [TransactionRecord(**dict(zip(TransactionRecord.model_fields, row))) for row in cur.fetchall()]
        return PaginatedTransactions(items=items, page=page, page_size=page_size, total=total)
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "Analytics database is unavailable or not initialized") from exc


@router.get("/analytics/fraud-trends", response_model=list[TrendPoint])
@router.get("/analytics/weekly", response_model=list[TrendPoint], include_in_schema=False)
def fraud_trends(business_id: int = Depends(get_business_id)) -> list[TrendPoint]:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT DATE_TRUNC('week', transaction_ts), COUNT(*),
                       COUNT(*) FILTER (WHERE is_fraud),
                       ROUND(100.0 * COUNT(*) FILTER (WHERE is_fraud) / NULLIF(COUNT(*), 0), 3)
                FROM transactions WHERE business_id = %s
                GROUP BY 1 ORDER BY 1
                """,
                (business_id,),
            )
            return [TrendPoint(period_start=row[0], transaction_count=row[1], fraud_count=row[2], fraud_rate_pct=row[3]) for row in cur.fetchall()]
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "Analytics database is unavailable or not initialized") from exc


@router.get("/analytics/transaction-types", response_model=list[TransactionTypeSummary])
def transaction_types(business_id: int = Depends(get_business_id)) -> list[TransactionTypeSummary]:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT transaction_type, COUNT(*), COALESCE(SUM(amount), 0), COALESCE(AVG(amount), 0)
                FROM transactions WHERE business_id = %s
                GROUP BY transaction_type ORDER BY SUM(amount) DESC
                """,
                (business_id,),
            )
            return [TransactionTypeSummary(transaction_type=row[0], transaction_count=row[1], total_value=row[2], average_value=row[3]) for row in cur.fetchall()]
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "Analytics database is unavailable or not initialized") from exc


@router.get("/analytics/regions", response_model=list[RegionSummary])
def regions(business_id: int = Depends(get_business_id)) -> list[RegionSummary]:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(a.region, 'Unattributed'), COUNT(t.*), COALESCE(SUM(t.amount), 0),
                       COUNT(*) FILTER (WHERE t.is_fraud)
                FROM transactions t
                LEFT JOIN agents a ON a.agent_id = t.agent_id AND a.business_id = t.business_id
                WHERE t.business_id = %s
                GROUP BY 1 ORDER BY COUNT(t.*) DESC
                """,
                (business_id,),
            )
            return [RegionSummary(region=row[0], transaction_count=row[1], transaction_value=row[2], fraud_count=row[3]) for row in cur.fetchall()]
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "Analytics database is unavailable or not initialized") from exc


@router.get("/analytics/channels")
def channel_analytics(business_id: int = Depends(get_business_id)) -> list[dict]:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT COALESCE(NULLIF(BTRIM(channel), ''), 'Unspecified') AS channel,
                          COUNT(*), COALESCE(SUM(amount), 0), COUNT(*) FILTER (WHERE is_fraud)
                   FROM transactions WHERE business_id = %s GROUP BY 1 ORDER BY COUNT(*) DESC""",
                (business_id,),
            )
            return [{"channel": r[0], "transaction_count": r[1], "transaction_value": r[2], "fraud_count": r[3]} for r in cur.fetchall()]
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "Channel analytics are unavailable") from exc


@router.get("/data-quality", response_model=DataQualityResponse)
@router.get("/analytics/data-quality", response_model=DataQualityResponse, include_in_schema=False)
def data_quality(business_id: int = Depends(get_business_id)) -> DataQualityResponse:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE t.customer_id IS NULL),
                       COUNT(*) FILTER (WHERE t.agent_id IS NULL),
                       COUNT(*) FILTER (WHERE t.amount < 0),
                       COUNT(*) FILTER (WHERE t.transaction_ts IS NULL),
                       COUNT(*) FILTER (WHERE t.hour_of_day NOT BETWEEN 0 AND 23),
                       COUNT(*) FILTER (WHERE t.channel IS NULL OR BTRIM(t.channel) = ''),
                       COUNT(*) FILTER (WHERE t.channel IS NOT NULL AND t.channel <> BTRIM(t.channel)),
                       COUNT(*) FILTER (WHERE c.customer_id IS NULL AND t.customer_id IS NOT NULL),
                       COUNT(*) FILTER (WHERE a.agent_id IS NULL AND t.agent_id IS NOT NULL)
                FROM transactions t
                LEFT JOIN customers c ON c.customer_id = t.customer_id AND c.business_id = t.business_id
                LEFT JOIN agents a ON a.agent_id = t.agent_id AND a.business_id = t.business_id
                WHERE t.business_id = %s
                """,
                (business_id,),
            )
            row = cur.fetchone()
            cur.execute(
                "SELECT COUNT(*) FROM (SELECT transaction_id FROM transactions WHERE business_id = %s GROUP BY transaction_id HAVING COUNT(*) > 1) duplicates",
                (business_id,),
            )
            duplicate_ids = cur.fetchone()[0]
        return DataQualityResponse(
            business_id=business_id, total_records=row[0], missing_customer_id=row[1],
            missing_agent_id=row[2], invalid_amount=row[3], invalid_timestamp=row[4],
            invalid_hour=row[5], missing_channel=row[6], inconsistent_channel_format=row[7],
            inconsistent_customer_references=row[8], inconsistent_agent_references=row[9],
            duplicate_transaction_ids=duplicate_ids,
        )
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "Analytics database is unavailable or not initialized") from exc


@router.get("/models/metrics")
def model_metrics() -> dict:
    """Return metrics saved by the reproducible training pipeline."""
    metrics_path = Path(__file__).resolve().parents[2] / "artifacts" / "metrics.json"
    if not metrics_path.exists():
        raise HTTPException(status_code=404, detail="Model metrics are not available; train the model first")
    try:
        return json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("Unable to read model metrics")
        raise HTTPException(status_code=500, detail="Model metrics could not be read") from exc


@router.get("/datasets", response_model=list[DatasetResponse])
def datasets(business_id: int = Depends(get_business_id)) -> list[DatasetResponse]:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.dataset_id, d.workspace_id, d.dataset_name, d.source_type,
                       d.row_count, d.schema_version, d.created_at
                FROM datasets d JOIN workspaces w ON w.workspace_id = d.workspace_id
                WHERE w.business_id = %s ORDER BY d.created_at DESC
                """,
                (business_id,),
            )
            return [DatasetResponse(**dict(zip(DatasetResponse.model_fields, row))) for row in cur.fetchall()]
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "Analytics database is unavailable or not initialized") from exc


@router.post("/datasets/upload", response_model=DatasetResponse, status_code=201)
async def upload_dataset(
    file: UploadFile = File(...),
    business_id: int = Depends(get_business_id),
) -> DatasetResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file")
    try:
        contents = await file.read(25 * 1024 * 1024 + 1)
        if len(contents) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="CSV uploads are limited to 25 MB")
        frame, quality = validate_transaction_csv(io.BytesIO(contents))
    except (ValueError, pd.errors.ParserError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if quality.record_count == 0:
        raise HTTPException(status_code=422, detail="The CSV file has no records")
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM transactions WHERE business_id = %s AND transaction_id = ANY(%s)", (business_id, frame["transaction_id"].tolist()))
            existing_ids = cur.fetchone()[0]
            if existing_ids:
                raise HTTPException(status_code=409, detail="Some transaction IDs already exist for this business")
            cur.execute("SELECT workspace_id FROM workspaces WHERE business_id = %s ORDER BY workspace_id LIMIT 1", (business_id,))
            workspace = cur.fetchone()
            if workspace is None:
                raise HTTPException(status_code=404, detail="Business workspace was not found")
            workspace_id = workspace[0]
            cur.execute(
                """
                INSERT INTO datasets (workspace_id, dataset_name, source_type, row_count, schema_version)
                VALUES (%s, %s, 'csv-upload', %s, '1')
                RETURNING dataset_id, workspace_id, dataset_name, source_type, row_count, schema_version, created_at
                """,
                (workspace_id, Path(file.filename).name[:160], len(frame)),
            )
            dataset = cur.fetchone()
            for customer_id in frame["customer_id"].dropna().astype(int).unique():
                cur.execute(
                    "INSERT INTO customers (customer_id, business_id, customer_segment) VALUES (%s, %s, 'uploaded') ON CONFLICT DO NOTHING",
                    (int(customer_id), business_id),
                )
            for agent_id in frame["agent_id"].dropna().astype(int).unique():
                cur.execute(
                    "INSERT INTO agents (agent_id, business_id, region, agent_tier) VALUES (%s, %s, 'Uploaded data', 'uploaded') ON CONFLICT DO NOTHING",
                    (int(agent_id), business_id),
                )
            upload_frame = frame.copy()
            upload_frame["business_id"] = business_id
            optional_defaults = {
                "channel": None,
                "device_age_days": None,
                "failed_attempts_24h": 0,
                "customer_tenure_days": None,
                "hour_of_day": upload_frame["transaction_ts"].dt.hour,
                "risk_reason": None,
            }
            for column, default in optional_defaults.items():
                if column not in upload_frame:
                    upload_frame[column] = default
            copy_columns = [
                "transaction_id", "business_id", "customer_id", "agent_id",
                "transaction_ts", "transaction_type", "amount", "channel",
                "device_age_days", "failed_attempts_24h", "customer_tenure_days",
                "hour_of_day", "is_fraud", "risk_reason",
            ]
            upload_frame = upload_frame[copy_columns]
            columns = ",".join(copy_columns)
            with cur.copy(f"COPY transactions ({columns}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)") as copy:
                copy.write(upload_frame.to_csv(index=False))
        return DatasetResponse(**dict(zip(DatasetResponse.model_fields, dataset)))
    except HTTPException:
        raise
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "The dataset could not be loaded") from exc


@router.post("/datasets/demo", status_code=201)
def load_demo_dataset(business_id: int = Depends(get_business_id)) -> dict:
    """Load the bundled reproducible synthetic transaction dataset into this tenant."""
    csv_path = Path(__file__).resolve().parents[3] / "data" / "transactions.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail="Bundled synthetic dataset is not available")
    try:
        frame, quality = validate_transaction_csv(csv_path)
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT workspace_id FROM workspaces WHERE business_id = %s ORDER BY workspace_id LIMIT 1", (business_id,))
            workspace = cur.fetchone()
            if not workspace:
                raise HTTPException(status_code=404, detail="Create a workspace before loading the demo dataset")
            workspace_id = workspace[0]
            cur.execute("SELECT COUNT(*) FROM transactions WHERE business_id = %s AND transaction_id = ANY(%s)", (business_id, frame["transaction_id"].tolist()))
            if cur.fetchone()[0]:
                raise HTTPException(status_code=409, detail="The synthetic dataset is already loaded for this workspace")
            for customer_id in frame["customer_id"].dropna().astype(int).unique():
                cur.execute("INSERT INTO customers (customer_id, business_id, customer_segment) VALUES (%s, %s, 'retail') ON CONFLICT DO NOTHING", (int(customer_id), business_id))
            for agent_id in frame["agent_id"].dropna().astype(int).unique():
                cur.execute("INSERT INTO agents (agent_id, business_id, region, agent_tier) VALUES (%s, %s, 'Greater Accra', 'standard') ON CONFLICT DO NOTHING", (int(agent_id), business_id))
            upload_frame = frame.copy()
            upload_frame["business_id"] = business_id
            columns = ["transaction_id", "business_id", "customer_id", "agent_id", "transaction_ts", "transaction_type", "amount", "channel", "device_age_days", "failed_attempts_24h", "customer_tenure_days", "hour_of_day", "is_fraud", "risk_reason"]
            upload_frame = upload_frame[columns]
            with cur.copy(f"COPY transactions ({','.join(columns)}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)") as copy:
                copy.write(upload_frame.to_csv(index=False))
            cur.execute("INSERT INTO datasets (workspace_id, dataset_name, source_type, row_count, schema_version) VALUES (%s, %s, 'synthetic', %s, '1') RETURNING dataset_id", (workspace_id, "Synthetic mobile-money transactions", len(frame)))
            dataset_id = cur.fetchone()[0]
        return {"dataset_id": dataset_id, "row_count": len(frame), "missing_values": quality.missing_values, "duplicate_transaction_ids": quality.duplicate_transaction_ids, "message": "Synthetic demonstration data loaded successfully"}
    except HTTPException:
        raise
    except (ValueError, pd.errors.ParserError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "The synthetic dataset could not be loaded") from exc


@router.get("/reports/latest", response_model=ReportResponse)
def latest_report(business_id: int = Depends(get_business_id)) -> ReportResponse:
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(amount), 0), COALESCE(AVG(amount), 0),
                       COUNT(*) FILTER (WHERE is_fraud),
                       COUNT(*) FILTER (WHERE failed_attempts_24h >= 2)
                FROM transactions WHERE business_id = %s
                """,
                (business_id,),
            )
            count, value, average, fraud_count, high_failed_attempts = cur.fetchone()
        return {
            "title": "Business transaction report",
            "business_id": business_id,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "transactions": count,
                "transaction_value": value,
                "average_transaction": average,
                "labelled_fraud": fraud_count,
                "high_failed_attempts": high_failed_attempts,
            },
            "notes": [
                "This report describes the loaded data. Labelled fraud is not proof of confirmed fraud.",
                "Review high failed-attempt activity with the underlying transaction records.",
            ],
        }
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "The report could not be generated") from exc


@router.post("/ai/insights")
async def generate_insights(request: InsightRequest, user: dict = Depends(get_current_user)):
    business_id = int(user["business_id"])
    if request.business_id is not None and request.business_id != business_id:
        raise HTTPException(status_code=403, detail="You do not have access to this business")
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0), COUNT(*) FILTER (WHERE is_fraud), COALESCE(AVG(amount), 0) FROM transactions WHERE business_id = %s", (business_id,))
            count, value, fraud_count, avg_value = cur.fetchone()
        context = (
            "Business context: synthetic Ghana mobile-money transaction-risk demonstration.\n"
            f"Transaction count: {count}; total value: {float(value):.2f} GHS; labelled fraud count: {fraud_count}; "
            f"average transaction: {float(avg_value):.2f} GHS.\nBusiness ID: {business_id}.\nBusiness user question: {request.question}\n"
            "Use only these supplied figures. Distinguish observed data from hypotheses. Do not claim causation or invent metrics."
        )
        return {"result": await ask_snwolley(context), "context_scope": "aggregate_only"}
    except SnwolleyConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SnwolleyRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": exc.retry_after}) from exc
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "AI insight request failed") from exc
    except SnwolleyResponseError as exc:
        logger.warning("Snwolley returned an invalid response")
        raise HTTPException(status_code=502, detail="The AI provider returned an invalid response") from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("Snwolley returned HTTP %s", exc.response.status_code)
        raise HTTPException(status_code=502, detail="The AI provider could not complete the request") from exc
    except httpx.HTTPError as exc:
        logger.warning("Snwolley transport failure: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="The AI provider is temporarily unreachable") from exc


class PredictionInput(BaseModel):
    amount: float = Field(gt=0, le=10_000_000)
    hour_of_day: int = Field(ge=0, le=23)
    device_age_days: int | None = Field(default=None, ge=0, le=100_000)
    failed_attempts_24h: int = Field(default=0, ge=0, le=1000)
    customer_tenure_days: int | None = Field(default=None, ge=0, le=100_000)
    transaction_type: str = Field(min_length=1, max_length=30)
    channel: str | None = Field(default=None, max_length=30)


class PredictionRequest(BaseModel):
    transactions: list[PredictionInput] = Field(min_length=1, max_length=500)


@lru_cache(maxsize=1)
def _load_model():
    model_path = Path(__file__).resolve().parents[2] / "artifacts" / "fraud_risk_pipeline.joblib"
    if not model_path.exists():
        raise FileNotFoundError("Model artifact is not available; train the model first")
    return joblib.load(model_path)


@router.post("/models/predict")
def predict_risk(request: PredictionRequest):
    try:
        model = _load_model()
        metrics_path = Path(__file__).resolve().parents[2] / "artifacts" / "metrics.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        threshold = float(metrics.get("threshold", 0.5))
        frame = pd.DataFrame([item.model_dump() for item in request.transactions])
        probabilities = model.predict_proba(frame)[:, 1]
        results = []
        for index, probability in enumerate(probabilities):
            score = float(probability)
            flagged = score >= threshold
            results.append({
                "row": index + 1,
                "risk_score": round(score, 6),
                "risk_threshold": threshold,
                "risk_band": "high" if score >= max(threshold, 0.35) else "elevated" if score >= threshold * 0.65 else "lower",
                "flagged_for_review": bool(flagged),
                "recommendation": "Review this transaction using additional evidence" if flagged else "No model alert; continue normal controls",
            })
        return {"model": "fraud_risk_pipeline", "model_type": "RandomForestClassifier", "threshold": threshold,
                "results": results, "disclaimer": "Synthetic-data demonstration only. Scores are not calibrated probabilities and must not be used as standalone fraud decisions."}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, OSError, KeyError) as exc:
        logger.exception("Model inference failed")
        raise HTTPException(status_code=500, detail="Model inference could not be completed") from exc


class AIReportRequest(BaseModel):
    business_id: int | None = Field(default=None, ge=1)
    question: str = Field(default="Prepare an executive summary of the business performance, key risk patterns and practical next steps.", min_length=8, max_length=2000)


async def _build_ai_report(business_id: int, question: str) -> tuple[dict, str]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*), COALESCE(SUM(amount), 0), COALESCE(AVG(amount), 0),
                      COUNT(*) FILTER (WHERE is_fraud),
                      COUNT(*) FILTER (WHERE failed_attempts_24h >= 2)
               FROM transactions WHERE business_id = %s""", (business_id,)
        )
        count, value, average, fraud_count, failed = cur.fetchone()
        cur.execute(
            """SELECT transaction_type, COUNT(*), COALESCE(SUM(amount), 0)
               FROM transactions WHERE business_id = %s GROUP BY transaction_type ORDER BY COUNT(*) DESC LIMIT 8""",
            (business_id,),
        )
        type_rows = cur.fetchall()
        cur.execute(
            """SELECT COALESCE(NULLIF(BTRIM(channel), ''), 'Unspecified'), COUNT(*), COUNT(*) FILTER (WHERE is_fraud)
               FROM transactions WHERE business_id = %s GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 8""",
            (business_id,),
        )
        channel_rows = cur.fetchall()
    metrics_path = Path(__file__).resolve().parents[2] / "artifacts" / "metrics.json"
    model_metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {"status": "not trained"}
    context = {
        "business_context": "Synthetic Ghana mobile-money transaction-risk demonstration",
        "business_id": business_id,
        "observed_database_metrics": {
            "transaction_count": count, "transaction_value_GHS": float(value),
            "average_transaction_GHS": float(average), "labelled_fraud_count": fraud_count,
            "transactions_with_two_or_more_failed_attempts": failed,
        },
        "transaction_type_summary": [{"type": r[0], "count": r[1], "value_GHS": float(r[2])} for r in type_rows],
        "channel_summary": [{"channel": r[0], "count": r[1], "labelled_fraud_count": r[2]} for r in channel_rows],
        "model_evaluation": {k: model_metrics.get(k) for k in ("roc_auc", "average_precision", "baseline_roc_auc", "baseline_average_precision", "threshold", "threshold_metrics", "note")},
        "user_request": question,
    }
    prompt = (
        "You are an analytical assistant preparing a concise management report. Use only the supplied context. "
        "Separate observed facts from hypotheses, mention the synthetic-data limitation, and do not claim causation. "
        "Do not describe labelled fraud as confirmed fraud. Discuss the model's limitations and recommend practical human-reviewed actions. "
        "If a metric is absent, say it is unavailable rather than inventing it.\n\n" + json.dumps(context, ensure_ascii=False)
    )
    provider_response = await ask_snwolley(prompt)
    content = provider_response.get("content") or provider_response.get("choices", [{}])[0].get("message", {}).get("content") or json.dumps(provider_response)
    if isinstance(content, dict):
        content = content.get("content") or json.dumps(content)
    return context, str(content)


@router.post("/reports/ai")
async def generate_ai_report(request: AIReportRequest, user: dict = Depends(get_current_user)):
    business_id = int(user["business_id"])
    if request.business_id is not None and request.business_id != business_id:
        raise HTTPException(status_code=403, detail="You do not have access to this business")
    try:
        context, narrative = await _build_ai_report(business_id, request.question)
        return {"title": "AI-assisted business intelligence report", "business_id": business_id,
                "generated_at": datetime.now().isoformat(), "context": context, "narrative": narrative,
                "disclaimer": "AI-generated analysis is advisory and must be checked against source data."}
    except SnwolleyConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SnwolleyRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": exc.retry_after}) from exc
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "Report data could not be retrieved") from exc
    except SnwolleyResponseError as exc:
        raise HTTPException(status_code=502, detail="The AI provider returned an invalid response") from exc
    except httpx.HTTPError as exc:
        logger.warning("AI report provider failure: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="The AI provider could not generate the report") from exc


@router.post("/reports/ai.pdf")
async def download_ai_report(request: AIReportRequest, user: dict = Depends(get_current_user)):
    business_id = int(user["business_id"])
    if request.business_id is not None and request.business_id != business_id:
        raise HTTPException(status_code=403, detail="You do not have access to this business")
    try:
        context, narrative = await _build_ai_report(business_id, request.question)
    except SnwolleyConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SnwolleyRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": exc.retry_after}) from exc
    except (DatabaseConnectionError, PsycopgError) as exc:
        raise _database_error(exc, "Report data could not be retrieved") from exc
    except SnwolleyResponseError as exc:
        raise HTTPException(status_code=502, detail="The AI provider returned an invalid response") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="The AI provider could not generate the report") from exc

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42)
    styles = getSampleStyleSheet()
    story = [Paragraph("Nexus Analytics", styles["Title"]), Paragraph("AI-assisted Business Intelligence Report", styles["Heading2"]),
             Paragraph(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} · Business workspace {business_id}", styles["Normal"]), Spacer(1, 16),
             Paragraph("Observed metrics", styles["Heading2"])]
    observed = context["observed_database_metrics"]
    table_data = [["Metric", "Observed value"], ["Transactions", f"{observed['transaction_count']:,}"],
                  ["Transaction value", f"GHS {observed['transaction_value_GHS']:,.2f}"],
                  ["Average transaction", f"GHS {observed['average_transaction_GHS']:,.2f}"],
                  ["Labelled fraud records", f"{observed['labelled_fraud_count']:,}"],
                  ["Records with >=2 failed attempts", f"{observed['transactions_with_two_or_more_failed_attempts']:,}"]]
    table = Table(table_data, colWidths=[245, 220])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d3557")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("PADDING", (0, 0), (-1, -1), 7)]))
    story.extend([table, Spacer(1, 16), Paragraph("AI-generated management analysis", styles["Heading2"])])
    for paragraph in narrative.splitlines():
        cleaned = paragraph.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if cleaned:
            story.extend([Paragraph(cleaned, styles["BodyText"]), Spacer(1, 6)])
    story.extend([Spacer(1, 12), Paragraph("Limitations: This demonstration uses synthetic data. Labels are not verified cases, model scores are not calibrated probabilities, and generated recommendations require human review.", styles["Italic"])])
    doc.build(story)
    return FastAPIResponse(content=buffer.getvalue(), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=nexus-analytics-ai-report.pdf"})
