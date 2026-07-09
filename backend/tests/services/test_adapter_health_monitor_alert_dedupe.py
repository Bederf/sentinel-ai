from app.services.adapter_health_monitor import build_source_dedupe_key


def test_named_bms_point_key_wins_over_transient_bacnet_object():
    first = {
        "notification_class": 18,
        "bacnet_object": "binaryInput,2200",
        "equipment_id": "FCU07.FAULT_STATE",
        "code": "CHANGE_OF_STATE",
        "event_type": "fault",
    }
    second = {
        "notification_class": 18,
        "bacnet_object": "binaryInput,2288",
        "equipment_id": "FCU07.FAULT_STATE",
        "code": "CHANGE_OF_STATE",
        "event_type": "fault",
    }

    assert build_source_dedupe_key(first) == build_source_dedupe_key(second)
    assert build_source_dedupe_key(first) == "point:fcu07.fault_state|code:change_of_state|type:fault"


def test_named_bms_point_can_be_extracted_from_message_text():
    alarm = {
        "notification_class": 18,
        "bacnet_object": "binaryInput,2218",
        "message_text": "CHILLER1.COMP_CURRENT out of range",
        "code": "CHANGE_OF_STATE",
        "event_type": "fault",
    }

    assert build_source_dedupe_key(alarm) == "point:chiller1.comp_current|code:change_of_state|type:fault"


def test_bacnet_object_identity_still_used_when_no_named_point_exists():
    alarm = {
        "notification_class": 10,
        "bacnet_object": "analogInput,2007",
        "equipment_id": "S002-AHU-B1-001",
        "code": "OUT_OF_RANGE",
        "event_type": "fault",
    }

    assert build_source_dedupe_key(alarm) == "nc:10|obj:analogInput,2007"
