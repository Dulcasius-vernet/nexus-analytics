CREATE TABLE IF NOT EXISTS users (
    user_id BIGSERIAL PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(254) NOT NULL,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));

CREATE TABLE IF NOT EXISTS businesses (
    business_id BIGSERIAL PRIMARY KEY,
    business_name VARCHAR(160) NOT NULL,
    industry VARCHAR(100) NOT NULL,
    country_code CHAR(2) NOT NULL DEFAULT 'GH',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS business_memberships (
    membership_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    business_id BIGINT NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    role VARCHAR(30) NOT NULL DEFAULT 'analyst' CHECK (role IN ('owner', 'admin', 'analyst', 'viewer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, business_id)
);

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_id BIGSERIAL PRIMARY KEY,
    business_id BIGINT NOT NULL REFERENCES businesses(business_id) ON DELETE CASCADE,
    workspace_name VARCHAR(160) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (business_id, workspace_name)
);

CREATE TABLE IF NOT EXISTS analytical_objectives (
    objective_id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    objective_name VARCHAR(160) NOT NULL,
    objective_type VARCHAR(80) NOT NULL,
    description TEXT,
    status VARCHAR(30) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id BIGSERIAL PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
    dataset_name VARCHAR(160) NOT NULL,
    source_type VARCHAR(40) NOT NULL,
    row_count BIGINT CHECK (row_count >= 0),
    schema_version VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGINT NOT NULL,
    business_id BIGINT NOT NULL REFERENCES businesses(business_id),
    customer_segment VARCHAR(40),
    account_age_days INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (business_id, customer_id)
);

CREATE TABLE IF NOT EXISTS agents (
    agent_id BIGINT NOT NULL,
    business_id BIGINT NOT NULL REFERENCES businesses(business_id),
    region VARCHAR(80),
    agent_tier VARCHAR(30),
    PRIMARY KEY (business_id, agent_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id BIGINT NOT NULL,
    business_id BIGINT NOT NULL REFERENCES businesses(business_id),
    customer_id BIGINT,
    agent_id BIGINT,
    transaction_ts TIMESTAMPTZ NOT NULL,
    transaction_type VARCHAR(30) NOT NULL,
    amount NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    channel VARCHAR(30),
    device_age_days INTEGER,
    failed_attempts_24h INTEGER CHECK (failed_attempts_24h >= 0),
    customer_tenure_days INTEGER CHECK (customer_tenure_days >= 0),
    hour_of_day SMALLINT CHECK (hour_of_day BETWEEN 0 AND 23),
    is_fraud BOOLEAN NOT NULL,
    risk_reason VARCHAR(80),
    PRIMARY KEY (business_id, transaction_id),
    FOREIGN KEY (business_id, customer_id) REFERENCES customers(business_id, customer_id),
    FOREIGN KEY (business_id, agent_id) REFERENCES agents(business_id, agent_id)
);

-- Upgrade installations created by the earlier single-column identifier schema.
-- Composite keys allow different businesses to reuse their own source-system IDs.
DO $$
BEGIN
    -- Foreign keys use the customer and agent primary-key indexes, so remove
    -- them briefly while upgrading older single-column keys.
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_customer_id_fkey;
    ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_agent_id_fkey;
    IF EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = 'customers'::regclass AND c.contype = 'p'
          AND array_length(c.conkey, 1) = 1
    ) THEN
        ALTER TABLE customers DROP CONSTRAINT customers_pkey;
        ALTER TABLE customers ADD CONSTRAINT customers_pkey PRIMARY KEY (business_id, customer_id);
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = 'agents'::regclass AND c.contype = 'p'
          AND array_length(c.conkey, 1) = 1
    ) THEN
        ALTER TABLE agents DROP CONSTRAINT agents_pkey;
        ALTER TABLE agents ADD CONSTRAINT agents_pkey PRIMARY KEY (business_id, agent_id);
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = 'transactions'::regclass AND c.contype = 'p'
          AND array_length(c.conkey, 1) = 1
    ) THEN
        ALTER TABLE transactions DROP CONSTRAINT transactions_pkey;
        ALTER TABLE transactions ADD CONSTRAINT transactions_pkey PRIMARY KEY (business_id, transaction_id);
    END IF;
    ALTER TABLE transactions
        ADD CONSTRAINT transactions_customer_id_fkey
        FOREIGN KEY (business_id, customer_id) REFERENCES customers(business_id, customer_id);
    ALTER TABLE transactions
        ADD CONSTRAINT transactions_agent_id_fkey
        FOREIGN KEY (business_id, agent_id) REFERENCES agents(business_id, agent_id);
END $$;

CREATE INDEX IF NOT EXISTS idx_workspaces_business ON workspaces(business_id);
CREATE INDEX IF NOT EXISTS idx_objectives_workspace ON analytical_objectives(workspace_id);
CREATE INDEX IF NOT EXISTS idx_datasets_workspace ON datasets(workspace_id);
CREATE INDEX IF NOT EXISTS idx_transactions_business_time ON transactions(business_id, transaction_ts);
CREATE INDEX IF NOT EXISTS idx_transactions_customer ON transactions(business_id, customer_id);
CREATE INDEX IF NOT EXISTS idx_transactions_fraud ON transactions(business_id, is_fraud);
