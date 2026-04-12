"""
SENTINEL Email Intake — Advisor Strategy Classification Service

Uses Anthropic's advisor tool (advisor_20260301) to run Haiku as the
executor for routine classification, with Opus as advisor for complex cases.

Replaces the GPT-4.1 classification in the n8n workflow.
Called by the SENTRY-EMAIL Python backend after n8n extracts headers/signatures.
"""

import json
import logging
import re
from typing import Optional

from pydantic import BaseModel, Field

import anthropic

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────

# Executor: Haiku for 85%+ of emails (routine classification)
# Advisor: Opus for ambiguous/multi-issue/safety-critical emails
EXECUTOR_MODEL = "claude-haiku-4-5"
ADVISOR_MODEL = "claude-opus-4-6"
ADVISOR_MAX_USES = 2  # Cap: max 2 Opus consultations per email
BETA_HEADER = "advisor-tool-2026-03-01"


# ── Response Model ───────────────────────────────────────────────


class EmailClassification(BaseModel):
    """Structured classification result from the AI."""

    issue_description: str = Field(default="", description="1-2 sentence technical description")
    issue_category: str = Field(default="General")
    urgency: str = Field(default="medium")
    specific_location: Optional[str] = None
    equipment_mentioned: Optional[str] = None
    is_followup: bool = False
    existing_reference: Optional[str] = None
    missing_info: list[str] = []
    summary: str = Field(default="", description="Brief 1-line summary for work order")
    advisor_consulted: bool = False
    classification_confidence: float = 0.0


# ── System Prompt ────────────────────────────────────────────────
# ruff: noqa: E501
SYSTEM_PROMPT = """You are SENTINEL's email intake classifier for facilities management.

You receive maintenance request emails from building occupants.

Pre-extracted data from email headers and signatures is provided. Only classify what the LLM adds value to — don't re-extract what's already given.

Return ONLY valid JSON matching this schema:
{
  "issue_description": "1-2 sentence technical description of the problem",
  "issue_category": "HVAC|Electrical|Plumbing|Structural|Cleaning|Security|IT_Network|Elevator|Fire_Safety|General",
  "urgency": "critical|high|medium|low",
  "specific_location": "room, zone, desk, or area mentioned (e.g. 'Centre Court 2', 'boardroom 6.2') or null",
  "equipment_mentioned": "specific equipment referenced (e.g. 'aircon unit', 'ceiling', 'tap', 'UPS') or null",
  "is_followup": true/false,
  "existing_reference": "any work order reference mentioned (e.g. 'FNBFW:30673', 'FAR-04521') or null",
  "missing_info": ["list of critical fields still unclear"],
  "summary": "Brief 1-line summary for the work order"
}

Urgency guidelines:
- critical: Safety hazard, water flooding, fire alarm, power failure, gas leak, ceiling collapse
- high: Major discomfort affecting multiple people, executive areas, server room, events today
- medium: Standard maintenance — broken fixture, HVAC not working, minor leak
- low: Cosmetic, nice-to-have, future planning requests

If this email is ambiguous, involves multiple issues, or has safety implications,
consult your advisor before finalising the classification."""


# ── Classification Service ───────────────────────────────────────


class EmailClassifierService:
    """
    Classifies maintenance emails using Haiku executor + Opus advisor.

    The advisor pattern means:
    - Simple emails (broken tap, light out): Haiku classifies directly (~$0.001)
    - Complex emails (multi-issue, safety, ambiguous): Haiku consults Opus (~$0.01)
    - vs running Sonnet on everything: ~$0.005 per email
    - vs running Opus on everything: ~$0.05 per email
    """

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def classify_email(
        self,
        from_email: str,
        from_name: str,
        subject: str,
        body_text: str,
        # Pre-extracted data from n8n layers 1-3
        sig_building: Optional[str] = None,
        sig_floor: Optional[str] = None,
        sig_cost_center: Optional[str] = None,
        sig_specific_location: Optional[str] = None,
        existing_reference: Optional[str] = None,
        is_reply: bool = False,
        importance: str = "normal",
        urgency_boost: bool = False,
        has_manager_cc: bool = False,
    ) -> EmailClassification:
        """
        Classify a maintenance email using the advisor strategy.

        Returns structured classification with cost tracking.
        """

        # Build the user message with pre-extracted context
        user_message = f"""Classify this maintenance email:

From: {from_email} ({from_name})
Subject: {subject}

Pre-extracted data:
- Building (from signature/body): {sig_building or "unknown"}
- Floor (from signature): {sig_floor or "unknown"}
- Cost Center: {sig_cost_center or "unknown"}
- Specific Location: {sig_specific_location or "unknown"}
- Existing Reference: {existing_reference or "none"}
- Is Reply/Follow-up: {is_reply}
- Email Priority: {importance}
- Urgency Boost (high importance / manager CC): {urgency_boost}
- Manager CC'd: {has_manager_cc}

Email Body:
{body_text}

Return JSON only."""

        try:
            # Single API call with advisor tool
            response = self.client.beta.messages.create(
                model=EXECUTOR_MODEL,
                max_tokens=1024,
                betas=[BETA_HEADER],
                system=SYSTEM_PROMPT,
                tools=[
                    {
                        "type": "advisor_20260301",
                        "name": "advisor",
                        "model": ADVISOR_MODEL,
                        "max_uses": ADVISOR_MAX_USES,
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )

            # Extract classification from response
            classification = self._parse_response(response)

            # Track whether advisor was consulted
            advisor_consulted = any(
                hasattr(block, "type") and block.type == "advisor_tool_result" for block in response.content
            )
            classification.advisor_consulted = advisor_consulted

            # Log cost breakdown
            usage = response.usage
            logger.info(
                f"Email classified: category={classification.issue_category}, "
                f"urgency={classification.urgency}, "
                f"advisor_consulted={advisor_consulted}, "
                f"input_tokens={usage.input_tokens}, "
                f"output_tokens={usage.output_tokens}"
            )

            return classification

        except anthropic.APIError as e:
            logger.error(f"Anthropic API error during classification: {e}")
            return self._fallback_classification(subject, body_text)

        except Exception as e:
            logger.error(f"Classification failed: {e}", exc_info=True)
            return self._fallback_classification(subject, body_text)

    def _parse_response(self, response) -> EmailClassification:
        """Extract JSON classification from the API response."""
        # Find the text block in the response
        for block in response.content:
            if hasattr(block, "text") and block.text:
                text = block.text.strip()
                # Extract JSON from possible markdown fencing
                if "```" in text:
                    match = re.search(r"\{[\s\S]*\}", text)
                    if match:
                        text = match.group(0)
                elif text.startswith("{"):
                    pass
                else:
                    # Try to find JSON in the text
                    match = re.search(r"\{[\s\S]*\}", text)
                    if match:
                        text = match.group(0)
                    else:
                        continue

                try:
                    data = json.loads(text)
                    return EmailClassification(**data)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse classification JSON: {e}")
                    continue

        logger.error("No valid classification JSON found in response")
        return EmailClassification(
            issue_description="Classification parsing failed",
            issue_category="General",
            urgency="medium",
            missing_info=["AI classification failed — manual review needed"],
            summary="Classification failed - manual review needed",
        )

    def _fallback_classification(self, subject: str, body_text: str) -> EmailClassification:
        """
        Rule-based fallback when the API is unavailable.
        Ensures emails still get processed even without AI.
        """
        # Simple keyword-based classification
        text = (subject + " " + body_text).lower()

        category = "General"
        urgency = "medium"

        category_keywords = {
            "HVAC": [
                "aircon",
                "air con",
                "hvac",
                "temperature",
                "cold",
                "hot",
                "heating",
                "cooling",
            ],
            "Plumbing": ["water", "leak", "tap", "drain", "pipe", "toilet", "plumbing", "flooding"],
            "Electrical": ["power", "light", "switch", "socket", "electrical", "ups", "generator"],
            "Elevator": ["lift", "elevator"],
            "Fire_Safety": ["fire", "smoke", "alarm", "sprinkler", "extinguisher"],
            "Security": ["access", "card", "cctv", "security", "lock", "door"],
            "Cleaning": ["clean", "dirty", "rubbish", "waste", "hygiene"],
            "IT_Network": ["wifi", "network", "internet", "printer", "cable"],
            "Structural": ["ceiling", "wall", "floor", "window", "roof", "crack"],
        }

        for cat, keywords in category_keywords.items():
            if any(kw in text for kw in keywords):
                category = cat
                break

        # Urgency from keywords
        if any(kw in text for kw in ["flood", "fire", "gas leak", "collapse", "emergency", "safety"]):
            urgency = "critical"
        elif any(kw in text for kw in ["urgent", "high priority", "immediately", "vip", "executive"]):
            urgency = "high"

        return EmailClassification(
            issue_description=subject,
            issue_category=category,
            urgency=urgency,
            summary=f"[FALLBACK] {subject}",
            missing_info=["Classified by fallback rules — AI unavailable"],
            classification_confidence=0.4,
        )


# ── Singleton ────────────────────────────────────────────────────

_classifier_instance: Optional[EmailClassifierService] = None


def get_email_classifier() -> EmailClassifierService:
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = EmailClassifierService()
    return _classifier_instance
