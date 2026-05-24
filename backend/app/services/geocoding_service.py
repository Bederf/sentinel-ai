"""Geocoding service for building site lookup during onboarding.

Uses OpenStreetMap Nominatim (free) for:
- Forward geocoding (address → lat/lon + formatted address)
- OSM building polygon for GPS orientation (longest axis bearing)

Free tier: 1 req/s. Always add User-Agent header.
"""

import json as json_mod
import logging
import math
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class GeocodingService:
    """Geocode building addresses and extract GPS orientation."""

    BASE_URL = "https://nominatim.openstreetmap.org"

    def geocode(self, query: str) -> dict[str, Any] | None:
        """Forward geocode: address string → lat, lon, display_name.

        Args:
            query: Address or building name to geocode

        Returns:
            Dict with lat, lon, display_name, type or None if not found
        """
        import urllib.request

        params = f"q={urllib.parse.quote(query)}&format=json&limit=1&addressdetails=1"
        url = f"{self.BASE_URL}/search?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "SentinelBMS/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read())
                if not data:
                    return None
                d = data[0]
                addr = d.get("address", {})
                return {
                    "lat": float(d["lat"]),
                    "lon": float(d["lon"]),
                    "display_name": d.get("display_name", ""),
                    "type": addr.get("building") or addr.get("amenity") or "unknown",
                    "address": {
                        "road": addr.get("road", ""),
                        "suburb": addr.get("suburb", ""),
                        "city": addr.get("city", "") or addr.get("town", "") or addr.get("metropolis", ""),
                        "province": addr.get("state", ""),
                        "country": addr.get("country", ""),
                        "postcode": addr.get("postcode", ""),
                    },
                    "osm_id": d.get("osm_id"),
                }
        except Exception as e:
            logger.warning(f"Geocoding failed for '{query}': {e}")
            return None

    def get_building_polygon(self, lat: float, lon: float, radius_m: int = 100) -> list[list[float]] | None:
        """Get building footprint polygon near lat/lon from OSM Overpass.

        Uses Overpass API to find building polygon near coordinates.
        Returns the outermost ring as [[lon, lat], ...] suitable for orientation calc.

        Args:
            lat: Latitude of search center
            lon: Longitude of search center
            radius_m: Search radius in metres

        Returns:
            List of [lon, lat] polygon coordinates or None if nothing found
        """
        import json as json_mod
        import urllib.request

        overpass_url = "https://overpass-api.de/api/interpreter"
        query = f"""
[out:json][timeout:15];
(
  way["building"](around:{radius_m},{lat},{lon});
);
out body geom;
"""
        req = urllib.request.Request(
            overpass_url,
            data=query.encode(),
            headers={"User-Agent": "SentinelBMS/1.0", "Content-Type": "application/x-www-form-urlencoded"},
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json_mod.loads(r.read())
        except Exception as e:
            logger.warning(f"Overpass API failed for ({lat},{lon}): {e}")
            return None

        elements = data.get("elements", [])
        if not elements:
            return None

        best = None
        best_area = 0.0

        for el in elements:
            if el["type"] != "way":
                continue
            tags = el.get("tags", {})
            if not tags.get("building"):
                continue
            geometry = el.get("geometry", [])
            if len(geometry) < 3:
                continue

            # Calculate approximate area using shoelace formula on projected coords
            coords = [(g["lon"], g["lat"]) for g in geometry]
            area = self._shoelace_area(coords)
            if area > best_area:
                best_area = area
                best = coords

        return best

    def calculate_orientation(self, polygon: list[list[float]]) -> float | None:
        """Calculate building orientation from polygon.

        Finds the longest axis of the building footprint (longest distance
        between any two polygon vertices) and returns its bearing in degrees
        clockwise from North (0°).

        Args:
            polygon: List of [lon, lat] pairs from OSM geometry

        Returns:
            Bearing in degrees (0-360, clockwise from north) or None if degenerate
        """
        if len(polygon) < 3:
            return None

        # Project to local Cartesian (approx metres from centroid)
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)

        def proj(lon, lat):
            # Simple equirectangular approx in metres
            lat_m = (lat - cy) * 111320.0
            lon_m = (lon - cx) * 111320.0 * math.cos(math.radians(cy))
            return lon_m, lat_m

        proj_coords = [proj(p[0], p[1]) for p in polygon]

        # Find farthest pair = longest axis
        max_dist = 0.0
        p1, p2 = proj_coords[0], proj_coords[1]
        for i in range(len(proj_coords)):
            for j in range(i + 1, len(proj_coords)):
                dx = proj_coords[j][0] - proj_coords[i][0]
                dy = proj_coords[j][1] - proj_coords[i][1]
                d = math.sqrt(dx * dx + dy * dy)
                if d > max_dist:
                    max_dist = d
                    p1, p2 = proj_coords[i], proj_coords[j]

        if max_dist < 2.0:  # less than 2m — probably invalid
            return None

        # Bearing from p1 to p2
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        bearing = math.degrees(math.atan2(dx, dy)) % 360.0
        return round(bearing, 1)

    def _shoelace_area(self, coords: list[tuple[float, float]]) -> float:
        """Approximate area of polygon using shoelace formula on lon/lat."""
        n = len(coords)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += coords[i][0] * coords[j][1]
            area -= coords[j][0] * coords[i][1]
        return abs(area) * 0.5 * 111320.0 * 111320.0 * math.cos(math.radians(coords[0][1]))


_service = None


def get_geocoding_service() -> GeocodingService:
    global _service
    if _service is None:
        _service = GeocodingService()
    return _service
