"""
Equipment Lookup Service

Provides fault code lookup, parts sourcing, and equipment issue resolution
for HVAC technicians. Integrates with local fault code database and web scrapers.

Usage:
    from app.services.equipment_lookup import EquipmentLookup

    lookup = EquipmentLookup()
    result = await lookup.lookup_fault_code("Carrier", "E4", "30XA")
"""
from typing import Dict, List, Optional
import asyncio
import aiohttp
import json
from pathlib import Path
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


class EquipmentLookup:
    """
    Equipment fault code and parts lookup service.

    Provides instant lookup from local database with web scraping fallback
    for manufacturer documentation and parts sourcing.
    """

    # Manufacturer technical documentation sources
    MANUFACTURER_SOURCES = {
        "carrier": {
            "name": "Carrier",
            "base_url": "https://www.carrier.com",
            "support_url": "https://support.carrier.com",
            "search_url": "https://www.carrier.com/commercial/en/us/support-and-resources"
        },
        "trane": {
            "name": "Trane",
            "base_url": "https://www.trane.com",
            "support_url": "https://www.trane.com/content/trane/commercial/en_us/products/systems/chillers.html",
            "search_url": "https://www.trane.com/search.html"
        },
        "daikin": {
            "name": "Daikin",
            "base_url": "https://www.daikin.com",
            "support_url": "https://www.daikinac.com",
            "search_url": "https://www.daikinac.com/support"
        },
        "abb": {
            "name": "ABB",
            "base_url": "https://new.abb.com",
            "support_url": "https://new.abb.com/drives",
            "search_url": "https://new.abb.com/search"
        },
        "danfoss": {
            "name": "Danfoss",
            "base_url": "https://www.danfoss.com",
            "support_url": "https://www.danfoss.com/en/products/drives/",
            "search_url": "https://www.danfoss.com/search"
        },
        "york": {
            "name": "York",
            "base_url": "https://www.york.com",
            "support_url": "https://www.york.com/contact-us",
            "search_url": "https://www.york.com/search"
        },
        "honeywell": {
            "name": "Honeywell",
            "base_url": "https://www.honeywell.com",
            "support_url": "https://buildings.honeywell.com",
            "search_url": "https://buildings.honeywell.com/search"
        },
        "siemens": {
            "name": "Siemens",
            "base_url": "https://new.siemens.com",
            "support_url": "https://support.industry.siemens.com",
            "search_url": "https://new.siemens.com/search"
        },
        "schneider": {
            "name": "Schneider Electric",
            "base_url": "https://www.se.com",
            "support_url": "https://www.se.com/ww/en/services/",
            "search_url": "https://www.se.com/ww/en/search/"
        }
    }

    # South African parts suppliers
    SA_PARTS_SUPPLIERS = [
        {
            "name": "Carrier South Africa",
            "url": "https://www.carrier.com/en-za/",
            "location": "Johannesburg",
            "phone": "+27 11 207 2000"
        },
        {
            "name": "Voltex",
            "url": "https://www.voltex.co.za",
            "location": "Nationwide",
            "phone": "+27 11 875 1000"
        },
        {
            "name": "RS Components South Africa",
            "url": "https://za.rs-online.com",
            "location": "Johannesburg",
            "phone": "+27 11 617 2000"
        },
        {
            "name": "Midas",
            "url": "https://www.midas.co.za",
            "location": "Nationwide",
            "phone": "+27 11 608 1000"
        },
        {
            "name": "CMC Refrigeration",
            "url": "https://www.cmcair.co.za",
            "location": "Cape Town",
            "phone": "+27 21 511 4800"
        },
        {
            "name": "BUCO",
            "url": "https://www.buco.co.za",
            "location": "Nationwide",
            "phone": "+27 861 282 263"
        },
        {
            "name": "Aircon Direct",
            "url": "https://www.aircondirect.co.za",
            "location": "Johannesburg",
            "phone": "+27 11 914 1400"
        },
        {
            "name": "HVA Supplies",
            "url": "https://hva.co.za",
            "location": "Cape Town",
            "phone": "+27 21 552 1000"
        },
        {
            "name": "Refrigeration & Air Conditioning Centre",
            "url": "https://www.rac.co.za",
            "location": "Johannesburg",
            "phone": "+27 11 453 2700"
        },
        {
            "name": "Thermal Control Products",
            "url": "https://www.thermalcontrol.co.za",
            "location": "Durban",
            "phone": "+27 31 564 1000"
        },
        {
            "name": "Adcock HVAC",
            "url": "https://www.adcock.co.za",
            "location": "Nationwide",
            "phone": "+27 11 396 4000"
        }
    ]

    def __init__(self):
        """Initialize EquipmentLookup service."""
        self._fault_codes_db: Optional[Dict] = None
        self._load_fault_codes_db()

    def _load_fault_codes_db(self) -> None:
        """Load fault codes database from JSON file."""
        try:
            db_path = Path(__file__).parent.parent / "data" / "fault_codes.json"
            with open(db_path, 'r') as f:
                self._fault_codes_db = json.load(f)
            logger.info(f"Loaded fault codes database with {self._count_total_codes()} codes")
        except FileNotFoundError:
            logger.error("Fault codes database not found")
            self._fault_codes_db = {"manufacturers": {}}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in fault codes database: {e}")
            self._fault_codes_db = {"manufacturers": {}}

    def _count_total_codes(self) -> int:
        """Count total fault codes in database."""
        total = 0
        for mfg_data in self._fault_codes_db.get("manufacturers", {}).values():
            for model_data in mfg_data.get("models", {}).values():
                total += len(model_data)
        return total

    async def lookup_fault_code(
        self,
        manufacturer: str,
        fault_code: str,
        model: Optional[str] = None,
        equipment_type: Optional[str] = None
    ) -> Dict:
        """
        Look up fault code from local database with web scraping fallback.

        Args:
            manufacturer: Equipment manufacturer (e.g., "Carrier", "Trane")
            fault_code: Fault code (e.g., "E4", "Error 1", "ALARM 1")
            model: Equipment model (e.g., "30XA", "RTAC")
            equipment_type: Type of equipment (chiller, AHU, VSD, etc.)

        Returns:
            Dictionary with:
            - fault: Fault code info or None if not found
            - manufacturer: Normalized manufacturer name
            - scraped_data: Additional info from web scraping (if available)
            - parts: Suggested parts from suppliers (if applicable)
            - sources: List of source URLs for reference

        Example:
            >>> result = await lookup.lookup_fault_code("Carrier", "E4", "30XA")
            >>> print(result['fault']['name'])
            'Low Oil Pressure'
        """
        # Normalize manufacturer name
        mfg_normalized = self._normalize_manufacturer(manufacturer)

        # Try local database lookup first
        fault_info = self._lookup_local_db(mfg_normalized, model, fault_code)

        result = {
            "fault": fault_info,
            "manufacturer": mfg_normalized,
            "model": model,
            "scraped_data": None,
            "parts": [],
            "sources": []
        }

        # If not found locally or needs enrichment, scrape manufacturer
        if not fault_info or self._should_enrich(fault_info):
            try:
                scraped = await self._scrape_manufacturer(mfg_normalized, model, fault_code)
                result["scraped_data"] = scraped
                if scraped:
                    result["sources"].append(scraped.get("source_url"))
            except Exception as e:
                logger.warning(f"Web scraping failed for {mfg_normalized} {fault_code}: {e}")

        # Search for parts if causes suggest component failure
        if fault_info and self._needs_parts_search(fault_info):
            try:
                parts = await self._search_parts(mfg_normalized, model, fault_code, fault_info.get("probable_causes", []))
                result["parts"] = parts
            except Exception as e:
                logger.warning(f"Parts search failed for {mfg_normalized} {fault_code}: {e}")

        # Search forums for real-world solutions
        if fault_info:
            try:
                forum_results = await self._search_forums(mfg_normalized, model, fault_code)
                result["forum_solutions"] = forum_results
            except Exception as e:
                logger.warning(f"Forum search failed for {mfg_normalized} {fault_code}: {e}")

        return result

    def _normalize_manufacturer(self, manufacturer: str) -> str:
        """Normalize manufacturer name for lookup."""
        mfg_lower = manufacturer.lower().strip()

        # Map common variants to canonical names
        mappings = {
            "carrier": "carrier",
            "trane": "trane",
            "daikin": "daikin",
            "abb": "abb",
            "danfoss": "danfoss",
            "york": "york",
            "honeywell": "honeywell",
            "siemens": "siemens",
            "schneider": "schneider",
            "schneider electric": "schneider"
        }

        return mappings.get(mfg_lower, mfg_lower)

    def _lookup_local_db(
        self,
        manufacturer: str,
        model: Optional[str],
        fault_code: str
    ) -> Optional[Dict]:
        """
        Look up fault code in local database.

        Args:
            manufacturer: Normalized manufacturer name
            model: Equipment model
            fault_code: Fault code string

        Returns:
            Fault code dict or None if not found
        """
        if not self._fault_codes_db:
            return None

        manufacturers = self._fault_codes_db.get("manufacturers", {})
        mfg_data = manufacturers.get(manufacturer)

        if not mfg_data:
            return None

        models = mfg_data.get("models", {})

        # Normalize fault code for case-insensitive lookup
        fault_code_normalized = fault_code.upper().strip()

        # If model specified, try model-specific lookup first
        if model:
            model_lower = model.lower()
            # Try exact match
            if model_lower in models:
                model_data = models[model_lower]
                # Case-insensitive fault code search
                for fc_key, fc_value in model_data.items():
                    if fc_key.upper() == fault_code_normalized:
                        return fc_value

            # Try partial match
            for model_name, model_data in models.items():
                if model_lower in model_name.lower():
                    for fc_key, fc_value in model_data.items():
                        if fc_key.upper() == fault_code_normalized:
                            return fc_value

        # Fallback: search all models for this manufacturer (case-insensitive)
        for model_name, model_data in models.items():
            for fc_key, fc_value in model_data.items():
                if fc_key.upper() == fault_code_normalized:
                    return fc_value

        # Not found
        return None

    def _should_enrich(self, fault_info: Optional[Dict]) -> bool:
        """Determine if fault info needs web scraping enrichment."""
        if not fault_info:
            return True

        # Enrich if critical or high severity
        severity = fault_info.get("severity", "")
        return severity in ["critical", "high"]

    def _needs_parts_search(self, fault_info: Dict) -> bool:
        """Check if parts search should be performed based on probable causes."""
        causes = fault_info.get("probable_causes", [])

        # Keywords suggesting part replacement
        parts_keywords = ["sensor", "motor", "valve", "pump", "board", "igbt", "resistor"]

        for cause in causes:
            cause_str = cause.get("cause", "").lower()
            if any(keyword in cause_str for keyword in parts_keywords):
                return True

        return False

    async def _scrape_manufacturer(
        self,
        manufacturer: str,
        model: Optional[str],
        fault_code: str
    ) -> Optional[Dict]:
        """
        Scrape manufacturer website for fault code documentation.

        Args:
            manufacturer: Normalized manufacturer name
            model: Equipment model
            fault_code: Fault code

        Returns:
            Dictionary with scraped info or None
        """
        mfg_source = self.MANUFACTURER_SOURCES.get(manufacturer)

        if not mfg_source:
            logger.warning(f"No source configured for manufacturer: {manufacturer}")
            return None

        # Build search URL
        search_query = f"{manufacturer} {model if model else ''} {fault_code} error".strip()

        # Simulate scraping (actual implementation would make HTTP requests)
        # This is a placeholder - real scraping would use aiohttp + BeautifulSoup
        scraped_info = {
            "source_url": f"{mfg_source['search_url']}?q={search_query.replace(' ', '+')}",
            "manufacturer": mfg_source["name"],
            "fault_code": fault_code,
            "note": "Web scraping placeholder - implement actual scraping in production"
        }

        # In production, actual scraping logic:
        # async with aiohttp.ClientSession() as session:
        #     async with session.get(url, headers=...) as response:
        #         html = await response.text()
        #         soup = BeautifulSoup(html, 'lxml')
        #         # Extract relevant info from page

        return scraped_info

    async def _search_forums(
        self,
        manufacturer: str,
        model: Optional[str],
        fault_code: str
    ) -> List[Dict]:
        """
        Search technical forums for real-world solutions.

        Args:
            manufacturer: Equipment manufacturer
            model: Equipment model
            fault_code: Fault code

        Returns:
            List of forum threads/solutions
        """
        # Placeholder for forum search
        # Would integrate with HVAC-Talk, Reddit r/hvac, etc.
        search_query = f"{manufacturer} {model if model else ''} {fault_code}".strip()

        results = [
            {
                "source": "HVAC-Talk (placeholder)",
                "url": f"https://hvac-talk.com/search?query={search_query.replace(' ', '+')}",
                "title": f"{manufacturer} {fault_code} Discussion",
                "snippet": "Real-world solutions from HVAC technicians"
            }
        ]

        return results

    async def _search_parts(
        self,
        manufacturer: str,
        model: Optional[str],
        fault_code: str,
        causes: List[Dict]
    ) -> List[Dict]:
        """
        Search for parts from South African suppliers.

        Args:
            manufacturer: Equipment manufacturer
            model: Equipment model
            fault_code: Fault code
            causes: Probable causes list

        Returns:
            List of available parts with suppliers
        """
        # Extract part suggestions from causes
        parts_suggested = []

        for cause in causes:
            cause_str = cause.get("cause", "").lower()

            # Map fault causes to parts
            if "sensor" in cause_str:
                parts_suggested.append("Temperature Sensor")
            elif "motor" in cause_str:
                parts_suggested.append("Motor Assembly")
            elif "valve" in cause_str:
                parts_suggested.append("Expansion Valve")
            elif "pump" in cause_str:
                parts_suggested.append("Pump Assembly")
            elif "board" in cause_str:
                parts_suggested.append("Control Board")
            elif "igbt" in cause_str:
                parts_suggested.append("IGBT Module")
            elif "resistor" in cause_str:
                parts_suggested.append("Brake Resistor")

        # Build parts list with supplier info
        parts_list = []

        for part in parts_suggested:
            parts_list.append({
                "part_name": part,
                "manufacturer": manufacturer,
                "suppliers": [
                    {
                        "name": supplier["name"],
                        "url": supplier["url"],
                        "location": supplier["location"],
                        "phone": supplier["phone"]
                    }
                    for supplier in self.SA_PARTS_SUPPLIERS[:5]  # Top 5 suppliers
                ],
                "note": "Contact suppliers for availability and pricing"
            })

        return parts_list


# Convenience function for quick lookups
async def lookup_fault_code_quick(
    manufacturer: str,
    fault_code: str,
    model: Optional[str] = None
) -> Dict:
    """
    Quick lookup function for fault codes.

    Example:
        >>> result = await lookup_fault_code_quick("Carrier", "E4", "30XA")
        >>> print(result['fault']['name'])
        'Low Oil Pressure'
    """
    lookup = EquipmentLookup()
    return await lookup.lookup_fault_code(manufacturer, fault_code, model)


if __name__ == "__main__":
    # Test basic functionality
    import asyncio

    async def test():
        lookup = EquipmentLookup()

        # Test local DB lookup
        print("Testing local database lookup...")
        result = await lookup.lookup_fault_code("Carrier", "E4", "30XA")

        if result["fault"]:
            print(f"✓ Found: {result['fault']['name']}")
            print(f"  Severity: {result['fault']['severity']}")
            print(f"  Causes: {len(result['fault']['probable_causes'])}")
        else:
            print("✗ Not found in database")

        # Test fuzzy manufacturer matching
        print("\nTesting fuzzy manufacturer matching...")
        result = await lookup.lookup_fault_code("carrier", "e4")  # lowercase

        if result["fault"]:
            print(f"✓ Found with fuzzy match: {result['fault']['name']}")

        print("\n✅ EquipmentLookup service test complete!")

    asyncio.run(test())
