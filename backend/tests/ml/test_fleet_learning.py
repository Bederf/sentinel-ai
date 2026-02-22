"""
Tests for Fleet Learning modules.

Tests FleetAggregator, GlobalModelTrainer, and LocalFineTuner.
Phase 45-02: Fleet Learning and Cross-Site Insights.
"""


# --- FleetAggregator Tests ---


class TestFleetAggregator:
    """Tests for FleetAggregator anonymized failure pattern aggregation."""

    def _get_aggregator(self):
        from ml.fleet.aggregator import FleetAggregator

        return FleetAggregator()

    def test_aggregate_failure_patterns_returns_all(self):
        aggregator = self._get_aggregator()
        patterns = aggregator.aggregate_failure_patterns()
        assert len(patterns) > 0
        # Should have demo data
        assert len(patterns) >= 8

    def test_aggregate_failure_patterns_filter_by_type(self):
        aggregator = self._get_aggregator()
        patterns = aggregator.aggregate_failure_patterns(equipment_type="CHILLER")
        assert len(patterns) > 0
        for p in patterns:
            assert p["equipment_type"] == "CHILLER"

    def test_aggregate_failure_patterns_sorted_by_count(self):
        aggregator = self._get_aggregator()
        patterns = aggregator.aggregate_failure_patterns()
        counts = [p["occurrence_count"] for p in patterns]
        assert counts == sorted(counts, reverse=True)

    def test_failure_pattern_anonymized(self):
        """Patterns should not contain site identifiers."""
        aggregator = self._get_aggregator()
        patterns = aggregator.aggregate_failure_patterns()
        for p in patterns:
            assert "site_code" not in p
            assert "site_id" not in p
            # sites_affected is a count, not identifiers
            assert isinstance(p["sites_affected"], int)

    def test_get_similar_failures(self):
        aggregator = self._get_aggregator()
        similar = aggregator.get_similar_failures(
            equipment_type="CHILLER",
            exclude_site="site-002",
        )
        assert len(similar) > 0
        for s in similar:
            assert s["equipment_type"] == "CHILLER"
            assert "precursor_pattern" in s
            assert "confidence" in s

    def test_get_similar_failures_exclude_site_reduces_count(self):
        aggregator = self._get_aggregator()
        all_similar = aggregator.get_similar_failures(equipment_type="CHILLER")
        excluded = aggregator.get_similar_failures(equipment_type="CHILLER", exclude_site="site-002")
        # Excluding a site should reduce counts
        for a, e in zip(all_similar, excluded):
            assert e["fleet_occurrences"] <= a["fleet_occurrences"]

    def test_fleet_summary(self):
        aggregator = self._get_aggregator()
        summary = aggregator.get_fleet_summary()
        assert "fleet_overview" in summary
        assert "type_distribution" in summary
        assert "top_failure_patterns" in summary
        overview = summary["fleet_overview"]
        assert overview["total_sites"] > 0
        assert overview["total_equipment"] > 0
        assert 0 <= overview["avg_fleet_health"] <= 100

    def test_benchmarks(self):
        aggregator = self._get_aggregator()
        benchmarks = aggregator.get_benchmarks()
        assert len(benchmarks) > 0
        for b in benchmarks:
            assert "equipment_type" in b
            assert "fleet_avg_health" in b
            assert "fleet_avg_mtbf_days" in b
            assert b["fleet_best_health"] >= b["fleet_worst_health"]

    def test_benchmark_site_above_average(self):
        aggregator = self._get_aggregator()
        result = aggregator.benchmark_site(
            site_code="site-002",
            site_health=90.0,
        )
        assert result["status"] == "above_average"
        assert result["percentile"] > 50

    def test_benchmark_site_below_average(self):
        aggregator = self._get_aggregator()
        result = aggregator.benchmark_site(
            site_code="site-003",
            site_health=40.0,
        )
        assert result["status"] == "below_average"
        assert result["percentile"] < 50

    def test_risk_distribution(self):
        aggregator = self._get_aggregator()
        risk = aggregator.get_risk_distribution()
        assert "distribution" in risk
        total_pct = sum(risk["distribution"][level]["percentage"] for level in ("critical", "high", "medium", "low"))
        # Should add up to approximately 100%
        assert 98 <= total_pct <= 102


# --- GlobalModelTrainer Tests ---


class TestGlobalModelTrainer:
    """Tests for GlobalModelTrainer fleet-wide model training."""

    def _get_trainer(self):
        from ml.fleet.global_model import GlobalModelTrainer

        return GlobalModelTrainer()

    def test_list_global_models(self):
        trainer = self._get_trainer()
        models = trainer.list_global_models()
        assert len(models) >= 8  # Seeded models

    def test_list_global_models_filter(self):
        trainer = self._get_trainer()
        lstm_models = trainer.list_global_models(model_type="lstm")
        assert len(lstm_models) > 0
        for m in lstm_models:
            assert m["model_type"] == "lstm"

    def test_get_global_model(self):
        trainer = self._get_trainer()
        model = trainer.get_global_model("lstm", "chiller")
        assert model is not None
        assert model["model_type"] == "lstm"
        assert model["equipment_type"] == "chiller"
        assert model["variant"] == "global"

    def test_get_global_model_missing(self):
        trainer = self._get_trainer()
        model = trainer.get_global_model("lstm", "nonexistent")
        assert model is None

    def test_train_global_model(self):
        trainer = self._get_trainer()
        result = trainer.train_global_model("lstm", "chiller")
        assert result.success is True
        assert result.global_model_id is not None
        assert result.metrics.get("r2_score", 0) > 0

    def test_train_new_model_type(self):
        trainer = self._get_trainer()
        result = trainer.train_global_model("lstm", "new_type")
        assert result.success is True
        assert result.global_model_id == "global_lstm_new_type"

    def test_compare_global_vs_local_keep_local(self):
        trainer = self._get_trainer()
        result = trainer.compare_global_vs_local(
            model_type="lstm",
            equipment_type="chiller",
            local_metrics={"r2_score": 0.95},
        )
        assert result["recommendation"] == "keep_local"

    def test_compare_global_vs_local_use_global(self):
        trainer = self._get_trainer()
        result = trainer.compare_global_vs_local(
            model_type="lstm",
            equipment_type="chiller",
            local_metrics={"r2_score": 0.5},
        )
        assert result["recommendation"] == "use_global"

    def test_training_history(self):
        trainer = self._get_trainer()
        trainer.train_global_model("lstm", "chiller")
        history = trainer.get_training_history()
        assert len(history) > 0


# --- LocalFineTuner Tests ---


class TestLocalFineTuner:
    """Tests for LocalFineTuner site-specific model fine-tuning."""

    def _get_tuner(self):
        from ml.fleet.fine_tuning import LocalFineTuner

        return LocalFineTuner()

    def test_list_fine_tuned_models(self):
        tuner = self._get_tuner()
        models = tuner.list_fine_tuned_models()
        assert len(models) >= 5  # Seeded models

    def test_list_fine_tuned_filter_by_site(self):
        tuner = self._get_tuner()
        models = tuner.list_fine_tuned_models(site_code="site-002")
        assert len(models) > 0
        for m in models:
            assert m["site_code"] == "site-002"

    def test_get_fine_tuned_model(self):
        tuner = self._get_tuner()
        model = tuner.get_fine_tuned_model("site-002", "lstm", "chiller")
        assert model is not None
        assert model["variant"] == "fine_tuned"
        assert model["metrics"]["r2_score"] > model["global_metrics"]["r2_score"]

    def test_fine_tune_existing(self):
        tuner = self._get_tuner()
        result = tuner.fine_tune(
            site_code="site-002",
            model_type="lstm",
            equipment_type="chiller",
        )
        assert result.success is True
        assert result.fine_tuned_model_id is not None
        # Fine-tuned should improve over global
        ft_r2 = result.fine_tuned_metrics.get("r2_score", 0)
        global_r2 = result.global_metrics.get("r2_score", 0)
        assert ft_r2 >= global_r2

    def test_fine_tune_new_site(self):
        tuner = self._get_tuner()
        result = tuner.fine_tune(
            site_code="site-099",
            model_type="lstm",
            equipment_type="chiller",
        )
        assert result.success is True
        # Improvement should be positive
        assert result.improvement.get("r2_score", 0) >= 0

    def test_improvement_summary(self):
        tuner = self._get_tuner()
        summary = tuner.get_improvement_summary()
        assert summary["models_count"] > 0
        assert summary["avg_improvement_pct"] > 0

    def test_improvement_summary_by_site(self):
        tuner = self._get_tuner()
        summary = tuner.get_improvement_summary(site_code="site-002")
        assert summary["site_code"] == "site-002"
        assert summary["models_count"] > 0

    def test_fine_tune_history(self):
        tuner = self._get_tuner()
        tuner.fine_tune("site-002", "lstm", "chiller")
        history = tuner.get_fine_tune_history()
        assert len(history) > 0


# --- Singleton Tests ---


class TestSingletons:
    """Test singleton factory functions."""

    def test_fleet_aggregator_singleton(self):
        from ml.fleet.aggregator import get_fleet_aggregator

        a1 = get_fleet_aggregator()
        a2 = get_fleet_aggregator()
        assert a1 is a2

    def test_global_model_trainer_singleton(self):
        from ml.fleet.global_model import get_global_model_trainer

        t1 = get_global_model_trainer()
        t2 = get_global_model_trainer()
        assert t1 is t2

    def test_local_fine_tuner_singleton(self):
        from ml.fleet.fine_tuning import get_local_fine_tuner

        f1 = get_local_fine_tuner()
        f2 = get_local_fine_tuner()
        assert f1 is f2
