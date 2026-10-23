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

### 4. Gap C: Safe Retries After Platform Timeout & Zero Duplicate Guarantee (Must-Have 6 & Hard Case 1)

- **Action**: Implemented the `reconcile` contract across all connectors (`DevtoConnector`, `DiscourseConnector`, `LemmyConnector`, `GhostConnector`, `SignedWebhookConnector`).
  - Connector queries platform by title, post query, or idempotency key.
  - If post is found, returns existing `PublishResult` without duplicating.
- **Action**: Enhanced `app/storage/idempotency_store.py` with `outcome_unknown` state and `record_outcome_unknown()` method.
- **Action**: Updated `app/api/middleware.py`:
  - Enforced idempotency check across both `/api/v1/` POST routes and `/connector/v1/.../publish`.
  - When status is 408/504 or timeout occurs, record status `outcome_unknown`.
  - On retry with identical key in `outcome_unknown` state, sets `request.state.is_retry_after_unknown = True`.
- **Action**: Updated `app/api/connector_routes.py` and `app/jobs/manager.py`:
  - Inspect `is_retry_after_unknown` and invoke `connector.reconcile(...)` before executing publish.
  - Configured `execute_with_retry` with `is_idempotent_operation=False` and `reconcile_func` to prevent blind retries during backoff.
- **Action**: Enhanced `mock_platforms/server.py` to support `x-simulate: timeout-after-create` and added search/reconciliation endpoints for all platforms.
- **Action**: Created `tests/integration/test_safe_retries_after_timeout.py` testing late timeout responses across Dev.to, Discourse, and Signed Webhook, proving the retry returns the SAME post and platform holds exactly 1 post (0 duplicates). Also verified strict enforcement of `Idempotency-Key` on CSV import with 0 exemptions.
- **Command**: `.venv\Scripts\python -m pytest tests/integration/test_safe_retries_after_timeout.py -v`
  - **Result**: 4 passed in 0.90s.
- **Command**: `.venv\Scripts\python -m pytest`
  - **Result**: 39 passed in 2.74s (all 39 tests green).

### 5. Gap E: Posting Rules Engine Enhancements (Must-Have 4)

- **Action**: Enhanced `PostingRulesEngine` in `app/rules/engine.py`:
  - **Configurable Frequency Cap Period**: Added `frequency_period_hours` (not only 24h) to `DestinationModel` and `DestinationSchema`. Second post inside the cap is blocked with HTTP 429 and clear reason explaining window and cap.
  - **Comprehensive Link Extraction**: Implemented detection of links across every written form: HTTP, HTTPS, www-prefixed addresses, Markdown `[text](url)`, HTML `<a href="...">`, and bare domains (`incubrix.ai`, `techcrunch.com`).
  - **Multi-Marker Self-Promotion Detection**: Replaced tiny keyword list with categorized multi-marker heuristic (CTAs, Conversion/Sign-up, Promotional Terms, Standalone Commercial Keywords). Blocks only on strong commercial keywords or when at least 2 distinct marker categories are present, preventing false blocks.
  - **Fail-Closed Missing Rules Check**: If any of the 5 required posting rules (`frequency_cap`, `self_promo_allowed`, `link_policy`, `disclosure_required`, `automation_allowed`) is missing or NULL, publication is refused with HTTP 422 `DEST_SPEC_VIOLATION`.
  - **All-Path Enforcement**: Enforced rule validation on both background jobs (`app/jobs/manager.py`) and direct connector contract route (`POST /connector/v1/{connector_key}/publish`).
  - **Verification**: Created `tests/unit/test_posting_rules_enhanced.py` covering link forms, multi-marker promo, fail-closed refusal on missing rules, link policies (`none`, `restricted`, `max:1`), and frequency cap blocking.
- **Command**: `.venv\Scripts\python -m pytest tests/unit/test_posting_rules_enhanced.py -v`
  - **Result**: 5 passed in 0.54s.
- **Command**: `.venv\Scripts\python -m pytest`
  - **Result**: 44 passed in 2.88s (all 44 tests green).

### 6. Gap B, D, G, H, I, K, L, M: Core Certification, Secret Scan, Zero-Code Expansion, and 1,000-Row Benchmark

- **Action**: Enhanced `CertificationHarness` (`app/certification/harness.py`):
  - Added robust cleanup loop with 10-minute timeout and verification that status read confirms post deletion.
  - Implemented schema drift detection: if platform renames response fields, verdict is `failed` and destination is demoted (`status = 'demoted'`).
  - Added handling for 429 rate limit with capped sleep on Retry-After (`inconclusive`).
  - Added evidence emission writing structured JSON and human-readable text logs to `outputs/evidence/`.
- **Action**: Created `scripts/secret_scan.py` to scan repository files and captured logs for unmasked tokens or API keys. Added `tests/integration/test_secret_leak_prevention.py`.
- **Action**: Proved Zero-Code Community Expansion (Must-Have 3) with `tests/integration/test_must_have_3_zero_code_addition.py`: adding a 2nd Discourse instance via API row and a 2nd Lemmy community via CSV row with 0 code changes.
- **Action**: Created 1,000-row CSV benchmark test (`tests/integration/test_csv_benchmark_1000.py`) generating 1,000 realistic rows:
  - Benchmark result: 1.37 seconds (727.4 rows/sec), well within the 5-minute requirement.
  - Result saved to `outputs/test_runs/csv_1000_benchmark.json`.
- **Command**: `.venv\Scripts\python -m pytest tests/integration/test_csv_benchmark_1000.py`
  - **Result**: 1 passed in 1.48s.

### 7. Advanced Level Features (Items 1 - 5)

- **Advanced 1 (Catalogue Import Engine)**:
  - Full URL normalization, de-duplication, SSRF guard blocking private/link-local addresses (RFC 1918, RFC 3927) unless explicitly allowed for testing, robots.txt check, and row-by-row status reporting.
- **Advanced 2 (Rules Capture with Verbatim Quote Verification)**:
  - Implemented `CommunityRulesAdapter` in `app/rules/capture.py`.
  - Offline keyword adapter scans community HTML and extracts 5 proposed rules.
  - Verifies that every proposed rule's quote is a literal, verbatim substring of the page text before returning it with status `pending`.
  - Added confirm endpoint: loosening an existing rule strictly requires `confirm_loosening: True`.
- **Advanced 3 (Audience Relevance Scoring 1 to 5)**:
  - Implemented in `app/rules/relevance.py`: scores destinations 1.0 to 5.0 against IncuBrix's audience (AI, video, marketing, SaaS, creators, founders).
  - Strict rule enforced: if a destination has no audience keyword match, score is hard-capped at <= 2.0.
- **Advanced 4 (Manifest-Driven Tailoring Engine)**:
  - Implemented in `app/catalogue/tailoring.py`: reads platform manifest configuration (discussion-first closing question for forums, canonical URL for articles, word-boundary truncation preserving whole words, hashtag formatting, and AI disclosure preserving complete text).
- **Advanced 5 (Three Additional Production Connectors)**:
  - Implemented `HashnodeConnector`, `SlackConnector`, and `MailchimpConnector` (strict draft-only mode: campaigns created with status `save_draft`, `send()` strictly prohibited).
  - All 3 connectors feature full manifests, mock endpoints, and certification tests.
- **Command**: `.venv\Scripts\python -m pytest tests/integration/test_advanced_features.py -v`
  - **Result**: 6 passed in 0.95s.
- **Command**: `.venv\Scripts\python -m pytest`
  - **Result**: 57 passed in 4.90s.

### 8. Outstanding Level Features (Items 1 - 4)

- **Outstanding 1 (Content-to-Destination Recommender & Evaluation)**:
  - Implemented in `app/catalogue/recommender.py`: ranks destinations by audience fit, filtering out demoted or rule-blocking destinations.
  - Created labelled evaluation test set in `tests/evaluation/test_recommender_eval.py`.
  - Evaluated against random and simple baselines: IncuBrix Recommender achieved Precision@10 of 0.94 (vs 0.32 random baseline and 0.65 simple keyword baseline).
  - Saved evaluation report to `outputs/test_runs/recommender_precision_eval.json`.
- **Outstanding 2 (Metrics Normalization Engine)**:
  - Implemented `fetch_metrics` across Dev.to, Lemmy, Ghost, and Hashnode in `app/catalogue/metrics.py`.
  - Normalizes platform metrics into standard schema: views, likes, comments, shares, clicks, with source attribution.
  - Verified with `tests/integration/test_metrics_normalisation.py`.
- **Outstanding 3 (30-Day Recertification Scheduler with Fake Clock)**:
  - Implemented `RecertificationScheduler` in `app/certification/scheduler.py`.
  - Recertifies destinations approaching 30 days. Failing destinations are demoted (`status = 'demoted'`) and raise alerts in the `alerts` database table.
  - Verified with `tests/integration/test_recertification_fake_clock.py` using simulated time advance.
- **Outstanding 4 (150 Real Verified Destinations Catalogue)**:
  - Curated `catalogue/real_destinations_150.csv` containing 150 real, verified developer, creator, AI, and SaaS communities.
  - Every entry contains real name, clean normalized URL, platform type, relevance score, verbatim rules quote, and `catalogue_only = True` flag preventing live posting.
  - Verified with `tests/integration/test_real_catalogue_150.py`.
- **Command**: `.venv\Scripts\python -m pytest`
  - **Result**: 67 passed in 6.39s.

### 9. Demo Deployment, Rate Limiting, and Candidate Support

- **Action**: Created `Dockerfile.demo` implementing a single-container deployment running both the IncuBrix API and mock platform server in simulation mode under a non-root `incubrix` user.
- **Action**: Created `render.yaml` infrastructure blueprint for Render cloud deployment.
- **Action**: Created `app/api/demo.py` with failure switch routes (`/api/v1/demo/failure-switch`) for live resilience testing (timeout, rate_limit, auth_error, reset).
- **Action**: Added `DemoAuthAndRateLimitMiddleware` in `app/api/middleware.py` enforcing `DEMO_API_TOKEN` and 120 req/min sliding-window rate limit with HTTP 429 `RATE_LIMITED` and `Retry-After: 10`.
- **Action**: Created `scripts/run_demo.py` orchestrator script.
- **Action**: Created `scripts/check_live_demo.py` performing 6 live verification checks.
- **Action**: Created `docs/DEPLOY.md` and `docs/EXPLAINED.md` (with one analogy per concept and 15 quiz questions).
- **Action**: Added `tests/unit/test_demo_mode.py` covering failure switch toggling and demo authentication.
- **Command**: `.venv\Scripts\python -m pytest`
  - **Result**: 69 passed in 6.54s.

### 10. Final System Verification

- **Command**: `.venv\Scripts\python -m pytest tests/integration/test_openapi.py`
  - **Result**: 2 passed. Verified `openapi.yaml` strictly matches running FastAPI application.
- **Command**: `.venv\Scripts\python scripts/secret_scan.py`
  - **Result**: Scanned 330 files across repository and logs. 0 leaks found. CLEAN.
- **Command**: `.venv\Scripts\python -m pytest`
  - **Result**: 69 passed, 1 warning (deprecation notice from starlette testclient) in 6.54s. All tests green.



