"""Single-container Demo Runner for IncuBrix Distribution Network.

Runs both:
1. Simulated platform mock server (127.0.0.1:8001)
2. Main IncuBrix Distribution Network API (0.0.0.0:PORT)
Enables standalone live demonstration with zero external dependencies.
"""

import os
import sys
import time
import subprocess
import uvicorn
from multiprocessing import Process


def run_mock_server():
    """Runs simulated platform mock server."""
    uvicorn.run(
        "mock_platforms.server:mock_app",
        host="127.0.0.1",
        port=8001,
        log_level="warning"
    )


def run_main_app():
    """Runs main IncuBrix FastAPI application."""
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    os.environ["SIMULATION_MODE"] = "true"
    os.environ["MOCK_SERVER_URL"] = "http://127.0.0.1:8001"
    os.environ["DISCOURSE_BASE_URL"] = "http://127.0.0.1:8001/discourse"
    os.environ["LEMMY_BASE_URL"] = "http://127.0.0.1:8001/lemmy"
    os.environ["DEVTO_BASE_URL"] = "http://127.0.0.1:8001/devto"
    os.environ["GHOST_BASE_URL"] = "http://127.0.0.1:8001/ghost"
    os.environ["WEBHOOK_TEST_URL"] = "http://127.0.0.1:8001/webhook"

    print("=== Starting IncuBrix Standalone Demo Container ===")
    mock_process = Process(target=run_mock_server, daemon=True)
    mock_process.start()

    time.sleep(1.0)
    print("Mock platforms running on http://127.0.0.1:8001")
    print(f"Launching IncuBrix API on port {os.environ.get('PORT', 8000)}...")

    try:
        run_main_app()
    finally:
        mock_process.terminate()
