# Nexus Analytics — Architecture and Engineering Note

## 1. Overview

Nexus Analytics is a modular monolith for business analytics. The initial demonstration analyses synthetic mobile-money transaction-risk data. The application separates user/business/workspace management, relational data storage, analytical queries, model inference, AI augmentation and reporting.

## 2. Logical architecture

```text
Business user
   |
   v
Next.js / React frontend
   |  same-origin API proxy; HTTP-only session cookie
   v
FastAPI application
   |-- Authentication and workspace services
   |-- Data ingestion and validation
   |-- SQL analytics API
   |-- Model metrics and inference API
   |-- Snwolley orchestration and report API
   |
   +------ PostgreSQL 16
   |          users, businesses, memberships, workspaces,
   |          objectives, datasets, customers, agents, transactions
   |
   +------ Scikit-learn pipeline (Joblib artifact)
   |
   +------ Snwolley Agent API (server-to-server HTTPS)
   |
   +------ ReportLab PDF renderer
```

## 3. Business and tenant model

A user can be a member of one or more businesses through `business_memberships`. Registration currently creates one business and assigns the user the `owner` role. A business can own multiple workspaces; each workspace can contain analytical objectives and datasets. Transactions, customers and agents are associated with a business.

The `customers`, `agents` and `transactions` tables use composite primary keys beginning with `business_id`. This permits source identifiers to be reused by different businesses without cross-tenant collisions. Composite foreign keys ensure a transaction can only reference a customer and agent belonging to the same business.

API endpoints resolve the business ID from the authenticated session and reject a caller-supplied business ID that does not match the user's business membership. The current role model is intentionally small; fine-grained RBAC and invitations are future work.

## 4. Authentication and security

Passwords are hashed with PBKDF2-HMAC-SHA256 using a random 16-byte salt and 310,000 iterations. Sessions are signed using HMAC-SHA256, expire after 12 hours and are stored in HTTP-only, SameSite=Lax cookies. Cookies are marked Secure when `APP_ENV=production`. The session signing secret and Snwolley API key are configured through environment variables.

Database access uses psycopg context managers, bound SQL parameters, explicit business scoping and backend-side validation. AI requests receive aggregate summaries and model evaluation metrics, not individual customer rows. Provider errors are normalised; rate-limit responses preserve `Retry-After`.

This prototype does not yet provide password reset, email verification, login throttling, full CSRF controls for every deployment topology, granular RBAC, managed secret rotation or production audit logging. It must not be exposed publicly without additional security work.

## 5. Data engineering and SQL

The bundled data generator uses a fixed random seed to produce 30,000 synthetic transaction records. It includes missing customer identifiers and inconsistent channel formatting to demonstrate data-quality checks. The loader creates or finds a dedicated demo business and only replaces that business's synthetic transaction rows; it does not truncate other tenants.

CSV ingestion validates required fields, timestamp and amount validity, duplicate transaction IDs and row counts before bulk COPY into PostgreSQL. SQL examples and API queries demonstrate joins, filters, aggregations, conditional aggregation, CTEs and window functions. Indexes support business/time, business/customer and business/fraud filtering.

## 6. Machine learning

The reproducible Scikit-learn pipeline imputes numeric and categorical missing values, scales numeric fields, one-hot encodes categorical fields and trains a class-weighted Random Forest. A DummyClassifier provides a baseline. Evaluation uses a stratified holdout split, ROC AUC, average precision, a classification report and a threshold selected to maximise holdout F1. The saved model is loaded by the prediction API and accepts one or more transaction feature records.

The current holdout ROC AUC is approximately 0.627 and average precision approximately 0.032. At the selected threshold (approximately 0.127), precision is approximately 4.1% and recall approximately 26.5%. The model has limited discrimination and low precision. Its scores are not calibrated probabilities; predictions are only review signals and are not operational decisions.

Production evolution should include time-based validation, leakage review, calibration, cost-sensitive threshold selection, segment-level performance, model versioning, drift and performance monitoring, approval gates and rollback.

## 7. Snwolley and reporting

The Snwolley service receives a bounded prompt containing the user's question, business aggregates, transaction-type/channel summaries and selected model metrics. The prompt instructs the agent to distinguish observed facts from hypotheses, avoid causal claims, identify missing evidence and state synthetic-data limitations. The application presents the returned narrative as advisory analysis.

The PDF reporting endpoint combines observed metrics with the AI narrative. The integration uses `stream=false`, server-side credentials and a 30-second timeout. The provider's five-requests-per-minute limit is surfaced to the client through HTTP 429 and `Retry-After`; distributed queuing and automatic retry are not yet implemented.

## 8. Scaling and operations

For larger workloads, ingestion can move to scheduled batch jobs or Kafka-backed streaming. Data validation and feature engineering can become background jobs. A model registry and asynchronous training workers can manage model versions. Elasticsearch can support operational search and log analysis; Prometheus/Grafana can monitor API latency, database health, ingestion lag, model drift and provider errors. These are proposed extension points, not components currently deployed.

## 9. Known limitations

- One transaction-risk ML use case is implemented; other objective types are captured but need separate pipelines.
- Synthetic labels and features are not representative of a real operator.
- The model's low precision limits business utility.
- Live PostgreSQL and Snwolley connectivity must be verified in the target environment with a running database and fresh API credential.
- Production account recovery, advanced RBAC, queueing, monitoring and deployment hardening remain incomplete.
