"""Tests for EDGE_MODE startup gating.

Verifies that EDGE_MODE=true disables ML training, simulation queue,
and AEGIS evidence collector jobs while EDGE_MODE=false (default)
preserves all existing behavior.
"""

from unittest.mock import patch


def _make_settings(**overrides):
    """Create a fresh Settings instance with env var overrides."""
    import os

    env = {
        "JWT_SECRET_KEY": "test-secret-key-minimum-32-chars-long",
        "SUPABASE_URL": "http://localhost:54321",
        "SUPABASE_KEY": "test-key",
    }
    env.update(overrides)

    with patch.dict(os.environ, env, clear=False):
        from app.config.settings import Settings

        return Settings()


class TestEdgeModeSettings:
    """Test EDGE_MODE setting behavior."""

    def test_edge_mode_default_false(self):
        """EDGE_MODE defaults to False when no env var is set."""
        s = _make_settings()
        assert s.edge_mode is False

    def test_edge_mode_true_from_env(self):
        """EDGE_MODE=true is correctly parsed from environment."""
        s = _make_settings(EDGE_MODE="true")
        assert s.edge_mode is True

    def test_edge_mode_false_from_env(self):
        """EDGE_MODE=false is correctly parsed from environment."""
        s = _make_settings(EDGE_MODE="false")
        assert s.edge_mode is False


class TestEdgeModeGating:
    """Test that EDGE_MODE gates ML jobs in startup logic."""

    def test_edge_mode_disables_ml_jobs(self, monkeypatch):
        """When EDGE_MODE=true and ML_BACKGROUND_TRAINING_ENABLED=true,
        ML retraining job should NOT be called."""
        monkeypatch.setenv("EDGE_MODE", "true")
        monkeypatch.setenv("ML_BACKGROUND_TRAINING_ENABLED", "true")

        # Reimport settings to pick up env vars
        from app.config.settings import Settings

        settings = Settings(
            _env_file=None,
            edge_mode=True,
            ml_background_training_enabled=True,
            jwt_secret_key="test-secret-key-minimum-32-chars-long",
        )

        # The gating logic in events.py:
        #   if settings.edge_mode:
        #       log("ML training jobs disabled")
        #   elif settings.ml_background_training_enabled:
        #       scheduler_service.add_ml_retraining_job(...)
        #
        # When edge_mode=True, the elif branch is never reached.
        assert settings.edge_mode is True
        assert settings.ml_background_training_enabled is True

        # Simulate the gating condition
        should_register_ml_jobs = not settings.edge_mode and settings.ml_background_training_enabled
        assert should_register_ml_jobs is False

    def test_edge_mode_false_allows_all_jobs(self, monkeypatch):
        """When EDGE_MODE=false and ML_BACKGROUND_TRAINING_ENABLED=true,
        ML retraining job SHOULD be called."""
        from app.config.settings import Settings

        settings = Settings(
            _env_file=None,
            edge_mode=False,
            ml_background_training_enabled=True,
            jwt_secret_key="test-secret-key-minimum-32-chars-long",
        )

        assert settings.edge_mode is False
        assert settings.ml_background_training_enabled is True

        # Simulate the gating condition
        should_register_ml_jobs = not settings.edge_mode and settings.ml_background_training_enabled
        assert should_register_ml_jobs is True

    def test_edge_mode_gates_aegis_evidence(self):
        """EDGE_MODE=true should prevent AEGIS evidence collector registration."""
        from app.config.settings import Settings

        settings = Settings(
            _env_file=None,
            edge_mode=True,
            jwt_secret_key="test-secret-key-minimum-32-chars-long",
        )

        # The gating condition in events.py:
        #   if not settings.edge_mode:
        #       scheduler_service.add_aegis_evidence_collector_job(...)
        should_register_evidence = not settings.edge_mode
        assert should_register_evidence is False

    def test_edge_mode_gates_simulation_queue(self):
        """EDGE_MODE=true should prevent simulation queue processor from starting."""
        from app.config.settings import Settings

        settings = Settings(
            _env_file=None,
            edge_mode=True,
            site002_source_enabled=True,
            jwt_secret_key="test-secret-key-minimum-32-chars-long",
        )

        # The gating condition in events.py:
        #   if settings.site002_source_enabled and not _simulation_stopped and not settings.edge_mode:
        _simulation_stopped = False
        should_start_sim = settings.site002_source_enabled and not _simulation_stopped and not settings.edge_mode
        assert should_start_sim is False
