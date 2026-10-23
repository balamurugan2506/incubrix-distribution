"""Structured JSON logging configuration."""

import logging
import json
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "job_id": getattr(record, "job_id", None),
            "correlation_id": getattr(record, "correlation_id", None)
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
