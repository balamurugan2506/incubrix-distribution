# Evidence and Command Execution Log

This log contains a dated record of commands executed during development and verification, their exact results, any failures encountered, and how they were resolved.

---

## Session Date: 2026-10-23

### 1. Initial State Assessment & Pre-flight Checks

- **Command**: `git status`
  - **Result**: Checked status on master branch. Verified working tree had modified `REQUIREMENTS_CHECKLIST.md`, `SOURCES.md`, `docker-compose.yml`, `mock_platforms/server.py`, `outputs/submission_summary.json` and untracked `Problem Statements/`.
- **Command**: `git log -n 5 --oneline`
  - **Result**: Confirmed baseline commit `06959c3` ("feat: complete production implementation of IncuBrix distribution network").
- **Command**: `pytest`
  - **Result**: Failed initially because system Python (Python 3.14) on Windows PATH lacked `aiosqlite`.
  - **Fix**: Located existing local virtual environment at `.venv/` containing Python 3.12 and all dependencies.
- **Command**: `.venv\Scripts\python -m pytest`
  - **Result**: Passed 28 tests in 5.80s.
  - **Status**: Clean baseline confirmed. 28 tests passing.
- **Command**: `pip install pypdf` (in `.venv`)
  - **Result**: Successfully installed `pypdf-6.21.2` to inspect the assessment brief PDF.
- **Command**: `.venv\Scripts\python` PDF extraction script
  - **Result**: Extracted 9 pages of `Problem Statements/IncuBrix_Assessment_4_Distribution_Long_Tail_Destination_Network_Brief.pdf` to `Problem Statements/extracted_brief.txt`.
- **Command**: `.venv\Scripts\python` Excel inspection script
  - **Result**: Read all 8 sheets in `Problem Statements/Assessment4_BalaMurugan.xlsx` to audit baseline claims and formulas.
- **Action**: Created `docs/GAP_ANALYSIS.md` detailing every Must-have (1-9), Level item (Core, Advanced, Outstanding), and Integration Standard point (1-10) with exact gap mapping and execution plan.

### 2. Gap A: Local Instances Stack, Dynamic Credentials, and DB Volume Isolation

- **Action**: Configured `docker-compose.yml` with full multi-container stack:
  - `incubrix-api`: FastAPI backend with named volume `db-data:/app/data` (preventing clean-machine directory mount collisions).
  - `incubrix-mock`: Local mock server on port 8001 with health check.
  - `minio`: Chainguard MinIO S3-compatible evidence storage on ports 9000-9001.
  - `lemmy-postgres`: Dedicated PostgreSQL 15 alpine container.
  - `lemmy-pictrs`: Official Lemmy image hosting service.
  - `lemmy`: Official Lemmy 0.19.5 fediverse backend on port 8536.
  - `lemmy-ui`: Official Lemmy UI 0.19.5 on port 1234.
  - `ghost-mysql`: Dedicated MySQL 8.0 container.
  - `ghost`: Official Ghost 5 alpine blog platform on port 2368.
  - `incubrix-seed`: Automated seeder container executing `scripts/seed_local_instances.py`.
- **Action**: Created `lemmy/lemmy.hjson` with local test configuration and credentials.
- **Action**: Created `scripts/seed_local_instances.py` to auto-provision Lemmy admin & community and Ghost owner & API key, writing credentials to `outputs/shared_credentials.json` with fallback for offline environments.
- **Action**: Updated `app/config.py` with dynamic file-watching helper `get_shared_credentials()`, `get_lemmy_token()`, and `get_ghost_api_key()` to hot-reload credentials without restart.
- **Action**: Updated `app/connectors/lemmy.py` and `app/connectors/ghost.py` to use dynamic settings getters.
- **Command**: `.venv\Scripts\python -m pytest tests/unit/test_config.py`
  - **Result**: Passed 2 tests, verifying that credentials modified on disk after service start are picked up immediately.
- **Command**: `.venv\Scripts\python -m pytest`
  - **Result**: 29 passed in 2.79s.

### 3. Gap F & Gap J: Standardized Error Envelopes, Exact OpenAPI 3.1 Verification, and Asynchronous Jobs

- **Action**: Standardized all application error responses to the canonical Integration Standard 5 format `{"error": {"code", "message", "retryable", "details"}}`.
  - Added `UNAUTHORIZED` and `RATE_LIMITED` to `ErrorCode` taxonomy in `app/rules/errors.py`.
  - Enhanced `ConnectorException.to_dict()` to produce `{ "error": { ... }, "code": ..., "message": ..., "retryable": ..., "details": ... }` providing nested envelope structure while maintaining top-level backward compatibility.
  - Added global `RequestValidationError` and `StarletteHTTPException` handlers in `app/main.py`.
  - Standardized `IdempotencyMiddleware` error responses (missing key, conflict, in-flight rate limit).
- **Action**: Removed all exemptions from `IdempotencyMiddleware` so that CSV import and every route under `/api/v1/` strictly require and enforce `Idempotency-Key`.
- **Action**: Enhanced `app/jobs/manager.py` with:
  - Removal of `destination_model.last_certified_at` modification on normal publications (Gap E).
  - Background certification job runner: `run_certification_job()`.
  - Background CSV catalogue import job runner: `run_csv_import_job()`.
- **Action**: Added endpoints `POST /api/v1/certification/jobs` and `POST /api/v1/destinations/import-csv-job` returning HTTP 202 Accepted and `job_id` for asynchronous execution.
- **Action**: Updated `scripts/export_openapi.py` and exported updated specification to `openapi.yaml`.
- **Action**: Created `tests/unit/test_error_envelope.py` verifying that all error paths return the standard envelope.
- **Action**: Created `tests/integration/test_openapi.py` verifying that `openapi.yaml` exactly matches the running application schema and that all routes conform to the `/api/v1/` prefix rules.
- **Command**: `.venv\Scripts\python -m pytest`
  - **Result**: 35 passed in 2.59s (all 35 tests green).
