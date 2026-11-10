from dataclasses import dataclass
from pathlib import Path
from typing import IO

import pandas as pd


REQUIRED_COLUMNS = (
    "transaction_id",
    "business_id",
    "customer_id",
    "agent_id",
    "transaction_ts",
    "transaction_type",
    "amount",
    "is_fraud",
)


@dataclass(frozen=True)
class DataQualitySummary:
    record_count: int
    missing_values: int
    duplicate_transaction_ids: int
    invalid_amounts: int
    invalid_timestamps: int
    invalid_foreign_keys: int


def validate_transaction_csv(csv_path: Path | IO[bytes]) -> tuple[pd.DataFrame, DataQualitySummary]:
    frame = pd.read_csv(csv_path)
    missing_columns = set(REQUIRED_COLUMNS) - set(frame.columns)
    if missing_columns:
        raise ValueError(f"Transaction CSV is missing columns: {', '.join(sorted(missing_columns))}")

    timestamp_values = pd.to_datetime(frame["transaction_ts"], errors="coerce", utc=True)
    invalid_timestamps = int(timestamp_values.isna().sum())
    frame["transaction_ts"] = timestamp_values
    numeric_amounts = pd.to_numeric(frame["amount"], errors="coerce")
    invalid_amounts = int((numeric_amounts.isna() | (numeric_amounts < 0)).sum())
    duplicate_ids = int(frame["transaction_id"].duplicated(keep=False).sum())
    missing_values = int(frame.isna().sum().sum())
    invalid_foreign_keys = int(frame["customer_id"].isna().sum() + frame["agent_id"].isna().sum())
    summary = DataQualitySummary(
        record_count=len(frame),
        missing_values=missing_values,
        duplicate_transaction_ids=duplicate_ids,
        invalid_amounts=invalid_amounts,
        invalid_timestamps=invalid_timestamps,
        invalid_foreign_keys=invalid_foreign_keys,
    )
    if invalid_amounts or invalid_timestamps or duplicate_ids:
        raise ValueError(
            "Transaction CSV failed validation: "
            f"duplicate IDs={duplicate_ids}, invalid amounts={invalid_amounts}, "
            f"invalid timestamps={invalid_timestamps}"
        )
    return frame, summary
