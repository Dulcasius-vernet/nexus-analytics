-- These parameterised examples use :business_id as the application-supplied
-- parameter. Each result is an auditable business metric, not a model claim.

-- 1. Transaction types ranked by value: where transaction value is concentrated.
SELECT transaction_type, COUNT(*) AS transaction_count,
       SUM(amount) AS total_value_ghs, AVG(amount) AS average_value_ghs
FROM transactions
WHERE business_id = :business_id
GROUP BY transaction_type
ORDER BY total_value_ghs DESC;

-- 2. Channel distribution: how customers use the available channels.
SELECT COALESCE(channel, 'Unknown') AS channel, COUNT(*) AS transaction_count,
       SUM(amount) AS transaction_value_ghs
FROM transactions
WHERE business_id = :business_id
GROUP BY channel
ORDER BY transaction_count DESC;

-- 3. Hourly activity and fraud: operational volume and labelled outcomes by hour.
SELECT hour_of_day, COUNT(*) AS transaction_count,
       COUNT(*) FILTER (WHERE is_fraud) AS fraud_count,
       AVG(amount) AS average_amount_ghs
FROM transactions
WHERE business_id = :business_id
GROUP BY hour_of_day
ORDER BY hour_of_day;

-- 4. Regional volume: joins fact records to agent attribution.
SELECT COALESCE(a.region, 'Unattributed') AS region, COUNT(*) AS transaction_count,
       SUM(t.amount) AS transaction_value_ghs
FROM transactions t
LEFT JOIN agents a ON a.agent_id = t.agent_id AND a.business_id = t.business_id
WHERE t.business_id = :business_id
GROUP BY a.region
ORDER BY transaction_count DESC;

-- 5. Weekly labelled-fraud trend using a CTE.
WITH weekly AS (
    SELECT DATE_TRUNC('week', transaction_ts) AS week_start,
           COUNT(*) AS transaction_count,
           COUNT(*) FILTER (WHERE is_fraud) AS fraud_count,
           SUM(amount) AS transaction_value,
           SUM(amount) FILTER (WHERE is_fraud) AS labelled_fraud_value
    FROM transactions
    WHERE business_id = :business_id
    GROUP BY 1
)
SELECT week_start, transaction_count, fraud_count, transaction_value,
       ROUND(100.0 * fraud_count / NULLIF(transaction_count, 0), 3) AS fraud_rate_pct,
       ROUND(100.0 * labelled_fraud_value / NULLIF(transaction_value, 0), 3) AS labelled_fraud_value_pct
FROM weekly
ORDER BY week_start;

-- 6. Proportion of value associated with labelled fraud: conditional aggregation.
SELECT SUM(amount) AS total_value_ghs,
       SUM(amount) FILTER (WHERE is_fraud) AS labelled_fraud_value_ghs,
       ROUND(100.0 * SUM(amount) FILTER (WHERE is_fraud) / NULLIF(SUM(amount), 0), 3)
           AS labelled_fraud_value_pct
FROM transactions
WHERE business_id = :business_id;

-- 7. Unusually active customers: CTE and window comparison to the customer mean.
WITH customer_activity AS (
    SELECT customer_id, COUNT(*) AS transaction_count,
           AVG(COUNT(*)) OVER () AS average_customer_transactions
    FROM transactions
    WHERE business_id = :business_id AND customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT customer_id, transaction_count, average_customer_transactions
FROM customer_activity
WHERE transaction_count > average_customer_transactions * 2
ORDER BY transaction_count DESC;

-- 8. Failed attempts and labelled fraud: grouped risk indicator comparison.
SELECT failed_attempts_24h, COUNT(*) AS transaction_count,
       COUNT(*) FILTER (WHERE is_fraud) AS fraud_count,
       ROUND(100.0 * COUNT(*) FILTER (WHERE is_fraud) / NULLIF(COUNT(*), 0), 3) AS fraud_rate_pct
FROM transactions
WHERE business_id = :business_id
GROUP BY failed_attempts_24h
ORDER BY failed_attempts_24h;

-- 9. Data-quality checks: missingness, invalid values and foreign-key drift.
SELECT COUNT(*) AS total_records,
       COUNT(*) FILTER (WHERE t.customer_id IS NULL) AS missing_customer_id,
       COUNT(*) FILTER (WHERE t.agent_id IS NULL) AS missing_agent_id,
       COUNT(*) FILTER (WHERE t.amount < 0) AS invalid_amount,
       COUNT(*) FILTER (WHERE t.transaction_ts IS NULL) AS invalid_timestamp,
       COUNT(*) FILTER (WHERE t.hour_of_day NOT BETWEEN 0 AND 23) AS invalid_hour,
       COUNT(*) FILTER (WHERE c.customer_id IS NULL AND t.customer_id IS NOT NULL)
           AS inconsistent_customer_reference,
       COUNT(*) FILTER (WHERE a.agent_id IS NULL AND t.agent_id IS NOT NULL)
           AS inconsistent_agent_reference
FROM transactions t
LEFT JOIN customers c ON c.customer_id = t.customer_id AND c.business_id = t.business_id
LEFT JOIN agents a ON a.agent_id = t.agent_id AND a.business_id = t.business_id
WHERE t.business_id = :business_id;
