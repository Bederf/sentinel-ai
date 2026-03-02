"""Email Intake AI Agent — Phase 134.

Replaces keyword matching + template replies with a single LLM call that
classifies the issue, extracts location/phone, scores completeness, and
generates a natural context-aware reply.

LLM fallback chain: OpenAI (settings.openai_model) → Claude → keyword matching.

Follows the ``ai_optimizer.py`` pattern: gather context → build prompt →
call LLM → parse JSON → fallback to rules if LLM fails.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.config.settings import settings
from app.services.issue_classifier import (
    CALL_LOG_TAXONOMY,
    DISCIPLINE_TO_CATEGORY,
    classify_email_subject,
    extract_area_from_message,
    extract_desk_from_message,
    extract_floor_from_message,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class AgentResult:
    """Structured output from the email intake agent."""

    discipline: str  # "Electrical"
    sub_category: str  # "Power outlet not working"
    specialty: str  # "electrical"
    priority: str  # low|medium|high|critical
    location_desk: Optional[str] = None  # "204"
    location_floor: Optional[str] = None  # "L2"
    location_area: Optional[str] = None
    phone: Optional[str] = None
    issue_summary: str = ""  # "Broken power outlet at desk 204"
    completeness: float = 0.0  # 0.0-1.0
    action: str = "manual_review"  # auto_submit|request_info|manual_review
    reply_text: str = ""  # plain text reply
    reply_html: str = ""  # branded HTML reply
    agent_model: str = "keyword_fallback"
    agent_latency_ms: int = 0


# ---------------------------------------------------------------------------
# Prompt taxonomy reference (built once)
# ---------------------------------------------------------------------------

_TAXONOMY_REFERENCE: Optional[str] = None


def _build_taxonomy_reference() -> str:
    """Serialize the 47-category taxonomy into a compact prompt section."""
    global _TAXONOMY_REFERENCE
    if _TAXONOMY_REFERENCE is not None:
        return _TAXONOMY_REFERENCE

    lines: list[str] = []
    current_disc = ""
    for entry in CALL_LOG_TAXONOMY:
        disc = entry["discipline"]
        if disc != current_disc:
            lines.append(f"\n## {disc}")
            current_disc = disc
        lines.append(
            f"- {entry['sub_category']} (specialty: {entry['specialty']}, default_priority: {entry['priority']})"
        )

    _TAXONOMY_REFERENCE = "\n".join(lines)
    return _TAXONOMY_REFERENCE


# ---------------------------------------------------------------------------
# Valid values (for validation)
# ---------------------------------------------------------------------------

_VALID_DISCIPLINES = {e["discipline"] for e in CALL_LOG_TAXONOMY}
_VALID_SUB_CATEGORIES = {(e["discipline"], e["sub_category"]) for e in CALL_LOG_TAXONOMY}
_VALID_PRIORITIES = {"low", "medium", "high", "critical"}
_VALID_ACTIONS = {"auto_submit", "request_info", "manual_review"}


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------


class EmailIntakeAgent:
    """AI agent for classifying FM emails and generating replies."""

    def __init__(self):
        self._api_key = settings.openai_api_key
        self._base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        # Use configured model — not hardcoded — so it picks up env overrides
        self._model = settings.openai_model or "gpt-4.1-nano"
        self._timeout = settings.email_intake_agent_timeout_seconds

    async def classify_and_reply(
        self,
        *,
        from_name: Optional[str],
        from_email: str,
        subject: str,
        body_plain: Optional[str],
        site_id: Optional[str],
        bms_context: Optional[dict[str, Any]],
    ) -> AgentResult:
        """Main entry point. Try LLM, fall back to keywords."""
        t0 = time.monotonic()

        prompt = self._build_prompt(
            from_name=from_name,
            from_email=from_email,
            subject=subject,
            body_plain=body_plain,
            site_id=site_id,
            bms_context=bms_context,
        )

        try:
            raw, used_model = await self._call_llm(prompt)
            parsed = self._parse_response(raw)
            result = self._validate(parsed, used_model=used_model)
            result.agent_latency_ms = int((time.monotonic() - t0) * 1000)
            # Wrap HTML around the reply text
            result.reply_html = self._wrap_html(
                result.reply_text,
                ref="{ref}",  # placeholder — backend replaces after WO creation
                category=DISCIPLINE_TO_CATEGORY.get(result.discipline, "general"),
                from_name=from_name or "",
            )
            return result
        except Exception as exc:
            logger.error(
                "Agent LLM failed for sender=%s subject=%r — falling back to keywords. Error: %s",
                from_email,
                subject,
                exc,
                exc_info=True,
            )
            result = self._keyword_fallback(
                from_name=from_name,
                from_email=from_email,
                subject=subject,
                body_plain=body_plain,
                site_id=site_id,
            )
            result.agent_latency_ms = int((time.monotonic() - t0) * 1000)
            return result

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        *,
        from_name: Optional[str],
        from_email: str,
        subject: str,
        body_plain: Optional[str],
        site_id: Optional[str],
        bms_context: Optional[dict[str, Any]],
    ) -> str:
        taxonomy = _build_taxonomy_reference()

        bms_section = ""
        if bms_context:
            parts: list[str] = []
            if bms_context.get("building_name"):
                parts.append(f"Building: {bms_context['building_name']}")
            alerts = bms_context.get("active_alerts", [])
            if alerts:
                alert_lines = [f"  - [{a.get('severity', 'info').upper()}] {a.get('message', '')}" for a in alerts[:5]]
                parts.append("Active Alerts:\n" + "\n".join(alert_lines))
            wos = bms_context.get("recent_work_orders", [])
            if wos:
                wo_lines = [f"  - {w.get('code', '')} {w.get('title', '')} ({w.get('status', '')})" for w in wos[:3]]
                parts.append("Recent Work Orders:\n" + "\n".join(wo_lines))
            health = bms_context.get("equipment_health")
            if health:
                parts.append(f"Equipment at risk: {health.get('at_risk_count', 0)}")
            if parts:
                bms_section = "\n\n## Current Building Context\n" + "\n".join(parts)

        return f"""\
You are a facilities management email triage agent for SENTINEL, \
an AI-powered building management system in South Africa.

Your task: Analyse the inbound email and return a JSON object with \
classification, location extraction, completeness score, and reply.

## Fixed Taxonomy (47 categories)
Classify into one of these disciplines and sub-categories. \
If nothing matches, use discipline="General", sub_category="Unclassified".
{taxonomy}

## Classification Rules
- Match the most specific sub-category that fits the email.
- If multiple categories match, choose the one with the most keywords.
- Use the default priority unless email describes an emergency or \
safety hazard (escalate to "high" or "critical").
- Escalation keywords: fire, smoke, gas, trapped, flooding, sparking, \
danger, unsafe, emergency, urgent, immediately, burst, pouring, hazard.
- "specialty" must match the taxonomy entry's specialty value.

## Location Extraction
- Look for desk numbers (e.g. "desk 204", "my desk 302", "near desk 15").
- Look for floor references (e.g. "Level 2", "L1", "ground floor", "basement").
- Look for named areas (e.g. "kitchen", "boardroom", "reception", "parking").
- Desk-to-floor convention: 001-099=L0 (Ground), 100-199=L1, 200-299=L2.
- Extract SA phone numbers: 0XX XXX XXXX or +27XXXXXXXXX.

## Completeness Scoring
Score 0.0-1.0 based on available information:
- Has specific category (not General): +0.30
- Has location (desk/floor/area): +0.25
- Has contact info (phone): +0.10
- Has clear description of the problem: +0.20
- Has time/when info: +0.05
- Has requester name: +0.10

Routing:
- completeness >= 0.85: action = "auto_submit"
- completeness >= 0.60: action = "request_info"
- completeness < 0.60: action = "manual_review"

## Reply Guidelines
- Write a concise, professional, context-aware reply as if from SENTINEL Building Management.
- Address the sender by first name if available.
- If action is "auto_submit": Confirm issue logged, team notified. \
Use placeholder {{{{ref}}}} for work order reference.
- If action is "request_info": Acknowledge issue, mention what info \
is missing (only things NOT already provided), ask specifically.
- If action is "manual_review": Thank them and explain a facilities coordinator will review shortly.
- Never fabricate work order numbers — use {{{{ref}}}} as placeholder.
- Use South African English conventions.
- Keep the reply under 150 words.
- Sign off as "Kind regards,\\nSENTINEL Building Management"
{bms_section}

## Email to Classify
From: {from_name or "Unknown"} <{from_email}>
Subject: {subject}
Body:
{(body_plain or "(no body)")[:3000]}

## Required JSON Response
Respond with ONLY a JSON object (no markdown, no explanation):
{{
  "discipline": "string",
  "sub_category": "string",
  "specialty": "string",
  "priority": "low|medium|high|critical",
  "location_desk": "string or null",
  "location_floor": "string or null",
  "location_area": "string or null",
  "phone": "string or null",
  "issue_summary": "One-line summary of the issue",
  "completeness": 0.0,
  "action": "auto_submit|request_info|manual_review",
  "reply_text": "The full reply text"
}}"""

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> tuple[str, str]:
        """OpenAI → Claude → raise. Returns (response_text, model_name)."""
        # Try OpenAI first
        if self._api_key:
            try:
                text = await self._call_openai(prompt)
                return text, self._model
            except Exception as exc:
                logger.error(
                    "OpenAI call failed (model=%s): %s — trying Claude fallback",
                    self._model,
                    exc,
                )

        # Try Claude fallback
        claude_model = settings.claude_model or "claude-haiku-4-5-20251001"
        try:
            text = await self._call_claude(prompt)
            return text, f"claude:{claude_model}"
        except Exception as exc:
            raise RuntimeError(f"All LLM providers failed. Last error: {exc}") from exc

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI chat completions API."""
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a JSON-only facilities management "
                    "email triage agent. Respond with valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 1000,
        }

        async with httpx.AsyncClient(timeout=float(self._timeout)) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        body = response.json()
        choices = body.get("choices", [])
        if not choices:
            raise RuntimeError("OpenAI returned no choices")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise RuntimeError("OpenAI returned empty content")

        logger.info("Agent LLM response from %s (%d chars)", self._model, len(content))
        return content

    async def _call_claude(self, prompt: str) -> str:
        """Call Claude via Anthropic API as fallback."""
        api_key = settings.anthropic_api_key
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")

        claude_model = settings.claude_model or "claude-haiku-4-5-20251001"
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": claude_model,
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}],
            "system": "You are a JSON-only facilities management email triage agent. Respond with valid JSON only.",
        }

        async with httpx.AsyncClient(timeout=float(self._timeout)) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

        body = response.json()
        content_blocks = body.get("content", [])
        text = ""
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")
        if not text:
            raise RuntimeError("Claude returned empty content")

        logger.info("Agent LLM response from Claude/%s (%d chars)", claude_model, len(text))
        return text

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, response_text: str) -> dict:
        """Extract JSON from LLM response (handle ```json blocks)."""
        text = response_text.strip()

        # Try to extract JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if json_match:
            text = json_match.group(1).strip()

        # Try to find JSON object
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            text = text[brace_start : brace_end + 1]

        return json.loads(text)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self, parsed: dict, *, used_model: str) -> AgentResult:
        """Validate discipline/sub_category against taxonomy, clamp values."""
        discipline = parsed.get("discipline", "General")
        sub_category = parsed.get("sub_category", "Unclassified")
        specialty = parsed.get("specialty", "general")
        priority = parsed.get("priority", "medium")

        # Validate discipline
        if discipline not in _VALID_DISCIPLINES and discipline != "General":
            logger.warning("Agent returned invalid discipline: %s", discipline)
            discipline = "General"
            sub_category = "Unclassified"

        # Validate sub_category belongs to discipline
        if discipline != "General" and (discipline, sub_category) not in _VALID_SUB_CATEGORIES:
            logger.warning("Agent returned invalid sub_category: %s/%s", discipline, sub_category)
            # Find valid sub_categories for this discipline
            valid_subs = [e for e in CALL_LOG_TAXONOMY if e["discipline"] == discipline]
            if valid_subs:
                sub_category = valid_subs[0]["sub_category"]
                specialty = valid_subs[0]["specialty"]
            else:
                discipline = "General"
                sub_category = "Unclassified"

        # Validate priority
        if priority not in _VALID_PRIORITIES:
            priority = "medium"

        # Clamp completeness
        completeness = max(0.0, min(1.0, float(parsed.get("completeness", 0.0))))

        # Validate action
        action = parsed.get("action", "manual_review")
        if action not in _VALID_ACTIONS:
            action = "manual_review"

        # Re-derive action from completeness (don't trust LLM's action blindly)
        if completeness >= 0.85:
            action = "auto_submit"
        elif completeness >= 0.60:
            action = "request_info"
        else:
            action = "manual_review"

        return AgentResult(
            discipline=discipline,
            sub_category=sub_category,
            specialty=specialty,
            priority=priority,
            location_desk=parsed.get("location_desk"),
            location_floor=parsed.get("location_floor"),
            location_area=parsed.get("location_area"),
            phone=parsed.get("phone"),
            issue_summary=parsed.get("issue_summary", ""),
            completeness=completeness,
            action=action,
            reply_text=parsed.get("reply_text", ""),
            # Track exactly which model produced this result
            agent_model=used_model,
        )

    # ------------------------------------------------------------------
    # Keyword fallback
    # ------------------------------------------------------------------

    def _keyword_fallback(
        self,
        *,
        from_name: Optional[str],
        from_email: str,
        subject: str,
        body_plain: Optional[str],
        site_id: Optional[str],
    ) -> AgentResult:
        """Existing keyword pipeline as fallback."""
        combined = f"{subject} {body_plain or ''}"

        # Classify
        tax = classify_email_subject(subject, body_plain or "")
        if tax:
            discipline = tax["discipline"]
            sub_category = tax["sub_category"]
            specialty = tax["specialty"]
            priority = tax["priority"]
        else:
            discipline = "General"
            sub_category = "Unclassified"
            specialty = "general"
            priority = "medium"

        # Location extraction
        desk = extract_desk_from_message(combined)
        floor = extract_floor_from_message(combined)
        area = extract_area_from_message(combined)

        # Phone extraction
        phone = None
        phone_match = re.search(r"\b(0\d{9})\b", combined)
        if not phone_match:
            phone_match = re.search(r"\b(\+27\d{9})\b", combined)
        if phone_match:
            phone = phone_match.group(1)

        # Completeness scoring
        completeness = 0.0
        if discipline != "General":
            completeness += 0.30
        if desk or floor or area:
            completeness += 0.25
        if phone:
            completeness += 0.10
        if body_plain and len(body_plain.strip()) > 20:
            completeness += 0.20
        if from_name:
            completeness += 0.10
        completeness = min(1.0, round(completeness, 2))

        # Route
        if completeness >= 0.85:
            action = "auto_submit"
        elif completeness >= 0.60:
            action = "request_info"
        else:
            action = "manual_review"

        # Build template reply
        category = DISCIPLINE_TO_CATEGORY.get(discipline, "general")
        greeting = f"Dear {from_name}," if from_name else "Dear Tenant,"
        if action == "auto_submit":
            reply_text = (
                f"{greeting}\n\n"
                f"Thank you for reporting this {category} issue. "
                f"Reference: {{ref}}. "
                f"Our {specialty} team has been notified and will attend to it.\n\n"
                "Kind regards,\n"
                "SENTINEL Building Management"
            )
        elif action == "request_info":
            missing: list[str] = []
            if not desk and not floor and not area:
                missing.append("specific location (floor/desk/room)")
            if not phone:
                missing.append("contact phone number")
            missing_text = " and ".join(missing) if missing else "additional details"
            reply_text = (
                f"{greeting}\n\n"
                f"Thank you for reporting this {category} issue. "
                f"Reference: {{ref}}.\n\n"
                f"To help us respond quickly, could you please provide your {missing_text}?\n\n"
                "Kind regards,\n"
                "SENTINEL Building Management"
            )
        else:
            reply_text = (
                f"{greeting}\n\n"
                "Thank you for your message. A facilities coordinator will review "
                "your request shortly and get back to you.\n\n"
                "Kind regards,\n"
                "SENTINEL Building Management"
            )

        result = AgentResult(
            discipline=discipline,
            sub_category=sub_category,
            specialty=specialty,
            priority=priority,
            location_desk=desk,
            location_floor=floor,
            location_area=area,
            phone=phone,
            issue_summary=subject,
            completeness=completeness,
            action=action,
            reply_text=reply_text,
            agent_model="keyword_fallback",
        )
        result.reply_html = self._wrap_html(
            reply_text,
            ref="{ref}",
            category=category,
            from_name=from_name or "",
        )
        return result

    # ------------------------------------------------------------------
    # HTML reply wrapper
    # ------------------------------------------------------------------

    def _wrap_html(
        self,
        reply_text: str,
        ref: str,
        category: str,
        from_name: str,
    ) -> str:
        """Wrap plain text reply in SENTINEL branded HTML template."""
        cat_colours = {
            "hvac": "#2563eb",
            "electrical": "#d97706",
            "plumbing": "#0891b2",
            "fire": "#dc2626",
            "lighting": "#7c3aed",
            "access": "#059669",
            "elevator": "#6366f1",
            "pest": "#84cc16",
            "structural": "#78716c",
            "general": "#6b7280",
        }
        badge_colour = cat_colours.get(category, "#6b7280")

        # Convert plain text to HTML paragraphs
        body_html = ""
        for para in reply_text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            escaped = _esc(para).replace("\n", "<br>")
            body_html += f"<p>{escaped}</p>"

        return (
            "<!DOCTYPE html>"
            '<html><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
            '</head><body style="margin:0;padding:0;font-family:Arial,Helvetica,sans-serif;'
            'background:#f3f4f6;">'
            '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;">'
            '<tr><td align="center" style="padding:24px 16px;">'
            '<table width="600" cellpadding="0" cellspacing="0" '
            'style="background:#ffffff;border-radius:8px;overflow:hidden;'
            'box-shadow:0 1px 3px rgba(0,0,0,0.1);">'
            # Header bar
            '<tr><td style="background:#1e3a5f;padding:20px 24px;">'
            '<table width="100%" cellpadding="0" cellspacing="0"><tr>'
            '<td style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:1px;">'
            "SENTINEL</td>"
            '<td align="right" style="color:#94a3b8;font-size:12px;">'
            "Building Intelligence</td>"
            "</tr></table></td></tr>"
            # Reference banner
            '<tr><td style="background:#f0f9ff;padding:14px 24px;'
            'border-bottom:1px solid #e0f2fe;">'
            '<table width="100%" cellpadding="0" cellspacing="0"><tr>'
            f'<td style="font-size:14px;color:#1e3a5f;font-weight:600;">'
            f"Reference: {_esc(ref)}</td>"
            f'<td align="right"><span style="display:inline-block;padding:3px 10px;'
            f"background:{badge_colour};color:#ffffff;border-radius:12px;"
            f'font-size:11px;font-weight:600;text-transform:uppercase;">'
            f"{_esc(category)}</span></td>"
            "</tr></table></td></tr>"
            # Body
            '<tr><td style="padding:24px;color:#374151;font-size:14px;line-height:1.6;">'
            f"{body_html}"
            "</td></tr>"
            # Footer
            '<tr><td style="background:#f9fafb;padding:16px 24px;'
            "border-top:1px solid #e5e7eb;font-size:12px;color:#6b7280;"
            'line-height:1.5;">'
            '<p style="margin:0 0 4px;font-weight:600;color:#1e3a5f;">SENTINEL Building Management</p>'
            '<p style="margin:0;">This is an automated message from the SENTINEL '
            "building management system. Please reply to this email if you have "
            "additional information to share.</p>"
            "</td></tr>"
            "</table></td></tr></table></body></html>"
        )


def _esc(text: str) -> str:
    """Minimal HTML escaping."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_agent: Optional[EmailIntakeAgent] = None


def get_email_intake_agent() -> EmailIntakeAgent:
    """Get or create singleton EmailIntakeAgent."""
    global _agent
    if _agent is None:
        _agent = EmailIntakeAgent()
    return _agent
