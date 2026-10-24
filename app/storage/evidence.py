"""Evidence storage module supporting local disk and MinIO S3-compatible backend (Integration Standard 7)."""

import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from app.config import settings
from app.logging_conf import logger

try:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


class EvidenceStorage:
    def __init__(self, local_dir: Optional[str] = None):
        self.local_dir = local_dir or settings.STORAGE_LOCAL_DIR
        os.makedirs(self.local_dir, exist_ok=True)
        self.evidence_dir = os.path.join("outputs", "evidence")
        os.makedirs(self.evidence_dir, exist_ok=True)
        self.assist_packs_dir = os.path.join(self.local_dir, "assist_packs")
        os.makedirs(self.assist_packs_dir, exist_ok=True)
        self.import_reports_dir = os.path.join(self.local_dir, "import_reports")
        os.makedirs(self.import_reports_dir, exist_ok=True)

        self.backend = settings.STORAGE_BACKEND.lower()
        self.bucket = settings.MINIO_BUCKET
        self.s3_client = None
        self._s3_available = False

        if self.backend == "s3" and BOTO3_AVAILABLE:
            self._init_s3()

    def _init_s3(self, endpoint_url: Optional[str] = None):
        """Initialize S3/MinIO client and ensure destination bucket exists."""
        try:
            if not endpoint_url:
                endpoint = settings.MINIO_ENDPOINT.strip()
                if not endpoint.startswith("http://") and not endpoint.startswith("https://"):
                    scheme = "https" if settings.MINIO_SECURE else "http"
                    endpoint_url = f"{scheme}://{endpoint}"
                else:
                    endpoint_url = endpoint

            self.s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=settings.MINIO_ACCESS_KEY,
                aws_secret_access_key=settings.MINIO_SECRET_KEY,
                region_name=settings.MINIO_REGION,
                config=Config(
                    s3={"addressing_style": "path"},
                    signature_version="s3v4",
                    connect_timeout=2,
                    read_timeout=3
                )
            )
            self._ensure_bucket()
            self._s3_available = True
            logger.info(f"S3/MinIO storage backend initialized on bucket '{self.bucket}' at {endpoint_url}")
        except Exception as exc:
            logger.warning(f"Failed to initialize S3 backend ({exc}); falling back to local disk storage.")
            self._s3_available = False

    def _ensure_bucket(self):
        """Check if S3 bucket exists, create if missing."""
        if not self.s3_client:
            return
        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                if settings.MINIO_REGION and settings.MINIO_REGION != "us-east-1":
                    self.s3_client.create_bucket(
                        Bucket=self.bucket,
                        CreateBucketConfiguration={"LocationConstraint": settings.MINIO_REGION}
                    )
                else:
                    self.s3_client.create_bucket(Bucket=self.bucket)
                logger.info(f"Created S3 bucket '{self.bucket}'")
            except Exception as create_exc:
                logger.warning(f"Could not create S3 bucket '{self.bucket}': {create_exc}")

    def is_s3_active(self) -> bool:
        """Check if S3 backend is configured and currently reachable."""
        return self.backend == "s3" and self._s3_available and self.s3_client is not None

    def get_presigned_url(self, key: str, expires_in: Optional[int] = None) -> Optional[str]:
        """Generate a presigned GET download URL for an S3 object."""
        if not self.is_s3_active():
            return None
        try:
            expires = expires_in or settings.S3_PRESIGNED_EXPIRY_SECONDS
            url = self.s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires
            )
            return url
        except Exception as exc:
            logger.warning(f"Failed to generate presigned URL for key '{key}': {exc}")
            return None

    def save_evidence(self, identifier: str, data: Dict[str, Any], txt_summary: Optional[str] = None) -> str:
        """Save certification or audit evidence as JSON and TXT, mirroring to S3 if enabled."""
        filename = f"{identifier}.json"
        filepath = os.path.join(self.evidence_dir, filename)

        s3_key_json = f"evidence/{filename}"
        s3_key_txt = f"evidence/{identifier}.txt"

        download_url = f"/api/v1/evidence/{identifier}"
        presigned_url = self.get_presigned_url(s3_key_json) if self.is_s3_active() else None

        envelope = {
            "evidence_id": identifier,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "storage_backend": "s3" if self.is_s3_active() else "local",
            "download_url": download_url,
            "presigned_download_url": presigned_url,
            "s3_uri": f"s3://{self.bucket}/{s3_key_json}" if self.is_s3_active() else None,
            "payload": data
        }

        # Write local disk files
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)

        txt_filename = f"{identifier}.txt"
        txt_filepath = os.path.join(self.evidence_dir, txt_filename)
        if not txt_summary:
            lines = [
                f"INCUBRIX EVIDENCE AUDIT REPORT: {identifier}",
                f"Timestamp: {envelope['created_at']}",
                f"Backend: {'s3' if self.is_s3_active() else 'local'}",
                f"S3 URI: {envelope.get('s3_uri') or 'N/A'}",
                f"Download URL: {download_url}",
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

        # Upload to S3 if active
        if self.is_s3_active():
            try:
                json_bytes = json.dumps(envelope, indent=2).encode("utf-8")
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key_json,
                    Body=json_bytes,
                    ContentType="application/json"
                )
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key_txt,
                    Body=txt_summary.encode("utf-8"),
                    ContentType="text/plain"
                )
                logger.info(f"Uploaded evidence artifacts to s3://{self.bucket}/{s3_key_json}")
            except Exception as exc:
                logger.warning(f"Failed to upload evidence to S3: {exc}; local copy preserved.")

        logger.info(f"Saved evidence documents to {filepath} and {txt_filepath}")
        return filepath

    def save_assist_pack(self, identifier: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save assisted publishing pack document to local disk and S3."""
        filename = f"{identifier}.json"
        filepath = os.path.join(self.assist_packs_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        s3_key = f"assist_packs/{filename}"
        presigned_url = None

        if self.is_s3_active():
            try:
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=json.dumps(data, indent=2).encode("utf-8"),
                    ContentType="application/json"
                )
                presigned_url = self.get_presigned_url(s3_key)
            except Exception as exc:
                logger.warning(f"Failed to upload assist pack to S3: {exc}")

        download_url = presigned_url or f"/api/v1/evidence/{identifier}?category=assist_packs"
        return {
            "identifier": identifier,
            "path": filepath,
            "s3_uri": f"s3://{self.bucket}/{s3_key}" if self.is_s3_active() else None,
            "download_url": download_url,
            "presigned_url": presigned_url
        }

    def save_import_report(self, identifier: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save destination catalogue CSV import summary report to local disk and S3."""
        filename = f"{identifier}.json"
        filepath = os.path.join(self.import_reports_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        s3_key = f"import_reports/{filename}"
        presigned_url = None

        if self.is_s3_active():
            try:
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=json.dumps(data, indent=2).encode("utf-8"),
                    ContentType="application/json"
                )
                presigned_url = self.get_presigned_url(s3_key)
            except Exception as exc:
                logger.warning(f"Failed to upload import report to S3: {exc}")

        download_url = presigned_url or f"/api/v1/evidence/{identifier}?category=import_reports"
        return {
            "identifier": identifier,
            "path": filepath,
            "s3_uri": f"s3://{self.bucket}/{s3_key}" if self.is_s3_active() else None,
            "download_url": download_url,
            "presigned_url": presigned_url
        }

    def get_evidence(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored evidence document from S3 or local disk."""
        filename = f"{identifier}.json"

        # Try S3 if active
        if self.is_s3_active():
            for prefix in ("evidence", "assist_packs", "import_reports"):
                s3_key = f"{prefix}/{filename}"
                try:
                    resp = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
                    content = resp["Body"].read().decode("utf-8")
                    return json.loads(content)
                except Exception:
                    continue

        # Fallback to local files
        for search_dir in (self.evidence_dir, self.assist_packs_dir, self.import_reports_dir):
            filepath = os.path.join(search_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)

        return None

    def get_evidence_bytes(self, identifier: str, format_type: str = "json") -> Optional[Tuple[bytes, str]]:
        """Retrieve raw bytes and media type for evidence document."""
        clean_id = identifier.replace(".json", "").replace(".txt", "")
        filename = f"{clean_id}.{format_type}"
        media_type = "application/json" if format_type == "json" else "text/plain"

        # Try S3 if active
        if self.is_s3_active():
            for prefix in ("evidence", "assist_packs", "import_reports"):
                s3_key = f"{prefix}/{filename}"
                try:
                    resp = self.s3_client.get_object(Bucket=self.bucket, Key=s3_key)
                    return resp["Body"].read(), media_type
                except Exception:
                    continue

        # Fallback to local disk
        for search_dir in (self.evidence_dir, self.assist_packs_dir, self.import_reports_dir):
            filepath = os.path.join(search_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    return f.read(), media_type

        return None

    def get_evidence_path(self, identifier: str, format_type: str = "json") -> Optional[str]:
        """Return path to evidence file on disk if present."""
        clean_id = identifier.replace(".json", "").replace(".txt", "")
        filename = f"{clean_id}.{format_type}"
        for search_dir in (self.evidence_dir, self.assist_packs_dir, self.import_reports_dir):
            filepath = os.path.join(search_dir, filename)
            if os.path.exists(filepath):
                return filepath
        return None


evidence_storage = EvidenceStorage()
