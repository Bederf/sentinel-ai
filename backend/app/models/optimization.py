"""Optimization data models for AI-powered building optimization.

Defines the data structures for the AI optimization engine that analyzes
building telemetry and generates optimal HVAC setpoint recommendations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


class ControlTier(str, Enum):
    """Control tier for automation level."""

    MONITOR = "monitor"  # View-only, no recommendations
    HUMAN_IN_LOOP = "human_in_loop"  # Recommendations require approval
    AUTO_EXECUTE = "auto_execute"  # Automatic execution of recommendations


class OptimizationProfile(str, Enum):
    """Optimization profile types."""

    SWEAT_ASSETS = "sweat_assets"  # Maximize equipment utilization
    COMFORT = "comfort"  # Prioritize occupant comfort
    COST = "cost"  # Minimize operational costs


@dataclass
class ZoneProfileOverride:
    """Override profile for a specific zone."""

    zone_id: str
    profile: str  # "sweat_assets" | "comfort" | "cost"
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "zone_id": self.zone_id,
            "profile": self.profile,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ZoneProfileOverride":
        """Create instance from dictionary."""
        return cls(
            zone_id=data.get("zone_id", ""),
            profile=data.get("profile", "cost"),
            reason=data.get("reason", ""),
        )


@dataclass
class ScheduleProfileOverride:
    """Override profile for a specific time schedule."""

    day_of_week: str  # "monday" | "tuesday" | ... | "sunday"
    start_hour: int  # 0-23
    end_hour: int  # 0-23
    profile: str  # "sweat_assets" | "comfort" | "cost"
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "day_of_week": self.day_of_week,
            "start_hour": self.start_hour,
            "end_hour": self.end_hour,
            "profile": self.profile,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleProfileOverride":
        """Create instance from dictionary."""
        return cls(
            day_of_week=data.get("day_of_week", ""),
            start_hour=data.get("start_hour", 0),
            end_hour=data.get("end_hour", 23),
            profile=data.get("profile", "cost"),
            reason=data.get("reason", ""),
        )


@dataclass
class SiteProfileConfig:
    """Site-level profile configuration."""

    site_id: str
    active_profile: str  # "sweat_assets" | "comfort" | "cost"
    control_tier: str  # "monitor" | "human_in_loop" | "auto_execute"
    zone_overrides: List[ZoneProfileOverride] = field(default_factory=list)
    schedule_overrides: List[ScheduleProfileOverride] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "site_id": self.site_id,
            "active_profile": self.active_profile,
            "control_tier": self.control_tier,
            "zone_overrides": [zo.to_dict() for zo in self.zone_overrides],
            "schedule_overrides": [so.to_dict() for so in self.schedule_overrides],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SiteProfileConfig":
        """Create instance from dictionary."""
        return cls(
            site_id=data.get("site_id", ""),
            active_profile=data.get("active_profile", "cost"),
            control_tier=data.get("control_tier", "human_in_loop"),
            zone_overrides=[ZoneProfileOverride.from_dict(zo) for zo in data.get("zone_overrides", [])],
            schedule_overrides=[ScheduleProfileOverride.from_dict(so) for so in data.get("schedule_overrides", [])],
        )


class OptimizationStatus(str, Enum):
    """Optimization status for a building."""

    OPTIMIZED = "optimized"
    RECOMMENDATION_PENDING = "recommendation_pending"
    WARNING = "warning"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class OptimizationRecommendation:
    """AI-generated optimization recommendation for a building.

    Contains specific setpoint changes, projected savings, and confidence score.
    Supports both HVAC and DALI lighting recommendations.
    Includes profile information for recommendations.
    """

    site_id: str
    timestamp: str
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    projected_savings: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reasoning: str = ""
    # Phase 3: Cross-system coordination
    cross_system_recommendations: Optional[List[Dict[str, Any]]] = None
    lighting_summary: Optional[Dict[str, Any]] = None
    # Phase 72.2: Profile-aware optimization
    profile: Optional[str] = None  # Active profile name (e.g., "cost", "comfort", "asset_sweating")
    profile_applied: bool = False  # Whether profile was applied to recommendations
    # Phase 72.3: Multi-objective scoring
    scoring_summary: Optional[Dict[str, Any]] = None  # Scoring statistics: total_recommendations, top_score, avg_score
    # Data quality tracking: which sensors were live vs defaulted
    data_quality: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "site_id": self.site_id,
            "timestamp": self.timestamp,
            "recommendations": self.recommendations,
            "projected_savings": self.projected_savings,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "profile": self.profile,
            "profile_applied": self.profile_applied,
        }
        if self.cross_system_recommendations:
            result["cross_system_recommendations"] = self.cross_system_recommendations
        if self.lighting_summary:
            result["lighting_summary"] = self.lighting_summary
        if self.scoring_summary:
            result["scoring_summary"] = self.scoring_summary
        if self.data_quality:
            result["data_quality"] = self.data_quality
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizationRecommendation":
        """Create instance from dictionary."""
        return cls(
            site_id=data.get("site_id", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            recommendations=data.get("recommendations", []),
            projected_savings=data.get("projected_savings", {}),
            confidence=data.get("confidence", 0.0),
            reasoning=data.get("reasoning", ""),
            cross_system_recommendations=data.get("cross_system_recommendations"),
            lighting_summary=data.get("lighting_summary"),
            profile=data.get("profile"),
            profile_applied=data.get("profile_applied", False),
            scoring_summary=data.get("scoring_summary"),
            data_quality=data.get("data_quality"),
        )


@dataclass
class OptimizationSettings:
    """Optimization settings for a site."""

    enabled: bool = False
    mode: str = "supervised"  # "automatic" or "supervised"
    last_analysis: Optional[str] = None
    analysis_interval_minutes: int = 15

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "last_analysis": self.last_analysis,
            "analysis_interval_minutes": self.analysis_interval_minutes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizationSettings":
        """Create instance from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            mode=data.get("mode", "supervised"),
            last_analysis=data.get("last_analysis"),
            analysis_interval_minutes=data.get("analysis_interval_minutes", 15),
        )


@dataclass
class OptimizationHistoryEntry:
    """Entry in the optimization history log."""

    timestamp: str
    action: str  # "analyzed", "approved", "rejected", "error"
    result: str  # "success", "warning", "error"
    user: str = "system"
    details: Dict[str, Any] = field(default_factory=dict)
    routing_summary: Optional[Dict[str, Any]] = None  # Phase 82-02: tier routing metadata

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "timestamp": self.timestamp,
            "action": self.action,
            "result": self.result,
            "user": self.user,
            "details": self.details,
        }
        if self.routing_summary is not None:
            result["routing_summary"] = self.routing_summary
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizationHistoryEntry":
        """Create instance from dictionary."""
        return cls(
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            action=data.get("action", "analyzed"),
            result=data.get("result", "success"),
            user=data.get("user", "system"),
            details=data.get("details", {}),
            routing_summary=data.get("routing_summary"),
        )


@dataclass
class SiteOptimizationStatus:
    """Current optimization status for a site."""

    site_id: str
    status: OptimizationStatus
    settings: OptimizationSettings
    last_recommendation: Optional[OptimizationRecommendation] = None
    last_optimization: Optional[str] = None
    history: List[OptimizationHistoryEntry] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "site_id": self.site_id,
            "status": self.status.value if isinstance(self.status, OptimizationStatus) else self.status,
            "settings": self.settings.to_dict(),
            "last_recommendation": self.last_recommendation.to_dict() if self.last_recommendation else None,
            "last_optimization": self.last_optimization,
            "history": [entry.to_dict() for entry in self.history],
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SiteOptimizationStatus":
        """Create instance from dictionary."""
        status_str = data.get("status", "unknown")
        status = OptimizationStatus(status_str) if isinstance(status_str, str) else status_str

        return cls(
            site_id=data.get("site_id", ""),
            status=status,
            settings=OptimizationSettings.from_dict(data.get("settings", {})),
            last_recommendation=OptimizationRecommendation.from_dict(data.get("last_recommendation", {}))
            if data.get("last_recommendation")
            else None,
            last_optimization=data.get("last_optimization"),
            history=[OptimizationHistoryEntry.from_dict(entry) for entry in data.get("history", [])],
            error_message=data.get("error_message"),
        )
