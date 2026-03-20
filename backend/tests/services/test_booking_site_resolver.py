from app.services.block_booking_detector import site_resolver
from app.services.block_booking_detector.site_resolver import normalize_site_id, resolve_site_id_for_room


def test_normalize_site_id_supports_short_code():
    assert normalize_site_id("S002") == "site-002"


def test_resolve_site_id_for_site_002_meeting_room_name():
    assert resolve_site_id_for_room("S002-L1-MR1") == "site-002"


def test_resolve_site_id_for_site_002_friendly_alias():
    assert resolve_site_id_for_room("Site 002 Level 2 Meeting Room 1") == "site-002"


def test_resolve_site_id_for_fairlands_registry_room():
    class _FakeClient:
        def table(self, _name):
            return self

        def select(self, *_args, **_kwargs):
            return self

        def execute(self):
            return type(
                "Resp",
                (),
                {"data": [{"site_id": "S001", "room_id": "FA2-1Q1-MR-01", "friendly_name": None}]},
            )()

    site_resolver._load_room_aliases.cache_clear()
    site_resolver.get_supabase_client = lambda: _FakeClient()
    assert resolve_site_id_for_room("FA2-1Q1-MR-01") == "site-001"
    site_resolver._load_room_aliases.cache_clear()
