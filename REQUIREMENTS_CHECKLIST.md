# Requirements Checklist: IncuBrix Distribution Network

This document tracks every mandatory and advanced requirement for the IncuBrix Engineering Assessment 4: "Distribution: Long-Tail Destination Network", mapping requirements directly to architecture, source files, and automated tests.

---

## 1. System Architecture & Standards

| Req ID | Requirement | Planned / Actual Source File(s) | Verification / Test File(s) | Status |
|---|---|---|---|---|
| **ARCH-01** | Python 3.11+, FastAPI, Pydantic v2 schemas | `app/main.py`, `app/schemas/*`, `app/config.py` | `tests/unit/test_config.py`, `tests/e2e/test_api.py` | ✅ Completed |
| **ARCH-02** | SQLite + SQLAlchemy ORM with async/sync session management | `app/database.py`, `app/models/*` | `tests/unit/test_database.py`, `tests/integration/test_destinations_api.py` | ✅ Completed |
| **ARCH-03** | OpenAPI 3.1 schema specification & documentation export | `app/main.py`, `scripts/export_openapi.py`, `openapi.yaml` | `tests/integration/test_openapi.py`, manual export | ✅ Completed |
| **ARCH-04** | Structured JSON logging with `timestamp`, `level`, `job_id`, `X-Correlation-Id` | `app/logging_conf.py`, `app/api/middleware.py` | `tests/unit/test_logging.py`, `tests/unit/test_connector_contract.py` | ✅ Completed |
| **ARCH-05** | Service Health check endpoints (`GET /health`, `GET /ready`) | `app/api/health.py` | `tests/unit/test_connector_contract.py` | ✅ Completed |
| **ARCH-06** | Configuration via environment variables & `.env.example` | `app/config.py`, `.env.example` | `tests/unit/test_config.py` | ✅ Completed |
| **ARCH-07** | Docker containerization & Docker Compose stack | `Dockerfile`, `docker-compose.yml` | Verified compose configuration | ✅ Completed |

---

## 2. Connector Contract (HTTP POST `/connector/v1/{connector_key}/{method}`)

| Req ID | Method & Signature | Output Shape | Source File(s) | Test File(s) | Status |
|---|---|---|---|---|---|
| **CONN-01** | `validate(rendition, destination, connection)` | `{ok: bool, violations: list[str]}` | `app/connectors/base.py`, `app/api/connector_routes.py` | `tests/unit/test_connector_contract.py` | ✅ Completed |
| **CONN-02** | `publish(rendition, destination, connection, idempotency_key)` | `{platform_post_id: str, live_url: str, status: str}` | `app/connectors/base.py`, `app/api/connector_routes.py` | `tests/unit/test_connector_contract.py` | ✅ Completed |
| **CONN-03** | `get_status(platform_post_id, connection)` | `{status: str, live_url: str}` | `app/connectors/base.py`, `app/api/connector_routes.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **CONN-04** | `delete(platform_post_id, connection)` | `{deleted: bool}` | `app/connectors/base.py`, `app/api/connector_routes.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **CONN-05** | `fetch_metrics(platform_post_id, connection, since)` | `{views, likes, comments, shares, saves, watch_time_s, clicks}` | `app/connectors/base.py`, `app/api/connector_routes.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **CONN-06** | `refresh_auth(connection)` | `{expires_at: str}` | `app/connectors/base.py`, `app/api/connector_routes.py` | `tests/unit/test_connector_contract.py` | ✅ Completed |
| **CONN-07** | `build_assist_pack(rendition, destination)` | `{files: list[str], caption: str, deep_link: str, checklist: list[str]}` | `app/connectors/assisted.py`, `app/api/connector_routes.py` | `tests/unit/test_connector_contract.py` | ✅ Completed |
| **CONN-08** | YAML Connector Manifests (key, tier, auth, surfaces, content_types, limits, rates, error_map, instance_param) | `connectors/manifests/*.yaml`, `app/connectors/registry.py` | `tests/unit/test_manifests.py` | ✅ Completed |
| **CONN-09** | Pure connector runtime (returns result structures, does not mutate DB directly) | `app/connectors/*` | `tests/unit/test_connector_contract.py` | ✅ Completed |

---

## 3. Mandatory 6 Connectors

| Req ID | Connector | Authentication & Protocol | Source File(s) | Test File(s) | Status |
|---|---|---|---|---|---|
| **CORE-01** | **Discourse** | API-Key + API-Username HTTP headers, Topics & Posts API | `app/connectors/discourse.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **CORE-02** | **Lemmy** | Auth token (JWT / Cookie), Community & Post creation API | `app/connectors/lemmy.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **CORE-03** | **Dev.to** | Forem API (`api-key`), Articles API | `app/connectors/devto.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **CORE-04** | **Ghost** | Ghost Admin API (API key / JWT token), Posts API | `app/connectors/ghost.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **CORE-05** | **Signed Webhook** | Generic HMAC-SHA256 signature in headers (`X-IncuBrix-Signature`), replay timestamp | `app/connectors/signed_webhook.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **CORE-06** | **Assisted Publishing** | Manual assist package builder (assets, checklist, copyable text, deep links) | `app/connectors/assisted.py` | `tests/unit/test_connector_contract.py` | ✅ Completed |

---

## 4. Posting-Rules Engine & Error Handling

| Req ID | Rule Check / Error Code | Behavior | Source File(s) | Test File(s) | Status |
|---|---|---|---|---|---|
| **RULE-01** | Destination frequency caps | Blocks/reschedules if cap exceeded (`DEST_RULE_FREQUENCY_CAP`) | `app/rules/engine.py` | `tests/unit/test_rules_engine.py` | ✅ Completed |
| **RULE-02** | Self-promotion restrictions | Validates rendition content vs policy (`DEST_SPEC_VIOLATION`) | `app/rules/engine.py` | `tests/unit/test_rules_engine.py` | ✅ Completed |
| **RULE-03** | Link policy & limits | Validates external link count/domains (`DEST_SPEC_VIOLATION`) | `app/rules/engine.py` | `tests/unit/test_rules_engine.py` | ✅ Completed |
| **RULE-04** | AI content disclosure | Enforces disclosure tags/statements if required (`DEST_SPEC_VIOLATION`) | `app/rules/engine.py` | `tests/unit/test_rules_engine.py` | ✅ Completed |
| **RULE-05** | Title and body length limits | Enforces min/max character limits (`DEST_SPEC_VIOLATION`) | `app/rules/engine.py` | `tests/unit/test_rules_engine.py` | ✅ Completed |
| **RULE-06** | Media & content type support | Checks mime types, aspect ratios, file size (`DEST_SPEC_VIOLATION`) | `app/rules/engine.py` | `tests/unit/test_rules_engine.py` | ✅ Completed |
| **RULE-07** | Automation allowance & destination enabled/certified check | Disallows automated publish if `automation_allowed=False` or disabled (`CONNECTOR_DISABLED`) | `app/rules/engine.py` | `tests/unit/test_rules_engine.py` | ✅ Completed |
| **RULE-08** | Shared Error Taxonomy: `DEST_SPEC_VIOLATION`, `DEST_RULE_FREQUENCY_CAP`, `CONNECTION_AUTH_EXPIRED`, `PLATFORM_RATE_LIMIT`, `PLATFORM_QUOTA_EXHAUSTED`, `PLATFORM_CONTENT_REJECTED`, `PLATFORM_UNAVAILABLE`, `CONNECTOR_DISABLED` | Structured JSON: `{code, message, retryable, details}` | `app/rules/errors.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **RULE-09** | Rate limiting, backoff & 5-failure abort | Respects HTTP 429 Retry-After, exponential backoff, max 5 consecutive failures | `app/rules/backoff.py` | `tests/unit/test_backoff.py` | ✅ Completed |

---

## 5. Safe Retries & Idempotency

| Req ID | Requirement | Behavior | Source File(s) | Test File(s) | Status |
|---|---|---|---|---|---|
| **IDEM-01** | Header requirement: `Idempotency-Key` on all `POST /api/v1/*` | 400 Bad Request if missing | `app/api/middleware.py` | `tests/unit/test_idempotency.py` | ✅ Completed |
| **IDEM-02** | Persistent idempotency storage | Records survive service restarts (SQLite) | `app/models/idempotency.py`, `app/storage/idempotency_store.py` | `tests/unit/test_idempotency.py` | ✅ Completed |
| **IDEM-03** | Identical request returns identical result | Returns original response and status code without re-execution | `app/api/middleware.py` | `tests/unit/test_idempotency.py` | ✅ Completed |
| **IDEM-04** | Payload mismatch detection | Returns 409 Conflict if key reused with different body | `app/api/middleware.py` | `tests/unit/test_idempotency.py` | ✅ Completed |
| **IDEM-05** | Concurrent requests & recovery tests | Atomic locking and in-flight request waiting | `app/storage/idempotency_store.py` | `tests/unit/test_idempotency.py` | ✅ Completed |

---

## 6. Destination Catalogue

| Req ID | Requirement | Details | Source File(s) | Test File(s) | Status |
|---|---|---|---|---|---|
| **CAT-01** | Destination data model | All fields (`id`, `name`, `url`, `platform_key`, `surface`, `category`, `audience_tags`, `language`, `geo`, `est_audience`, `rules_url`, `frequency_cap`, `self_promo_allowed`, `link_policy`, `disclosure_required`, `automation_allowed`, `connector_key`, `relevance_score`, `relevance_reason`, `level`, `last_certified_at`, `enabled`) | `app/models/destination.py`, `app/schemas/destination.py` | `tests/integration/test_destinations_api.py` | ✅ Completed |
| **CAT-02** | CRUD API routes | `GET /api/v1/destinations`, `POST`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` | `app/api/destinations.py` | `tests/integration/test_destinations_api.py` | ✅ Completed |
| **CAT-03** | CSV Import with validation | URL normalisation, duplicate detection (normalised URL + platform), reachability timeout checks, row-by-row reports | `app/catalogue/csv_importer.py`, `app/api/destinations.py` | `tests/integration/test_destinations_api.py` | ✅ Completed |

---

## 7. Publication Certification Harness

| Req ID | Step | Validation | Source File(s) | Test File(s) | Status |
|---|---|---|---|---|---|
| **CERT-01** | Test rendition validation | Validates test payload against connector rules | `app/certification/harness.py` | `tests/integration/test_certification.py` | ✅ Completed |
| **CERT-02** | Identifiable test post publishing | Uniquely identifiable post (`test_cert_{uuid}`) | `app/certification/harness.py` | `tests/integration/test_certification.py` | ✅ Completed |
| **CERT-03** | Verification of visibility | Live URL or verified API response verification | `app/certification/harness.py` | `tests/integration/test_certification.py` | ✅ Completed |
| **CERT-04** | Status fetch check | Calls `get_status` on published post | `app/certification/harness.py` | `tests/integration/test_certification.py` | ✅ Completed |
| **CERT-05** | Deletion and verification | Calls `delete`, verifies removal | `app/certification/harness.py` | `tests/integration/test_certification.py` | ✅ Completed |
| **CERT-06** | Evidence logging and storage | Records timestamps, connector version, responses, cleanup confirmations | `app/certification/harness.py`, `app/storage/evidence.py` | `tests/integration/test_certification.py` | ✅ Completed |
| **CERT-07** | Mock vs Real certification distinction | Sets `environment: "mock"` or `"production"` | `app/certification/harness.py` | `tests/integration/test_certification.py` | ✅ Completed |
| **CERT-08** | Certification API endpoint | `POST /api/v1/certification/run` | `app/api/certification.py` | `tests/integration/test_certification.py` | ✅ Completed |

---

## 8. Asynchronous Jobs & Webhooks

| Req ID | Feature | Specification | Source File(s) | Test File(s) | Status |
|---|---|---|---|---|---|
| **JOB-01** | Job submission | `POST /api/v1/jobs` returns HTTP 202 + `job_id` | `app/api/jobs.py` | `tests/integration/test_jobs.py` | ✅ Completed |
| **JOB-02** | Job status tracking | `GET /api/v1/jobs/{job_id}` returns status (queued, running, succeeded, failed), progress (0-100), results | `app/api/jobs.py`, `app/jobs/manager.py` | `tests/integration/test_jobs.py` | ✅ Completed |
| **JOB-03** | Background worker runtime | Asynchronous task execution with retry & status updates | `app/jobs/manager.py` | `tests/integration/test_jobs.py` | ✅ Completed |
| **JOB-04** | Webhook callback support | Signed POST to callback URL with HMAC-SHA256 in `X-IncuBrix-Signature` | `app/jobs/callback.py` | `tests/integration/test_jobs.py` | ✅ Completed |

---

## 9. Simulation Mode & Mock Platform Servers

| Req ID | Scenario | Mock Response | Source File(s) | Test File(s) | Status |
|---|---|---|---|---|---|
| **SIM-01** | Standalone Simulation Mode | Operates without real credentials via mock servers | `mock_platforms/server.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **SIM-02** | Simulated Success | Valid publish, get_status, delete | `mock_platforms/server.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **SIM-03** | Simulated HTTP 429 Rate Limit | Returns 429 with `Retry-After: 2` | `mock_platforms/server.py` | `tests/unit/test_all_connectors.py`, `tests/unit/test_backoff.py` | ✅ Completed |
| **SIM-04** | Simulated Expired Auth | Returns 401 Unauthorized (`CONNECTION_AUTH_EXPIRED`) | `mock_platforms/server.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **SIM-05** | Simulated Content Rejection | Returns 422 Unprocessable (`PLATFORM_CONTENT_REJECTED`) | `mock_platforms/server.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **SIM-06** | Simulated Platform Unavailable | Returns 503 Service Unavailable (`PLATFORM_UNAVAILABLE`) | `mock_platforms/server.py` | `tests/unit/test_all_connectors.py` | ✅ Completed |
| **SIM-07** | Simulated Timeout & Retry | Delayed responses simulating socket timeout | `mock_platforms/server.py` | `tests/unit/test_backoff.py` | ✅ Completed |

---

## 10. CLI Batch Runner & Deliverables

| Req ID | Deliverable | Description | Location | Status |
|---|---|---|---|---|
| **DELIV-01** | CLI Batch Runner | Runs test publication batch, outputs JSON manifest & evidence to directory | `scripts/batch_runner.py` | ✅ Completed |
| **DELIV-02** | Dockerfile & Docker Compose Stack | App, mock platforms, MinIO storage container | `Dockerfile`, `docker-compose.yml` | ✅ Completed |
| **DELIV-03** | Comprehensive Documentation | `README.md`, `REPORT.md` (2-4 pages), `SOURCES.md`, `AI_USE.md` | Root folder | ✅ Completed |
| **DELIV-04** | Certification & Evidence Pack | Real/mock run logs, responses, deletion receipts | `outputs/` | ✅ Completed |
| **DELIV-05** | Submission Form Template | Filled submission checklist matching exact requirements | `outputs/submission_summary.json` | ✅ Completed |
