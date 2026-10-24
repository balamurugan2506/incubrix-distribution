"""Root pytest configuration and session fixtures.
Ensures the test suite is 100% self-contained with no external setup required (Integration Standard 1).
"""

import threading
import time
import socket
import pytest
import uvicorn
import httpx
from mock_platforms.server import mock_app


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


@pytest.fixture(scope="session", autouse=True)
def run_mock_platform_server():
    """
    Session fixture that ensures the mock platform server is running on port 8001.
    If an external server (e.g. docker-compose) is already listening, it uses that;
    otherwise, it launches an in-process Uvicorn server in a daemon thread.
    """
    # Check if port 8001 is already answering health checks
    try:
        resp = httpx.get("http://localhost:8001/health", timeout=0.5)
        if resp.status_code == 200:
            yield
            return
    except Exception:
        pass

    config = uvicorn.Config(
        app=mock_app,
        host="127.0.0.1",
        port=8001,
        log_level="error"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to become responsive
    start = time.time()
    server_ready = False
    while time.time() - start < 10.0:
        try:
            resp = httpx.get("http://localhost:8001/health", timeout=0.5)
            if resp.status_code == 200:
                server_ready = True
                break
        except Exception:
            time.sleep(0.1)

    if not server_ready:
        raise RuntimeError("Failed to start in-process mock platforms server on port 8001 within 10s")

    yield

    server.should_exit = True
    thread.join(timeout=2.0)
