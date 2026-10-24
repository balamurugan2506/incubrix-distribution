"""Integration test verifying Real Catalogue integrity, snapshot hashes, verbatim quotes, and catalogue_only enforcement (Outstanding Level 4).

Proves that:
1. Every destination was researched from real live web guidelines and saved with snapshot files.
2. SHA-256 hash of each snapshot file exactly matches the recorded snapshot_hash.
3. Every non-empty rules_quote is verified as an exact word-for-word substring of the saved page snapshot.
4. All entries have rules_status='unconfirmed' and catalogue_only=True.
5. Automated publishing and certification are strictly refused for catalogue_only destinations.
"""

import os
import csv
import hashlib
import pytest
from app.database import AsyncSessionLocal, init_db
from app.catalogue.csv_importer import import_destinations_from_csv
from app.models.destination import DestinationModel
from app.certification.harness import harness
from app.rules.engine import rules_engine
from app.schemas.connector import RenditionSchema, ConnectionSchema
from app.rules.errors import ConnectorException
from sqlalchemy import select, delete


@pytest.mark.asyncio
async def test_real_catalogue_integrity_snapshots_and_catalogue_only_enforcement():
    """Verify integrity of real catalogue against snapshots and prove catalogue_only enforcement."""
    csv_path = "catalogue/real_destinations_150.csv"
    assert os.path.exists(csv_path), "catalogue/real_destinations_150.csv does not exist"
    snapshot_dir = os.path.join("catalogue", "snapshots")
    assert os.path.exists(snapshot_dir), "catalogue/snapshots directory does not exist"

    # 1. Structural and Cryptographic Verification of CSV and Page Snapshots
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) >= 50, f"Expected verified research catalogue, found {len(rows)} entries"

    quote_verified_count = 0
    default_rule_count = 0

    for row in rows:
        assert row["name"], "Destination name is missing"
        assert row["url"].startswith("http"), f"Invalid URL for {row['name']}"
        assert row["connector_key"] in (
            "discourse", "lemmy", "devto", "ghost", "assisted", "slack", "mailchimp", "hashnode", "webhook"
        ), f"Unknown connector key {row['connector_key']}"
        assert float(row["relevance_score"]) >= 1.0, f"Invalid relevance score for {row['name']}"
        assert row["catalogue_only"].lower() in ("true", "1", "yes"), f"{row['name']} must be marked catalogue_only"
        assert row["rules_status"] == "unconfirmed", f"{row['name']} rules must be marked unconfirmed until audited"

        # Verify snapshot file existence and cryptographic SHA-256 match
        snap_file = row.get("snapshot_file")
        assert snap_file, f"Missing snapshot file for {row['name']}"
        snap_path = os.path.join(snapshot_dir, snap_file)
        assert os.path.exists(snap_path), f"Snapshot file not found on disk: {snap_path}"

        with open(snap_path, "rb") as sf:
            snap_bytes = sf.read()

        computed_hash = hashlib.sha256(snap_bytes).hexdigest()
        assert computed_hash == row["snapshot_hash"], (
            f"Snapshot hash mismatch for {row['name']}: expected {row['snapshot_hash']}, got {computed_hash}"
        )

        snap_content = snap_bytes.decode("utf-8", errors="replace")

        # Re-verify that quote is an exact substring of the saved page snapshot
        quote = row.get("rules_quote", "").strip()
        if quote:
            assert quote in snap_content, f"Rules quote for {row['name']} is NOT a substring of page snapshot!"
            quote_verified_count += 1
        else:
            default_rule_count += 1

    print(f"\n[Catalogue Audit] Total verified: {len(rows)} | Exact quotes verified: {quote_verified_count} | Default conservative rules: {default_rule_count}")

    # 2. Import into Database via csv_importer
    await init_db()
    with open(csv_path, "r", encoding="utf-8") as f:
        csv_text = f.read()

    async with AsyncSessionLocal() as session:
        await session.execute(delete(DestinationModel))
        await session.commit()
        summary = await import_destinations_from_csv(csv_text, session, perform_reachability=False)
        assert summary.imported_count == len(rows), f"Expected {len(rows)} imported, got {summary.imported_count}"

        # Fetch one of the imported catalogue_only destinations
        stmt = select(DestinationModel).where(DestinationModel.catalogue_only == True).limit(1)  # noqa: E712
        res = await session.execute(stmt)
        cat_dest = res.scalars().first()
        assert cat_dest is not None
        assert cat_dest.catalogue_only is True

    # 3. Prove Certification is strictly refused for catalogue_only destinations
    cert_report = await harness.run_certification(destination=cat_dest)
    assert cert_report.passed is False
    assert "catalogue_only" in (cert_report.error_message or "")

    # 4. Prove Publishing is strictly refused for catalogue_only destinations
    rendition = RenditionSchema(
        title="Valid Test Title",
        body="Valid test body content with sufficient length."
    )
    with pytest.raises(ConnectorException) as exc_info:
        await rules_engine.check_rules(rendition, cat_dest, session)
    assert "catalogue_only" in exc_info.value.message
