"""Tests for ResidentialAIRecommender."""

from __future__ import annotations

from app.services.residential.residential_ai_recommender import (
    ResidentialAIRecommender,
    ResidentialRecommendation,
)


class TestRecommendationDataclass:
    def test_from_dict(self):
        rec = ResidentialRecommendation(
            title="Switch geyser off",
            message="Stage 2 in 45min. Battery at 25%. Save R8.",
            action_app="Home Assistant",
            severity="warning",
            trigger="battery low pre-shed",
            expected_benefit="Extend battery backup",
            cost_impact_zar=8.0,
            confidence=0.85,
        )
        assert rec.title == "Switch geyser off"
        assert rec.severity == "warning"
        assert rec.cost_impact_zar == 8.0


class TestRecommenderPrompt:
    def test_build_prompt_includes_platform(self):
        from app.services.residential.residential_recommendation_context import (
            ResidentialRecommendationContext,
        )

        r = ResidentialAIRecommender()
        ctx = ResidentialRecommendationContext(
            site_id="res-123",
            platform="solarman",
            platform_app_name="SOLARMAN app",
            battery_soc_pct=50.0,
            pv_power_w=2000.0,
            grid_power_w=0.0,
            load_power_w=1500.0,
            loadshedding_stage=0,
            eskom_area_code="jhb-north",
        )
        prompt = r._build_prompt(ctx)
        assert "SOLARMAN app" in prompt
        assert "50.0%" in prompt
        assert "2000.0W" in prompt
        assert "Stage 0" in prompt

    def test_build_prompt_handles_none_grid(self):
        from app.services.residential.residential_recommendation_context import (
            ResidentialRecommendationContext,
        )

        r = ResidentialAIRecommender()
        ctx = ResidentialRecommendationContext(
            site_id="res-999",
            platform="victron",
            platform_app_name="Victron VRM portal",
            battery_soc_pct=80.0,
            pv_power_w=5000.0,
            grid_power_w=None,
            load_power_w=3000.0,
            loadshedding_stage=0,
            eskom_area_code=None,
        )
        prompt = r._build_prompt(ctx)
        assert "Victron VRM portal" in prompt
        assert "unknown" in prompt  # grid direction when None

    def test_parse_response_valid_json(self):
        r = ResidentialAIRecommender()
        from app.services.residential.residential_recommendation_context import (
            ResidentialRecommendationContext,
        )

        ctx = ResidentialRecommendationContext(
            site_id="res-test",
            platform="solarman",
            platform_app_name="SOLARMAN app",
        )
        response = '[{"title":"Test","message":"Do this.","action_app":"SOLARMAN app","severity":"advisory","trigger":"test","expected_benefit":"saving","cost_impact_zar":5.0,"confidence":0.9}]'
        recs = r._parse_response(response, ctx)
        assert len(recs) == 1
        assert recs[0].title == "Test"
        assert recs[0].cost_impact_zar == 5.0
        assert recs[0].confidence == 0.9

    def test_parse_response_empty_array(self):
        r = ResidentialAIRecommender()
        from app.services.residential.residential_recommendation_context import (
            ResidentialRecommendationContext,
        )

        ctx = ResidentialRecommendationContext(
            site_id="res-test",
            platform="solarman",
            platform_app_name="SOLARMAN app",
        )
        recs = r._parse_response("[]", ctx)
        assert recs == []

    def test_parse_response_invalid_json(self):
        r = ResidentialAIRecommender()
        from app.services.residential.residential_recommendation_context import (
            ResidentialRecommendationContext,
        )

        ctx = ResidentialRecommendationContext(
            site_id="res-test",
            platform="solarman",
            platform_app_name="SOLARMAN app",
        )
        recs = r._parse_response("not json at all", ctx)
        assert recs == []
