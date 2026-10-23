"""Structured JSON logging configuration."""

import logging
import json
import sys
from datetime import datetime, timezone


import contextvars

current_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_correlation_id", default=None)
current_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_job_id", default=None)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        cid = getattr(record, "correlation_id", None) or current_correlation_id.get()
        jid = getattr(record, "job_id", None) or current_job_id.get()
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "job_id": jid,
            "correlation_id": cid
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    # Avoid duplicate handlers on reload
    if not logger.handlers:
        logger.addHandler(handler)
    else:
        logger.handlers = [handler]


setup_logging()
logger = logging.getLogger("incubrix")
