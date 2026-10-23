"""Unit tests for YAML connector manifests loading and schema validation."""

from app.connectors.registry import ConnectorRegistry


def test_manifest_loader():
    reg = ConnectorRegistry()
    reg.load_manifests()
    manifests = reg.list_manifests()

    assert len(manifests) >= 6

    keys = {m.key for m in manifests}
    expected_keys = {"discourse", "lemmy", "devto", "ghost", "signed_webhook", "assisted"}
    assert expected_keys.issubset(keys), f"Missing keys: {expected_keys - keys}"

    # Validate detailed structure of devto manifest
    devto_m = reg.get_manifest("devto")
    assert devto_m.tier == "core"
    assert "markdown" in devto_m.content_types
    assert devto_m.capabilities.publish is True
    assert devto_m.format_limits.title_min_chars == 5
    assert devto_m.error_map.get(422) == "PLATFORM_CONTENT_REJECTED"
    assert devto_m.error_map.get(429) == "PLATFORM_RATE_LIMIT"

    # Validate assisted manifest
    assisted_m = reg.get_manifest("assisted")
    assert assisted_m.capabilities.publish is False
    assert assisted_m.capabilities.build_assist_pack is True
