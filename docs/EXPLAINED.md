# IncuBrix Engineering Architecture & Codebase Guide (EXPLAINED.md)

*A plain-language guide for the live technical interview. Read this before your technical interview to understand every layer, architectural rationale, and execution path.*

---

## 1. Core Architecture Concepts (With One Analogy Per Concept)

### Concept 1: The Request Path (From POST to Platform and Back)
* **Analogy**: Mailing an insured parcel through a registered postal depot.
  1. **Drop-off**: The parcel arrives at the counter (`POST /connector/v1/{platform}/publish` or `POST /api/v1/jobs/publish`).
  2. **Security & Stamp**: The postal clerk inspects your credentials, stamps a tracking barcode (`X-Correlation-Id`), and checks whether this parcel was already accepted earlier (`Idempotency-Key`).
  3. **Parcel Scanner**: The customs inspector verifies weight, dimension, and prohibited items (`PostingRulesEngine` checks link policies, promo markers, frequency caps, and character limits).
  4. **Adaptation**: If the destination requires a specific format (e.g. word boundary truncation or forum question framing), the parcel gets wrapped appropriately (`tailoring.py`).
  5. **Dispatch & Delivery**: The courier carries the request to the external service (`Connector.publish()`).
  6. **Receipt**: The carrier brings back a proof of delivery (`platform_post_id`, `live_url`), which gets recorded in the depot ledger (`PublicationRecordModel`), cached in the idempotency vault, and handed back to the sender.

### Concept 2: Why the Order is Idempotency -> Limits/Rules -> Connector
* **Analogy**: An ATM machine dispensing cash.
  * **Why Idempotency First**: If you press the "Withdraw $100" button twice because the screen flickered, the ATM must immediately look at the transaction reference *before* checking your account limits or counting banknotes. If it counted notes first, you'd trigger overdraft penalties or withdraw twice. Checking idempotency first guarantees that retrying an identical request never executes side-effects twice and instantly returns the cached result.
  * **Why Limits and Rules Second**: You must check if the destination allows links, allows self-promotion, or is on a 24-hour cool-down *before* calling the remote network. Calling the platform first and failing afterwards burns your platform API quota, risks account bans, and leaks draft content to communities with strict moderation.
  * **Why Connector Third**: The connector is the only component that touches external I/O. By placing it last, external network calls only occur if the request is guaranteed to be new, safe, policy-compliant, and tailored.

### Concept 3: What Reconcile Does After a Timeout
* **Analogy**: Calling a restaurant when your delivery app crashes while ordering pizza.
  * When your phone battery dies while the payment spinner is turning, you don't immediately order a second pizza (or you'll end up with two pizzas and two charges). Instead, you call the restaurant and ask: *"Did you receive an order under the name 'Token-123'?"*
  * In IncuBrix, if an HTTP publish call times out after 10 seconds or returns an unknown outcome (`504 Gateway Timeout`), we mark the state `OUTCOME_UNKNOWN`.
  * On any subsequent retry with the same key, the service calls `connector.reconcile()`:
    * Dev.to searches by article title.
    * Discourse queries `search.json?q=...` by title token.
    * Ghost queries posts with title filter.
    * Webhook sends the idempotency key for partner deduplication.
  * If the post already exists on the platform, `reconcile` returns the existing post receipt directly. We never call create again, guaranteeing **0 duplicate posts under retry**.

### Concept 4: How Certification Cleans Up
* **Analogy**: A health inspector tasting a test dish and wiping down the workstation before leaving.
  * When certifying a connector against a platform, IncuBrix publishes a labelled probe post (`[IncuBrix Certification Probe] ...`), verifies it is live, reads its status, and then immediately deletes it.
  * If the probe fails, or if a network hiccup occurs halfway through, the harness does not abandon the post.
  * It enters `_execute_guaranteed_cleanup()`: it reconciles by the test token, queries the post ID, and retries the delete operation with exponential backoff until the post is verified gone (`status in ('not_found', 'deleted')`).
  * If the platform renames an API response field or changes its schema, certification immediately issues a verdict of `failed (demote)` and demotes the destination to `status = 'demoted'`. Demoted destinations are refused at publish time.

### Concept 5: How a Manifest Drives Tailoring and Limits
* **Analogy**: An architect's blueprint driving a modular 3D printer.
  * Instead of writing giant `if platform == "discourse": ... elif platform == "lemmy": ...` conditional spaghetti in Python code, every destination connector defines a declarative YAML manifest in `connectors/manifests/`.
  * The manifest specifies:
    * `format_limits`: minimum and maximum character counts for title and body, maximum tags, media byte limits.
    * `tailoring`: tag style (`slug`, `hashtag`, `none`), framing (`discussion_first`, `article`), closing question (`true`/`false`), canonical URL attachment.
  * The engine reads the manifest tokens dynamically:
    * Truncation occurs strictly at whitespace word boundaries (never cutting a word in half).
    * AI disclosure notices (`This article was created with AI assistance...`) are protected from being severed.
    * Forum communities receive discussion prompts and closing questions automatically.

### Concept 6: How to Add a New Destination and a New Connector
* **Adding a Destination (Zero Code Change)**:
  * Adding a second Discourse forum, a new Lemmy community, or a new Dev.to tag requires **exactly one catalogue row** inserted via `POST /api/v1/destinations` or imported from CSV.
  * You supply `name`, `url`, `platform_key="discourse"`, `connector_key="discourse"`, and rules parameters. The platform logic is completely reusable.
* **Adding a Connector (Plug-and-Play Contract)**:
  * 1. Create `connectors/manifests/{key}.yaml` declaring authentication, surface types, format limits, and capabilities.
  * 2. Create `app/connectors/{key}.py` implementing `BaseConnector` (`validate`, `publish`, `reconcile`, `get_status`, `delete`, `fetch_metrics`).
  * 3. Register the class in `app/connectors/registry.py`. The harness, rules engine, and API routes support it automatically.

### Concept 7: S3 / MinIO Evidence Storage & Presigned Links
* **Analogy**: A bank safe-deposit vault with time-limited visitor passes.
  * All certification receipts, assist packs, and import reports are stored in S3-compatible object storage via `boto3` (`app/storage/evidence.py`).
  * If S3/MinIO is active (`STORAGE_BACKEND=s3`), objects are pushed to the bucket and the API issues secure, time-limited presigned download URLs (e.g., expiring in 3600 seconds).
  * If MinIO is offline or during standalone local testing, it falls back seamlessly to the local filesystem mirror (`outputs/evidence/`) without throwing exceptions.
  * Destination catalogue CSVs are accepted as direct multipart file uploads OR via remote HTTP/HTTPS URLs with SSRF protection (private/loopback ranges blocked).

### Concept 8: Live-Verified Community Research & Cryptographic Substring Proof
* **Analogy**: A legal researcher citing statute pages with court-stamped exhibits.
  * Rather than relying on LLM-generated summaries or guesses, IncuBrix uses 75 real communities verified live over HTTP via `scripts/build_verified_catalogue.py`.
  * For every community with explicit guidelines, exact word-for-word quotes are captured.
  * Raw HTML snapshots are stored in `catalogue/snapshots/` alongside SHA-256 cryptographic hashes.
  * The integration test `tests/integration/test_real_catalogue_150.py` independently recalculates the SHA-256 of each snapshot and verifies that every rules quote is an exact, unedited substring of the page.
  * Communities without dedicated rules pages are given empty quotes and fail-closed default rules. Every entry is flagged `catalogue_only=True` and `rules_status="unconfirmed"` until a person confirms them.

### Concept 9: Real LLM Rules Extractor with Substring Guard & Human-in-the-Loop
* **Analogy**: A paralegal drafting brief recommendations that require senior partner sign-off.
  * `GeminiRulesCaptureAdapter` in `app/rules/capture.py` connects to Google Gemini via official REST endpoints.
  * The API key is read strictly from the `GEMINI_API_KEY` environment variable (never logged, displayed, or committed).
  * It includes built-in exponential backoff retry for HTTP 429 rate limit responses.
  * **Strict Anti-Hallucination Guard**: Every rule proposed by the LLM MUST contain a verbatim quote that exists as an exact substring of the community's page text. If the quote does not match the page text verbatim, the proposed rule is immediately dropped as an unverifiable hallucination.
  * Extracted proposals remain in `pending` state and cannot govern publication until confirmed by a human through `POST /api/v1/rules/confirm`. Loosening a rule requires explicit confirmation acknowledgement.

---

## 2. Fifteen Quiz Questions for the Candidate

### Q1: What is the primary difference between a transient error and a non-retryable error?
**Answer**: Transient errors (`retryable=True`) occur due to network timeouts, platform 503 unavailability, or temporary rate limits (429 with `Retry-After`). Non-retryable errors (`retryable=False`) stem from deterministic violations: authentication expiration, rule rejections (e.g. self-promotion in a no-promo community), format limit violations, or schema mismatches.

### Q2: Why does IncuBrix never retry a non-idempotent create call inside an automatic backoff loop?
**Answer**: Because a timeout on a create request means the platform might have already created the post but dropped the connection before answering. Retrying a blind create causes duplicate posts. Instead, the service records state `OUTCOME_UNKNOWN` and requires a reconciliation step before attempting any further creation.

### Q3: How does the system ensure zero duplicate posts if a network timeout occurs?
**Answer**: The idempotency middleware marks the idempotency key as `OUTCOME_UNKNOWN`. When the client or job retries with the same idempotency key, the connector calls `reconcile()` to search the external platform by title or token. If the post exists, it returns the existing post receipt without publishing again.

### Q4: What happens if a destination community has missing posting rules in the catalogue?
**Answer**: IncuBrix enforces a **fail-closed** security architecture. If required rules (such as link policy, self-promotion allowance, or frequency cap) are missing or null, `PostingRulesEngine.check_rules()` raises `DEST_SPEC_VIOLATION` and refuses to publish.

### Q5: How does the link counter count links in content?
**Answer**: It extracts and counts links in 5 distinct written forms: (1) explicit `https://` and `http://` URLs, (2) `www.` prefixed hostnames, (3) Markdown links `[anchor](url)`, (4) HTML anchor hrefs `<a href="...">`, and (5) bare domain names with standard TLDs (e.g. `incubrix.ai`, `github.com`).

### Q6: How does the self-promotion heuristic avoid false positives?
**Answer**: Instead of matching isolated single words like "product", it evaluates multi-marker signals combining calls to action ("check out our", "sign up", "try our beta"), transactional discount wording ("50% discount", "pricing plan", "coupon code"), and commercial affiliate markers. In ambiguous contexts, it requires multiple corroborating markers before flagging a post as self-promotional.

### Q7: Why are long-running tasks like CSV import and full certification executed as asynchronous jobs?
**Answer**: Per the Integration Standard, any operation taking longer than 2 seconds must return `202 Accepted` with a `job_id`. Long-running tasks run asynchronously in the background via `JobManager`, allowing clients to poll progress (`0 to 100 percent`) or receive an HMAC-SHA256 signed callback upon completion.

### Q8: What does the recertification scheduler do if a destination was certified 32 days ago?
**Answer**: The system enforces a strict 30-day recertification hard cap. Any destination older than 30 days is re-tested. If the test fails, the scheduler immediately demotes the destination (`status = 'demoted'`), disables it (`enabled = False`), and creates a high-severity alert in the `alerts` table (`GET /api/v1/alerts`).

### Q9: Can a candidate publish to or certify a `catalogue_only` destination?
**Answer**: No. `catalogue_only` destinations represent real reference communities added for audience discovery. Both `CertificationHarness.run_certification()` and `PostingRulesEngine.check_rules()` check `catalogue_only == True` and immediately refuse any certification or publication attempt.

### Q10: How does the Recommender rank destinations for a given piece of content?
**Answer**: It first filters out demoted, disabled, catalogue-only, and rule-blocked destinations. It then computes a 0–100 fit score combining: (1) vertical audience topic alignment (AI, SaaS, Video, Marketing) using keyword pillar overlap (up to 50 pts), (2) recent certification freshness within 30 days (up to 20 pts), (3) media/text format synergy (up to 15 pts), and (4) frequency cap headroom (up to 15 pts).

### Q11: How does the word-boundary truncation algorithm work in `tailoring.py`?
**Answer**: It slices text to `max_chars - 3`, finds the last whitespace character within that slice, cuts at that word boundary, strips trailing punctuation, and appends an ellipsis (`...`). It guarantees words are never sliced in half (e.g. "artificial" never becomes "artifi...").

### Q12: Why are Mailchimp newsletters restricted to draft status only?
**Answer**: Assessment rule Non-Negotiable 2 strictly forbids posting or emailing real communities. The Mailchimp connector creates campaigns in `status="save"` (draft mode) with `emails_sent: 0`, and raises `DEST_SPEC_VIOLATION` if any attempt is made to trigger live dispatch.

### Q13: What does the `secret_scan.py` script verify?
**Answer**: It scans all repository files, git commits, and docker logs using regex heuristics for high-entropy tokens, API keys (e.g. `ghp_`, `sk_live_`, `Ghost JWT`, `bearer`), and verifies that Authorization headers and credential values are never logged in plaintext.

### Q14: How does the OpenAPI 3.1 specification test ensure schema accuracy?
**Answer**: `tests/integration/test_openapi.py` compares every registered FastAPI path, HTTP method, and schema definition against `openapi.yaml`. If a developer adds an endpoint or modifies parameters without re-exporting `openapi.yaml`, the test fails immediately.

### Q15: If an interviewer asks you to change the frequency cap period from 24 hours to 12 hours during the live session, which file and column do you touch?
**Answer**: You update `frequency_period_hours` on `DestinationModel` in `app/models/destination.py` (defaulting to 12), and the database column `destinations.frequency_period_hours`. In `app/rules/engine.py`, `PostingRulesEngine._check_frequency_cap()` dynamically queries publications within `timedelta(hours=dest.frequency_period_hours)`.
