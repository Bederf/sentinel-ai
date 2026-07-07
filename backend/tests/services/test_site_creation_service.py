import json
from pathlib import Path

from app.services.site_creation_service import SiteCreationService


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, table_name: str, calls: list[tuple[str, object]]):
        self._table_name = table_name
        self._calls = calls
        self._payload = None

    def insert(self, payload):
        self._payload = payload
        self._calls.append((f"{self._table_name}.insert", payload))
        return self

    def upsert(self, payload, **_kwargs):
        self._payload = payload
        self._calls.append((f"{self._table_name}.upsert", payload))
        return self

    def execute(self):
        if self._table_name == "sites" and self._payload:
            return _Result([{**self._payload, "id": "site-row-id"}])
        return _Result([])


class _Supabase:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def table(self, table_name: str):
        return _Query(table_name, self.calls)


def _write_policy_template(policy_dir: Path) -> None:
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "site-002-mode-policy.json").write_text(
        json.dumps(
            {
                "site_id": "site-002",
                "version": "test",
                "dry_run": True,
                "default_stage": "commissioning",
                "stage_order": ["commissioning", "shadow_live", "advisory", "supervised", "automatic"],
                "stages": {
                    "commissioning": {
                        "promotion": {
                            "entry_thresholds": {
                                "truth_check_required": False,
                            },
                        },
                    },
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_create_site_seeds_mode_policy_files(tmp_path):
    policy_dir = tmp_path / "policies"
    _write_policy_template(policy_dir)

    service = SiteCreationService(supabase_client=_Supabase(), policy_dir=policy_dir)

    created = service.create_site(
        site_name="Gateway Hospital",
        building_type="hospital",
        location="Umhlanga",
        site_code="site-105",
        onboarding_phase="shadow_live",
    )

    assert created["code"] == "site-105"

    policy = json.loads((policy_dir / "site-105-mode-policy.json").read_text(encoding="utf-8"))
    state = json.loads((policy_dir / "site-105-mode-policy-state.json").read_text(encoding="utf-8"))

    assert policy["site_id"] == "site-105"
    assert policy["default_stage"] == "shadow_live"
    assert state["site_id"] == "site-105"
    assert state["current_stage"] == "shadow_live"
    assert state["stage_entered_at"]
