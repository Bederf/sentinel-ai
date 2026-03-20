import json
from pathlib import Path


def test_site_002_has_meeting_room_on_each_office_floor():
    path = Path("/opt/bms-intelligence/backend/app/data/buildings/site-002/zones.json")
    data = json.loads(path.read_text())

    meeting_rooms = {
        zone["floor"]: zone["zone_id"] for zone in data["zones"] if zone.get("zone_type") == "meeting_room"
    }

    assert meeting_rooms["L1"] == "Zone-L1-MR1"
    assert meeting_rooms["L2"] == "Zone-L2-MR1"
    assert meeting_rooms["L3"] == "Zone-L3-MR1"


def test_site_002_has_five_open_office_zones_per_office_floor():
    path = Path("/opt/bms-intelligence/backend/app/data/buildings/site-002/zones.json")
    data = json.loads(path.read_text())

    office_zones_by_floor = {}
    for zone in data["zones"]:
        if zone.get("zone_type") != "open_office":
            continue
        office_zones_by_floor.setdefault(zone["floor"], []).append(zone["zone_id"])

    assert sorted(office_zones_by_floor["L1"]) == [
        "Zone-L1-A",
        "Zone-L1-B",
        "Zone-L1-C",
        "Zone-L1-D",
        "Zone-L1-E",
    ]
    assert sorted(office_zones_by_floor["L2"]) == [
        "Zone-L2-A",
        "Zone-L2-B",
        "Zone-L2-C",
        "Zone-L2-D",
        "Zone-L2-E",
    ]
    assert sorted(office_zones_by_floor["L3"]) == [
        "Zone-L3-A",
        "Zone-L3-B",
        "Zone-L3-C",
        "Zone-L3-D",
        "Zone-L3-E",
    ]
