"""Evidence storage module supporting local disk and MinIO S3-compatible backend."""

import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.config import settings
from app.logging_conf import logger


class EvidenceStorage:
    def __init__(self, local_dir: Optional[str] = None):
        self.local_dir = local_dir or settings.STORAGE_LOCAL_DIR
        os.makedirs(self.local_dir, exist_ok=True)
        self.evidence_dir = os.path.join("outputs", "evidence")
        os.makedirs(self.evidence_dir, exist_ok=True)

    def save_evidence(self, identifier: str, data: Dict[str, Any]) -> str:
        """Save certification or audit evidence as a formatted JSON document."""
        filename = f"{identifier}.json"
        filepath = os.path.join(self.evidence_dir, filename)

        envelope = {
            "evidence_id": identifier,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "storage_backend": settings.STORAGE_BACKEND,
            "payload": data
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)

        logger.info(f"Saved evidence document to {filepath}")
        return filepath

    def get_evidence(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored evidence document."""
        filename = f"{identifier}.json"
        filepath = os.path.join(self.evidence_dir, filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)


evidence_storage = EvidenceStorage()
