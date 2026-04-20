"""Equipment Lookup API endpoints.

Provides fault code lookup, parts search, and equipment issue resolution
for HVAC technicians via REST API.

Endpoints:
    GET  /api/equipment-lookup/fault-code - Look up fault code
    GET  /api/equipment-lookup/parts - Search for parts
    POST /api/equipment-lookup/search - Natural language search
"""

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.equipment_lookup import EquipmentLookup

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/equipment-lookup", tags=["equipment-lookup"])

# Initialize lookup service (singleton)
_lookup_instance: EquipmentLookup | None = None


def get_lookup() -> EquipmentLookup:
    """Get or create EquipmentLookup singleton."""
    global _lookup_instance
    if _lookup_instance is None:
        _lookup_instance = EquipmentLookup()
    return _lookup_instance


# ============================================================================
# Response Models
# ============================================================================


class ProbableCause(BaseModel):
    """Probable cause for a fault."""

    cause: str
    likelihood: str
    component: str | None = None
    check: str | None = None


class RecommendedFix(BaseModel):
    """Recommended fix for a fault."""

    immediate: list[str] = []
    scenarios: dict[str, str] = {}


class FaultInfo(BaseModel):
    """Fault code information."""

    code: str
    name: str
    severity: str
    description: str
    probable_causes: list[ProbableCause] = []
    recommended_fix: RecommendedFix | None = None
    safety_notes: str | None = None


class SupplierResult(BaseModel):
    """Part supplier search result."""

    supplier: str
    name: str | None = None
    part_number: str | None = None
    price: str | None = None
    lead_time: str | None = None
    available: bool = True
    url: str | None = None


class GenericAlternative(BaseModel):
    """Generic alternative for OEM part."""

    category: str
    generic_part_number: str | None = None
    manufacturer: str | None = None
    description: str | None = None
    suppliers: list[str] = []


class PartResult(BaseModel):
    """Part search result."""

    part_name: str
    part_number: str | None = None
    manufacturer: str | None = None
    suppliers: list[SupplierResult] = []
    generic_alternative: GenericAlternative | None = None


class ForumResult(BaseModel):
    """Forum search result."""

    source: str
    url: str
    title: str | None = None
    snippet: str | None = None
    description: str | None = None
    coverage: list[str] = []


class FaultCodeResponse(BaseModel):
    """Response for fault code lookup."""

    fault: FaultInfo | None = None
    manufacturer: str
    model: str | None = None
    parts: list[PartResult] = []
    forum_solutions: list[ForumResult] = []
    sources: list[str] = []
    scraped_data: dict[str, Any] | None = None


class SearchSuggestion(BaseModel):
    """Search suggestion from keyword matching."""

    problem: str
    solution: str
    source: str


class SearchResponse(BaseModel):
    """Response for natural language search."""

    query_type: str
    fault: FaultInfo | None = None
    manufacturer: str | None = None
    model: str | None = None
    suggestions: list[SearchSuggestion] = []
    parts: list[PartResult] = []
    forum_solutions: list[ForumResult] = []
    note: str | None = None


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/fault-code", response_model=FaultCodeResponse)
async def get_fault_code(
    manufacturer: str = Query(..., description="Equipment manufacturer (e.g., Carrier, Trane, Daikin)"),
    fault_code: str = Query(..., description="Fault code (e.g., E4, FAULT_001, ALARM_1)"),
    model: str | None = Query(None, description="Equipment model (e.g., 30XA, RTAC)"),
    equipment_type: str | None = Query(None, description="Equipment type (chiller, ahu, vsd)"),
) -> FaultCodeResponse:
    """
    Look up fault code and get diagnosis, fix, and parts.

    Returns comprehensive fault information including:
    - Fault code details (name, severity, description)
    - Probable causes with likelihood ranking
    - Recommended fixes
    - Suggested parts with SA suppliers
    - Forum solutions from HVAC community
    - Source citations

    Example:
        GET /api/equipment-lookup/fault-code?manufacturer=Carrier&fault_code=E4&model=30XA
    """
    lookup = get_lookup()

    try:
        result = await lookup.lookup_fault_code(
            manufacturer=manufacturer, fault_code=fault_code, model=model, equipment_type=equipment_type
        )

        if not result.get("fault"):
            raise HTTPException(status_code=404, detail=f"Fault code '{fault_code}' not found for {manufacturer}")

        # Convert to response model
        fault_info = result.get("fault")
        fault = None
        if fault_info:
            # Parse recommended_fix (can be dict or string)
            rec_fix = fault_info.get("recommended_fix")
            recommended_fix = None
            if isinstance(rec_fix, dict):
                recommended_fix = RecommendedFix(
                    immediate=rec_fix.get("immediate", []), scenarios=rec_fix.get("scenarios", {})
                )
            elif isinstance(rec_fix, str):
                recommended_fix = RecommendedFix(immediate=[rec_fix], scenarios={})

            fault = FaultInfo(
                code=fault_code,
                name=fault_info.get("name", "Unknown"),
                severity=fault_info.get("severity", "medium"),
                description=fault_info.get("description", ""),
                probable_causes=[ProbableCause(**cause) for cause in fault_info.get("probable_causes", [])],
                recommended_fix=recommended_fix,
                safety_notes=fault_info.get("safety_notes"),
            )

        # Convert parts
        parts = []
        for part in result.get("parts", []):
            suppliers = [SupplierResult(**s) for s in part.get("suppliers", [])]
            generic = None
            if part.get("generic_alternative"):
                generic = GenericAlternative(**part["generic_alternative"])

            parts.append(
                PartResult(
                    part_name=part.get("part_name", ""),
                    part_number=part.get("part_number"),
                    manufacturer=part.get("manufacturer"),
                    suppliers=suppliers,
                    generic_alternative=generic,
                )
            )

        # Convert forum results
        forums = [ForumResult(**f) for f in result.get("forum_solutions", [])]

        return FaultCodeResponse(
            fault=fault,
            manufacturer=result.get("manufacturer", manufacturer),
            model=model,
            parts=parts,
            forum_solutions=forums,
            sources=result.get("sources", []),
            scraped_data=result.get("scraped_data"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fault code lookup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/parts", response_model=list[PartResult])
async def search_parts(
    part_number: str | None = Query(None, description="OEM or generic part number"),
    part_description: str | None = Query(None, description="Part description to search"),
    manufacturer: str | None = Query(None, description="Filter by manufacturer"),
    include_alternatives: bool = Query(True, description="Include generic alternatives"),
) -> list[PartResult]:
    """
    Search for parts across South African suppliers.

    Returns parts matching criteria with:
    - Part name and number
    - Manufacturer
    - Multiple suppliers with pricing
    - Lead times and stock availability
    - Generic alternatives (if available)

    Example:
        GET /api/equipment-lookup/parts?part_number=30HX-405-332&manufacturer=Carrier
        GET /api/equipment-lookup/parts?part_description=oil+filter
    """
    if not part_number and not part_description:
        raise HTTPException(status_code=400, detail="Either part_number or part_description is required")

    lookup = get_lookup()

    try:
        results = []

        if part_number:
            # Search by part number
            results = await _search_by_part_number(lookup, part_number, manufacturer)
        else:
            # Search by description
            results = await _search_by_description(lookup, part_description, manufacturer)

        if include_alternatives:
            # Add generic alternatives where available
            for part in results:
                if part.part_number and part.part_number != "N/A":
                    generic = lookup._find_generic_alternative(part.part_number)
                    if generic:
                        part.generic_alternative = GenericAlternative(**generic)

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Parts search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=SearchResponse)
async def search_equipment_issue(
    query: str = Query(..., description="Natural language query"),
    manufacturer: str | None = Query(None, description="Filter by manufacturer"),
    model: str | None = Query(None, description="Filter by model"),
) -> SearchResponse:
    """
    Natural language search for equipment issues.

    Uses keyword matching to find relevant:
    - Fault codes (if detected in query)
    - Common problems
    - Solutions from knowledge base

    Supports queries like:
    - "chiller making loud noise"
    - "VSD showing fault 29"
    - "AHU not cooling"
    - "Carrier 30XA error E4"

    Example:
        POST /api/equipment-lookup/search?query=carrier+fault+E4
    """
    lookup = get_lookup()

    try:
        result = await _natural_language_search(lookup, query, manufacturer, model)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Natural language search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Helper Functions
# ============================================================================


async def _search_by_part_number(
    lookup: EquipmentLookup, part_number: str, manufacturer: str | None = None
) -> list[PartResult]:
    """Search suppliers by exact part number."""
    results = []
    query = part_number

    for supplier in lookup.SA_PARTS_SUPPLIERS:
        # Filter by manufacturer if specified
        if manufacturer and not lookup._supplier_relevant(supplier, manufacturer):
            continue

        supplier_results = await lookup._search_supplier(supplier, query, manufacturer or "", None)

        if supplier_results:
            results.append(
                PartResult(
                    part_name=query,
                    part_number=part_number,
                    manufacturer=manufacturer,
                    suppliers=[SupplierResult(**s) for s in supplier_results],
                )
            )
            break  # One result per part number

    # If no supplier results, return basic info
    if not results:
        results.append(
            PartResult(
                part_name=f"Part {part_number}", part_number=part_number, manufacturer=manufacturer, suppliers=[]
            )
        )

    return results


async def _search_by_description(
    lookup: EquipmentLookup, description: str, manufacturer: str | None = None
) -> list[PartResult]:
    """Search suppliers by part description."""
    results = []

    # Extract keywords from description
    keywords = description.lower().split()

    # Map keywords to part categories
    part_categories = {
        "filter": "Oil Filter",
        "sensor": "Temperature Sensor",
        "switch": "Pressure Switch",
        "valve": "Expansion Valve",
        "motor": "Motor Assembly",
        "pump": "Pump Assembly",
        "board": "Control Board",
        "igbt": "IGBT Module",
        "contactor": "Contactor",
        "belt": "Drive Belt",
        "bearing": "Bearing",
        "fan": "Fan Motor",
    }

    matched_parts = set()
    for keyword in keywords:
        if keyword in part_categories:
            matched_parts.add(part_categories[keyword])

    # If no matches, use description as-is
    if not matched_parts:
        matched_parts = {description}

    for part_name in matched_parts:
        suppliers_list = []

        for supplier in lookup.SA_PARTS_SUPPLIERS:
            if manufacturer and not lookup._supplier_relevant(supplier, manufacturer):
                continue

            try:
                supplier_results = await lookup._search_supplier(supplier, part_name, manufacturer or "", None)
                suppliers_list.extend([SupplierResult(**s) for s in supplier_results])
            except Exception:
                pass

        results.append(
            PartResult(
                part_name=part_name,
                manufacturer=manufacturer,
                suppliers=suppliers_list[:5],  # Limit to 5 suppliers per part
            )
        )

    return results


async def _natural_language_search(
    lookup: EquipmentLookup, query: str, manufacturer: str | None = None, model: str | None = None
) -> SearchResponse:
    """
    Parse natural language query and return relevant results.

    Supports queries like:
    - "chiller making loud noise"
    - "VSD showing fault 29"
    - "AHU not cooling"
    """
    query_lower = query.lower()

    # Extract fault code patterns - ordered from most specific to least specific
    fault_patterns = [
        r"([A-Z]+[_-]?\d+)",  # FAULT_001, ALARM_1, E4 - catches codes with prefix
        r"(?:^|\s)([EFAUHLueh]\d+)(?:\s|$)",  # E4, F1, A1, H1, L1, U4 - single letter codes
        r"(?:fault|error|code|alarm)\s*[:#]?\s*([a-zA-Z0-9_-]+)",  # "fault E4", "error 29"
    ]

    fault_code = None
    for pattern in fault_patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            fault_code = match.group(1).upper()
            break

    # Extract manufacturer mentions
    manufacturers = ["carrier", "trane", "daikin", "abb", "danfoss", "york", "honeywell", "siemens", "schneider"]
    for mfr in manufacturers:
        if mfr in query_lower:
            manufacturer = manufacturer or mfr.title()
            break

    # If fault code detected and manufacturer known, do direct lookup
    if fault_code and manufacturer:
        try:
            result = await lookup.lookup_fault_code(manufacturer, fault_code, model)

            if result.get("fault"):
                fault_info = result["fault"]
                # Parse recommended_fix (can be dict or string)
                rec_fix = fault_info.get("recommended_fix")
                recommended_fix = None
                if isinstance(rec_fix, dict):
                    recommended_fix = RecommendedFix(
                        immediate=rec_fix.get("immediate", []), scenarios=rec_fix.get("scenarios", {})
                    )
                elif isinstance(rec_fix, str):
                    recommended_fix = RecommendedFix(immediate=[rec_fix], scenarios={})

                fault = FaultInfo(
                    code=fault_code,
                    name=fault_info.get("name", "Unknown"),
                    severity=fault_info.get("severity", "medium"),
                    description=fault_info.get("description", ""),
                    probable_causes=[ProbableCause(**cause) for cause in fault_info.get("probable_causes", [])],
                    recommended_fix=recommended_fix,
                    safety_notes=fault_info.get("safety_notes"),
                )

                parts = []
                for part in result.get("parts", []):
                    suppliers = [SupplierResult(**s) for s in part.get("suppliers", [])]
                    generic = None
                    if part.get("generic_alternative"):
                        generic = GenericAlternative(**part["generic_alternative"])
                    parts.append(
                        PartResult(
                            part_name=part.get("part_name", ""),
                            part_number=part.get("part_number"),
                            manufacturer=part.get("manufacturer"),
                            suppliers=suppliers,
                            generic_alternative=generic,
                        )
                    )

                forums = [ForumResult(**f) for f in result.get("forum_solutions", [])]

                return SearchResponse(
                    query_type="fault_code",
                    fault=fault,
                    manufacturer=manufacturer,
                    model=model,
                    parts=parts,
                    forum_solutions=forums,
                )
        except Exception as e:
            logger.warning(f"Fault code lookup failed during search: {e}")

    # Fallback to keyword search
    return await _keyword_search(lookup, query, manufacturer, model)


async def _keyword_search(
    lookup: EquipmentLookup, query: str, manufacturer: str | None, model: str | None
) -> SearchResponse:
    """Fallback keyword search when no fault code detected."""

    # Problem keywords and solutions
    problem_keywords = {
        "noise": {
            "solution": "Check bearings, belts, fan blades for wear or imbalance",
            "parts": ["Bearing", "Drive Belt", "Fan Motor"],
        },
        "loud": {
            "solution": "Check bearings, belts, fan blades for wear or imbalance",
            "parts": ["Bearing", "Drive Belt", "Fan Motor"],
        },
        "vibration": {
            "solution": "Check mounting bolts, alignment, bearings, shaft balance",
            "parts": ["Bearing", "Motor Mount"],
        },
        "leak": {
            "solution": "Check seals, gaskets, connections, refrigerant charge",
            "parts": ["Seal Kit", "Gasket", "O-Ring"],
        },
        "leaking": {
            "solution": "Check seals, gaskets, connections, refrigerant charge",
            "parts": ["Seal Kit", "Gasket", "O-Ring"],
        },
        "overheat": {
            "solution": "Check airflow, filters, refrigerant charge, thermal protection",
            "parts": ["Air Filter", "Thermal Switch", "Fan Motor"],
        },
        "hot": {
            "solution": "Check airflow, filters, refrigerant charge, thermal protection",
            "parts": ["Air Filter", "Thermal Switch", "Fan Motor"],
        },
        "not cooling": {
            "solution": "Check refrigerant charge, compressor, condenser airflow, expansion valve",
            "parts": ["Expansion Valve", "Condenser Fan", "Compressor"],
        },
        "not heating": {
            "solution": "Check reversing valve, defrost cycle, heat strips",
            "parts": ["Reversing Valve", "Heat Strip", "Defrost Timer"],
        },
        "tripping": {
            "solution": "Check for overcurrent, short circuit, ground fault, overload",
            "parts": ["Circuit Breaker", "Contactor", "Overload Relay"],
        },
        "won't start": {
            "solution": "Check power supply, contactor, capacitor, control board",
            "parts": ["Contactor", "Capacitor", "Control Board"],
        },
        "short cycling": {
            "solution": "Check refrigerant charge, thermostat, high/low pressure switches",
            "parts": ["Pressure Switch", "Thermostat", "Refrigerant"],
        },
        "freezing": {
            "solution": "Check airflow, refrigerant charge, expansion valve, defrost",
            "parts": ["Air Filter", "Expansion Valve", "Defrost Timer"],
        },
        "ice": {
            "solution": "Check airflow, refrigerant charge, expansion valve, defrost",
            "parts": ["Air Filter", "Expansion Valve", "Defrost Timer"],
        },
    }

    suggestions = []
    related_parts = set()
    query_lower = query.lower()

    for keyword, info in problem_keywords.items():
        if keyword in query_lower:
            suggestions.append(
                SearchSuggestion(
                    problem=keyword.replace("_", " ").title(),
                    solution=info["solution"],
                    source="General troubleshooting guide",
                )
            )
            related_parts.update(info.get("parts", []))

    # Search for related parts
    parts = []
    if related_parts:
        for part_name in list(related_parts)[:3]:  # Limit to 3 parts
            suppliers = []
            for supplier in lookup.SA_PARTS_SUPPLIERS[:3]:  # Check top 3 suppliers
                try:
                    results = await lookup._search_supplier(supplier, part_name, manufacturer or "", model)
                    suppliers.extend([SupplierResult(**s) for s in results])
                except Exception:
                    pass

            parts.append(PartResult(part_name=part_name, manufacturer=manufacturer, suppliers=suppliers[:3]))

    # Get forum search results
    search_query = f"{manufacturer or ''} {model or ''} {query}".strip()
    forums = []
    for forum in lookup.FORUM_SOURCES:
        forum_url = forum["url"] + forum["search_url"].format(query=search_query.replace(" ", "+"))
        forums.append(
            ForumResult(
                source=forum["name"],
                url=forum_url,
                title=f"Search {forum['name']} for: {query}",
                description=forum.get("description", ""),
                coverage=forum.get("coverage", []),
            )
        )

    return SearchResponse(
        query_type="keyword",
        manufacturer=manufacturer,
        model=model,
        suggestions=suggestions,
        parts=parts,
        forum_solutions=forums,
        note="Try including a fault code for more specific results" if not suggestions else None,
    )
