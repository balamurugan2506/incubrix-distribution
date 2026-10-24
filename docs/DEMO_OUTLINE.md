# Demo Video Recording Outline (Maximum 8 Minutes)

**IncuBrix Engineering Assessment 4: Long-Tail Destination Network**  
**Target Duration**: 7:30 – 8:00 minutes  
**Format**: Screen capture with voiceover walkthrough  

---

## Part 1: Project Overview & Architecture (1:30)
- **0:00 - 0:45**: Introduction to IncuBrix Distribution Network.
  - Show the architecture diagram from [README.md](file:///c:/Users/Bala%20murugan/OneDrive/Desktop/incubrix-distribution/README.md).
  - Highlight the core principle: **Pure connector runtime** that returns typed result shapes without touching IncuBrix domain models.
- **0:45 - 1:30**: File structure overview.
  - Show `app/connectors/base.py` and `connectors/manifests/` (all 6 YAML manifests).
  - Point out `openapi.yaml` (OpenAPI 3.1) and `.env.example`.

---

## Part 2: Exact Connector Contract Walkthrough (1:30)
- **1:30 - 2:15**: `POST /connector/v1/{connector_key}/{method}` contract.
  - Show `app/api/connector_routes.py` with typed endpoints: `validate`, `publish`, `get_status`, `delete`, `fetch_metrics`, `refresh_auth`, `build_assist_pack`.
- **2:15 - 3:00**: Connectors in action:
  - Demonstrate `devto.py`, `discourse.py`, `lemmy.py`, `ghost.py`, `signed_webhook.py` (HMAC signature verification).
  - Demonstrate `assisted.py`: Explain why automated publishing is blocked and show the assist pack generation (caption, checklist, deep links).

---

## Part 3: Posting-Rules Engine & Safe Idempotency (1:30)
- **3:00 - 3:45**: Posting Rules Engine (`app/rules/engine.py`):
  - Frequency caps (SQLite 24-hour publication checks).
  - Anti-spam & self-promotion detection.
  - AI content disclosure enforcement.
  - Link policy enforcement (`none`, `restricted`, `allowed`).
- **3:45 - 4:30**: Idempotency & Safe Retries (`app/api/middleware.py` & `app/storage/idempotency_store.py`):
  - Header requirement `Idempotency-Key` on `/api/v1/*`.
  - SHA-256 payload collision detection (409 Conflict).
  - Persistence across server restarts.
  - Exponential backoff respecting HTTP 429 `Retry-After` headers and 5-failure abort.

---

## Part 4: Destination Catalogue, CSV Importer & Background Jobs (1:30)
- **4:30 - 5:15**: Destination Catalogue (`/api/v1/destinations`):
  - CRUD operations.
  - CSV Import (`/import-csv`) with URL normalisation, duplicate rejection on `(normalised_url, platform_key)`, and reachability checks.
- **5:15 - 6:00**: Background Jobs Engine (`/api/v1/jobs`):
  - Submit publication job returning `HTTP 202 Accepted` with `job_id`.
  - Poll `/api/v1/jobs/{job_id}` showing progress progressing from 0 to 100 percent.
  - Explain optional HMAC-SHA256 signed callback notification.

---

## Part 5: 7-Step Certification Harness & Automated Test Suite (1:30)
- **6:00 - 6:45**: Publication Certification Harness (`app/certification/harness.py`):
  - Show the 7-step lifecycle: Validate -> Publish identifiable test post -> Confirm visibility -> Get status -> Delete post -> Confirm deletion -> Save evidence receipt to `outputs/evidence/`.
  - Differentiate `mock` vs `production` environment labeling.
- **6:45 - 7:30**: Test Suite & Batch Runner:
  - Run `pytest -v` in the terminal demonstrating all 28 unit and integration tests passing.
  - Run `python scripts/batch_runner.py` showing batch execution across all 6 connectors and the generated output manifest.
  - Wrap up and reference [REPORT.md](file:///c:/Users/Bala%20murugan/OneDrive/Desktop/incubrix-distribution/REPORT.md).
