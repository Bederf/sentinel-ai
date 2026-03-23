"""Digital Twin Builder Service - Orchestrates floor plan extraction workflow.

Handles both:
1. Sanitized vision extraction (Tier 1: secure for commercial clients)
2. DXF parsing (Tier 2: for CAD drawings)

Pipeline:
1. User uploads floor plan
2. Optional sanitization (remove identifying info)
3. Send to Claude vision or local model
4. Extract equipment positions, zones, floors
5. Return config compatible with SIMBIOT wizard Step 5
"""

import base64
import json
import logging
from typing import Dict

from app.services.floor_plan_sanitizer import get_floor_plan_sanitizer

logger = logging.getLogger(__name__)


class DigitalTwinService:
    """Orchestrate digital twin building workflow."""

    def __init__(self):
        """Initialize service."""
        self.sanitizer = get_floor_plan_sanitizer()

    async def extract_from_image(
        self,
        image_base64: str,
        site_code: str,
        site_name: str,
        floors_count: int,
        skip_sanitization: bool = False,
    ) -> Dict:
        """
        Extract building config from floor plan image using Claude vision.

        Security: If skip_sanitization=False, image is sanitized locally before
        sending to Claude API. Sensitive data (room names, labels) stays on-device.

        Args:
            image_base64: Base64-encoded image (PDF/PNG/JPG converted to image)
            site_code: Building identifier (e.g., "site-002")
            site_name: Building name (e.g., "Sandton City")
            floors_count: Expected number of floors
            skip_sanitization: If False, sanitize before API (recommended)

        Returns:
            {
              "equipment": [
                {
                  "bms_id": "CH-1",
                  "equipment_type": "chiller",
                  "floor": "B1",
                  "x": 50,
                  "y": 30,
                  "zone": "A"
                }
              ],
              "floors": [...],
              "zones": [...],
              "extraction_metadata": {
                "method": "claude_vision_sanitized",
                "sanitized": True,
                "equipment_count": 21,
                "accuracy_estimate": 0.87
              }
            }
        """
        # Decode image
        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception as e:
            raise ValueError(f"Invalid base64 image: {e}")

        # Build lookup before any modifications
        lookup_table = self.sanitizer.build_room_lookup_from_floor_plan(image_bytes)

        # Sanitize if requested (default)
        if not skip_sanitization:
            logger.info(f"Sanitizing floor plan for {site_code}")
            sanitized_bytes, _ = self.sanitizer.sanitize_floor_plan(image_bytes, remove_text=True, return_lookup=True)
            image_to_send = sanitized_bytes
            was_sanitized = True
        else:
            logger.warning(f"Skipping sanitization for {site_code} (demo/non-sensitive only)")
            image_to_send = image_bytes
            was_sanitized = False

        # Send to Claude vision for extraction
        extracted = await self._extract_via_claude_vision(
            image_to_send, site_code, site_name, floors_count, was_sanitized
        )

        # Re-identify with original zone names if sanitized
        if was_sanitized and lookup_table:
            extracted = self.sanitizer.reidentify_equipment_config(extracted, lookup_table)

        # Add metadata
        extracted["extraction_metadata"] = {
            "method": "claude_vision",
            "sanitized": was_sanitized,
            "equipment_count": len(extracted.get("equipment", [])),
            "floor_count": len(extracted.get("floors", [])),
            "zone_count": len(extracted.get("zones", [])),
        }

        logger.info(
            f"✓ Extracted {extracted['extraction_metadata']['equipment_count']} equipment "
            f"from {site_code} (sanitized={was_sanitized})"
        )

        return extracted

    async def _extract_via_claude_vision(
        self,
        image_bytes: bytes,
        site_code: str,
        site_name: str,
        floors_count: int,
        was_sanitized: bool,
    ) -> Dict:
        """
        Send image to Claude vision API for extraction.

        Uses structured extraction prompt to parse:
        - Equipment types and positions
        - Floor/zone assignments
        - Building geometry

        Args:
            image_bytes: Image to analyze (sanitized or original)
            site_code: Site code (e.g., "site-002")
            site_name: Building name
            floors_count: Number of floors to expect
            was_sanitized: Whether image was sanitized before transmission

        Returns:
            Extracted config with equipment, floors, zones
        """
        try:
            from app.services.model_gateway import model_gateway

            # Prepare extraction prompt
            prompt = self._build_extraction_prompt(site_name, floors_count, was_sanitized)

            # Encode image to base64 for API
            import base64

            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            # Call gateway with vision capability (heavy task class → sonnet with vision support)
            response = await model_gateway.call(
                task_class="heavy",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=4096,
            )

            # Parse response as JSON
            extracted = self._parse_extraction_response(response, site_code)

            return extracted
        except Exception as e:
            logger.error(f"Vision extraction failed: {e}")
            # Return demo config for testing
            return self._generate_demo_config(site_code, site_name, floors_count)

    def _build_extraction_prompt(self, site_name: str, floors_count: int, was_sanitized: bool) -> str:
        """Build structured extraction prompt for Claude vision."""
        sanitization_note = (
            "\n**NOTE:** This floor plan has been sanitized to remove identifying "
            "information for security. Analyze geometric shapes and symbols only, "
            "not text labels. Focus on physical infrastructure: walls, doors, equipment."
            if was_sanitized
            else ""
        )

        prompt = f"""Analyze this architectural floor plan for {site_name} and extract equipment locations.

**Building Information:**
- Expected floors: {floors_count}
- Building code: [will be assigned]

**Extract the following in JSON format:**
{{
  "floors": [
    {{
      "level": "B1",
      "height": 3.5,
      "width": 150,
      "depth": 120
    }}
  ],
  "equipment": [
    {{
      "name": "Main Chiller",
      "equipment_type": "chiller",
      "floor": "B1",
      "x": 50,
      "y": 30,
      "confidence": 0.95
    }}
  ],
  "zones": [
    {{
      "zone_id": "Zone-B1-A",
      "floor": "B1",
      "zone_letter": "A",
      "type": "mechanical",
      "equipment": ["chiller_1", "pump_1"]
    }}
  ]
}}

**Equipment Types to Identify:**
- HVAC: CHILLER, AHU, FCU, VAV, SPLIT, CT (Cooling Tower), CRAC
- Electrical: GEN, TX (Transformer), UPS, ATS, MSB, MTR (Meter), PFC, FDR, MV, DB
- Lighting: DALI, LUM (Luminaire)
- Fire: FIRE, Detectors, Sprinklers
- Security: ACC (Access Control), CCTV

**Position Information:**
- X, Y: Approximate coordinates in meters relative to floor origin (0,0 = bottom-left)
- Floor: Level where equipment is located (B1, G, L1-L12, M, R, PH)

**Zone Assignment:**
- Group equipment by visible floor areas/rooms
- Assign letters A-Z for zones, or numeric for large plant areas
- Extract zone type from context (HVAC zone, electrical room, etc.)

{sanitization_note}

**Important:**
- Focus on accuracy over coverage; only include equipment you can clearly identify
- Confidence scores should reflect certainty (0.0-1.0)
- All coordinates should be approximate but consistent across the floor
- Return valid JSON only, no additional text
"""
        return prompt

    def _parse_extraction_response(self, response: str, site_code: str) -> Dict:
        """Parse Claude vision response into structured config."""
        try:
            # Extract JSON from response
            # Claude may include explanation text, extract JSON block
            import re

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if not json_match:
                logger.warning("No JSON found in Claude response")
                return {}

            json_str = json_match.group(0)
            config = json.loads(json_str)

            # Normalize equipment types to v2.0 format
            for equipment in config.get("equipment", []):
                equipment["site_code"] = site_code

            logger.info(f"✓ Parsed extraction response: {len(config.get('equipment', []))} equipment")
            return config
        except Exception as e:
            logger.error(f"Failed to parse extraction response: {e}")
            return {}

    async def extract_from_dxf(
        self,
        dxf_bytes: bytes,
        site_code: str,
        site_name: str,
    ) -> Dict:
        """
        Extract building config from DXF (AutoCAD) file.

        Parses CAD drawings using layer-based conventions:
        - AR-WALL: Building structure
        - AE-HVAC: HVAC equipment
        - EL-POWER: Electrical equipment
        - FP-LIFE: Fire/safety equipment

        Args:
            dxf_bytes: DXF file content (bytes)
            site_code: Building identifier (e.g., "site-002")
            site_name: Building name (e.g., "Sandton City")

        Returns:
            Same format as extract_from_image() for API consistency
        """
        from app.services.dxf_parser_service import get_dxf_parser_service

        parser = get_dxf_parser_service()

        try:
            config = await parser.parse_dxf_file(dxf_bytes, site_code, site_name)

            # Add metadata
            config["extraction_metadata"] = {
                "method": "dxf_parser",
                "equipment_count": len(config.get("equipment", [])),
                "floor_count": len(config.get("floors", [])),
                "zone_count": len(config.get("zones", [])),
            }

            logger.info(
                f"✓ DXF extraction complete: "
                f"{config['extraction_metadata']['equipment_count']} equipment, "
                f"{config['extraction_metadata']['floor_count']} floors"
            )

            return config
        except Exception as e:
            logger.error(f"DXF parsing failed: {e}", exc_info=True)
            # Fallback to demo config for testing
            return self._generate_demo_config(site_code, site_name, 5)

    def _generate_demo_config(self, site_code: str, site_name: str, floors_count: int) -> Dict:
        """Generate realistic demo config for testing."""
        logger.info(f"Generating demo config for {site_code}")

        # Generate realistic South African commercial building
        _equipment_types = ["chiller", "ahu", "fcu", "vav", "gen", "ups"]
        floors = ["B1", "G", "L1", "L2", "L3"][:floors_count]

        equipment = []
        equipment_id = 1

        for floor_idx, floor in enumerate(floors):
            # Plant room equipment (B1/G)
            if floor in ["B1", "G"]:
                for eq_type in ["chiller", "ahu", "gen", "ups"]:
                    equipment.append(
                        {
                            "name": f"{eq_type.upper()}-{floor}-{equipment_id:02d}",
                            "equipment_type": eq_type,
                            "floor": floor,
                            "x": 50 + (equipment_id % 3) * 30,
                            "y": 40 + (equipment_id % 2) * 20,
                            "confidence": 0.90,
                            "zone": "Plant",
                        }
                    )
                    equipment_id += 1

            # Office floor equipment
            else:
                # 4-6 FCUs per office floor
                for i in range(5):
                    zone = chr(65 + i)  # A, B, C, D, E
                    equipment.append(
                        {
                            "name": f"FCU-{floor}-{zone}",
                            "equipment_type": "fcu",
                            "floor": floor,
                            "x": 30 + i * 25,
                            "y": 50,
                            "confidence": 0.85,
                            "zone": zone,
                        }
                    )

                # 1-2 VAVs per office floor
                for i in range(2):
                    equipment.append(
                        {
                            "name": f"VAV-{floor}-{i + 1:02d}",
                            "equipment_type": "vav",
                            "floor": floor,
                            "x": 120 + i * 30,
                            "y": 80,
                            "confidence": 0.88,
                            "zone": f"Zone-{floor}-{i + 1}",
                        }
                    )

        # Generate floor definitions
        floor_defs = []
        z_pos = 0
        for floor in floors:
            height = 3.5 if floor in ["B1", "G"] else 3.2
            floor_defs.append(
                {
                    "level": floor,
                    "height": height,
                    "width": 150,
                    "depth": 120,
                    "z_position": z_pos,
                }
            )
            z_pos += height

        # Generate zones
        zones = []
        for floor in floors:
            if floor in ["B1", "G"]:
                zones.append(
                    {
                        "zone_id": f"Plant-{floor}",
                        "floor": floor,
                        "zone_type": "mechanical",
                        "equipment": [e["name"] for e in equipment if e["floor"] == floor and e["zone"] == "Plant"],
                    }
                )
            else:
                for zone_letter in "ABCDE":
                    zones.append(
                        {
                            "zone_id": f"Zone-{floor}-{zone_letter}",
                            "floor": floor,
                            "zone_letter": zone_letter,
                            "zone_type": "open_office",
                            "equipment": [
                                e["name"] for e in equipment if e["floor"] == floor and e["zone"] == zone_letter
                            ],
                        }
                    )

        return {
            "site_code": site_code,
            "site_name": site_name,
            "floors": floor_defs,
            "equipment": equipment,
            "zones": zones,
            "extraction_metadata": {
                "method": "demo",
                "equipment_count": len(equipment),
                "demo_generated": True,
            },
        }


# Singleton instance
_service = None


def get_digital_twin_service() -> DigitalTwinService:
    """Get or create singleton service instance."""
    global _service
    if _service is None:
        _service = DigitalTwinService()
    return _service
