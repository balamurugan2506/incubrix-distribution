"""Integration test verifying Real Catalogue of 150 destinations (Outstanding Level 4).

Verifies:
1. File catalogue/real_destinations_150.csv exists with >= 150 entries.
2. Every entry carries a verbatim rules quote, relevance score, and valid connector key.
3. Every entry has catalogue_only=True.
4. Publishing or certifying against any catalogue_only destination is strictly refused.
"""

import os
import csv
import pytest
from app.database import AsyncSessionLocal, init_db
from app.catalogue.csv_importer import import_destinations_from_csv
from app.models.destination import DestinationModel
from app.certification.harness import CertificationHarness
from app.rules.engine import PostingRulesEngine
from app.schemas.connector import RenditionSchema, ConnectionSchema
from app.rules.errors import ConnectorException
from sqlalchemy import select


@pytest.mark.anyio
async def test_real_catalogue_150_integrity_and_catalogue_only_enforcement():
    """Verify integrity of real catalogue and prove catalogue_only prevents publication and certification."""
    csv_path = "catalogue/real_destinations_150.csv"
    assert os.path.exists(csv_path), "catalogue/real_destinations_150.csv does not exist"

    # 1. Structural Verification of CSV
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) >= 150, f"Expected at least 150 rows, found {len(rows)}"

    for row in rows:
        assert row["name"], "Destination name is missing"
        assert row["url"].startswith("http"), f"Invalid URL for {row['name']}"
        assert row["connector_key"] in (
            "discourse", "lemmy", "devto", "ghost", "assisted", "slack", "mailchimp", "hashnode", "webhook"
        ), f"Unknown connector key {row['connector_key']}"
        assert len(row["rules_quote"]) > 10, f"Missing or trivial rules quote for {row['name']}"
        assert float(row["relevance_score"]) >= 1.0, f"Invalid relevance score for {row['name']}"
        assert row["catalogue_only"].lower() in ("true", "1", "yes"), f"{row['name']} must be marked catalogue_only"

    # 2. Import into Database
    await init_db()
    with open(csv_path, "rb") as f:
        csv_bytes = f.read()

    from sqlalchemy import delete
    async with AsyncSessionLocal() as session:
        await session.execute(delete(DestinationModel))
        await session.commit()
        summary = await import_destinations_from_csv(csv_bytes, session, perform_reachability=False, allow_local=False)
        assert summary.imported_count >= 150, f"Import accepted fewer than 150 rows: {summary.imported_count}"

        # Fetch one of the imported catalogue_only destinations
        stmt = select(DestinationModel).where(DestinationModel.catalogue_only == True).limit(1)  # noqa: E712
        res = await session.execute(stmt)
        cat_dest = res.scalars().first()
        assert cat_dest is not None
        assert cat_dest.catalogue_only is True

    # 3. Prove Certification is strictly refused for catalogue_only destinations
    cert_report = await CertificationHarness.run_certification(destination=cat_dest)
    assert cert_report.passed is False
    assert "catalogue_only" in cert_report.error_message

    # 4. Prove Publishing is strictly refused for catalogue_only destinations
    rules_engine = PostingRulesEngine()
    rendition = RenditionSchema(
        title="Valid Test Title",
        body="Valid test body content with sufficient length."
    )
    with pytest.raises(ConnectorException) as exc_info:
        await rules_engine.check_rules(rendition, cat_dest, session)
    assert "catalogue_only" in exc_info.value.message
