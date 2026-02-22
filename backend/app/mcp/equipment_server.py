"""
MCP Server for Equipment Lookup Tools

Provides tools for AI chat integration with equipment fault code lookup,
parts search, and natural language equipment issue resolution.

Usage:
    from app.mcp import EquipmentMCPServer

    server = EquipmentMCPServer()
    result = await server.call_tool("lookup_fault_code", manufacturer="Carrier", fault_code="E4")
"""

from typing import Optional, Dict, List, Any
import logging

from app.services.equipment_lookup import EquipmentLookup

logger = logging.getLogger(__name__)

# Singleton lookup instance
_lookup_instance: Optional[EquipmentLookup] = None


def get_lookup() -> EquipmentLookup:
    """Get or create EquipmentLookup singleton."""
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = EquipmentLookup()
    return _lookup_instance


# ============================================================================
# MCP Tool Functions
# ============================================================================


async def lookup_fault_code_tool(
    manufacturer: str, fault_code: str, model: Optional[str] = None, equipment_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Look up a fault code for specific equipment and get diagnosis, fix, and parts.

    MCP Tool: lookup_fault_code

    Args:
        manufacturer: Equipment manufacturer (e.g., "Carrier", "Trane", "Daikin")
        fault_code: Fault code (e.g., "E4", "FAULT_001", "ALARM_1")
        model: Equipment model (e.g., "30XA", "RTAC") - optional
        equipment_type: Equipment type (chiller, ahu, vsd) - optional

    Returns:
        Dictionary with:
        - fault: Fault code details (name, severity, description, causes, fixes)
        - manufacturer: Normalized manufacturer name
        - model: Equipment model
        - parts: Suggested parts with SA suppliers
        - forum_solutions: Real-world solutions from HVAC forums
        - sources: Reference URLs
    """
    lookup = get_lookup()

    try:
        result = await lookup.lookup_fault_code(
            manufacturer=manufacturer, fault_code=fault_code, model=model, equipment_type=equipment_type
        )
        return result
    except Exception as e:
        logger.error(f"lookup_fault_code_tool failed: {e}")
        return {"error": str(e), "fault": None, "manufacturer": manufacturer, "model": model}


async def lookup_parts_tool(
    part_number: Optional[str] = None,
    part_description: Optional[str] = None,
    manufacturer: Optional[str] = None,
    include_alternatives: bool = True,
) -> List[Dict[str, Any]]:
    """
    Search for parts across South African suppliers.

    MCP Tool: lookup_parts

    Args:
        part_number: OEM or generic part number (e.g., "30HX-405-332")
        part_description: Part description to search (e.g., "oil filter")
        manufacturer: Filter by manufacturer (e.g., "Carrier")
        include_alternatives: Include generic alternatives (default: True)

    Returns:
        List of parts with suppliers:
        - part_name: Part name/description
        - part_number: OEM part number
        - manufacturer: Part manufacturer
        - suppliers: List of {supplier, price, lead_time, url}
        - generic_alternative: Generic equivalent info (if available)
    """
    if not part_number and not part_description:
        return [{"error": "Either part_number or part_description is required"}]

    lookup = get_lookup()
    results = []

    try:
        if part_number:
            # Search by part number
            for supplier in lookup.SA_PARTS_SUPPLIERS:
                if manufacturer and not lookup._supplier_relevant(supplier, manufacturer):
                    continue

                supplier_results = await lookup._search_supplier(supplier, part_number, manufacturer or "", None)

                if supplier_results:
                    part_result = {
                        "part_name": part_number,
                        "part_number": part_number,
                        "manufacturer": manufacturer,
                        "suppliers": supplier_results,
                    }

                    if include_alternatives:
                        generic = lookup._find_generic_alternative(part_number)
                        if generic:
                            part_result["generic_alternative"] = generic

                    results.append(part_result)
                    break

        else:
            # Search by description
            keywords = part_description.lower().split()
            part_categories = {
                "filter": "Oil Filter",
                "sensor": "Temperature Sensor",
                "switch": "Pressure Switch",
                "valve": "Expansion Valve",
                "motor": "Motor Assembly",
                "pump": "Pump Assembly",
                "board": "Control Board",
                "igbt": "IGBT Module",
            }

            matched_parts = set()
            for keyword in keywords:
                if keyword in part_categories:
                    matched_parts.add(part_categories[keyword])

            if not matched_parts:
                matched_parts = {part_description}

            for part_name in matched_parts:
                suppliers_list = []
                for supplier in lookup.SA_PARTS_SUPPLIERS[:5]:
                    if manufacturer and not lookup._supplier_relevant(supplier, manufacturer):
                        continue
                    try:
                        supplier_results = await lookup._search_supplier(supplier, part_name, manufacturer or "", None)
                        suppliers_list.extend(supplier_results)
                    except Exception:
                        pass

                results.append({"part_name": part_name, "manufacturer": manufacturer, "suppliers": suppliers_list[:5]})

        return results if results else [{"part_name": part_number or part_description, "suppliers": []}]

    except Exception as e:
        logger.error(f"lookup_parts_tool failed: {e}")
        return [{"error": str(e)}]


async def search_equipment_issue_tool(
    query: str, manufacturer: Optional[str] = None, model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Natural language search for equipment issues.

    MCP Tool: search_equipment_issue

    Supports queries like:
    - "chiller making loud noise"
    - "VSD showing fault 29"
    - "AHU not cooling"
    - "Carrier 30XA error E4"

    Args:
        query: Natural language search query
        manufacturer: Filter by manufacturer (optional, auto-detected from query)
        model: Filter by model (optional)

    Returns:
        Dictionary with:
        - query_type: "fault_code" or "keyword"
        - fault: Fault code details (if fault code detected)
        - suggestions: Problem solutions from keyword matching
        - parts: Related parts with suppliers
        - forum_solutions: Links to HVAC forums
        - note: Additional guidance
    """
    import re

    lookup = get_lookup()
    query_lower = query.lower()

    try:
        # Extract fault code patterns
        fault_patterns = [
            r"(?:fault|error|code|alarm)\s*[:#]?\s*([a-zA-Z0-9_-]+)",
            r"([A-Z]+[_-]?\d+)",
            r"(?:^|\s)([EFAUHLueh]\d+)(?:\s|$)",
        ]

        fault_code = None
        for pattern in fault_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                fault_code = match.group(1).upper()
                break

        # Extract manufacturer
        manufacturers = ["carrier", "trane", "daikin", "abb", "danfoss", "york", "honeywell", "siemens", "schneider"]
        for mfr in manufacturers:
            if mfr in query_lower:
                manufacturer = manufacturer or mfr.title()
                break

        # Direct fault code lookup if detected
        if fault_code and manufacturer:
            result = await lookup.lookup_fault_code(manufacturer, fault_code, model)
            if result.get("fault"):
                return {
                    "query_type": "fault_code",
                    "fault": result.get("fault"),
                    "manufacturer": manufacturer,
                    "model": model,
                    "parts": result.get("parts", []),
                    "forum_solutions": result.get("forum_solutions", []),
                }

        # Keyword-based search
        problem_keywords = {
            "noise": "Check bearings, belts, fan blades for wear or imbalance",
            "vibration": "Check mounting bolts, alignment, bearings, shaft balance",
            "leak": "Check seals, gaskets, connections, refrigerant charge",
            "overheat": "Check airflow, filters, refrigerant charge, thermal protection",
            "not cooling": "Check refrigerant charge, compressor, condenser airflow",
            "not heating": "Check reversing valve, defrost cycle, heat strips",
            "tripping": "Check for overcurrent, short circuit, ground fault",
            "won't start": "Check power supply, contactor, capacitor, control board",
            "short cycling": "Check refrigerant charge, thermostat, pressure switches",
            "freezing": "Check airflow, refrigerant charge, expansion valve",
        }

        suggestions = []
        for keyword, solution in problem_keywords.items():
            if keyword in query_lower:
                suggestions.append(
                    {
                        "problem": keyword.replace("_", " ").title(),
                        "solution": solution,
                        "source": "General troubleshooting guide",
                    }
                )

        # Forum search URLs
        search_query = f"{manufacturer or ''} {model or ''} {query}".strip()
        forums = []
        for forum in lookup.FORUM_SOURCES:
            forum_url = forum["url"] + forum["search_url"].format(query=search_query.replace(" ", "+"))
            forums.append({"source": forum["name"], "url": forum_url, "description": forum.get("description", "")})

        return {
            "query_type": "keyword",
            "manufacturer": manufacturer,
            "model": model,
            "suggestions": suggestions,
            "forum_solutions": forums,
            "note": "Try including a fault code for more specific results" if not suggestions else None,
        }

    except Exception as e:
        logger.error(f"search_equipment_issue_tool failed: {e}")
        return {"error": str(e), "query_type": "error", "query": query}


# ============================================================================
# MCP Tool Definitions (JSON Schema)
# ============================================================================

MCP_TOOLS = [
    {
        "name": "lookup_fault_code",
        "description": "Look up a fault code for specific equipment and get diagnosis, fix, and parts. Returns comprehensive fault information including probable causes, recommended fixes, suggested parts with SA suppliers, and forum solutions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "manufacturer": {
                    "type": "string",
                    "description": "Equipment manufacturer (e.g., Carrier, Trane, Daikin, ABB)",
                },
                "fault_code": {"type": "string", "description": "Fault code (e.g., E4, FAULT_001, ALARM_1)"},
                "model": {"type": "string", "description": "Equipment model (e.g., 30XA, RTAC)"},
                "equipment_type": {"type": "string", "description": "Equipment type (chiller, ahu, vsd)"},
            },
            "required": ["manufacturer", "fault_code"],
        },
    },
    {
        "name": "lookup_parts",
        "description": "Search for parts across South African suppliers. Returns parts with pricing, lead times, and generic alternatives.",
        "input_schema": {
            "type": "object",
            "properties": {
                "part_number": {"type": "string", "description": "OEM or generic part number"},
                "part_description": {"type": "string", "description": "Part description to search"},
                "manufacturer": {"type": "string", "description": "Filter by manufacturer"},
                "include_alternatives": {
                    "type": "boolean",
                    "description": "Include generic alternatives (default: true)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_equipment_issue",
        "description": "Natural language search for equipment issues. Supports queries like 'chiller making loud noise' or 'VSD showing fault 29'. Auto-detects fault codes and manufacturers from the query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "manufacturer": {
                    "type": "string",
                    "description": "Filter by manufacturer (optional, auto-detected from query)",
                },
                "model": {"type": "string", "description": "Filter by model"},
            },
            "required": ["query"],
        },
    },
]


# ============================================================================
# MCP Server Class
# ============================================================================


class EquipmentMCPServer:
    """
    MCP Server for equipment lookup tools.

    Provides a unified interface for AI chat to call equipment lookup tools.

    Usage:
        server = EquipmentMCPServer()
        tools = server.list_tools()  # Get available tools
        result = await server.call_tool("lookup_fault_code", manufacturer="Carrier", fault_code="E4")
    """

    def __init__(self):
        """Initialize MCP server."""
        self.tools = MCP_TOOLS
        self.tool_handlers = {
            "lookup_fault_code": lookup_fault_code_tool,
            "lookup_parts": lookup_parts_tool,
            "search_equipment_issue": search_equipment_issue_tool,
        }

    def list_tools(self) -> List[Dict[str, Any]]:
        """List available MCP tools with their schemas."""
        return self.tools

    async def call_tool(self, tool_name: str, **kwargs) -> Any:
        """
        Call an MCP tool by name.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Tool arguments

        Returns:
            Tool result

        Raises:
            ValueError: If tool not found
        """
        handler = self.tool_handlers.get(tool_name)
        if not handler:
            raise ValueError(f"Unknown tool: {tool_name}. Available: {list(self.tool_handlers.keys())}")

        return await handler(**kwargs)

    def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get JSON schema for a specific tool."""
        for tool in self.tools:
            if tool["name"] == tool_name:
                return tool
        return None
