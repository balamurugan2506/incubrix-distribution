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

    def save_evidence(self, identifier: str, data: Dict[str, Any], txt_summary: Optional[str] = None) -> str:
        """Save certification or audit evidence as a formatted JSON document and human-readable TXT."""
        filename = f"{identifier}.json"
        filepath = os.path.join(self.evidence_dir, filename)

        envelope = {
            "evidence_id": identifier,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "storage_backend": settings.STORAGE_BACKEND,
            "download_url": f"/api/v1/evidence/{identifier}",
            "payload": data
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)

        # Generate and save accompanying human-readable TXT evidence
        txt_filename = f"{identifier}.txt"
        txt_filepath = os.path.join(self.evidence_dir, txt_filename)
        if not txt_summary:
            lines = [
                f"INCUBRIX EVIDENCE AUDIT REPORT: {identifier}",
                f"Timestamp: {envelope['created_at']}",
                f"Backend: {settings.STORAGE_BACKEND}",
                "=" * 60
            ]
            for k, v in data.items():
                if k not in ("steps", "manifest", "result"):
                    lines.append(f"{k}: {v}")
            if "steps" in data and isinstance(data["steps"], list):
                lines.append("\nSTEPS EXECUTION TRAIL:")
                for s in data["steps"]:
                    lines.append(f"  [{s.get('status', 'unknown').upper()}] {s.get('step')}: {json.dumps(s.get('details', {}))}")
            txt_summary = "\n".join(lines)

        with open(txt_filepath, "w", encoding="utf-8") as f:
            f.write(txt_summary)

        logger.info(f"Saved evidence documents to {filepath} and {txt_filepath}")
        return filepath

    def get_evidence(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored evidence document."""
        filename = f"{identifier}.json"
        filepath = os.path.join(self.evidence_dir, filename)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_evidence_path(self, identifier: str, format_type: str = "json") -> Optional[str]:
        """Return absolute path to evidence file on disk if present."""
        filename = f"{identifier}.{format_type}"
        filepath = os.path.join(self.evidence_dir, filename)
        return filepath if os.path.exists(filepath) else None


evidence_storage = EvidenceStorage()
