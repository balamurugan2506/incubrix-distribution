import os
import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from typing import Optional, Dict, Any


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core App
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    SIMULATION_MODE: bool = True

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./incubrix.db"
    SYNC_DATABASE_URL: Optional[str] = None

    @model_validator(mode="after")
    def sync_database_urls(self):
        if not self.SYNC_DATABASE_URL:
            if "sqlite+aiosqlite" in self.DATABASE_URL:
                self.SYNC_DATABASE_URL = self.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite")
            elif "postgresql+asyncpg" in self.DATABASE_URL:
                self.SYNC_DATABASE_URL = self.DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
            else:
                self.SYNC_DATABASE_URL = self.DATABASE_URL
        return self

    # Security & HMAC
    INCUBRIX_WEBHOOK_SECRET: str = "incubrix_dev_secret_key_change_in_prod_32bytes"
    CALLBACK_SIGNATURE_HEADER: str = "X-IncuBrix-Signature"
    DEMO_API_TOKEN: Optional[str] = None
    DEMO_RATE_LIMIT_PER_MINUTE: int = 120
    RULES_EXTRACTOR: str = "keyword"


    # Platform Mock URLs
    MOCK_SERVER_URL: str = "http://localhost:8001"
    DISCOURSE_BASE_URL: str = "http://localhost:8001/discourse"
    LEMMY_BASE_URL: str = "http://localhost:8001/lemmy"
    DEVTO_BASE_URL: str = "http://localhost:8001/devto"
    GHOST_BASE_URL: str = "http://localhost:8001/ghost"
    WEBHOOK_TEST_URL: str = "http://localhost:8001/webhook"

    # Default Mock Credentials
    DISCOURSE_API_KEY: str = "test_discourse_api_key"
    DISCOURSE_API_USERNAME: str = "incubrix_bot"
    LEMMY_AUTH_TOKEN: str = "jwt_test_lemmy_token"
    DEVTO_API_KEY: str = "test_devto_api_key"
    GHOST_ADMIN_API_KEY: str = "64f1a2b3c4d5e6f7a8b9c0d1:e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1"

    # Storage
    STORAGE_BACKEND: str = "local"
    STORAGE_LOCAL_DIR: str = "./outputs/storage"
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "incubrix-evidence"
    MINIO_REGION: str = "us-east-1"
    MINIO_SECURE: bool = False
    S3_PRESIGNED_EXPIRY_SECONDS: int = 3600

    # Manifests Directory
    MANIFESTS_DIR: str = "connectors/manifests"

    # Shared Credentials File (written by seed step, dynamic re-read)
    SHARED_CREDENTIALS_FILE: str = "./outputs/shared_credentials.json"

    def get_shared_credentials(self) -> dict:
        """Dynamically load credentials from SHARED_CREDENTIALS_FILE if present or changed."""
        filepath = self.SHARED_CREDENTIALS_FILE
        if not os.path.exists(filepath):
            return getattr(self, "_cached_shared_creds", {})

        try:
            mtime = os.path.getmtime(filepath)
            cached_mtime = getattr(self, "_cached_creds_mtime", 0.0)
            if mtime > cached_mtime:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    setattr(self, "_cached_shared_creds", data)
                    setattr(self, "_cached_creds_mtime", mtime)
        except Exception:
            pass
        return getattr(self, "_cached_shared_creds", {})

    def get_lemmy_token(self) -> str:
        creds = self.get_shared_credentials()
        return creds.get("lemmy_auth_token") or self.LEMMY_AUTH_TOKEN

    def get_lemmy_base_url(self) -> str:
        creds = self.get_shared_credentials()
        return creds.get("lemmy_base_url") or self.LEMMY_BASE_URL

    def get_lemmy_community_id(self) -> int:
        creds = self.get_shared_credentials()
        return creds.get("lemmy_community_id") or 1

    def get_ghost_api_key(self) -> str:
        creds = self.get_shared_credentials()
        return creds.get("ghost_admin_api_key") or self.GHOST_ADMIN_API_KEY

    def get_ghost_base_url(self) -> str:
        creds = self.get_shared_credentials()
        return creds.get("ghost_base_url") or self.GHOST_BASE_URL


settings = Settings()
