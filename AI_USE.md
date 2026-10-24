# AI_USE: Transparent Record of AI-Assisted Engineering

## Assessment
**IncuBrix Engineering Assessment 4: Distribution: Long-Tail Destination Network**

## AI Assistance Disclosure

In accordance with IncuBrix assessment guidelines and engineering integrity requirements, this project was developed and refined with the assistance of **Google Antigravity (Advanced Agentic AI)**.

### Tools Used
- **Agent Environment**: Google Antigravity IDE & Autonomous Agentic Workflow
- **Model Engine**: Gemini 3.8 Flash (Medium)

---

### Role & Contributions of the AI Agent

#### First Pass (Core Architecture & Baseline Gaps)
1. **Architecture & Design**:
   - Proposed modular layout implementing pure connector runtime, centralized posting-rules engine, and transactional idempotency middleware.
   - Designed schema specifications ensuring strict adherence to the required connector HTTP interface (`/connector/v1/{connector_key}/{method}`) and application API (`/api/v1/*`).
   - Planned and executed Gaps A through M, Advanced 1-5, and Outstanding 1-4.
2. **Code Implementation & Gaps Resolution**:
   - Built connectors for Discourse, Lemmy, Dev.to, Ghost, HMAC Webhook, Assisted Publishing, Hashnode, Slack, and Mailchimp (draft-only).
   - Built the mock platform server simulating 429 rate-limiting, expired authentication, content rejection, and network timeouts.
   - Built safe retry & reconciliation logic to guarantee zero duplicate publications under timeout conditions.
   - Enhanced posting rules engine with fail-closed missing rule checks, multi-marker self-promotion heuristics, and 5 link-format extractors.
   - Built the 1,000-row CSV importer with SSRF guards and normalization.
   - Built the Precision@10 recommender, metrics normalization engine, 30-day recertification scheduler.
   - Implemented demo infrastructure: `Dockerfile.demo`, `render.yaml`, `app/api/demo.py`, `DemoAuthAndRateLimitMiddleware`, and `scripts/check_live_demo.py`.

#### Second Pass (Review Audit & Remediation)
1. **S3 / MinIO Storage Backend (Integration 7)**:
   - Replaced placeholder storage with real `boto3` client implementation in `app/storage/evidence.py`.
   - Added bucket auto-creation, presigned URL generation, and fallback to disk mirror.
   - Added destination CSV input via file upload OR remote URL (SSRF guarded).
   - Configured `STORAGE_BACKEND=s3` and MinIO healthcheck in `docker-compose.yml`.
2. **Real Destination Catalogue Research (Outstanding 4)**:
   - Replaced AI-paraphrased catalogue with live HTTP crawler `scripts/build_verified_catalogue.py`.
   - Crawled 85 community URLs with polite User-Agent; verified exactly 75 destinations live (10 unreachable/403/404 dropped).
   - Extracted 62 verbatim exact substring quotes verified against saved HTML snapshots in `catalogue/snapshots/` with SHA-256 hashes.
   - Fixed mislabeled platforms (e.g. GitHub Discussions classified as `assisted`).
   - Honestly reported 75 verified destinations and marked item **Partial** (never padding or inventing entries).
3. **LLM Rules Capture Adapter (Advanced 1)**:
   - Implemented `GeminiRulesCaptureAdapter` in `app/rules/capture.py` calling Google Gemini 1.5 Flash via official REST API.
   - Added secret protection (key strictly read from `GEMINI_API_KEY` environment variable, never logged or committed).
   - Added exponential backoff retry on HTTP 429 rate limit.
   - Implemented strict anti-hallucination guard: quotes must exist as exact substrings of the source text or the proposed rule is dropped.
   - Added human-in-the-loop confirmation requirement (`pending` status).
   - Created live runner `scripts/run_live_rules_capture.py` and marked item **Partial** pending candidate terminal key.
4. **Self-Contained Test Suite (Integration 1)**:
   - Added session fixture in `conftest.py` starting in-process mock server on port 8001 during `pytest`.
   - Added guard test `tests/integration/test_self_contained_fixtures.py`.
   - All 76 tests now pass cleanly with a single command (`pytest`) with zero external setup.
5. **10x Local Instances Certification Suite (Core 2 / Outstanding 3)**:
   - Created `scripts/certify_local_instances_10x.py` running 10 full 5-step certification cycles for Lemmy and 10 for Ghost (20/20 passed, receipts saved, summary in `outputs/test_runs/real_instances_10x_summary.json`).

---

### Third-Party LLM Provider Terms & Data Privacy

- **Provider**: Google AI Studio / Google Gemini API
- **Model**: `gemini-1.5-flash`
- **Terms & Commercial Use**:
  - Covered by [Google AI Studio Terms of Service](https://ai.google.dev/terms).
  - Commercial use is permitted.
  - In paid/commercial tiers, customer prompts and outputs are not used to train Google models.
- **Credential Protection**:
  - API keys are never stored in the codebase, docker images, or git history.
  - The adapter strictly reads from the `GEMINI_API_KEY` environment variable.
  - The secret scanner (`scripts/secret_scan.py`) verifies zero key leaks.

---

### Human Engineering Oversight & Validation
- Every generated component was subjected to deterministic automated tests run locally in Python 3.12 (`pytest`).
- No live community postings or fabricated credentials were used: all tests executed against local mock servers or isolated instances.
- Personal candidate fields in the submission spreadsheet (`Problem Statements/Assessment4_*.xlsx`) were intentionally left blank for the candidate to fill and sign.
- All certification results and test evidence represent genuine, locally executed receipts stored in git-tracked directories.
