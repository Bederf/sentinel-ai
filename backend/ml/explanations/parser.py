"""Parser for extracting structured data from LLM explanation output.

Parses the formatted output from explanation templates into structured
dictionaries that can be used in the UI or stored in the database.
"""

import re
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class ActionPriority(str, Enum):
    """Priority levels for recommended actions."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class RecommendedAction:
    """A recommended maintenance action."""
    action: str
    priority: ActionPriority = ActionPriority.MEDIUM

    def to_dict(self) -> dict:
        return {"action": self.action, "priority": self.priority.value}


@dataclass
class PartNeeded:
    """A part needed for maintenance."""
    name: str
    quantity: Optional[str] = None
    part_number: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "quantity": self.quantity,
            "part_number": self.part_number
        }


@dataclass
class ParsedExplanation:
    """Structured explanation parsed from LLM output."""
    summary: str = ""
    key_factors: List[str] = field(default_factory=list)
    recommended_actions: List[RecommendedAction] = field(default_factory=list)
    parts_needed: List[PartNeeded] = field(default_factory=list)
    labor_estimate: str = ""
    additional_notes: str = ""
    raw_text: str = ""
    parse_success: bool = True
    parse_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "key_factors": self.key_factors,
            "recommended_actions": [a.to_dict() for a in self.recommended_actions],
            "parts_needed": [p.to_dict() for p in self.parts_needed],
            "labor_estimate": self.labor_estimate,
            "additional_notes": self.additional_notes,
            "parse_success": self.parse_success,
            "parse_errors": self.parse_errors
        }


@dataclass
class ParsedRecommendation:
    """Structured recommendation parsed from maintenance template."""
    immediate_actions: List[str] = field(default_factory=list)
    scheduled_maintenance: List[Dict[str, str]] = field(default_factory=list)
    preventive_measures: List[str] = field(default_factory=list)
    spare_parts: List[PartNeeded] = field(default_factory=list)
    technician_skills: List[str] = field(default_factory=list)
    estimated_downtime: str = ""
    raw_text: str = ""
    parse_success: bool = True
    parse_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "immediate_actions": self.immediate_actions,
            "scheduled_maintenance": self.scheduled_maintenance,
            "preventive_measures": self.preventive_measures,
            "spare_parts": [p.to_dict() for p in self.spare_parts],
            "technician_skills": self.technician_skills,
            "estimated_downtime": self.estimated_downtime,
            "parse_success": self.parse_success,
            "parse_errors": self.parse_errors
        }


class ExplanationParser:
    """Parser for LLM-generated explanations and recommendations."""

    # Section markers from templates
    EXPLANATION_SECTIONS = [
        "SUMMARY",
        "KEY_FACTORS",
        "RECOMMENDED_ACTIONS",
        "PARTS_NEEDED",
        "LABOR_ESTIMATE",
        "ADDITIONAL_NOTES"
    ]

    RECOMMENDATION_SECTIONS = [
        "IMMEDIATE_ACTIONS",
        "SCHEDULED_MAINTENANCE",
        "PREVENTIVE_MEASURES",
        "SPARE_PARTS",
        "TECHNICIAN_SKILLS",
        "ESTIMATED_DOWNTIME"
    ]

    @classmethod
    def parse_explanation(cls, text: str) -> ParsedExplanation:
        """Parse LLM output from prediction explanation template.

        Args:
            text: Raw LLM output text

        Returns:
            ParsedExplanation with structured fields
        """
        result = ParsedExplanation(raw_text=text)

        try:
            sections = cls._extract_sections(text, cls.EXPLANATION_SECTIONS)

            # Parse summary
            result.summary = cls._clean_text(sections.get("SUMMARY", ""))

            # Parse key factors
            result.key_factors = cls._parse_list_items(sections.get("KEY_FACTORS", ""))

            # Parse recommended actions with priorities
            result.recommended_actions = cls._parse_actions(
                sections.get("RECOMMENDED_ACTIONS", "")
            )

            # Parse parts needed
            result.parts_needed = cls._parse_parts(sections.get("PARTS_NEEDED", ""))

            # Parse labor estimate
            result.labor_estimate = cls._clean_text(sections.get("LABOR_ESTIMATE", ""))

            # Parse additional notes
            result.additional_notes = cls._clean_text(sections.get("ADDITIONAL_NOTES", ""))

            # Validate we got meaningful content
            if not result.summary and not result.recommended_actions:
                result.parse_success = False
                result.parse_errors.append("Could not extract summary or actions")

        except Exception as e:
            logger.error(f"Error parsing explanation: {e}")
            result.parse_success = False
            result.parse_errors.append(str(e))

        return result

    @classmethod
    def parse_recommendation(cls, text: str) -> ParsedRecommendation:
        """Parse LLM output from maintenance recommendation template.

        Args:
            text: Raw LLM output text

        Returns:
            ParsedRecommendation with structured fields
        """
        result = ParsedRecommendation(raw_text=text)

        try:
            sections = cls._extract_sections(text, cls.RECOMMENDATION_SECTIONS)

            # Parse immediate actions
            result.immediate_actions = cls._parse_list_items(
                sections.get("IMMEDIATE_ACTIONS", "")
            )

            # Parse scheduled maintenance with timeline
            result.scheduled_maintenance = cls._parse_scheduled_items(
                sections.get("SCHEDULED_MAINTENANCE", "")
            )

            # Parse preventive measures
            result.preventive_measures = cls._parse_list_items(
                sections.get("PREVENTIVE_MEASURES", "")
            )

            # Parse spare parts with details
            result.spare_parts = cls._parse_detailed_parts(
                sections.get("SPARE_PARTS", "")
            )

            # Parse technician skills
            result.technician_skills = cls._parse_list_items(
                sections.get("TECHNICIAN_SKILLS", "")
            )

            # Parse estimated downtime
            result.estimated_downtime = cls._clean_text(
                sections.get("ESTIMATED_DOWNTIME", "")
            )

        except Exception as e:
            logger.error(f"Error parsing recommendation: {e}")
            result.parse_success = False
            result.parse_errors.append(str(e))

        return result

    @classmethod
    def _extract_sections(cls, text: str, section_names: List[str]) -> Dict[str, str]:
        """Extract named sections from text.

        Args:
            text: Raw text to parse
            section_names: List of section names to look for

        Returns:
            Dictionary mapping section names to their content
        """
        sections = {}

        # Build pattern to find section headers
        # Match: ### SECTION_NAME or ## SECTION_NAME or **SECTION_NAME**
        for section in section_names:
            # Try different header formats
            patterns = [
                rf"###\s*{section}\s*\n(.*?)(?=###|$)",
                rf"##\s*{section}\s*\n(.*?)(?=##|$)",
                rf"\*\*{section}\*\*\s*\n(.*?)(?=\*\*[A-Z_]+\*\*|$)",
                rf"{section}:\s*\n(.*?)(?=[A-Z_]+:|$)"
            ]

            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    sections[section] = match.group(1).strip()
                    break

        return sections

    @classmethod
    def _clean_text(cls, text: str) -> str:
        """Clean extracted text.

        Args:
            text: Text to clean

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Remove markdown artifacts
        text = re.sub(r'\[([^\]]+)\]', r'\1', text)  # [text] -> text
        text = re.sub(r'\*+', '', text)  # Remove asterisks

        # Clean whitespace
        text = ' '.join(text.split())

        return text.strip()

    @classmethod
    def _parse_list_items(cls, text: str) -> List[str]:
        """Parse bulleted list items from text.

        Args:
            text: Text containing list items

        Returns:
            List of extracted items
        """
        if not text:
            return []

        items = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            # Match lines starting with -, *, or numbers
            match = re.match(r'^[\-\*\d\.]+\s*(.+)', line)
            if match:
                item = cls._clean_text(match.group(1))
                if item and item.lower() not in ['none', 'n/a', 'none anticipated']:
                    items.append(item)

        return items

    @classmethod
    def _parse_actions(cls, text: str) -> List[RecommendedAction]:
        """Parse recommended actions with priorities.

        Args:
            text: Text containing action items

        Returns:
            List of RecommendedAction objects
        """
        if not text:
            return []

        actions = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Match: - [PRIORITY] Action text
            match = re.match(r'^[\-\*]\s*\[?(HIGH|MEDIUM|LOW)\]?\s*(.+)', line, re.IGNORECASE)
            if match:
                priority_str = match.group(1).upper()
                action_text = cls._clean_text(match.group(2))

                try:
                    priority = ActionPriority(priority_str)
                except ValueError:
                    priority = ActionPriority.MEDIUM

                if action_text:
                    actions.append(RecommendedAction(action=action_text, priority=priority))
            else:
                # Try matching without priority marker
                match = re.match(r'^[\-\*\d\.]+\s*(.+)', line)
                if match:
                    action_text = cls._clean_text(match.group(1))
                    if action_text and action_text.lower() not in ['none', 'n/a']:
                        actions.append(RecommendedAction(
                            action=action_text,
                            priority=ActionPriority.MEDIUM
                        ))

        return actions

    @classmethod
    def _parse_parts(cls, text: str) -> List[PartNeeded]:
        """Parse parts needed list.

        Args:
            text: Text containing parts list

        Returns:
            List of PartNeeded objects
        """
        if not text:
            return []

        parts = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Match: - Part name (quantity)
            match = re.match(r'^[\-\*]\s*(.+?)(?:\s*\(([^)]+)\))?\s*$', line)
            if match:
                name = cls._clean_text(match.group(1))
                quantity = match.group(2) if match.group(2) else None

                if name and name.lower() not in ['none', 'n/a', 'none anticipated']:
                    parts.append(PartNeeded(name=name, quantity=quantity))

        return parts

    @classmethod
    def _parse_scheduled_items(cls, text: str) -> List[Dict[str, str]]:
        """Parse scheduled maintenance items with timeline.

        Args:
            text: Text containing scheduled items

        Returns:
            List of dicts with 'timeline' and 'action' keys
        """
        if not text:
            return []

        items = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Match: - [Timeline] Action
            match = re.match(r'^[\-\*]\s*\[([^\]]+)\]\s*(.+)', line)
            if match:
                items.append({
                    "timeline": cls._clean_text(match.group(1)),
                    "action": cls._clean_text(match.group(2))
                })
            else:
                # Try without timeline brackets
                match = re.match(r'^[\-\*]\s*(.+)', line)
                if match:
                    action = cls._clean_text(match.group(1))
                    if action and action.lower() not in ['none', 'n/a']:
                        items.append({
                            "timeline": "As scheduled",
                            "action": action
                        })

        return items

    @classmethod
    def _parse_detailed_parts(cls, text: str) -> List[PartNeeded]:
        """Parse parts with full details (name | part number | quantity).

        Args:
            text: Text containing parts details

        Returns:
            List of PartNeeded objects
        """
        if not text:
            return []

        parts = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Match: - Name | Part Number | Quantity
            match = re.match(r'^[\-\*]\s*(.+)', line)
            if match:
                content = match.group(1)
                segments = [s.strip() for s in content.split('|')]

                if segments and segments[0].lower() not in ['none', 'n/a']:
                    part = PartNeeded(
                        name=cls._clean_text(segments[0]),
                        part_number=cls._clean_text(segments[1]) if len(segments) > 1 else None,
                        quantity=cls._clean_text(segments[2]) if len(segments) > 2 else None
                    )
                    parts.append(part)

        return parts


def parse_llm_explanation(text: str) -> Dict[str, Any]:
    """Convenience function to parse explanation and return dict.

    Args:
        text: Raw LLM output text

    Returns:
        Dictionary with parsed explanation fields
    """
    return ExplanationParser.parse_explanation(text).to_dict()


def parse_llm_recommendation(text: str) -> Dict[str, Any]:
    """Convenience function to parse recommendation and return dict.

    Args:
        text: Raw LLM output text

    Returns:
        Dictionary with parsed recommendation fields
    """
    return ExplanationParser.parse_recommendation(text).to_dict()
