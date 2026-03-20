from datetime import date
import json

from app.services.site_holiday_service import SiteHolidayService


def test_site_holiday_service_matches_sa_public_holiday(tmp_path):
    site_dir = tmp_path / "site-002"
    site_dir.mkdir()
    (site_dir / "building.json").write_text(json.dumps({"holidays": []}))

    service = SiteHolidayService(data_path=tmp_path)

    assert service.is_holiday("site-002", date(2026, 12, 25)) is True
    assert service.is_holiday("site-002", date(2026, 12, 24)) is False


def test_site_holiday_service_matches_custom_site_holiday(tmp_path):
    site_dir = tmp_path / "site-002"
    site_dir.mkdir()
    (site_dir / "building.json").write_text(
        json.dumps(
            {
                "holidays": [
                    {"id": "custom-1", "date": "2026-07-17", "name": "Shutdown", "type": "custom", "recurring": False}
                ]
            }
        )
    )

    service = SiteHolidayService(data_path=tmp_path)

    assert service.is_holiday("site-002", date(2026, 7, 17)) is True
    assert service.is_holiday("site-002", date(2026, 7, 18)) is False
