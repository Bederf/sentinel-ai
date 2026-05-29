"""
Building Geometry Scraper — extracts building shape from web photos.

Flow:
1. Scrape building photo from web (Google Images / Bing / website)
2. Send photo to Claude Vision via model_gateway for geometry extraction
3. Store geometry on the site's Supabase record
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.models.building_geometry import BuildingGeometry

logger = logging.getLogger("sentinel.building_geometry")


async def scrape_site_geometry(
    site_id: str,
    site_name: str,
    address: str,
) -> BuildingGeometry:
    """Full pipeline: scrape photo → extract geometry → persist to Supabase."""
    image_bytes = await _scrape_building_photo(site_name, address)

    if image_bytes:
        geometry = await _extract_geometry_from_photo(image_bytes)
    else:
        logger.warning("No photo found for %s, using defaults", site_name)
        geometry = _default_geometry(site_name)

    await _persist_geometry(site_id, geometry)
    return geometry


async def _scrape_building_photo(
    site_name: str,
    address: str,
) -> bytes | None:
    """Scrape a building photo from the web using Google Custom Search or Bing."""
    import base64

    query = f"{site_name} {address} building"
    logger.info("Searching for building photo: %s", query)

    # Try Google Custom Search API if configured
    from app.config.settings import settings

    if settings.google_cse_api_key and settings.google_cse_engine_id:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": settings.google_cse_api_key,
                        "cx": settings.google_cse_engine_id,
                        "q": query,
                        "searchType": "image",
                        "num": 1,
                        "imgSize": "large",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    if items:
                        img_url = items[0]["link"]
                        logger.info("Found building photo at %s", img_url)
                        img_resp = await client.get(img_url, timeout=15.0)
                        if img_resp.status_code == 200:
                            return img_resp.content
        except Exception as e:
            logger.warning("Google CSE search failed: %s", e)

    # Fallback: try direct download from known patterns
    for url in _guess_photo_urls(site_name, address):
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200 and len(resp.content) > 1024:
                    content_type = resp.headers.get("content-type", "")
                    if "image" in content_type:
                        logger.info("Downloaded building photo from %s", url)
                        return resp.content
        except Exception:
            continue

    return None


def _guess_photo_urls(site_name: str, address: str) -> list[str]:
    """Generate likely photo URLs based on site name/address."""
    import re

    name_slug = re.sub(r"[^a-z0-9]+", "-", site_name.lower()).strip("-")
    clean_name = re.sub(r"[^a-z0-9]+", "", site_name.lower())

    urls = []

    # Busamed hospitals follow a pattern
    if "busamed" in clean_name:
        urls.append(
            f"https://busamed.co.za/wp-content/uploads/2025/03/{name_slug}.webp"
        )
        urls.append(
            f"https://busamed.co.za/wp-content/uploads/2024/08/{name_slug}.webp"
        )

    # Generic Wikimedia Commons
    urls.append(
        f"https://commons.wikimedia.org/wiki/Special:FilePath/{name_slug}.jpg"
    )

    return urls


async def _extract_geometry_from_photo(image_bytes: bytes) -> BuildingGeometry:
    """Send photo to Claude Vision and parse geometry response."""
    import base64

    b64 = base64.b64encode(image_bytes).decode()

    prompt = """Analyze this building photo and extract its physical geometry.
Return JSON only — no explanation, no markdown.

{
  "floor_count": <integer: count visible floors from window rows>,
  "shape": "<one of: rectangular, tower, L_shaped, stepped, courtyard>",
  "setbacks": [{"floor": <int>, "ratio": <float 0-1>}],
  "facade": "<one of: glass, concrete, mixed>",
  "footprint_width_depth_ratio": <float: width/depth, 0.3-5.0>,
  "roof_equipment": <bool>
}

Rules:
- floor_count: count horizontal window bands. Minimum 1.
- shape: rectangular = same width all floors. tower = narrow tall. stepped = different widths. courtyard = building surrounds open space.
- setbacks: only include if shape is stepped. Each entry is a floor index where the building width changes.
- footprint_width_depth_ratio: 1.0 = square. >1.5 = wide. <0.7 = narrow tower.
- roof_equipment: true if cooling towers, antennas, or mechanical penthouse visible.
"""

    from app.services.model_gateway import model_gateway

    response = await model_gateway.call(
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        task_class="heavy",
    )

    text = response.get("content", "")
    # Extract JSON from response (handle markdown-wrapped responses)
    json_str = text.strip()
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0].strip()
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.error("Failed to parse geometry JSON from Claude: %s", text[:500])
        return _default_geometry("unknown")

    return BuildingGeometry(**data)


def _default_geometry(site_name: str) -> BuildingGeometry:
    """Return sensible defaults when scraping fails."""
    return BuildingGeometry(
        floor_count=5,
        shape="rectangular",
        setbacks=[],
        facade="mixed",
        footprint_width_depth_ratio=1.0,
        roof_equipment=False,
        source="default",
    )


async def _persist_geometry(site_id: str, geometry: BuildingGeometry) -> None:
    """Store geometry on the site record in Supabase."""
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        client.table("sites").update(
            {"building_geometry": geometry.to_dict()}
        ).eq("code", site_id).execute()
        logger.info("Persisted building geometry for %s", site_id)
    except Exception as e:
        logger.warning("Failed to persist geometry for %s: %s", site_id, e)


async def get_site_geometry(site_id: str) -> BuildingGeometry | None:
    """Load stored geometry from Supabase."""
    try:
        from app.database.supabase_client import get_supabase_client

        client = get_supabase_client()
        result = (
            client.table("sites")
            .select("building_geometry")
            .eq("code", site_id)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("building_geometry"):
            return BuildingGeometry.from_dict(result.data[0]["building_geometry"])
    except Exception as e:
        logger.warning("Failed to load geometry for %s: %s", site_id, e)
    return None
