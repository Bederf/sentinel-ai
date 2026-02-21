"""
MCP Tool Registry Completeness Tests (C3).

Ensures every tool in the SIMBIOT MCP server has a corresponding entry in
the security registry, tool permissions, and handler map.

Run: pytest tests/api/test_mcp_registry_completeness.py -v
"""

import re


def _get_server():
    """Create a fresh SIMBIOTMCPServer instance."""
    from app.mcp.simbiot_server import SIMBIOTMCPServer

    return SIMBIOTMCPServer()


def _get_tool_names():
    """Get all tool names from the server."""
    server = _get_server()
    return {t["name"] for t in server.tools}


def _get_registry():
    """Get the security registry."""
    from app.mcp.tool_security_registry import TOOL_REGISTRY

    return TOOL_REGISTRY


class TestRegistryCompleteness:
    """Every tool must be registered in the security registry."""

    def test_all_tools_have_security_profile(self):
        """Every tool in the server must have a ToolSecurityProfile."""
        tool_names = _get_tool_names()
        registry = _get_registry()
        missing = tool_names - set(registry.keys())
        assert not missing, (
            f"Tools missing from tool_security_registry.py: {sorted(missing)}. "
            f"See docs/MCP_TOOL_ONBOARDING.md for onboarding checklist."
        )

    def test_registry_has_no_orphans(self):
        """Registry should not contain entries for non-existent tools."""
        tool_names = _get_tool_names()
        registry = _get_registry()
        orphans = set(registry.keys()) - tool_names
        assert not orphans, (
            f"Registry contains entries for non-existent tools: {sorted(orphans)}. "
            f"Remove stale entries from tool_security_registry.py."
        )

    def test_all_tools_have_handlers(self):
        """Every tool definition must have a corresponding handler."""
        server = _get_server()
        tool_names = {t["name"] for t in server.tools}
        handler_names = set(server.tool_handlers.keys())
        missing = tool_names - handler_names
        assert (
            not missing
        ), f"Tools missing handlers: {sorted(missing)}. Add handler functions to SIMBIOTMCPServer.__init__."


class TestMutatingToolConsistency:
    """Mutating tools must have permission entries."""

    def test_mutating_tools_in_module_requirements(self):
        """Every mutating tool in the registry must be in MCP_TOOL_MODULE_REQUIREMENTS."""
        from app.mcp.tool_permissions import MCP_TOOL_MODULE_REQUIREMENTS

        registry = _get_registry()
        mutating = {name for name, p in registry.items() if p.mutating}
        missing = mutating - set(MCP_TOOL_MODULE_REQUIREMENTS.keys())
        assert not missing, f"Mutating tools missing from MCP_TOOL_MODULE_REQUIREMENTS: {sorted(missing)}"

    def test_mutating_tools_in_min_role(self):
        """Every mutating tool in the registry must be in MCP_TOOL_MIN_ROLE."""
        from app.mcp.tool_permissions import MCP_TOOL_MIN_ROLE

        registry = _get_registry()
        mutating = {name for name, p in registry.items() if p.mutating}
        missing = mutating - set(MCP_TOOL_MIN_ROLE.keys())
        assert not missing, f"Mutating tools missing from MCP_TOOL_MIN_ROLE: {sorted(missing)}"

    def test_high_risk_tools_consistency(self):
        """Every high_risk tool in the registry must be in HIGH_RISK_TOOLS."""
        from app.mcp.tool_permissions import HIGH_RISK_TOOLS

        registry = _get_registry()
        high_risk_in_registry = {name for name, p in registry.items() if p.high_risk}
        missing = high_risk_in_registry - HIGH_RISK_TOOLS
        assert not missing, f"High-risk tools in registry but not in HIGH_RISK_TOOLS: {sorted(missing)}"
        extra = HIGH_RISK_TOOLS - high_risk_in_registry
        assert not extra, f"Tools in HIGH_RISK_TOOLS but not marked high_risk in registry: {sorted(extra)}"

    def test_mutating_tools_set_matches_registry(self):
        """MUTATING_TOOLS set must match registry mutating flags."""
        from app.mcp.tool_permissions import MUTATING_TOOLS

        registry = _get_registry()
        mutating_in_registry = {name for name, p in registry.items() if p.mutating}
        assert mutating_in_registry == MUTATING_TOOLS, (
            f"MUTATING_TOOLS mismatch. "
            f"In MUTATING_TOOLS but not registry: {MUTATING_TOOLS - mutating_in_registry}. "
            f"In registry but not MUTATING_TOOLS: {mutating_in_registry - MUTATING_TOOLS}."
        )


class TestToolDescriptionQuality:
    """Tool descriptions must be concise and free of internal details."""

    def test_descriptions_max_two_sentences(self):
        """Tool descriptions should be at most 2 sentences."""
        server = _get_server()
        violations = []
        for tool in server.tools:
            desc = tool.get("description", "")
            # Count sentences by splitting on '. ' (period + space) patterns
            # This is approximate but catches obvious over-sharing
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", desc) if s.strip()]
            if len(sentences) > 2:
                violations.append(f"  {tool['name']}: {len(sentences)} sentences")
        assert not violations, "Tool descriptions exceed 2 sentences (C5):\n" + "\n".join(violations)

    def test_descriptions_no_internal_paths(self):
        """Tool descriptions must not expose internal file paths."""
        server = _get_server()
        violations = []
        for tool in server.tools:
            desc = tool.get("description", "")
            # Check for common internal path patterns
            if re.search(r"[./]json\b", desc, re.IGNORECASE):
                violations.append(f"  {tool['name']}: references .json file")
            if re.search(r"/app/|/opt/|/home/", desc):
                violations.append(f"  {tool['name']}: contains absolute path")
            if re.search(r"\.py\b", desc):
                violations.append(f"  {tool['name']}: references .py file")
        assert not violations, "Tool descriptions expose internal details (C5):\n" + "\n".join(violations)

    def test_all_tools_have_input_schema(self):
        """Every tool must define an input_schema (or inputSchema for registry tools)."""
        server = _get_server()
        missing = [t["name"] for t in server.tools if "input_schema" not in t and "inputSchema" not in t]
        assert not missing, f"Tools missing input_schema: {sorted(missing)}"
