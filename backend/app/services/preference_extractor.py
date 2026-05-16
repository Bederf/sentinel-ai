"""Preference extraction service — Stage 03 Distillation.

Extracts FM preferences from chat exchanges using Claude Haiku.
Runs as async background task after chat response is streamed to client.
"""

import json
import logging
from typing import Optional

from app.models.preference import UserPreference, PreferenceType
from app.repositories.preference_repository import preference_repo
from app.services.model_gateway import model_gateway

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """Extract user preferences from this chat exchange about building operations.

User: {user_message}
Assistant: {assistant_response}

Identify preferences about:
- Zone setpoints (temperature targets, e.g., "keep zone 3 at 20°C")
- Comfort vs energy priority (e.g., "comfort first", "save energy")
- Timing/schedules (e.g., "only adjust during office hours")
- Equipment preferences (e.g., "prefer newer HVAC systems")

Respond ONLY with JSON (no markdown, no explanation):
{{
  "preference_type": "setpoint|priority|timing|equipment|none",
  "preference_value": {{ ... }},
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation of why you identified this preference"
}}

If no clear preference is expressed, set preference_type to "none".
"""

_CONFIDENCE_HIGH_THRESHOLD = 0.75
_CONFIDENCE_LOW_THRESHOLD = 0.5


async def extract_preference_from_chat(
    user_message: str,
    assistant_response: str,
    site_id: str,
    user_id: str,
) -> Optional[UserPreference]:
    """Extract FM preferences from a chat exchange using Claude Haiku.

    Routes through model_gateway with task_class="extraction".
    Returns UserPreference if confidence > 0.75, else None.
    Low-confidence extractions (0.5-0.75) are logged but not stored.
    """
    logger.debug("preference_extraction_started", extra={"site_id": site_id, "user_id": user_id})

    prompt = _EXTRACTION_PROMPT.format(
        user_message=user_message,
        assistant_response=assistant_response,
    )

    try:
        response = await model_gateway.call(
            task_class="extraction",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            stream=False,
        )
    except Exception as e:
        logger.warning("preference_extraction_gateway_error", extra={"site_id": site_id, "error": str(e)})
        return None

    try:
        result = json.loads(response)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(
            "haiku_response_malformed",
            extra={"site_id": site_id, "response": response[:200] if isinstance(response, str) else str(response)},
        )
        return None

    pref_type_str = result.get("preference_type", "none")
    confidence = result.get("confidence", 0.0)
    pref_value = result.get("preference_value", {})

    if pref_type_str == "none" or confidence < _CONFIDENCE_LOW_THRESHOLD:
        logger.debug("preference_not_detected", extra={"site_id": site_id, "confidence": confidence})
        return None

    if confidence < _CONFIDENCE_HIGH_THRESHOLD:
        logger.debug(
            "preference_low_confidence",
            extra={"site_id": site_id, "confidence": confidence, "extracted_type": pref_type_str},
        )
        return None

    try:
        pref_type = PreferenceType(pref_type_str)
    except ValueError:
        logger.warning("preference_unknown_type", extra={"site_id": site_id, "type": pref_type_str})
        return None

    preference = UserPreference(
        site_id=site_id,
        user_id=user_id,
        preference_type=pref_type,
        preference_value=pref_value,
        source="chat_explicit",
        confidence=confidence,
    )

    try:
        stored = await preference_repo.insert_preference(preference)
        logger.info(
            "preference_extracted",
            extra={
                "site_id": site_id,
                "user_id": user_id,
                "preference_type": pref_type.value,
                "confidence": confidence,
            },
        )
        return stored
    except Exception as e:
        logger.warning("preference_storage_failed", extra={"site_id": site_id, "error": str(e)})
        return None
