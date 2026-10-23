"""Models package aggregating all database entities."""

from app.database import Base
from app.models.destination import DestinationModel
from app.models.idempotency import IdempotencyRecordModel
from app.models.publication import PublicationRecordModel
from app.models.job import JobRecordModel
from app.models.certification import CertificationRecordModel
from app.models.alert import AlertModel

__all__ = [
    "Base",
    "DestinationModel",
    "IdempotencyRecordModel",
    "PublicationRecordModel",
    "JobRecordModel",
    "CertificationRecordModel",
    "AlertModel",
]
