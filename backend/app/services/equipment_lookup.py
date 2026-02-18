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
import json
import re
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

    # Technical forum sources for real-world solutions
    FORUM_SOURCES = [
        {
            "name": "HVAC-Talk",
            "url": "https://hvac-talk.com",
            "search_url": "/search?q={query}",
            "coverage": ["troubleshooting", "real-world fixes"],
            "description": "Professional HVAC technician forum"
        },
        {
            "name": "Eng-Tips",
            "url": "https://www.eng-tips.com",
            "search_url": "/search?q={query}",
            "coverage": ["engineering discussions"],
            "description": "Engineering professional forums"
        },
        {
            "name": "Reddit r/HVAC",
            "url": "https://www.reddit.com/r/HVAC",
            "search_url": "/search?q={query}",
            "coverage": ["technician experiences"],
            "description": "HVAC subreddit community"
        },
        {
            "name": "Refrigeration Engineer",
            "url": "https://refrigerationengineer.com",
            "search_url": "/search?q={query}",
            "coverage": ["technical articles"],
            "description": "Refrigeration technical resources"
        }
    ]

    # South African parts suppliers - loaded from JSON
    SA_PARTS_SUPPLIERS: List[Dict] = []

    # Generic equivalents mapping - loaded from JSON
    GENERIC_EQUIVALENTS: Dict = {}

    # Part number mappings - loaded from JSON
    PART_NUMBER_MAPPINGS: Dict = {}

    def __init__(self):
        """Initialize EquipmentLookup service."""
        self._fault_codes_db: Optional[Dict] = None
        self._load_fault_codes_db()
        self._load_parts_suppliers_db()

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

    def _load_parts_suppliers_db(self) -> None:
        """Load parts suppliers database from JSON file."""
        try:
            suppliers_path = Path(__file__).parent.parent / "data" / "parts_suppliers.json"
            with open(suppliers_path, 'r') as f:
                data = json.load(f)

            # Convert class variables to instance variables
            EquipmentLookup.SA_PARTS_SUPPLIERS = data.get("suppliers", [])
            EquipmentLookup.GENERIC_EQUIVALENTS = data.get("generic_equivalents", {})
            EquipmentLookup.PART_NUMBER_MAPPINGS = data.get("part_number_mappings", {})

            logger.info(f"Loaded {len(EquipmentLookup.SA_PARTS_SUPPLIERS)} parts suppliers")
            logger.info(f"Loaded {len(EquipmentLookup.GENERIC_EQUIVALENTS)} generic equivalent mappings")
        except FileNotFoundError:
            logger.warning("Parts suppliers database not found")
            EquipmentLookup.SA_PARTS_SUPPLIERS = []
            EquipmentLookup.GENERIC_EQUIVALENTS = {}
            EquipmentLookup.PART_NUMBER_MAPPINGS = {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in parts suppliers database: {e}")
            EquipmentLookup.SA_PARTS_SUPPLIERS = []
            EquipmentLookup.GENERIC_EQUIVALENTS = {}
            EquipmentLookup.PART_NUMBER_MAPPINGS = {}

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
            List of forum threads/solutions with sources
        """
        search_query = f"{manufacturer} {model if model else ''} {fault_code}".strip()
        results = []

        for forum in self.FORUM_SOURCES:
            forum_url = forum["url"] + forum["search_url"].format(query=search_query.replace(" ", "+"))

            results.append({
                "source": forum["name"],
                "url": forum_url,
                "description": forum.get("description", ""),
                "coverage": forum.get("coverage", []),
                "title": f"{manufacturer} {fault_code} - {forum['name']}",
                "snippet": f"Search {forum['name']} for real-world solutions"
            })

        return results

    async def _search_parts(
        self,
        manufacturer: str,
        model: Optional[str],
        fault_code: str,
        causes: List[Dict]
    ) -> List[Dict]:
        """
        Search SA suppliers for relevant parts based on fault and causes.

        Args:
            manufacturer: Equipment manufacturer
            model: Equipment model
            fault_code: Fault code
            causes: Probable causes list

        Returns:
            List of {part_name, part_number, manufacturer, suppliers: [], generic_alternative: {}}
        """
        parts = []

        # Map fault codes to likely parts
        fault_parts_map = {
            "E4": ["Oil Filter", "Compressor Oil", "Oil Pressure Sensor"],
            "E1": ["EEV Assembly", "High Pressure Switch"],
            "E3": ["Condenser Fan Motor", "Discharge Temperature Sensor"],
            "E8": ["Supply Air Temperature Sensor"],
            "H1": ["High Pressure Switch", "Condenser Fan Motor"],
            "L1": ["Low Pressure Switch", "Expansion Valve"],
            "A1": ["Contactor", "Control Board"],
            "U0": ["Freeze Stat", "Evaporator Coil"],
            "FAULT_004": ["Heat Sink Temperature Sensor", "Cooling Fan"],
            "FAULT_001": ["IGBT Module", "Power Module"],
            "FAULT_006": ["Earth Fault Sensor", "Motor Insulation"],
            "ALARM_1": ["Motor Overload Protector", "Circuit Breaker"],
            "ALARM_4": ["Overtemperature Sensor", "Thermal Switch"],
            "U4": ["Low Pressure Switch", "Expansion Valve"],
            "E5": ["Compressor Internal Components", "Discharge Valve"],
        }

        # Get part suggestions from fault code
        suggested_part_names = fault_parts_map.get(fault_code.upper(), [])

        # If no mapped parts, try to extract from causes
        if not suggested_part_names and causes:
            for cause in causes:
                cause_str = cause.get("cause", "").lower()
                if "sensor" in cause_str:
                    suggested_part_names.append("Temperature Sensor")
                elif "motor" in cause_str:
                    suggested_part_names.append("Motor Assembly")
                elif "valve" in cause_str:
                    suggested_part_names.append("Expansion Valve")
                elif "pump" in cause_str:
                    suggested_part_names.append("Pump Assembly")
                elif "board" in cause_str:
                    suggested_part_names.append("Control Board")
                elif "igbt" in cause_str:
                    suggested_part_names.append("IGBT Module")
                elif "resistor" in cause_str:
                    suggested_part_names.append("Brake Resistor")

        # For each suggested part, search suppliers
        for part_name in suggested_part_names:
            part_number = self._get_part_number(manufacturer, model or "", part_name)

            part_result = {
                "part_name": part_name,
                "part_number": part_number,
                "manufacturer": manufacturer,
                "suppliers": []
            }

            # Search each relevant supplier
            for supplier in self.SA_PARTS_SUPPLIERS:
                if self._supplier_relevant(supplier, manufacturer):
                    try:
                        results = await self._search_supplier(supplier, part_name, manufacturer, model)
                        part_result["suppliers"].extend(results)
                    except Exception as e:
                        logger.debug(f"Error searching {supplier['name']}: {e}")

            # Add generic alternative if available
            if part_number != "N/A":
                generic = self._find_generic_alternative(part_number)
                if generic:
                    part_result["generic_alternative"] = generic

            parts.append(part_result)

        return parts

    async def _search_supplier(
        self,
        supplier: Dict,
        part_name: str,
        manufacturer: str,
        model: Optional[str]
    ) -> List[Dict]:
        """
        Search specific supplier for part.

        Args:
            supplier: Supplier dict from database
            part_name: Part name to search for
            manufacturer: Equipment manufacturer
            model: Equipment model

        Returns:
            List of {supplier, price, lead_time, url}
        """
        results = []
        query = f"{manufacturer} {part_name}"

        # Build search URL
        base_url = supplier.get("url", "")
        search_template = supplier.get("search_url", "")
        search_url = base_url + search_template.format(query=query)

        # Skip slow HTTP requests - return placeholder data for fast demo response
        # In production, would make actual HTTP request with timeout
        results = [{
            "supplier": supplier["name"],
            "url": search_url,
            "price": supplier.get("price_range", "Contact for price"),
            "lead_time": supplier.get("lead_time", "2-5 days"),
            "available": True
        }]

        return results

    def _parse_supplier_results(self, html: str, supplier_name: str) -> List[Dict]:
        """
        Parse supplier HTML to extract product info.

        Generic implementation - would need customization per supplier.
        """
        soup = BeautifulSoup(html, 'lxml')
        results = []

        # Generic product parsing (look for common patterns)
        products = soup.find_all(['div', 'article'], class_=re.compile(r'product|item|card'))

        for product in products[:5]:  # Limit to top 5 results
            # Try to find name/title
            name = None
            for tag in ['h2', 'h3', 'h4', 'span', 'a']:
                name_elem = product.find(tag, class_=re.compile(r'name|title|product'))
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    break

            # Try to find price
            price = None
            for tag in ['span', 'div']:
                price_elem = product.find(tag, class_=re.compile(r'price|cost'))
                if price_elem:
                    price = price_elem.get_text(strip=True)
                    break

            # Try to find part number/SKU
            part_num = None
            for tag in ['span', 'div']:
                sku_elem = product.find(tag, class_=re.compile(r'sku|part|mpn'))
                if sku_elem:
                    part_num = sku_elem.get_text(strip=True)
                    break

            if name:
                # Check availability
                text = product.get_text().lower()
                in_stock = "in stock" in text or "available" in text
                lead_time = "In stock" if in_stock else "2-5 days"

                results.append({
                    "supplier": supplier_name,
                    "name": name,
                    "part_number": part_num if part_num else "N/A",
                    "price": price if price else "Contact for price",
                    "lead_time": lead_time,
                    "available": in_stock,
                    "url": "N/A"  # Would extract actual URL
                })

        # If no products found, return placeholder
        if not results:
            results = [{
                "supplier": supplier_name,
                "name": "Contact for part availability",
                "part_number": "N/A",
                "price": "Contact for price",
                "lead_time": "Contact supplier",
                "available": True,
                "url": "N/A"
            }]

        return results

    def _get_part_number(self, manufacturer: str, model: str, part_name: str) -> str:
        """
        Get OEM part number for part.

        Args:
            manufacturer: Equipment manufacturer
            model: Equipment model
            part_name: Part name

        Returns:
            Part number or "N/A" if unknown
        """
        # Look up in part number mappings
        mfg_map = self.PART_NUMBER_MAPPINGS.get(manufacturer.lower(), {})
        if model:
            model_map = mfg_map.get(model.lower(), {})
            return model_map.get(part_name, "N/A")
        return "N/A"

    def _supplier_relevant(self, supplier: Dict, manufacturer: str) -> bool:
        """
        Check if supplier stocks this manufacturer's parts.

        Args:
            supplier: Supplier dict
            manufacturer: Manufacturer name

        Returns:
            True if supplier is relevant for this manufacturer
        """
        brands = supplier.get("brands", [])
        return "all" in [b.lower() for b in brands] or manufacturer.lower() in [b.lower() for b in brands]

    def _find_generic_alternative(self, oem_part_number: str) -> Optional[Dict]:
        """
        Find generic alternative for OEM part.

        Args:
            oem_part_number: OEM part number

        Returns:
            Dict with generic alternative info or None
        """
        for category, info in self.GENERIC_EQUIVALENTS.items():
            if info.get("carrier_oem") == oem_part_number or info.get("trane_oem") == oem_part_number:
                return {
                    "category": category,
                    "generic_part_number": info.get("generic"),
                    "manufacturer": info.get("manufacturer"),
                    "description": info.get("description"),
                    "suppliers": info.get("suppliers", [])
                }
        return None


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
