# Nexus Analytics — Implementation and Verification Status

**Build:** 0.2.0  
**Verification date:** 10 November 2026  
**Status:** Expanded prototype implemented; live infrastructure acceptance checks still required.

## 1. Implemented in this build

| Area | Implementation | Verification status |
|---|---|---|
| Business onboarding | Registration, login, business, membership, default workspace and initial objective | API registration tested with database adapter stub; live database write not verified |
| Authentication | PBKDF2 password hashing, signed 12-hour session, HTTP-only cookie | Unit tests passed |
| Tenant isolation | Business resolved from session; foreign business IDs rejected; composite source keys | Access-control API test passed; SQL migration not run against live PostgreSQL |
| Workspace management | List and create workspaces | Implemented; live database test pending |
| Dataset management | CSV upload and tenant-scoped bundled synthetic-data loader | Code implemented; live COPY ingestion pending |
| SQL analytics | Overview, paginated transactions, weekly trends, type/channel/region aggregates, data quality | Routes and SQL implemented; live PostgreSQL execution pending |
| Machine learning | Saved Random Forest pipeline, threshold selection, baseline comparison and inference API | Training completed; inference API test passed |
| Visualisation | Weekly line chart, transaction-type bar chart and channel donut chart | TypeScript syntax/transpile check passed; full Next.js production build not run |
| Snwolley | Server-side aggregate-context insight and management-report requests | Request construction and error paths mocked/tested; live provider call pending |
| PDF reporting | ReportLab PDF endpoint using database aggregates and AI narrative | PDF response tested with mocked database and AI provider |
| Documentation | README, architecture note, business insights report and this status report | Updated |

## 2. Model evaluation

The bundled 30,000-row synthetic dataset was used to retrain the Random Forest pipeline. The holdout metrics are:

| Metric | Result |
|---|---:|
| ROC AUC | 0.6268 |
| Baseline ROC AUC | 0.5000 |
| Average precision | 0.0320 |
| Baseline average precision | 0.0207 |
| Selected threshold | 0.1267 |
| Precision | 0.0408 |
| Recall | 0.2645 |
| F1 | 0.0707 |
| Predicted-positive rate | 13.40% |

The selected threshold maximises F1 on a stratified holdout split. This is not an operationally validated threshold. Precision remains low and the score is not calibrated. The model must be treated as a demonstration of a reproducible ML workflow, not as an effective fraud detector.

## 3. Automated test results

Command:

```bash
cd backend
python -m unittest discover -s tests -p "test_*.py" -v
```

Result from this environment:

- 20 tests discovered.
- 14 passed.
- 6 PostgreSQL integration tests skipped because no PostgreSQL server was available.
- Tests cover generated CSV validation, invalid request handling, database-failure handling, password hashing, session integrity, registration response/cookie behaviour with a database stub, business scoping, saved-model inference, prediction validation, Snwolley request construction, missing-key handling, 429 propagation, AI report response and PDF response with mocked external dependencies.

Python compilation completed successfully for backend application, scripts and tests. The saved model was trained successfully and its inference endpoint returned a prediction in the automated test.

The frontend TypeScript/JSX source passed a syntax/transpile check using the installed TypeScript compiler and temporary declarations for unavailable package type definitions. A complete `npm run build` was not performed because package installation/build dependencies could not be fetched in this isolated environment.

## 4. Live integration checks not completed

**PostgreSQL:** Docker Engine and a PostgreSQL server binary were not available in the verification environment. A connection attempt to localhost:5432 was refused. Consequently, the schema initialisation/migration, real foreign-key enforcement, data COPY ingestion and database-backed SQL queries have not been verified against a running PostgreSQL instance.

**Snwolley:** No current valid API key was configured, and the previously shared testing credential was excluded from the project package. Snwolley request construction, response handling and rate-limit handling were tested with mocked HTTP responses. A live provider request has not been made.

**Frontend production build:** The environment could not download npm packages or the platform-specific Next.js SWC build binary. The application source passed a TypeScript/JSX syntax check, but a production build must be run on the developer machine with dependencies installed.

## 5. Required final acceptance checks on the developer machine

1. Create `backend/.env` from `.env.example`; set a unique `SESSION_SECRET` and a fresh `SNWOLLEY_API_KEY`.
2. Run `docker compose up -d db` and verify `docker compose ps` reports PostgreSQL healthy.
3. Run `python -m scripts.init_db` and confirm the schema initialises.
4. Start FastAPI and check `/api/v1/health/database` after signing in.
5. Register a business account in the frontend, load the bundled demo dataset and verify 30,000 records appear.
6. Open SQL analytics and verify charts/aggregates load.
7. Run a model prediction and verify a risk score and review flag appear.
8. Generate an AI management report and download the PDF using the current Snwolley key.
9. Run the full unittest suite with PostgreSQL running; all five database-dependent tests should execute rather than skip.
10. Run `npm install` and `npm run build` in `frontend`.
11. Run `RUN_LIVE_INTEGRATION_CHECKS=1 python -m scripts.live_integration_check` from `backend` to perform one live database and Snwolley connectivity check.

## 6. Security and release notes

- The submission package must not contain `backend/.env`, credentials, `.venv`, `node_modules`, `.next`, `.git` or caches.
- The Snwolley key shown in the original assignment material was previously included in an archive; do not reuse it. Obtain a fresh key from the provider/assignment contact.
- The default database password and fallback session secret are for local development only.
- Do not use real personal or financial data or expose the prototype publicly before a complete security review.

## 7. Remaining product work

- Live PostgreSQL migration, data ingestion and SQL integration verification.
- Live Snwolley connectivity and report generation.
- Full Next.js production build and browser acceptance test.
- Separate model pipelines for non-fraud objectives.
- Stronger model discrimination, precision/recall trade-off analysis, calibration and time-based validation.
- Password reset, email verification, login throttling, advanced role administration and production audit logs.
- Drift monitoring, performance alerts, asynchronous training and scheduled retraining.
