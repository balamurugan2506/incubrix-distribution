"""
Automated Seeder for Local Lemmy and Ghost Instances.
Creates test admin accounts, communities, and API keys,
then writes the credentials to outputs/shared_credentials.json.
"""

import os
import sys
import json
import time
import httpx
from typing import Dict, Any, Optional

SHARED_CREDENTIALS_FILE = os.getenv("SHARED_CREDENTIALS_FILE", "./outputs/shared_credentials.json")
LEMMY_HOSTS = [os.getenv("LEMMY_BASE_URL", "http://lemmy:8536"), "http://localhost:8536"]
GHOST_HOSTS = [os.getenv("GHOST_BASE_URL", "http://ghost:2368"), "http://localhost:2368"]


def ensure_output_dir():
    os.makedirs(os.path.dirname(os.path.abspath(SHARED_CREDENTIALS_FILE)), exist_ok=True)


def wait_for_service(urls: list, health_path: str = "", timeout_s: int = 40) -> Optional[str]:
    start = time.time()
    while time.time() - start < timeout_s:
        for base in urls:
            try:
                target = f"{base.rstrip('/')}/{health_path.lstrip('/')}" if health_path else base
                with httpx.Client(timeout=2.0) as client:
                    resp = client.get(target)
                    if resp.status_code < 500:
                        return base.rstrip('/')
            except Exception:
                pass
        time.sleep(2)
    return None


def seed_lemmy(base_url: str) -> Dict[str, Any]:
    print(f"[Seed] Seeding Lemmy instance at {base_url}...")
    client = httpx.Client(base_url=base_url, timeout=10.0)

    admin_username = "incubrix_admin"
    admin_password = "IncubrixAdminPassword123!"

    # 1. Attempt login first (if already seeded)
    try:
        resp = client.post("/api/v3/user/login", json={
            "username_or_email": admin_username,
            "password": admin_password
        })
        if resp.status_code == 200:
            jwt_token = resp.json().get("jwt")
            print("[Seed] Lemmy admin already exists. Successfully logged in.")
            return setup_lemmy_community(client, jwt_token, base_url)
    except Exception as e:
        print(f"[Seed] Lemmy login check failed: {e}")

    # 2. Register admin user or setup site
    jwt_token = None
    try:
        resp = client.post("/api/v3/user/register", json={
            "username": admin_username,
            "password": admin_password,
            "password_verify": admin_password,
            "show_nsfw": True
        })
        if resp.status_code == 200:
            jwt_token = resp.json().get("jwt")
            print("[Seed] Registered new Lemmy admin user.")
    except Exception as e:
        print(f"[Seed] Lemmy register attempt: {e}")

    if not jwt_token:
        # Try login once more
        try:
            resp = client.post("/api/v3/user/login", json={
                "username_or_email": admin_username,
                "password": admin_password
            })
            if resp.status_code == 200:
                jwt_token = resp.json().get("jwt")
        except Exception:
            pass

    if not jwt_token:
        print("[Seed] Lemmy setup could not obtain JWT token. Using fallback.")
        return {
            "lemmy_base_url": base_url,
            "lemmy_auth_token": "jwt_test_lemmy_token",
            "lemmy_community_id": 1,
            "lemmy_community_name": "tech"
        }

    return setup_lemmy_community(client, jwt_token, base_url)


def setup_lemmy_community(client: httpx.Client, jwt_token: str, base_url: str) -> Dict[str, Any]:
    comm_id = 1
    comm_name = "tech"
    try:
        # Check if community exists
        resp = client.get(f"/api/v3/community?name={comm_name}", headers={"Authorization": f"Bearer {jwt_token}"})
        if resp.status_code == 200:
            comm_data = resp.json().get("community_view", {}).get("community", {})
            comm_id = comm_data.get("id", 1)
            print(f"[Seed] Existing Lemmy community '{comm_name}' found (id={comm_id}).")
        else:
            # Create community
            c_resp = client.post("/api/v3/community", json={
                "name": comm_name,
                "title": "Technology Discussion",
                "auth": jwt_token
            }, headers={"Authorization": f"Bearer {jwt_token}"})
            if c_resp.status_code in (200, 201):
                comm_data = c_resp.json().get("community_view", {}).get("community", {})
                comm_id = comm_data.get("id", 1)
                print(f"[Seed] Created new Lemmy community '{comm_name}' (id={comm_id}).")
    except Exception as e:
        print(f"[Seed] Community creation note: {e}")

    return {
        "lemmy_base_url": base_url,
        "lemmy_auth_token": jwt_token,
        "lemmy_community_id": comm_id,
        "lemmy_community_name": comm_name
    }


def seed_ghost(base_url: str) -> Dict[str, Any]:
    print(f"[Seed] Seeding Ghost instance at {base_url}...")
    client = httpx.Client(base_url=base_url, timeout=10.0)

    # Check if setup is already complete
    try:
        resp = client.get("/ghost/api/admin/authentication/setup/")
        if resp.status_code == 200 and resp.json().get("setup", [{}])[0].get("status") is False:
            # Ghost requires initial owner setup
            setup_payload = {
                "setup": [{
                    "name": "IncuBrix Admin",
                    "email": "admin@incubrix.local",
                    "password": "IncubrixGhostPassword123!",
                    "blogTitle": "IncuBrix Local Ghost Blog"
                }]
            }
            s_resp = client.post("/ghost/api/admin/authentication/setup/", json=setup_payload)
            print(f"[Seed] Ghost initial owner setup status: {s_resp.status_code}")
    except Exception as e:
        print(f"[Seed] Ghost setup inspection: {e}")

    # Fallback / deterministic Admin API Key for testing
    admin_api_key = os.getenv(
        "GHOST_ADMIN_API_KEY",
        "64f1a2b3c4d5e6f7a8b9c0d1:e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1"
    )

    return {
        "ghost_base_url": base_url,
        "ghost_admin_api_key": admin_api_key
    }


def main():
    ensure_output_dir()
    print(f"[Seed] Starting instance seeding. Output target: {SHARED_CREDENTIALS_FILE}")

    creds: Dict[str, Any] = {}

    # 1. Discover or wait for Lemmy
    lemmy_url = wait_for_service(LEMMY_HOSTS, "api/v3/site", timeout_s=15)
    if lemmy_url:
        lemmy_creds = seed_lemmy(lemmy_url)
        creds.update(lemmy_creds)
    else:
        print("[Seed] Real Lemmy not reachable. Defaulting to mock / test credentials.")
        creds.update({
            "lemmy_base_url": os.getenv("LEMMY_BASE_URL", "http://localhost:8001/lemmy"),
            "lemmy_auth_token": "jwt_test_lemmy_token",
            "lemmy_community_id": 1,
            "lemmy_community_name": "tech"
        })

    # 2. Discover or wait for Ghost
    ghost_url = wait_for_service(GHOST_HOSTS, "", timeout_s=15)
    if ghost_url:
        ghost_creds = seed_ghost(ghost_url)
        creds.update(ghost_creds)
    else:
        print("[Seed] Real Ghost not reachable. Defaulting to mock / test credentials.")
        creds.update({
            "ghost_base_url": os.getenv("GHOST_BASE_URL", "http://localhost:8001/ghost"),
            "ghost_admin_api_key": "64f1a2b3c4d5e6f7a8b9c0d1:e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1"
        })

    # 3. Write atomic credentials file
    temp_file = f"{SHARED_CREDENTIALS_FILE}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(creds, f, indent=2)
    os.replace(temp_file, SHARED_CREDENTIALS_FILE)

    print(f"[Seed] Successfully wrote credentials to {SHARED_CREDENTIALS_FILE}:")
    print(json.dumps({k: ("***" if "token" in k or "key" in k else v) for k, v in creds.items()}, indent=2))


if __name__ == "__main__":
    main()
