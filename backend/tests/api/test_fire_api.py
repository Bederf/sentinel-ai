import pytest
from pydantic import ValidationError


def test_trigger_fire_alarm_request_requires_site_id():
    from app.api.fire import TriggerAlarmRequest

    with pytest.raises(ValidationError):
        TriggerAlarmRequest(zone_id="FZ-L1-C", alarm_type="smoke")
