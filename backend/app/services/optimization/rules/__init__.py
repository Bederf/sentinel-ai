"""Rule registry — collects all optimization rules from every module."""

from app.services.optimization.rule import OptimizationRule

from . import hvac, energy, solar, lighting, water, security, fire

ALL_RULES: list[OptimizationRule] = []
ALL_RULES.extend(hvac.RULES)
ALL_RULES.extend(energy.RULES)
ALL_RULES.extend(solar.RULES)
ALL_RULES.extend(lighting.RULES)
ALL_RULES.extend(water.RULES)
ALL_RULES.extend(security.RULES)
ALL_RULES.extend(fire.RULES)
