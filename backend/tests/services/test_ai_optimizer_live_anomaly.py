import pytest

from app.services.ai_optimizer import AIOptimizerService


class TestPullLiveAnomalyScores:
    """Tests for _pull_live_anomaly_scores (178-08 wire to recommendations)."""

    @pytest.mark.asyncio
    async def test_pull_live_anomaly_scores_returns_equipment_with_scores(self):
        """Returns equipment that has at least one of anomaly_score or lstm_anomaly_score."""
        from unittest.mock import patch


        svc = AIOptimizerService()

        fake_sb_resp = type("_FakeSBResp", (), {
            "data": [
                {
                    "code": "S002-CHILLER-B1-001",
                    "operating_data": {"anomaly_score": 0.72, "lstm_anomaly_score": 0.31},
                    "updated_at": "2026-04-05T10:30:00Z",
                }
            ]
        })()

        fake_site_resp = type("_FakeSiteResp", (), {"data": [{"id": "site-uuid-002"}]})()

        class FakeTable:
            def __init__(self, side_effect):
                self._side_effect = side_effect
            def select(self, *args): return self
            def eq(self, *args): return self
            def in_(self, *args): return self
            def execute(self):
                if self._side_effect == "site":
                    return fake_site_resp
                return fake_sb_resp

        fake_sb = type("_FakeSB", (), {
            "table": lambda self, name: FakeTable("equip" if name == "equipment" else "site"),
        })()

        with patch("app.database.supabase_client.get_supabase_client", return_value=fake_sb):
            result = await svc._pull_live_anomaly_scores("site-002", ["S002-CHILLER-B1-001"])

        assert len(result) == 1
        assert result[0]["equipment_id"] == "S002-CHILLER-B1-001"
        assert result[0]["anomaly_score"] == 0.72
        assert result[0]["lstm_anomaly_score"] == 0.31
        assert result[0]["as_of"] is not None

    @pytest.mark.asyncio
    async def test_pull_live_anomaly_scores_excludes_equipment_without_scores(self):
        """Equipment with both scores None is excluded from results."""
        from unittest.mock import patch


        svc = AIOptimizerService()

        fake_sb_resp = type("_FakeSBResp", (), {
            "data": [
                {"code": "S002-FCU-001", "operating_data": {}, "updated_at": "2026-04-05T10:30:00Z"},
                {"code": "S002-FCU-002", "operating_data": {"room_temp": 22.1}, "updated_at": "2026-04-05T10:30:00Z"},
            ]
        })()

        fake_site_resp = type("_FakeSiteResp", (), {"data": [{"id": "site-uuid-002"}]})()

        class FakeTable:
            def __init__(self, side):
                self._side = side
            def select(self, *args): return self
            def eq(self, *args): return self
            def in_(self, *args): return self
            def execute(self):
                return fake_site_resp if self._side == "site" else fake_sb_resp

        fake_sb = type("_FakeSB", (), {
            "table": lambda self, name: FakeTable("site" if name == "sites" else "equip"),
        })()

        with patch("app.database.supabase_client.get_supabase_client", return_value=fake_sb):
            result = await svc._pull_live_anomaly_scores(
                "site-002", ["S002-FCU-001", "S002-FCU-002"]
            )

        # Both rows have neither anomaly_score nor lstm_anomaly_score → excluded
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_pull_live_anomaly_scores_empty_list_returns_empty(self):
        """Empty equipment_ids returns empty list without querying DB."""
        svc = AIOptimizerService()
        result = await svc._pull_live_anomaly_scores("site-002", [])
        assert result == []


class TestFormatLiveAnomalyScores:
    """Tests for _format_live_anomaly_scores formatter."""

    def test_format_live_anomaly_scores_elevated_flag(self):
        """Score > 0.65 is labelled ELEVATED."""
        svc = AIOptimizerService()
        scores = [
            {
                "equipment_id": "S002-CHILLER-B1-001",
                "anomaly_score": 0.72,
                "lstm_anomaly_score": 0.31,
                "as_of": "2026-04-05T10:30:00Z",
            }
        ]
        output = svc._format_live_anomaly_scores(scores)
        assert "S002-CHILLER-B1-001" in output
        assert "IF_anomaly=0.72 (ELEVATED)" in output
        assert "LSTM_anomaly=0.31" in output
        assert "10:30" in output  # time extracted from ISO

    def test_format_live_anomaly_scores_normal_flag(self):
        """Score <= 0.65 is labelled normal."""
        svc = AIOptimizerService()
        scores = [
            {
                "equipment_id": "S002-FCU-001",
                "anomaly_score": 0.45,
                "lstm_anomaly_score": None,
                "as_of": "2026-04-05T09:00:00Z",
            }
        ]
        output = svc._format_live_anomaly_scores(scores)
        assert "IF_anomaly=0.45 (normal)" in output

    def test_format_live_anomaly_scores_empty_returns_fallback(self):
        """Empty list returns empty string (caller handles placeholder)."""
        svc = AIOptimizerService()
        result = svc._format_live_anomaly_scores([])
        assert result == ""
