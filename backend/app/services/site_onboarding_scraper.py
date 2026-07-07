"""Site onboarding fact scraper.

Uses public web results to prefill non-sensitive site metadata during onboarding.
Missing or low-confidence values are returned for manual completion by the operator.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

logger = logging.getLogger("sentinel.site_onboarding_scraper")

ONBOARDING_FIELDS = [
    "sqm",
    "year_built",
    "latitude",
    "longitude",
    "contact_phone",
    "contact_email",
    "whatsapp_phone",
    "nmd_limit_kva",
    "demand_charge_per_kva",
    "electricity_provider",
]


async def scrape_site_onboarding_facts(
    site_name: str,
    address: str = "",
    building_type: str = "",
) -> dict[str, Any]:
    """Return scraped onboarding values, field sources, and unresolved gaps."""
    values: dict[str, Any] = {}
    sources: dict[str, dict[str, Any]] = {}

    geocoded = await _geocode(site_name, address)
    if geocoded:
        values.update(
            {
                "latitude": geocoded["lat"],
                "longitude": geocoded["lon"],
            }
        )
        if geocoded.get("display_name"):
            values.setdefault("address", geocoded["display_name"])
        sources["latitude"] = {
            "source": "geocode",
            "confidence": 0.9,
            "evidence": geocoded.get("display_name", "geocoded from site name/address"),
        }
        sources["longitude"] = sources["latitude"]
        if "address" in values:
            sources["address"] = sources["latitude"]

    scraped_text = await _scrape_public_text(site_name, address, building_type)
    if scraped_text:
        extracted = _extract_facts(scraped_text)
        for field, value in extracted.items():
            if value not in (None, "", 0) and field not in values:
                values[field] = value
                sources[field] = {
                    "source": "firecrawl",
                    "confidence": _confidence_for_field(field),
                    "evidence": _evidence_for_field(scraped_text, field, value),
                }

    missing = [field for field in ONBOARDING_FIELDS if values.get(field) in (None, "", 0)]
    return {
        "status": "ok",
        "values": values,
        "sources": sources,
        "missing": missing,
        "scrape_available": bool(scraped_text),
    }


async def _geocode(site_name: str, address: str) -> dict[str, Any] | None:
    query = " ".join(part for part in [site_name, address] if part).strip()
    if not query:
        return None
    try:
        from app.services.geocoding_service import get_geocoding_service

        result = get_geocoding_service().geocode(query)
        if not result:
            return None
        return {
            "lat": result["lat"],
            "lon": result["lon"],
            "display_name": result.get("display_name"),
        }
    except Exception as exc:
        logger.info("Geocode enrichment failed for %s: %s", query, exc)
        return None


async def _scrape_public_text(site_name: str, address: str, building_type: str) -> str | None:
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        logger.info("FIRECRAWL_API_KEY not set; site fact scrape skipped")
        return None

    query = " ".join(
        part
        for part in [
            site_name,
            address,
            building_type,
            "floor area year built contact phone email electricity provider",
        ]
        if part
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            "npx",
            "firecrawl-cli@latest",
            "search",
            query,
            "--limit",
            "5",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "FIRECRAWL_API_KEY": api_key},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=35)
        if proc.returncode != 0:
            logger.info("Firecrawl site fact search failed: %s", stderr.decode(errors="ignore")[:300])
            return None
        from app.services.ai_usage_tracker import usage_tracker

        usage_tracker.record_service(
            provider="firecrawl",
            units=1,
            unit_type="scrape",
            source="site_onboarding_search",
            site_id="unknown",
        )
        return stdout.decode(errors="ignore")
    except (TimeoutError, FileNotFoundError) as exc:
        logger.info("Firecrawl site fact search unavailable: %s", exc)
        return None


def _extract_facts(text: str) -> dict[str, Any]:
    facts: dict[str, Any] = {}

    email = _first_match(text, r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    if email:
        facts["contact_email"] = email

    address = _labeled_line_value(text, "Address")
    if address:
        facts["address"] = address

    phone = _first_match(
        text,
        r"(?:\+27|0)\s*\(?\d{2,3}\)?[\s-]?\d{3}[\s-]?\d{4}\b",
        re.IGNORECASE,
    )
    if phone:
        facts["contact_phone"] = _normalize_phone(phone)
        facts["whatsapp_phone"] = _normalize_phone(phone)

    sqm = _first_match(
        text,
        r"(\d{1,3}(?:[,\s]\d{3})+|\d{4,7})\s*(?:m2|m²|sqm|square\s+met(?:er|re)s?)",
        re.IGNORECASE,
    )
    if sqm:
        facts["sqm"] = int(re.sub(r"\D", "", sqm))

    year = _first_match(
        text,
        r"(?:built|opened|completed|established|founded|constructed)\D{0,40}\b(19\d{2}|20\d{2})\b",
        re.IGNORECASE,
    )
    if year:
        facts["year_built"] = int(year)

    for provider in ["City Power", "Eskom", "eThekwini", "City of Cape Town", "Mangaung", "Nelson Mandela Bay"]:
        if provider.lower() in text.lower():
            facts["electricity_provider"] = provider
            break

    nmd = _first_match(text, r"(?:NMD|notified maximum demand)\D{0,30}(\d+(?:\.\d+)?)\s*kVA", re.IGNORECASE)
    if nmd:
        facts["nmd_limit_kva"] = float(nmd)

    demand_charge = _first_match(
        text,
        r"(?:demand charge|capacity charge)\D{0,30}(?:R|ZAR)?\s?(\d+(?:\.\d+)?)\s*(?:/|per)?\s*kVA",
        re.IGNORECASE,
    )
    if demand_charge:
        facts["demand_charge_per_kva"] = float(demand_charge)

    return facts


def _first_match(text: str, pattern: str, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags)
    if not match:
        return None
    return match.group(1) if match.lastindex else match.group(0)


def _labeled_line_value(text: str, label: str) -> str | None:
    match = re.search(rf"\b{re.escape(label)}\.\s*([^\n]+)", text, re.IGNORECASE)
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip(" .")
    return value or None


def _normalize_phone(phone: str) -> str:
    normalized = re.sub(r"[()\-]", " ", phone)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _confidence_for_field(field: str) -> float:
    return {
        "contact_email": 0.75,
        "contact_phone": 0.7,
        "whatsapp_phone": 0.55,
        "sqm": 0.65,
        "year_built": 0.65,
        "electricity_provider": 0.55,
        "nmd_limit_kva": 0.45,
        "demand_charge_per_kva": 0.45,
    }.get(field, 0.5)


def _evidence_for_field(text: str, field: str, value: Any) -> str:
    needle = str(value)
    index = text.lower().find(needle.lower())
    if index == -1:
        return needle
    start = max(0, index - 80)
    end = min(len(text), index + len(needle) + 80)
    return " ".join(text[start:end].split())
