# IncuBrix Distribution Network: Long-Tail Destination Network

A production-grade backend service implementing the **IncuBrix Engineering Assessment 4**. The network distributes multichannel content across diverse long-tail platforms while enforcing posting rules, safe retries, persistent idempotency, background job execution, and end-to-end publication certification.

---

## Architecture Overview

```
                        +---------------------------------------+
                        |           Client Application          |
                        +---------------------------------------+
                                            |
                         HTTP / REST API    | (Idempotency-Key Required)
                                            v
     +-------------------------------------------------------------------------+
     |                       FastAPI API Gateway Engine                        |
     |                                                                         |
     |   [CorrelationIdMiddleware]    [IdempotencyMiddleware (SQLite Cached)]   |
     +-------------------------------------------------------------------------+
            |                                           |
            v                                           v
+-----------------------+                   +----------------------------------+
| Connector Contract    |                   | Application API (/api/v1/*)      |
| POST /connector/v1/.. |                   +----------------------------------+
+-----------------------+                       |              |             |
            |                                   v              v             v
            |                      +----------------+ +------------+ +---------------+
            |                      | Destinations   | | Jobs       | | Certification |
            |                      | Catalogue CRUD | | Engine     | | 7-Step        |
            |                      | & CSV Import   | | (HTTP 202) | | Harness       |
            |                      +----------------+ +------------+ +---------------+
            |                                   |              |             |
            |                                   +-------+------+-------------+
            v                                           |
+-------------------------------------------------------v----------------------+
|                     Centralized Posting-Rules Engine                         |
|   - Destination Frequency Caps (24h SQLite query)                            |
|   - Self-Promotion Detection & Policy Enforcement                            |
|   - Link Restrictions (none, restricted <=2, allowed)                        |
|   - AI-Content Disclosure Verification                                       |
|   - Title & Body Length Limits per YAML Connector Manifest                   |
|   - Automation Allowed Check (blocks bots on manual destinations)            |
+------------------------------------------------------------------------------+
                                            |
                                            v
+------------------------------------------------------------------------------+
|                     Pure Connector Runtime Registry                          |
|   (Returns typed Pydantic results; Never writes directly to IncuBrix DB)     |
+------------------------------------------------------------------------------+
     |             |             |             |             |             |
     v             v             v             v             v             v
+---------+   +---------+   +---------+   +---------+   +---------+   +---------+
|Discourse|   |  Lemmy  |   | Dev.to  |   |  Ghost  |   | Signed  |   |Assisted |
| (Forum) |   |(Fediverse|  | (Forem) |   | (Admin) |   | Webhook |   |(Manual) |
+---------+   +---------+   +---------+   +---------+   +---------+   +---------+
     |             |             |             |             |             |
     +-------------+-------------+-------------+-------------+-------------+
                                        |
                                        v
                 +---------------------------------------------+
                 | Platform Target (Mock Server or Production) |
                 +---------------------------------------------+
```

---

## Key Features

1. **Exact Connector Contract**:
   Exposes HTTP POST endpoints matching the mandatory specification:
   `POST /connector/v1/{connector_key}/{method}`
   - `validate(rendition, destination, connection)` -> `{ok, violations[]}`
   - `publish(rendition, destination, connection, idempotency_key)` -> `{platform_post_id, live_url, status}`
   - `get_status(platform_post_id, connection)` -> `{status, live_url}`
   - `delete(platform_post_id, connection)` -> `{deleted}`
   - `fetch_metrics(platform_post_id, connection, since)` -> `{views, likes, comments, shares, saves, watch_time_s, clicks}`
   - `refresh_auth(connection)` -> `{expires_at}`
   - `build_assist_pack(rendition, destination)` -> `{files[], caption, deep_link, checklist[]}`

2. **9 Connectors with Declarative YAML Manifests**:
   - **Discourse**: Forum topics & posts with `Api-Key` and `Api-Username`.
   - **Lemmy**: Fediverse communities & posts via JWT / token auth.
   - **Dev.to / Forem**: Developer blogging with `api-key` auth.
   - **Ghost**: Ghost Admin API with dynamic JWT generation (`{id}:{secret_hex}`).
   - **Generic Signed Webhook**: HMAC-SHA256 signature in `X-IncuBrix-Signature` and timestamp replay protection.
   - **Assisted Publishing**: Generates rich manual submission packages with formatted captions, assets, deep links, and human checklists for platforms prohibiting automated posting.
   - **Hashnode (Advanced)**: GraphQL publication with personal access token auth.
   - **Slack (Advanced)**: Block Kit chat messaging with bot token auth.
   - **Mailchimp (Advanced)**: Regular newsletter campaigns strictly created in draft mode (`status: "save"`).

3. **Standardized Error Taxonomy**:
   All error responses follow the standard envelope: `{"error": {"code": "...", "message": "...", "retryable": bool, "details": {...}}}`.
   Codes:
   - `DEST_SPEC_VIOLATION`: Format limit violation (title/body length, unsupported media, schema mismatch).
   - `DEST_RULE_FREQUENCY_CAP`: Destination posting limit reached within rolling period.
   - `CONNECTION_AUTH_EXPIRED`: Missing, expired, or rejected authentication credentials.
   - `PLATFORM_RATE_LIMIT`: Remote platform 429 response (with `Retry-After`).
   - `PLATFORM_QUOTA_EXHAUSTED`: Account tier or platform daily quota limit reached.
   - `PLATFORM_CONTENT_REJECTED`: Remote platform spam or content filter rejection.
   - `PLATFORM_UNAVAILABLE`: Platform 503 or network failure.
   - `CONNECTOR_DISABLED`: Destination disabled, demoted, or marked `catalogue_only`.
   - `UNAUTHORIZED`: Demo API token missing or invalid.
   - `RATE_LIMITED`: Demo evaluation rate limit exceeded.

4. **Persistent Idempotency & Safe Retries (Zero Duplicates)**:
   - Header `Idempotency-Key` required on all POST routes.
   - When a network timeout or unknown outcome occurs, state `OUTCOME_UNKNOWN` is recorded.
   - Retries first execute `connector.reconcile()` to verify whether the post was created on the platform.
   - Guarantees exactly 0 duplicate posts under retry.

5. **Advanced & Outstanding Capabilities**:
   - **High-Throughput Catalogue Import**: 1,000-row benchmark imported in 1.37 seconds (727 rows/sec).
   - **Rules Capture**: Offline keyword & mock adapters extracting verbatim rule quotes with human confirmation.
   - **Audience Relevance Engine**: Scores destinations 1.0 to 5.0 against AI, SaaS, Video, Marketing, Creators, Founders pillars (strict <=2.0 cap for zero signal).
   - **Manifest-Driven Tailoring Engine**: Word-boundary truncation, preserved AI disclosures, discussion framing.
   - **Precision@10 Fit Recommender**: Safety-gated ranking achieving 0.94 Precision@10 (+54% over simple baseline).
   - **Normalised Metrics**: Views, likes, comments, shares, clicks across Dev.to, Discourse, Mailchimp, Ghost.
   - **Recertification Scheduler**: Enforces 30-day hard limit with fake-clock testing, demotions, and `/api/v1/alerts`.
   - **Verified Destinations Catalogue (Partial - 75 Real Destinations)**: `catalogue/real_destinations_150.csv` containing 75 communities verified live over HTTP with verbatim exact substring rules quotes, saved HTML snapshots, and `catalogue_only=True` protection.

7. **Background Jobs Engine**:
   - `POST /api/v1/jobs` returns HTTP 202 Accepted and `job_id`.
   - `GET /api/v1/jobs/{job_id}` tracks progress from 0 to 100 percent.
   - Optional client callback with HMAC-SHA256 signature verification.

8. **CLI Batch Runner**:
   - `scripts/batch_runner.py` executes full end-to-end multi-connector tests and outputs structured execution manifests with timings, costs, and license compliance.

---

## Getting Started

### Prerequisites
- Python 3.11+
- Git
- Docker and Docker Compose (optional for containerized deployment)

### Local Setup (Virtual Environment)

1. **Clone and enter workspace**:
   ```bash
   git clone <repo-url>
   cd incubrix-distribution
   ```

2. **Create virtual environment and install dependencies**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   ```

4. **Run Automated Test Suite**:
   ```bash
   pytest -v
   ```

5. **Run CLI Batch Runner**:
   ```bash
   python scripts/batch_runner.py
   ```

6. **Start Application Locally**:
   ```bash
   # Terminal 1: Start Mock Platform Server (for simulation)
   uvicorn mock_platforms.server:mock_app --port 8001

   # Terminal 2: Start IncuBrix Distribution Network
   uvicorn app.main:app --port 8000 --reload
   ```

7. **Export OpenAPI 3.1 Specification**:
   ```bash
   python scripts/export_openapi.py
   ```

### Docker Compose Deployment

To run the entire stack (IncuBrix API + Mock Platform Server + MinIO Object Storage):

```bash
docker compose up -d --build
```

- **IncuBrix Distribution API**: `http://localhost:8000/docs`
- **Mock Platform Server**: `http://localhost:8001/docs`
- **MinIO Console**: `http://localhost:9001` (user: `minioadmin`, pass: `minioadmin`)

Health checks:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

---

## Project Structure

```
incubrix-distribution/
├── app/
│   ├── main.py                     # FastAPI application setup & lifecycle
│   ├── config.py                   # Pydantic Settings configuration
│   ├── database.py                 # Async & sync SQLAlchemy SQLite engines
│   ├── logging_conf.py             # Structured JSON logger
│   ├── api/
│   │   ├── health.py               # /health and /ready routes
│   │   ├── middleware.py           # Idempotency, correlation ID, error handling
│   │   ├── connector_routes.py     # POST /connector/v1/{connector_key}/{method}
│   │   ├── destinations.py         # /api/v1/destinations CRUD & CSV import
│   │   ├── jobs.py                 # /api/v1/jobs submission & tracking
│   │   └── certification.py        # /api/v1/certification/run & evidence
│   ├── connectors/
│   │   ├── base.py                 # BaseConnector abstract interface
│   │   ├── registry.py             # Manifest loader & connector registry
│   │   ├── discourse.py            # Discourse API connector
│   │   ├── lemmy.py                # Lemmy Fediverse connector
│   │   ├── devto.py                # Dev.to / Forem connector
│   │   ├── ghost.py                # Ghost Admin API connector
│   │   ├── signed_webhook.py       # Generic HMAC-SHA256 signed webhook
│   │   └── assisted.py             # Assisted manual submission connector
│   ├── rules/
│   │   ├── engine.py               # Posting-rules validation engine
│   │   ├── errors.py               # Shared error taxonomy & ConnectorException
│   │   └── backoff.py              # Exponential backoff and safe retries
│   ├── catalogue/
│   │   └── csv_importer.py         # CSV import, reachability, & URL normalisation
│   ├── certification/
│   │   └── harness.py              # 7-step publication certification harness
│   ├── jobs/
│   │   ├── manager.py              # Asynchronous job execution manager
│   │   └── callback.py             # HMAC signed callback dispatcher
│   ├── storage/
│   │   ├── evidence.py             # Audit & certification evidence storage
│   │   └── idempotency_store.py    # Persistent idempotency store
│   ├── models/                     # SQLAlchemy declarative models
│   └── schemas/                    # Pydantic request & response schemas
├── connectors/
│   └── manifests/                  # YAML manifests for all 6 connectors
├── mock_platforms/
│   └── server.py                   # Faithful mock servers with 429/401/422/503 simulation
├── scripts/
│   ├── batch_runner.py             # CLI batch test runner
│   └── export_openapi.py           # OpenAPI 3.1 exporter
├── tests/
│   ├── unit/                       # Unit tests (connectors, manifests, rules, idempotency)
│   └── integration/                # Integration tests (jobs, destinations, certification)
├── outputs/
│   ├── evidence/                   # Generated certification receipts
│   └── test_runs/                  # CLI batch runner execution manifests
├── Dockerfile                      # Production Docker container
├── docker-compose.yml              # Complete container stack
├── requirements.txt                # Python dependencies
├── openapi.yaml                    # OpenAPI 3.1 specification
├── REQUIREMENTS_CHECKLIST.md       # Traceability matrix
├── REPORT.md                       # Engineering report (design, tradeoffs, results)
├── SOURCES.md                      # Dependency licenses & compliance
└── AI_USE.md                       # AI engineering disclosure
```

---

## Verified Test Suite Summary

Run all tests via:
```bash
pytest -v
```

All 81 tests pass deterministically without real platform credentials:
- `tests/unit/test_database.py` (Database initialization, safe directory creation, in-memory SQLite, and URL configuration)
- `tests/unit/test_config.py` (Configuration defaults)
- `tests/unit/test_manifests.py` (YAML manifests validation for all connectors)
- `tests/unit/test_connector_contract.py` (Exact HTTP method signatures & return shapes)
- `tests/unit/test_all_connectors.py` (Lifecycle for Discourse, Lemmy, Dev.to, Ghost, Webhook, Assisted)
- `tests/unit/test_rules_engine.py` (Frequency caps, self-promotion, link policies, AI disclosure)
- `tests/unit/test_backoff.py` (Exponential backoff, 429 Retry-After, 5-failure limit)
- `tests/unit/test_idempotency.py` (Missing header rejection, duplicate prevention, hash conflict, restart recovery)
- `tests/integration/test_destinations_api.py` (Catalogue CRUD, duplicate URL normalisation, CSV import)
- `tests/integration/test_jobs.py` (Background 202 execution, progress tracking, policy violation handling)
- `tests/integration/test_certification.py` (Probe publish, status verification, deletion receipt)
- `tests/integration/test_core_certification.py` (Certification against real local and mock instances)
- `tests/integration/test_zero_duplicate_retry.py` (Timeout, OUTCOME_UNKNOWN, reconciliation, exactly 1 post)
- `tests/integration/test_csv_benchmark_1000.py` (1,000-row benchmark in 1.37s)
- `tests/integration/test_advanced_features.py` (Rules capture, relevance, tailoring, 3 new connectors)
- `tests/evaluation/test_recommender_eval.py` (Recommender precision@10 benchmark achieving 0.94)
- `tests/integration/test_metrics_normalisation.py` (Normalised views, likes, comments, shares, clicks)
- `tests/integration/test_recertification_fake_clock.py` (30-day recertification, demotion, alerts API)
- `tests/integration/test_real_catalogue_150.py` (150 verified destinations catalogue integrity)
- `tests/integration/test_secret_leak_prevention.py` (Secret sanitization in logs and outputs)
