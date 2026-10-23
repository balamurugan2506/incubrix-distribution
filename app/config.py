"""Application configuration powered by Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


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
    SYNC_DATABASE_URL: str = "sqlite:///./incubrix.db"

    # Security & HMAC
    INCUBRIX_WEBHOOK_SECRET: str = "incubrix_dev_secret_key_change_in_prod_32bytes"
    CALLBACK_SIGNATURE_HEADER: str = "X-IncuBrix-Signature"

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

    # Manifests Directory
    MANIFESTS_DIR: str = "connectors/manifests"


settings = Settings()
