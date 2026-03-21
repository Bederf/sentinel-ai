"""Validates point values against physical/engineering bounds.

Phase 162: Semantic Control Foundation — Plan 03.
Guards against physically impossible classifications (e.g. SAT = 85°C).
"""

from __future__ import annotations

from app.models.validation_errors import ValidationError, ValidationErrorCategory


class BoundsValidator:
    """Validates point values against semantic tag bounds."""

    def validate_point_value(
        self,
        point_id: str,
        tag: str,
        value: float,
        bounds: dict,
    ) -> list[ValidationError]:
        """Check if point value is within acceptable bounds.

        Example: SAT = 85°C is physically impossible (should be 5-35°C).
        """
        errors: list[ValidationError] = []

        if bounds is None:
            return errors

        min_val = bounds.get("min")
        max_val = bounds.get("max")

        if min_val is not None and value < min_val:
            errors.append(
                ValidationError(
                    error_id=f"{point_id}_bounds_low",
                    category=ValidationErrorCategory.BOUNDS_VIOLATION,
                    severity="error",
                    message=f"Point {point_id} value {value} below minimum {min_val}",
                    point_id=point_id,
                    tag=tag,
                    actual_value=value,
                    expected_bounds=bounds,
                    suggestion="Check sensor calibration or verify correct point mapping",
                )
            )

        if max_val is not None and value > max_val:
            errors.append(
                ValidationError(
                    error_id=f"{point_id}_bounds_high",
                    category=ValidationErrorCategory.BOUNDS_VIOLATION,
                    severity="error",
                    message=f"Point {point_id} value {value} above maximum {max_val}",
                    point_id=point_id,
                    tag=tag,
                    actual_value=value,
                    expected_bounds=bounds,
                    suggestion="Check sensor range or verify equipment is operating correctly",
                )
            )

        return errors

    def validate_rate_of_change(
        self,
        point_id: str,
        tag: str,
        values: list[float],
        timestamps: list[float],
        rate_limit: dict,
    ) -> list[ValidationError]:
        """Check if rate of change exceeds physical limits.

        Example: Room temperature cannot change 10°C in 1 minute.
        """
        errors: list[ValidationError] = []
        max_per_minute = rate_limit.get("max_per_minute")

        if max_per_minute is None or len(values) < 2:
            return errors

        for i in range(1, len(values)):
            time_diff_min = (timestamps[i] - timestamps[i - 1]) / 60.0
            if time_diff_min <= 0:
                continue

            value_change = abs(values[i] - values[i - 1])
            rate_per_min = value_change / time_diff_min

            if rate_per_min > max_per_minute:
                errors.append(
                    ValidationError(
                        error_id=f"{point_id}_rate_violation_{i}",
                        category=ValidationErrorCategory.RATE_LIMIT_EXCEEDED,
                        severity="error" if rate_limit.get("alarm_if_exceeded") else "warning",
                        message=(f"Rate of change {rate_per_min:.1f}/min exceeds limit {max_per_minute}/min"),
                        point_id=point_id,
                        tag=tag,
                        suggestion="Check for sensor noise or actual equipment fault",
                    )
                )

        return errors
