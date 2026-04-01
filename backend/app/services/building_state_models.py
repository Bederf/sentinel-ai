"""Shared models for the SENTINEL building-state engine."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Voice = Literal[
    "comfort_stress",
    "asset_stress",
    "energy_pressure",
    "operational_stability",
    "occupant_friction",
]

BuildingPosture = Literal[
    "calm",
    "drifting",
    "compensating",
    "strained",
    "critical",
]

GuidanceMode = Literal[
    "none",
    "watch",
    "prepare",
    "intervene_soon",
    "act_now",
]

PropagationDirection = Literal[
    "contained",
    "upward",
    "downward",
    "lateral",
    "building_wide",
]


class NarrativeLocation(BaseModel):
    epicenter: str
    affected: list[str] = Field(default_factory=list)
    propagation: PropagationDirection


class PrimaryNarrative(BaseModel):
    voice: Voice
    message: str
    location: NarrativeLocation
    time_to_breach_min: int | None = None
    urgency: GuidanceMode
    action: str


class SecondaryTension(BaseModel):
    voice: Voice
    message: str


class OperatorGuidance(BaseModel):
    headline: str
    mode: GuidanceMode


class BuildingStatePayload(BaseModel):
    site_id: str
    building_posture: BuildingPosture
    primary_narrative: PrimaryNarrative | None
    secondary_tensions: list[SecondaryTension] = Field(default_factory=list)
    operator_guidance: OperatorGuidance


class NarrativeCandidate(BaseModel):
    candidate_id: str
    voice: Voice
    message: str
    location: NarrativeLocation
    action: str
    time_to_constraint_breach_min: int | None = None
    affected_occupants_est: int | None = None
    system_criticality: float = 0.0
    propagation_risk: float = 0.0
    resolved: bool = False
    spatially_grounded: bool = True
    eroding_margin: bool = False
