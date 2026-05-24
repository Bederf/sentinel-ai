"""
OEM Parts Scraper — uses Firecrawl CLI to scrape manufacturer parts pages.

Fetches OEM part numbers, names, and prices for equipment given
manufacturer + model. Falls back gracefully if Firecrawl isn't configured.
"""

import asyncio
import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# OEM search URLs per manufacturer for parts lookup
OEM_PARTS_URLS: dict[str, str] = {
    "carrier": "https://www.carrier.com/commercial/en/us/parts-and-supplies/",
    "trane": "https://www.trane.com/residential/en/parts-and-supplies/",
    "york": "https://www.york.com/parts/",
    "daikin": "https://www.daikinac.com/parts/",
    "grundfos": "https://www.grundfos.com/parts/",
    "siemens": "https://mail.industry.siemens.com/parts/",
    "honeywell": "https://buildings.honeywell.com/parts/",
    "schneider": "https://www.se.com/ww/en/parts/",
    "abb": "https://new.abb.com/parts/",
    "danfoss": "https://www.danfoss.com/parts/",
}


def is_configured() -> bool:
    """Check if Firecrawl CLI is available and API key is set."""
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return False
    try:
        subprocess.run(
            ["npx", "firecrawl-cli@latest", "view-config"],
            capture_output=True,
            timeout=10,
            env={**os.environ, "FIRECRAWL_API_KEY": api_key},
        )
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


async def scrape_oem_parts(
    manufacturer: str,
    model: str,
    equipment_type: str | None = None,
) -> list[dict[str, Any]]:
    """Scrape OEM parts for a given manufacturer + model using Firecrawl.

    Strategy:
    1. Search Firecrawl for manufacturer + model + "spare parts"
    2. Extract part numbers from search result snippets
    3. If found, also scrape promising URLs for full page content
    4. Deduplicate and return

    Returns empty list if Firecrawl isn't configured or no parts found.
    """
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        logger.info("[OEM SCRAPE] FIRECRAWL_API_KEY not set — skipping")
        return []

    search_query = f"{manufacturer} {model} spare parts list part number"
    if equipment_type:
        search_query = f"{manufacturer} {model} {equipment_type} OEM spare parts"

    all_parts: list[dict[str, Any]] = []
    seen_pn: set[str] = set()

    try:
        search_result = await _run_firecrawl_search(search_query, api_key)
        if search_result:
            parts = _extract_parts_from_content(search_result, manufacturer, model)
            for p in parts:
                pn = p.get("part_number", "")
                if pn and pn not in seen_pn:
                    seen_pn.add(pn)
                    all_parts.append(p)

            candidate_urls = _extract_urls_from_search(search_result, model)
            for url in candidate_urls[:2]:
                scrape_result = await _run_firecrawl_scrape(url, api_key)
                if scrape_result:
                    deep_parts = _extract_parts_from_content(scrape_result, manufacturer, model)
                    for p in deep_parts:
                        pn = p.get("part_number", "")
                        if pn and pn not in seen_pn:
                            seen_pn.add(pn)
                            all_parts.append(p)

        if all_parts:
            logger.info(
                "[OEM SCRAPE] Found %d parts for %s %s",
                len(all_parts), manufacturer, model,
            )
        else:
            logger.info("[OEM SCRAPE] No parts found for %s %s", manufacturer, model)
        return all_parts

    except Exception as e:
        logger.warning("[OEM SCRAPE] Failed for %s %s: %s", manufacturer, model, e)
        return []


async def _run_firecrawl_search(query: str, api_key: str) -> str | None:
    """Run Firecrawl search for parts query."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "npx", "firecrawl-cli@latest", "search", query,
            "--limit", "5",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "FIRECRAWL_API_KEY": api_key},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            logger.debug("[OEM SCRAPE] Search failed: %s", stderr.decode()[:200])
            return None
        return stdout.decode()
    except (asyncio.TimeoutError, FileNotFoundError) as e:
        logger.debug("[OEM SCRAPE] Search error: %s", e)
        return None


async def _run_firecrawl_scrape(url: str, api_key: str) -> str | None:
    """Run Firecrawl scrape on a URL."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "npx", "firecrawl-cli@latest", "scrape", url,
            "--format", "markdown",
            "--wait-for", "3000",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "FIRECRAWL_API_KEY": api_key},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            logger.debug("[OEM SCRAPE] Scrape failed: %s", stderr.decode()[:200])
            return None
        return stdout.decode()
    except (asyncio.TimeoutError, FileNotFoundError) as e:
        logger.debug("[OEM SCRAPE] Scrape error: %s", e)
        return None


def _extract_urls_from_search(search_output: str, model: str) -> list[str]:
    """Extract promising URLs from Firecrawl search output."""
    import re

    urls: list[str] = []
    url_pattern = re.compile(r"URL:\s*(https?://[^\s]+)")
    model_lower = model.lower()

    for line in search_output.split("\n"):
        match = url_pattern.search(line)
        if not match:
            continue
        url = match.group(1)
        if any(skip in url for skip in ["youtube.com", "facebook.com", "instagram.com"]):
            continue
        if model_lower in url.lower():
            urls.insert(0, url)
        else:
            urls.append(url)

    return urls


def _extract_parts_from_content(
    content: str,
    manufacturer: str,
    model: str,
) -> list[dict[str, Any]]:
    """Parse Firecrawl search/scrape output for part listings.

    Handles Firecrawl search output format:
      Title
        URL: https://...
        Description/snippet...

    Returns structured part data by looking for OEM part numbers
    in lines that mention parts-related keywords.
    """
    import re

    parts: list[dict[str, Any]] = []
    seen_pn: set[str] = set()

    part_number_patterns = [
        re.compile(r"\b(\d{2,}[A-Z][A-Z0-9]{7,})\b"),
        re.compile(r"\b([A-Z]{2,}[-][A-Z0-9]+[-][A-Z0-9]+)\b"),
    ]
    price_zar_pattern = re.compile(r"(?:R|ZAR|USD)\s*([\d,]+(?:\.\d{2})?)")
    parts_keywords = {"filter", "belt", "seal", "bearing", "valve", "sensor",
                      "actuator", "motor", "pump", "capacitor", "board",
                      "gasket", "impeller", "relay", "thermostat", "coil",
                      "drier", "strainer", "oil", "refrigerant", "spare",
                      "replacement", "part"}

    lines = content.split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith("URL:"):
            continue

        has_part_kw = any(kw in line.lower() for kw in parts_keywords)
        if not has_part_kw:
            continue

        pn_matches = []
        for pat in part_number_patterns:
            pn_matches.extend(pat.findall(line))
        if not pn_matches:
            continue

        for pn in pn_matches:
            clean_pn = pn.strip().rstrip(".- ")
            if len(clean_pn) < 7:
                continue
            if clean_pn.lower().startswith(model.lower()[:4]):
                continue
            if clean_pn in seen_pn:
                continue
            seen_pn.add(clean_pn)

            part_entry: dict[str, Any] = {
                "part_name": line[:120],
                "part_number": clean_pn,
                "manufacturer": manufacturer,
                "model": model,
                "source": "scraped",
                "criticality": "consumable",
            }

            price_match = price_zar_pattern.search(line)
            if price_match:
                try:
                    part_entry["unit_cost_zar"] = round(
                        float(price_match.group(1).replace(",", "")), 2
                    )
                except ValueError:
                    pass

            parts.append(part_entry)

    return parts


def _estimate_part_relevance(part_name: str, part_number: str, model: str) -> int:
    """Score how relevant a scraped part is to the target model (0-100)."""
    score = 50
    pn_lower = part_name.lower()
    if model.lower() in pn_lower or model.lower()[:4] in pn_lower:
        score += 30
    if any(kw in pn_lower for kw in ["genuine", "oem", "original"]):
        score += 15
    if any(kw in pn_lower for kw in ["compatible", "universal", "alternative"]):
        score -= 20
    return min(100, max(0, score))


async def scrape_and_populate_parts(
    equipment_id: str,
    equipment_type: str,
    manufacturer: str | None,
    model: str | None,
) -> int:
    """Scrape OEM parts and populate into spare_parts table.

    Returns number of parts populated (0 if none found or Firecrawl unavailable).
    """
    if not manufacturer or not model:
        return 0

    from app.database.repositories.spare_parts_repository import SparePartsRepository

    repo = SparePartsRepository()
    existing = repo.get_parts_for_equipment(equipment_id)
    if existing:
        return 0

    parts = await scrape_oem_parts(manufacturer, model, equipment_type)
    if not parts:
        return 0

    count = 0
    for part in parts:
        part_data = {
            "equipment_id": equipment_id,
            "equipment_type": equipment_type,
            "manufacturer": manufacturer,
            "model": model,
            "source": "scraped",
            "part_name": part["part_name"],
            "part_number": part.get("part_number"),
            "unit_cost_zar": part.get("unit_cost_zar"),
            "criticality": part.get("criticality", "consumable"),
            "initial_stock": 0,
        }
        created = repo.create_part(part_data)
        if created:
            count += 1

    logger.info("[OEM SCRAPE] Populated %d scraped parts for %s", count, equipment_id)
    return count
