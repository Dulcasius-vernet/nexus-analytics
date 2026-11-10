from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str
    service: str


class DatabaseHealthResponse(HealthResponse):
    database: str


class OverviewResponse(BaseModel):
    business_id: int
    transaction_count: int
    transaction_value: Decimal
    average_transaction_value: Decimal
    labelled_fraud_count: int
    labelled_fraud_rate_pct: Decimal
    customer_count: int
    agent_count: int


class TransactionRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    transaction_id: int
    customer_id: int | None
    agent_id: int | None
    transaction_ts: datetime
    transaction_type: str
    amount: Decimal
    channel: str | None
    is_fraud: bool
    risk_reason: str | None


class PaginatedTransactions(BaseModel):
    items: list[TransactionRecord]
    page: int
    page_size: int
    total: int


class TransactionTypeSummary(BaseModel):
    transaction_type: str
    transaction_count: int
    total_value: Decimal
    average_value: Decimal


class TrendPoint(BaseModel):
    period_start: datetime
    transaction_count: int
    fraud_count: int
    fraud_rate_pct: Decimal


class RegionSummary(BaseModel):
    region: str
    transaction_count: int
    transaction_value: Decimal
    fraud_count: int


class DataQualityResponse(BaseModel):
    business_id: int
    total_records: int
    missing_customer_id: int
    missing_agent_id: int
    duplicate_transaction_ids: int
    invalid_amount: int
    invalid_timestamp: int
    invalid_hour: int
    inconsistent_customer_references: int
    inconsistent_agent_references: int
    missing_channel: int
    inconsistent_channel_format: int


class DatasetResponse(BaseModel):
    dataset_id: int
    workspace_id: int
    dataset_name: str
    source_type: str
    row_count: int | None
    schema_version: str | None
    created_at: datetime


class ReportSummary(BaseModel):
    transactions: int
    transaction_value: Decimal
    average_transaction: Decimal
    labelled_fraud: int
    high_failed_attempts: int


class ReportResponse(BaseModel):
    title: str
    business_id: int
    generated_at: datetime
    summary: ReportSummary
    notes: list[str]
