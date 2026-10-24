# SOURCES & LICENSES: IncuBrix Distribution Network

This document tracks all external dependencies, libraries, APIs, and components used in the IncuBrix Distribution Network, verifying their licenses for commercial use and compliance.

## Direct Python Dependencies

| Package | Version Range | License | Primary Purpose | Commercial Use Permitted |
|---|---|---|---|---|
| **fastapi** | `>=0.111.0` | MIT | High-performance async REST API framework | ✅ Yes |
| **uvicorn** | `>=0.30.0` | BSD-3-Clause | ASGI web server runtime | ✅ Yes |
| **pydantic** | `>=2.7.0` | MIT | Data validation and connector contract schemas | ✅ Yes |
| **pydantic-settings** | `>=2.3.0` | MIT | Environment variable configuration loader | ✅ Yes |
| **sqlalchemy** | `>=2.0.30` | MIT | SQL ORM and transactional database abstraction | ✅ Yes |
| **aiosqlite** | `>=0.20.0` | MIT | Async driver for SQLite | ✅ Yes |
| **httpx** | `>=0.27.0` | BSD-3-Clause | Asynchronous HTTP client for platform APIs & mocks | ✅ Yes |
| **pyyaml** | `>=6.0.1` | MIT | Parser for YAML connector manifests | ✅ Yes |
| **python-multipart** | `>=0.0.9` | Apache-2.0 | Multipart form parser for CSV uploads | ✅ Yes |
| **pyjwt** | `>=2.8.0` | MIT | JWT token generation for Ghost Admin API | ✅ Yes |
| **cryptography** | `>=42.0.0` | Apache-2.0 / BSD | Cryptographic primitives for HMAC-SHA256 & JWT | ✅ Yes |
| **python-dotenv** | `>=1.0.1` | BSD-3-Clause | Loading `.env` in local development | ✅ Yes |
| **pytest** | `>=8.2.0` | MIT | Automated testing framework | ✅ Yes |
| **pytest-asyncio** | `>=0.23.0` | Apache-2.0 | Async test runners for FastAPI and HTTPX | ✅ Yes |
| **pytest-mock** | `>=3.14.0` | MIT | Mocking utilities for unit tests | ✅ Yes |
| **boto3** | `>=1.34.0` | Apache-2.0 | AWS S3 / MinIO storage client library | ✅ Yes |

## Infrastructure & Runtime Components

| Component | Image / Version | License | Purpose & Licensing Notes |
|---|---|---|---|
| **Python** | 3.12-slim | PSF License | Base Docker container runtime |
| **SQLite** | 3.x (Built-in) | Public Domain | Zero-configuration relational database |
| **Local Disk Storage** | Built-in | N/A | Shipped default storage backend (Permissive, zero AGPL contamination) |
| **MinIO (Default Compose)** | `cgr.dev/chainguard/minio:latest` | GNU AGPL-3.0 | S3-compatible object storage service in `docker-compose.yml`. **License Notice**: The server image is licensed under AGPLv3. The IncuBrix application communicates exclusively over standard HTTP/REST S3 protocol via the Apache-2.0 `boto3` client, maintaining a strict network separation boundary. For embedded distributions or environments strictly prohibiting AGPLv3 images, drop-in Apache-2.0 alternatives are supported: **SeaweedFS** (`chrislusf/seaweedfs:latest`, Apache-2.0), legacy **MinIO Apache-2.0** (`minio/minio:RELEASE.2021-04-22T15-44-28Z`, Apache-2.0), or **LocalStack** (Apache-2.0). |


## External Platform API Specs Consulted & Verified

1. **Discourse API**: Official Discourse API Documentation (REST endpoints for `/posts.json`, `/posts/{id}.json`, `/search.json`). Verified headers: `Api-Key`, `Api-Username`.
2. **Lemmy API**: Lemmy HTTP API v3 (REST endpoints for `/api/v3/post`, `/api/v3/post/delete`). Verified auth: JWT token.
3. **Dev.to / Forem API**: Dev.to API v0 (REST endpoints for `/api/articles`, `/api/articles/{id}`). Verified header: `api-key`.
4. **Ghost Admin API**: Ghost v5 Content & Admin API (REST endpoints for `/ghost/api/admin/posts/`). Verified HS256 JWT signed with Admin API hex secret.
5. **Generic Signed Webhook**: Standard HMAC-SHA256 header signature (`X-IncuBrix-Signature: sha256=...`) with timestamp replay prevention (`X-IncuBrix-Timestamp`).
6. **Assisted Publishing**: IncuBrix manual submission packaging contract for human-moderated platforms.
7. **Hashnode API**: Official Hashnode GraphQL API (`publishPost`, `deletePost`, `post` queries). Verified personal access token authentication.
8. **Slack Web API**: Official Slack Web API (`chat.postMessage`, `chat.delete`, `conversations.history`). Verified Bot Token (`xoxb-`) auth and Block Kit payload.
9. **Mailchimp API**: Official Mailchimp Marketing API v3 (`/3.0/campaigns`, `/3.0/campaigns/{id}/content`, `/3.0/reports/{id}`). Verified draft-only restriction (`status: "save"`).
10. **Google Gemini API**: Official Google Gemini REST API (`/v1beta/models/gemini-1.5-flash:generateContent`). Used for AI rules extraction with anti-hallucination substring guards. Terms: [Google AI Studio Terms of Service](https://ai.google.dev/terms). Free tier allows quality improvements; commercial paid tier guarantees prompts/outputs are not used for training.

## Datasets & Curated Catalogues

1. **Real Destinations Catalogue (`catalogue/real_destinations_150.csv`)**:
   - 75 real public developer, AI, SaaS, and video communities verified live over HTTP (out of 85 candidate URLs crawled; 10 dropped due to 403/404).
   - 62 community entries carry exact word-for-word quotes cryptographically verified as exact substrings against saved HTML snapshots in `catalogue/snapshots/` with SHA-256 hashes.
   - 13 communities without distinct rules pages have empty quotes and fail-closed default rules.
   - All rows flagged `catalogue_only=True` and `rules_status="unconfirmed"` to guarantee zero unsolicited automated posting.
2. **Precision@10 Recommender Evaluation Set (`tests/evaluation/test_recommender_eval.py`)**:
   - 10 distinct technical content queries and 30 destinations with hand-labelled binary relevance ground truth based on vertical pillar alignment and rule safety gating.
