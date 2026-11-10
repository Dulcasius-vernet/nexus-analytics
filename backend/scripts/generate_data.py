from pathlib import Path
import numpy as np
import pandas as pd

SEED = 20261108
N = 30000
OUT = Path(__file__).resolve().parents[2] / "data" / "transactions.csv"


def main():
    rng = np.random.default_rng(SEED)
    customer_ids = rng.integers(10001, 15001, size=N)
    agent_ids = rng.integers(5001, 5201, size=N)
    amount = np.round(np.clip(rng.lognormal(mean=3.5, sigma=1.0, size=N), 1, 12000), 2)
    hour = rng.integers(0, 24, size=N)
    failed = rng.poisson(0.18, size=N)
    device_age = rng.integers(1, 1500, size=N)
    tenure = rng.integers(1, 2500, size=N)
    tx_type = rng.choice(["cash_in", "cash_out", "transfer", "bill_payment", "merchant_payment"], N,
                         p=[.18, .28, .30, .09, .15])
    channel = rng.choice(["USSD", "APP", "AGENT"], N, p=[.48, .27, .25])

    # Synthetic risk mechanism: deliberately transparent and not intended to
    # represent the actual fraud prevalence or behaviour of any provider.
    logit = (-5.2 + 0.25 * np.log1p(amount) + 1.0 * (hour <= 4)
             + 1.3 * (failed >= 2) + 1.0 * (device_age <= 14)
             + 0.8 * (tenure <= 30) + 0.35 * (channel == "APP"))
    probability = 1 / (1 + np.exp(-logit))
    fraud = rng.binomial(1, probability).astype(bool)
    reasons = np.where(fraud, rng.choice(["velocity", "unusual_hour", "new_device", "high_value"], N), "none")
    start = np.datetime64("2026-01-01T00:00:00")
    seconds = rng.integers(0, 280 * 24 * 3600, size=N)
    timestamps = start + seconds.astype("timedelta64[s]")

    df = pd.DataFrame({
        "transaction_id": np.arange(9000001, 9000001 + N),
        "business_id": 1,
        "customer_id": pd.array(customer_ids, dtype="Int64"),
        "agent_id": agent_ids,
        "transaction_ts": pd.to_datetime(timestamps, utc=True),
        "transaction_type": tx_type,
        "amount": amount,
        "channel": channel,
        "device_age_days": device_age,
        "failed_attempts_24h": failed,
        "customer_tenure_days": tenure,
        "hour_of_day": hour,
        "is_fraud": fraud,
        "risk_reason": reasons,
    })

    # Introduce a small number of realistic data imperfections for SQL QA demos.
    missing_idx = rng.choice(df.index, size=45, replace=False)
    df.loc[missing_idx, "customer_id"] = np.nan
    inconsistent_idx = rng.choice(df.index.difference(missing_idx), size=20, replace=False)
    df.loc[inconsistent_idx, "channel"] = "ussd "
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"Wrote {len(df):,} synthetic rows to {OUT}")
    print(f"Synthetic fraud prevalence: {df['is_fraud'].mean():.3%}")


if __name__ == "__main__":
    main()
