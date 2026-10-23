# IncuBrix Live Demo Deployment Guide

This guide describes how to deploy the standalone IncuBrix Distribution Network live demonstration container to Render, Fly.io, or any Docker host in under 5 minutes.

---

## 1. Architecture of the Standalone Demo

The demo runs as a single, self-contained container configured in `Dockerfile.demo`:
- **Main API Service**: FastAPI service listening on `$PORT` (default 8000).
- **Simulated Platform Mock Server**: In-memory mock platform service listening on `127.0.0.1:8001` providing Discourse, Lemmy, Dev.to, Ghost, Hashnode, Slack, Mailchimp, and Webhook endpoints.
- **Security**: The container runs under an unprivileged non-root user (`incubrix`, UID 1000).
- **Authentication**: Protected by `DEMO_API_TOKEN` environment variable.
- **Rate Limiting**: Protected by sliding-window rate limiting (120 req/min with `429 RATE_LIMITED` and `Retry-After: 10`).
- **Failure Switches**: Evaluators can trigger live simulations (timeouts, 429s, auth expiration) via `/api/v1/demo/failure-switch`.

---

## 2. Deploying to Render (Recommended, Free Tier)

### Step 1: Connect GitHub Repository
1. Log in to [Render.com Dashboard](https://dashboard.render.com).
2. Click **New +** > **Blueprint**.
3. Select your repository (`incubrix-distribution`).
4. Render automatically detects `render.yaml` and sets up the web service.

### Step 2: Configure Environment Variables
Render automatically populates settings from `render.yaml`:
- `PORT`: `8000`
- `SIMULATION_MODE`: `true`
- `APP_ENV`: `production`
- `DEMO_API_TOKEN`: Automatically generated secret string (copy this for your assessment submission form!)
- `DEMO_RATE_LIMIT_PER_MINUTE`: `120`

### Step 3: Deploy & Verify
Click **Apply**. Deployment will complete in 2–3 minutes.
Render provides a public URL: `https://incubrix-distribution-network.onrender.com`.

---

## 3. Deploying to Fly.io (Alternative)

```bash
# Launch app using Dockerfile.demo
fly launch --dockerfile Dockerfile.demo --name incubrix-distribution-demo

# Set required environment variables
fly secrets set \
    SIMULATION_MODE=true \
    APP_ENV=production \
    DEMO_API_TOKEN=your_secure_demo_token_here \
    DEMO_RATE_LIMIT_PER_MINUTE=120

# Deploy
fly deploy
```

---

## 4. Running the Standalone Demo Locally (Docker)

To test the demo container locally before publishing:

```bash
# Build the single demo container
docker build -f Dockerfile.demo -t incubrix-demo:latest .

# Run container with a demo token
docker run -p 8000:8000 \
    -e DEMO_API_TOKEN=demo_secret_token_123 \
    -e SIMULATION_MODE=true \
    incubrix-demo:latest
```

---

## 5. Validating Your Live Deployment

Run the automated verification script against your deployed URL:

```bash
export DEMO_URL="https://your-app-name.onrender.com"
export DEMO_API_TOKEN="your_generated_demo_token"

python scripts/check_live_demo.py
```

The script runs all 6 verification checks:
1. `GET /health` returns 200 OK
2. Request without token returns `401 UNAUTHORIZED`
3. Content publishing returns `201 Created` with post ID
4. Replaying identical `Idempotency-Key` returns cached post with `X-Cache: IDEMPOTENT-HIT`
5. Timeout simulation followed by same-key retry results in **0 duplicate posts**
6. Catalogue export returns active destinations list

---

## 6. Measuring Cold Start Latency for Submission

Render free tier services spin down after 15 minutes of inactivity. Measure cold start latency for your report:

```bash
# Measure cold start time from a sleeping container
curl -w "\nTotal Cold Start Time: %{time_total}s\n" -o /dev/null -s "https://your-app-name.onrender.com/health"
```
Record the number (typically 25–45 seconds on Render free tier, or <1.5 seconds if warm) in your submission form and in `REPORT.md`.
