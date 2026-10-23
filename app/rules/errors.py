"""Standardized shared error codes and structured error exceptions."""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    DEST_SPEC_VIOLATION = "DEST_SPEC_VIOLATION"
    DEST_RULE_FREQUENCY_CAP = "DEST_RULE_FREQUENCY_CAP"
    CONNECTION_AUTH_EXPIRED = "CONNECTION_AUTH_EXPIRED"
    PLATFORM_RATE_LIMIT = "PLATFORM_RATE_LIMIT"
    PLATFORM_QUOTA_EXHAUSTED = "PLATFORM_QUOTA_EXHAUSTED"
    PLATFORM_CONTENT_REJECTED = "PLATFORM_CONTENT_REJECTED"
    PLATFORM_UNAVAILABLE = "PLATFORM_UNAVAILABLE"
    CONNECTOR_DISABLED = "CONNECTOR_DISABLED"
    UNAUTHORIZED = "UNAUTHORIZED"
    RATE_LIMITED = "RATE_LIMITED"


class StructuredError(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


class ConnectorException(Exception):
    """Exception raised by connectors adhering to the IncuBrix error taxonomy."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 400
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
        self.status_code = status_code

    def to_dict(self) -> Dict[str, Any]:
        err_envelope = {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details
        }
        return {
            "error": err_envelope,
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details
        }
