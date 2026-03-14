from app.utils.ai_provenance import (
    attach_ai_provenance,
    attach_runtime_metadata,
    get_ml_provenance,
    runtime_metadata,
)


def test_attach_runtime_metadata_to_dict():
    payload = {"recommendation": {"title": "Reduce chiller load"}}

    stamped = attach_runtime_metadata(payload)

    assert stamped["app_version"] == runtime_metadata()["app_version"]
    assert stamped["config_checksum"] == runtime_metadata()["config_checksum"]
    assert stamped["recommendation"] == payload["recommendation"]


def test_attach_ai_provenance_to_dict():
    payload = {"result": "ok"}

    stamped = attach_ai_provenance(payload, get_ml_provenance("recommendation-engine-v1"))

    assert stamped["app_version"] == runtime_metadata()["app_version"]
    assert stamped["config_checksum"] == runtime_metadata()["config_checksum"]
    assert stamped["ai_provenance"]["model"] == "recommendation-engine-v1"
    assert stamped["ai_provenance"]["app_version"] == runtime_metadata()["app_version"]


def test_attach_ai_provenance_to_list_of_dicts():
    payload = [{"equipment_id": "EQ-1"}, {"equipment_id": "EQ-2"}]

    stamped = attach_ai_provenance(payload, get_ml_provenance("failure-classifier-v1"))

    assert len(stamped) == 2
    assert stamped[0]["ai_provenance"]["model"] == "failure-classifier-v1"
    assert stamped[0]["app_version"] == runtime_metadata()["app_version"]
    assert stamped[1]["config_checksum"] == runtime_metadata()["config_checksum"]
