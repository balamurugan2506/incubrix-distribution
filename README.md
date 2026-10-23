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

2. **6 Core Connectors with Declarative YAML Manifests**:
   - **Discourse**: Forum topics & posts with `Api-Key` and `Api-Username`.
   - **Lemmy**: Fediverse communities & posts via JWT / token auth.
   - **Dev.to / Forem**: Developer blogging with `api-key` auth.
   - **Ghost**: Ghost Admin API with dynamic JWT generation (`{id}:{secret_hex}`).
   - **Generic Signed Webhook**: HMAC-SHA256 signature in `X-IncuBrix-Signature` and timestamp replay protection.
   - **Assisted Publishing**: Generates rich manual submission packages with formatted captions, assets, deep links, and human checklists for platforms prohibiting automated posting.

3. **Standardized Error Taxonomy**:
   Structured JSON responses matching:
   - `DEST_SPEC_VIOLATION`
   - `DEST_RULE_FREQUENCY_CAP`
   - `CONNECTION_AUTH_EXPIRED`
   - `PLATFORM_RATE_LIMIT`
   - `PLATFORM_QUOTA_EXHAUSTED`
   - `PLATFORM_CONTENT_REJECTED`
   - `PLATFORM_UNAVAILABLE`
   - `CONNECTOR_DISABLED`

4. **Persistent Idempotency & Safe Retries**:
   - Header `Idempotency-Key` required on all POST routes under `/api/v1/`.
   - SQLite persistence ensures deduplication survives server restarts.
   - SHA-256 payload hashing rejects key reuse with altered payloads (HTTP 409 Conflict).
   - In-flight request concurrency lock prevents race conditions.
   - Respects HTTP 429 `Retry-After` headers and exponential backoff; halts after 5 consecutive failures.

5. **Destination Catalogue & CSV Importer**:
   - Full CRUD API under `/api/v1/destinations`.
   - CSV importer with URL normalisation, duplicate detection on `(normalised_url, platform_key)`, field validation, and safe reachability checks.

6. **Publication Certification Harness**:
   - 7-step automated verification: Validate -> Publish identifiable probe -> Verify live URL -> Fetch status -> Delete -> Confirm deletion -> Save evidence.
   - Transparent distinction between `mock` and `production` environments.
   - Automatic cleanup of all test probes within seconds.
   - Evidence receipts saved to `./outputs/evidence/`.

7. **Background Jobs Engine**:
   - `POST /api/v1/jobs` returns HTTP 202 Accepted and `job_id`.
   - `GET /api/v1/jobs/{job_id}` tracks progress from 0–100%.
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

All 28 tests pass deterministically without real platform credentials:
- `tests/unit/test_config.py` (Configuration defaults)
- `tests/unit/test_manifests.py` (All 6 YAML manifests validation)
- `tests/unit/test_connector_contract.py` (Exact HTTP method signatures & return shapes)
- `tests/unit/test_all_connectors.py` (End-to-end lifecycle for Discourse, Lemmy, Devto, Ghost, Webhook, Assisted)
- `tests/unit/test_rules_engine.py` (Frequency caps, self-promotion, link policies, AI disclosure)
- `tests/unit/test_backoff.py` (Exponential backoff, 429 Retry-After, 5-failure limit)
- `tests/unit/test_idempotency.py` (Missing header rejection, duplicate prevention, hash conflict, restart recovery)
- `tests/integration/test_destinations_api.py` (Catalogue CRUD, duplicate URL normalisation, CSV import)
- `tests/integration/test_jobs.py` (Background 202 execution, progress tracking, policy violation handling)
- `tests/integration/test_certification.py` (7-step probe publish, status verification, deletion receipt)
