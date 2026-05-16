from enum import Enum
from typing import Any, Optional
from datetime import datetime

from pydantic import BaseModel


class PreferenceType(str, Enum):
    SETPOINT = "setpoint"
    PRIORITY = "priority"
    TIMING = "timing"
    EQUIPMENT = "equipment"
    NONE = "none"


class UserPreference(BaseModel):
    id: Optional[str] = None
    site_id: str
    user_id: str
    preference_type: PreferenceType
    preference_value: dict[str, Any]
    source: str = "chat_explicit"
    confidence: float
    created_at: Optional[datetime] = None


class PreferenceExtractionResult(BaseModel):
    preference_type: PreferenceType
    preference_value: dict[str, Any]
    confidence: float
    reasoning: Optional[str] = None
