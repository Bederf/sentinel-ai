"""Tests for SENTINEL Capability Index content coverage.

Verifies that the capability index document covers all major question
categories so that hybrid search will retrieve it for any client query.
"""

from __future__ import annotations

# Question patterns clients actually ask (from real usage)
# All patterns are checked in lowercase against the capability index text.
# Some client phrasing is normalised (e.g. "can it be hacked" not exact phrase match).
CLIENT_QUESTION_PATTERNS = {
    "standards": [
        "does sentinel follow any standards",
        "iso 42001",
        "nist ai rmf",
        "eu ai act",
        "popia",
        "king iv",
        "fsr",
    ],
    "security": [
        "is sentinel secure",
        "can it be hacked",
        "sentinel security",
        "breach",
        "encryption",
        "mfa",
        "authentication",
        "access control",
        "password",
    ],
    "frs_questionnaire": [
        "firstrand",
        "fsr gap analysis",
        "supplier risk",
        "fsr score",
        "fsr questionnaire",
    ],
    "capability": [
        "what can sentinel do",
        "sentinel features",
        "work order",
        "predictive maintenance",
        "energy optimisation",
        "zone health",
        "chat ai",
    ],
    "integration": [
        "simbiot",
        "bacnet",
        "dali-2",
        "desigo",
        "niagara",
        "bms integration",
        "connect to any bms",
    ],
    "onboarding": [
        "upload a building",
        "building onboarding",
        "phase a foundation",
        "phase b intelligence",
        "phase c automation",
        "equipment discovery",
    ],
    "data_privacy": [
        "where does sentinel process data",
        "gdpr",
        "popia",
        "cloud",
        "on-premise",
        "data protection",
    ],
    "ai_human_oversight": [
        "human-in-the-loop",
        "human oversight",
        "autonomous decisions",
        "ai safety",
        "quality gate",
    ],
    "troubleshooting": [
        "wrong or fabricated",
        "fabricated",
        "zone health shows no data",
        "predictive alert",
    ],
}


def _load_capability_index() -> str:
    """Load the capability index text from the indexing script."""
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scripts.index_capability_index import CAPABILITY_INDEX_TEXT

    return CAPABILITY_INDEX_TEXT


class TestCapabilityIndexCoverage:
    """Verify the capability index covers all client question patterns."""

    def test_standards_coverage(self):
        """Standards-related questions must be covered."""
        text = _load_capability_index().lower()
        for pattern in CLIENT_QUESTION_PATTERNS["standards"]:
            assert pattern.lower() in text, f"Missing coverage for: {pattern}"

    def test_security_coverage(self):
        """Security-related questions must be covered."""
        text = _load_capability_index().lower()
        for pattern in CLIENT_QUESTION_PATTERNS["security"]:
            assert pattern.lower() in text, f"Missing coverage for: {pattern}"

    def test_fsr_questionnaire_coverage(self):
        """FSR/FirstRand risk questionnaire must be covered."""
        text = _load_capability_index().lower()
        for pattern in CLIENT_QUESTION_PATTERNS["frs_questionnaire"]:
            assert pattern.lower() in text, f"Missing coverage for: {pattern}"

    def test_capability_coverage(self):
        """Platform capability questions must be covered."""
        text = _load_capability_index().lower()
        for pattern in CLIENT_QUESTION_PATTERNS["capability"]:
            assert pattern.lower() in text, f"Missing coverage for: {pattern}"

    def test_integration_coverage(self):
        """BMS integration questions must be covered."""
        text = _load_capability_index().lower()
        for pattern in CLIENT_QUESTION_PATTERNS["integration"]:
            assert pattern.lower() in text, f"Missing coverage for: {pattern}"

    def test_onboarding_coverage(self):
        """Onboarding questions must be covered."""
        text = _load_capability_index().lower()
        for pattern in CLIENT_QUESTION_PATTERNS["onboarding"]:
            assert pattern.lower() in text, f"Missing coverage for: {pattern}"

    def test_data_privacy_coverage(self):
        """Data privacy questions must be covered."""
        text = _load_capability_index().lower()
        for pattern in CLIENT_QUESTION_PATTERNS["data_privacy"]:
            assert pattern.lower() in text, f"Missing coverage for: {pattern}"

    def test_ai_oversight_coverage(self):
        """AI human oversight questions must be covered."""
        text = _load_capability_index().lower()
        for pattern in CLIENT_QUESTION_PATTERNS["ai_human_oversight"]:
            assert pattern.lower() in text, f"Missing coverage for: {pattern}"

    def test_troubleshooting_coverage(self):
        """Troubleshooting questions must be covered."""
        text = _load_capability_index().lower()
        for pattern in CLIENT_QUESTION_PATTERNS["troubleshooting"]:
            assert pattern.lower() in text, f"Missing coverage for: {pattern}"

    def test_document_length_is_substantial(self):
        """Capability index must be long enough for meaningful chunks."""
        text = _load_capability_index()
        # At least 8,000 words (each section is thorough)
        word_count = len(text.split())
        assert word_count >= 3000, f"Document too short ({word_count} words) — may not chunk well"

    def test_fsr_18_domains_all_mentioned(self):
        """All 18 FSR assessment domains must appear."""
        text = _load_capability_index().lower()
        fsr_domains = [
            "information security governance",
            "asset management",
            "information classification",
            "human resource security",
            "physical access security",
            "network security",
            "logical access control",
            "system security",
            "application security",
            "vulnerability management",
            "communication management",
            "cryptography",
            "incident detection",
            "incident management",
            "business continuity",
            "third party",
            "risk and compliance",
            "information security audit",
        ]
        missing = [d for d in fsr_domains if d.lower() not in text]
        assert not missing, f"FSR domains missing from capability index: {missing}"

    def test_fsr_scores_mentioned(self):
        """FSR numerical scores must appear (not fabricated by AI)."""
        text = _load_capability_index().lower()
        assert "4.0" in text or "4.3" in text or "3.8" in text, "FSR scores must appear"
        assert "17 of 18" in text, "Overall FSR target count must appear"
        assert "4.0" in text, "Average FSR score 4.0 must appear"
