"""Tests for Desigo BMS fault notification email parser."""

from datetime import datetime

from app.plant.email_parser import (
    EQUIPMENT_CATEGORIES,
    _classify_severity,
    _detect_equipment_category,
    parse_desigo_email,
)
from app.plant.models import AlarmSeverity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_body(severity_word: str) -> str:
    """Build a realistic 3-line Desigo email body."""
    return f"Place System Notification\n\nSome Equipment Fail Status (Fault) {severity_word}"


FIXED_TS = datetime(2026, 3, 7, 10, 0, 0)


# ---------------------------------------------------------------------------
# 1. Real Desigo email — cleared fan alarm
# ---------------------------------------------------------------------------


class TestParseRealDesigoEmail:
    def test_parse_real_desigo_email(self):
        subject = "Roof Atrium Extract Fan Fail Status (Normal)"
        body = "Place System Notification\n\nRoof Atrium Extract Fan Fail Status (Normal) High"
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS)

        assert alarm.equipment_description == "Roof Atrium Extract Fan"
        assert alarm.alarm_type == "Fail Status"
        assert alarm.status == "Normal"
        assert alarm.severity == AlarmSeverity.CLEARED
        assert alarm.equipment_category == "hvac"
        assert alarm.cleared is True
        assert alarm.cleared_at == FIXED_TS


# ---------------------------------------------------------------------------
# 2. Fire damper — very_critical
# ---------------------------------------------------------------------------


class TestParseFireDamperEmail:
    def test_parse_fire_damper_email(self):
        subject = "HVAC Plant Room FD 5 Fail Status (Fault)"
        body = "Place System Notification\n\nHVAC Plant Room FD 5 Fail Status (Fault) High"
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS)

        assert alarm.severity == AlarmSeverity.VERY_CRITICAL
        assert alarm.equipment_category == "fire_safety"
        assert alarm.cleared is False


# ---------------------------------------------------------------------------
# 3. Generator — critical
# ---------------------------------------------------------------------------


class TestParseGeneratorAlarm:
    def test_parse_generator_alarm(self):
        subject = "Generator 1 Start Fail (Fault)"
        body = "Place System Notification\n\nGenerator 1 Start Fail (Fault) High"
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS)

        assert alarm.severity == AlarmSeverity.CRITICAL
        assert alarm.equipment_category == "power"


# ---------------------------------------------------------------------------
# 4. Low severity → non_critical
# ---------------------------------------------------------------------------


class TestParseLowSeverity:
    def test_parse_low_severity(self):
        subject = "AHU 3 Supply Fan Status (Fault)"
        body = _make_body("Low")
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS)

        assert alarm.severity == AlarmSeverity.NON_CRITICAL


# ---------------------------------------------------------------------------
# 5. Normal severity with Normal status → cleared
# ---------------------------------------------------------------------------


class TestParseNormalSeverity:
    def test_parse_normal_severity(self):
        subject = "FCU 12 Fault Status (Normal)"
        body = _make_body("Normal")
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS)

        assert alarm.severity == AlarmSeverity.CLEARED
        assert alarm.cleared is True


# ---------------------------------------------------------------------------
# 6. No parentheses → status "Unknown"
# ---------------------------------------------------------------------------


class TestParseNoParentheses:
    def test_parse_no_parentheses(self):
        subject = "Some Equipment Alert Without Parens"
        body = _make_body("High")
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS)

        assert alarm.status == "Unknown"
        assert alarm.equipment_description == subject


# ---------------------------------------------------------------------------
# 7. Empty body → critical as safe default
# ---------------------------------------------------------------------------


class TestParseEmptyBody:
    def test_parse_empty_body(self):
        subject = "Generator 2 Start Fail (Fault)"
        alarm = parse_desigo_email(subject, "", received_at=FIXED_TS)

        assert alarm.severity == AlarmSeverity.CRITICAL

    def test_parse_whitespace_only_body(self):
        subject = "AHU 1 Trip (Fault)"
        alarm = parse_desigo_email(subject, "   \n  \n  ", received_at=FIXED_TS)

        assert alarm.severity == AlarmSeverity.CRITICAL


# ---------------------------------------------------------------------------
# 8. AHU with Reheat and OHS → hvac
# ---------------------------------------------------------------------------


class TestEquipmentCategoryAhu:
    def test_equipment_category_ahu(self):
        subject = "AHU 1 Reheat OHS Trip (Fault)"
        body = _make_body("High")
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS)

        assert alarm.equipment_category == "hvac"


# ---------------------------------------------------------------------------
# 9. UPS Room Temperature → category checks
# ---------------------------------------------------------------------------


class TestEquipmentCategoryUps:
    def test_equipment_category_ups(self):
        subject = "UPS Room Temperature High (Fault)"
        body = _make_body("High")
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS)

        # "UPS" matches power before "Temperature" matches monitoring
        assert alarm.equipment_category == "power"

    def test_equipment_category_temperature_standalone(self):
        subject = "Server Room Temperature High (Fault)"
        body = _make_body("High")
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS)

        assert alarm.equipment_category == "monitoring"


# ---------------------------------------------------------------------------
# 10. Default site_id
# ---------------------------------------------------------------------------


class TestDefaultSiteId:
    def test_default_site_id(self):
        subject = "AHU 1 Trip (Fault)"
        body = _make_body("Low")
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS)

        assert alarm.site_id == "FLN02"

    def test_custom_site_id(self):
        subject = "AHU 1 Trip (Fault)"
        body = _make_body("Low")
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS, site_id="S002")

        assert alarm.site_id == "S002"


# ---------------------------------------------------------------------------
# Extra: internal helpers
# ---------------------------------------------------------------------------


class TestInternalHelpers:
    def test_detect_equipment_category_unknown(self):
        assert _detect_equipment_category("Unknown Device XYZ") == "unknown"

    def test_detect_equipment_category_case_insensitive(self):
        assert _detect_equipment_category("main chiller plant") == "hvac"

    def test_classify_severity_cleared(self):
        result = _classify_severity("Fail Status", "Normal", "High", "hvac")
        assert result == AlarmSeverity.CLEARED

    def test_equipment_categories_dict_not_empty(self):
        assert len(EQUIPMENT_CATEGORIES) >= 10

    def test_alarm_has_uuid(self):
        subject = "AHU 1 Trip (Fault)"
        body = _make_body("High")
        alarm = parse_desigo_email(subject, body, received_at=FIXED_TS)
        # UUID format: 8-4-4-4-12 hex
        assert len(alarm.id) == 36
        assert alarm.id.count("-") == 4
