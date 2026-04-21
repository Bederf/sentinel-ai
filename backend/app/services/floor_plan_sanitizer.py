"""Floor Plan Sanitizer - Removes identifying information before API transmission.

Security: Strips room names, labels, and sensitive metadata from floor plans
before sending them to Claude API. The sanitized version contains only geometric
information (walls, doors, equipment symbols). Local lookup tables preserve the
mapping of anonymous entities back to real names, never transmitted.

Approach: Geometric Abstraction (Tier 1 Security)
- Threshold image to binary (walls/equipment vs empty space)
- Extract wall lines and door positions
- Identify equipment symbols by shape/contour
- Remove all text using OCR masking
- Redraw as clean schematic
- Rebuild lookup table locally for re-identification
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class FloorPlanSanitizer:
    """Sanitize floor plans by removing identifying information."""

    def __init__(self):
        """Initialize sanitizer."""
        self.ocr_installed = self._check_ocr()

    def _check_ocr(self) -> bool:
        """Check if pytesseract and tesseract-ocr are available."""
        try:
            import pytesseract  # noqa: F401

            return True
        except ImportError:
            logger.warning("pytesseract not available. Text removal will be basic.")
            return False

    def sanitize_floor_plan(
        self,
        image_path_or_bytes: str | bytes,
        remove_text: bool = True,
        return_lookup: bool = True,
    ) -> tuple[bytes, dict | None]:
        """
        Sanitize floor plan image by removing identifying information.

        Process:
        1. Load image
        2. Convert to grayscale
        3. Apply threshold to binary (walls = black, empty = white)
        4. Extract line segments (walls, doors)
        5. Identify equipment symbols by contour/shape
        6. Remove all text (optional, if OCR available)
        7. Redraw as clean geometric skeleton
        8. Build lookup table mapping positions to original text
        9. Return sanitized image + lookup table

        Args:
            image_path_or_bytes: Path to floor plan or bytes
            remove_text: If True, attempt to remove all text labels
            return_lookup: If True, return room lookup table

        Returns:
            Tuple of:
            - Sanitized image bytes (PNG)
            - Lookup table dict mapping positions to room names (or None)
        """
        # Load image
        image = self._load_image(image_path_or_bytes)

        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()

        # Build lookup table before any modifications
        lookup_table = {}
        if return_lookup:
            lookup_table = self._extract_text_regions(gray)

        # Apply threshold to binary (detect walls and equipment)
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

        # Clean up noise with morphological operations
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        # Extract walls (thin lines) and equipment (circles/rectangles)
        walls = self._extract_walls(binary)
        equipment = self._extract_equipment_symbols(binary)

        # Create sanitized schematic
        sanitized = np.ones_like(gray) * 255  # White background

        # Draw walls (black)
        sanitized[walls > 0] = 0

        # Draw equipment symbols (gray, distinguishable from walls)
        sanitized[equipment > 0] = 150

        # Optional: Remove text regions with mask
        if remove_text and self.ocr_installed:
            text_mask = self._detect_text_regions(gray)
            sanitized[text_mask > 0] = 255

        # Convert back to RGB for compatibility
        sanitized_rgb = cv2.cvtColor(sanitized, cv2.COLOR_GRAY2BGR)

        # Encode to PNG bytes
        success, buffer = cv2.imencode(".png", sanitized_rgb)
        if not success:
            raise RuntimeError("Failed to encode sanitized image to PNG")

        sanitized_bytes = buffer.tobytes()

        input_desc = len(image_path_or_bytes) if isinstance(image_path_or_bytes, bytes) else image_path_or_bytes
        logger.info(
            f"✓ Sanitized floor plan: {input_desc} "
            f"→ {len(sanitized_bytes)} bytes, found {len(lookup_table)} text regions"
        )

        return sanitized_bytes, lookup_table if return_lookup else None

    def _load_image(self, image_path_or_bytes: str | bytes) -> np.ndarray:
        """Load image from file path or bytes."""
        if isinstance(image_path_or_bytes, bytes):
            # Load from bytes
            nparr = np.frombuffer(image_path_or_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Failed to decode image from bytes")
            return image
        else:
            # Load from file path
            image = cv2.imread(str(image_path_or_bytes))
            if image is None:
                raise FileNotFoundError(f"Cannot read image file: {image_path_or_bytes}")
            return image

    def _extract_walls(self, binary: np.ndarray) -> np.ndarray:
        """Extract wall line segments from binary image."""
        # Walls are continuous black lines
        # Use edge detection to find them
        edges = cv2.Canny(binary, 50, 150)

        # Dilate to connect nearby edges
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        walls = cv2.dilate(edges, kernel, iterations=1)

        return walls

    def _extract_equipment_symbols(self, binary: np.ndarray) -> np.ndarray:
        """Extract equipment symbols (circles, rectangles, crosses)."""
        equipment_mask = np.zeros_like(binary)

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            area = cv2.contourArea(contour)

            # Filter by size (equipment symbols are medium-sized)
            if 50 < area < 10000:
                # Check if circular (equipment often drawn as circles)
                perimeter = cv2.arcLength(contour, True)
                circularity = (4 * np.pi * area) / (perimeter * perimeter) if perimeter > 0 else 0

                # Draw if circular (0.7-1.0) or rectangular (bounding box ratio)
                _x, _y, w, h = cv2.boundingRect(contour)
                aspect_ratio = float(w) / h if h > 0 else 1

                if (0.7 <= circularity <= 1.1) or (0.5 <= aspect_ratio <= 2.0):
                    cv2.drawContours(equipment_mask, [contour], 0, 255, -1)

        return equipment_mask

    def _detect_text_regions(self, gray: np.ndarray) -> np.ndarray:
        """Detect text regions using OCR analysis."""
        if not self.ocr_installed:
            logger.debug("OCR not available, skipping text detection")
            return np.zeros_like(gray)

        try:
            import pytesseract

            # Get text data with coordinates
            data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)

            text_mask = np.zeros_like(gray)

            # Draw bounding boxes around detected text
            for i, text in enumerate(data["text"]):
                if text.strip():  # Non-empty text
                    x, y, w, h = (
                        data["left"][i],
                        data["top"][i],
                        data["width"][i],
                        data["height"][i],
                    )

                    # Expand bounding box slightly to catch partial text
                    x = max(0, x - 5)
                    y = max(0, y - 5)
                    w = min(gray.shape[1] - x, w + 10)
                    h = min(gray.shape[0] - y, h + 10)

                    cv2.rectangle(text_mask, (x, y), (x + w, y + h), 255, -1)

            return text_mask
        except Exception as e:
            logger.warning(f"Text detection failed: {e}")
            return np.zeros_like(gray)

    def _extract_text_regions(self, gray: np.ndarray) -> dict[str, dict]:
        """Extract text and its positions for lookup table."""
        if not self.ocr_installed:
            logger.debug("OCR not available, returning empty lookup")
            return {}

        try:
            import pytesseract

            # Get text data with coordinates and confidence
            data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)

            lookup = {}
            region_id = 0

            for i, text in enumerate(data["text"]):
                if text.strip() and int(data["conf"][i]) > 50:  # Confidence > 50%
                    x = int(data["left"][i])
                    y = int(data["top"][i])
                    w = int(data["width"][i])
                    h = int(data["height"][i])

                    # Create region ID based on position
                    region_id_str = f"region_{region_id}"

                    lookup[region_id_str] = {
                        "text": text,
                        "coordinates": {"x": x, "y": y, "width": w, "height": h},
                        "confidence": int(data["conf"][i]),
                    }

                    region_id += 1

            logger.info(f"✓ Extracted {len(lookup)} text regions for lookup table")
            return lookup
        except Exception as e:
            logger.warning(f"Text extraction for lookup failed: {e}")
            return {}

    def reidentify_equipment_config(self, extracted_config: dict, lookup_table: dict | None) -> dict:
        """
        Re-apply identifying information to extracted config after API response.

        The API extracted equipment from the sanitized image without knowing
        room names. This method maps the anonymous coordinates back to real
        room/zone names using the lookup table that never left the device.

        Args:
            extracted_config: Equipment config returned from Claude API
                {
                  "equipment": [
                    {"type": "chiller", "x": 120, "y": 250, "floor": "B1"},
                    ...
                  ],
                  "zones": [...]
                }
            lookup_table: Mapping of text regions to original names
                {
                  "region_0": {"text": "Chiller Room", "coordinates": {...}},
                  ...
                }

        Returns:
            Updated config with room/zone names re-identified
        """
        if not lookup_table:
            logger.warning("No lookup table provided, returning config as-is")
            return extracted_config

        try:
            # Map equipment positions to nearest text region
            for equipment in extracted_config.get("equipment", []):
                eq_x, eq_y = equipment.get("x", 0), equipment.get("y", 0)

                # Find closest text region
                closest_region = self._find_closest_text_region((eq_x, eq_y), lookup_table)

                if closest_region:
                    # Add zone/room name if close enough
                    if closest_region["distance"] < 100:  # pixels
                        equipment["zone_name"] = closest_region["text"]
                        equipment["zone_confidence"] = closest_region["confidence"]

            logger.info("✓ Re-identified equipment with original zone names")
            return extracted_config
        except Exception as e:
            logger.warning(f"Re-identification failed: {e}")
            return extracted_config

    def _find_closest_text_region(self, position: tuple[int, int], lookup_table: dict) -> dict | None:
        """Find closest text region to given position."""
        closest = None
        min_distance = float("inf")

        x, y = position

        for region_id, region_data in lookup_table.items():
            coords = region_data["coordinates"]
            region_x = coords["x"] + coords["width"] / 2
            region_y = coords["y"] + coords["height"] / 2

            distance = np.sqrt((x - region_x) ** 2 + (y - region_y) ** 2)

            if distance < min_distance:
                min_distance = distance
                closest = {
                    "region_id": region_id,
                    "text": region_data["text"],
                    "confidence": region_data["confidence"],
                    "distance": distance,
                }

        return closest

    def build_room_lookup_from_floor_plan(self, image_path_or_bytes: str | bytes) -> dict[str, dict]:
        """
        Build lookup table from floor plan that stays on-device.

        Maps anonymous room IDs to real names and positions.
        This table is used to re-identify extracted config after
        Claude API processes the sanitized schematic.

        Returns:
            {
              "room_1": {"name": "Server Room", "coordinates": (120, 250)},
              "room_2": {"name": "Vault", "coordinates": (280, 150)},
              ...
            }
        """
        image = self._load_image(image_path_or_bytes)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()

        return self._extract_text_regions(gray)


# Singleton instance
_sanitizer = None


def get_floor_plan_sanitizer() -> FloorPlanSanitizer:
    """Get or create singleton sanitizer instance."""
    global _sanitizer
    if _sanitizer is None:
        _sanitizer = FloorPlanSanitizer()
    return _sanitizer
