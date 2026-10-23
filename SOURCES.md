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

## Infrastructure & Runtime Components

| Component | Image / Version | License | Purpose |
|---|---|---|---|
| **Python** | 3.12-slim | PSF License | Base Docker container runtime |
| **SQLite** | 3.x (Built-in) | Public Domain | Zero-configuration relational database |
| **MinIO** | RELEASE.2024-05-10 | AGPLv3 (runtime service) | S3-compatible local evidence & asset storage |

## External Platform API Specs Consulted

1. **Discourse API**: Official Discourse API Documentation (REST endpoints for `/posts.json`, `/t/{id}.json`). Headers: `Api-Key`, `Api-Username`.
2. **Lemmy API**: Lemmy HTTP API v3 (REST endpoints for `/api/v3/post`). Auth: Bearer / token.
3. **Dev.to / Forem API**: Dev.to API v0 (REST endpoints for `/api/articles`). Header: `api-key`.
4. **Ghost Admin API**: Ghost v5 Content & Admin API (REST endpoints for `/ghost/api/admin/posts/`). Token: HS256 JWT signed with Admin API hex secret.
5. **Generic Signed Webhook**: Industry standard HMAC-SHA256 header signature (`X-IncuBrix-Signature: sha256=...`) with timestamp replay prevention (`X-IncuBrix-Timestamp`).
6. **Assisted Publishing**: IncuBrix manual submission packaging contract for human-moderated platforms.
