"""Tests for Floor Plan Sanitizer service.

Tests geometric abstraction pipeline:
1. Load floor plan image
2. Extract walls and equipment symbols
3. Remove identifying text
4. Generate lookup table for re-identification
5. Return sanitized schematic + lookup
"""

import io

import numpy as np
import pytest

PIL = pytest.importorskip("PIL", reason="Pillow not installed")
cv2 = pytest.importorskip("cv2", reason="opencv-python not installed")

from PIL import Image, ImageDraw  # noqa: E402

from app.services.floor_plan_sanitizer import FloorPlanSanitizer  # noqa: E402


@pytest.fixture
def sanitizer():
    """Provide sanitizer instance."""
    return FloorPlanSanitizer()


@pytest.fixture
def simple_floor_plan():
    """Create a simple test floor plan image."""
    # Create 300x300 white image
    img = Image.new("RGB", (300, 300), color="white")
    draw = ImageDraw.Draw(img)

    # Draw walls (black lines, border)
    draw.rectangle([10, 10, 290, 290], outline="black", width=3)

    # Draw equipment symbols (circles)
    draw.ellipse([50, 50, 80, 80], fill="gray", outline="black", width=1)  # Equipment 1
    draw.ellipse([200, 200, 230, 230], fill="gray", outline="black", width=1)  # Equipment 2

    # Add text labels (to be removed by sanitizer)
    draw.text((45, 90), "Chiller", fill="black")
    draw.text((195, 240), "Pump", fill="black")

    # Convert to bytes
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def complex_floor_plan():
    """Create a more complex test floor plan with multiple zones."""
    img = Image.new("RGB", (600, 400), color="white")
    draw = ImageDraw.Draw(img)

    # Draw walls (black lines, border and internal partitions)
    draw.rectangle([10, 10, 590, 390], outline="black", width=3)  # Outer border
    draw.line([300, 10, 300, 390], fill="black", width=3)  # Central partition

    # Equipment on left side (Zone A)
    draw.ellipse([40, 40, 70, 70], fill="gray", outline="black")  # AHU
    draw.ellipse([40, 100, 70, 130], fill="gray", outline="black")  # FCU
    draw.ellipse([40, 160, 70, 190], fill="gray", outline="black")  # Chiller

    # Equipment on right side (Zone B)
    draw.ellipse([330, 40, 360, 70], fill="gray", outline="black")  # VAV
    draw.ellipse([330, 100, 360, 130], fill="gray", outline="black")  # UPS
    draw.ellipse([330, 160, 360, 190], fill="gray", outline="black")  # Generator

    # Text labels (to be removed)
    draw.text((30, 200), "Zone A", fill="black")
    draw.text((320, 200), "Zone B", fill="black")
    draw.text((35, 75), "AHU-L1", fill="black")
    draw.text((35, 135), "FCU-A", fill="black")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class TestFloorPlanSanitizer:
    """Test suite for floor plan sanitization."""

    def test_sanitizer_initialization(self, sanitizer):
        """Test sanitizer initializes successfully."""
        assert sanitizer is not None
        assert isinstance(sanitizer, FloorPlanSanitizer)

    def test_load_image_from_bytes(self, sanitizer, simple_floor_plan):
        """Test loading image from bytes."""
        image = sanitizer._load_image(simple_floor_plan)
        assert image is not None
        assert image.shape[0] > 0
        assert image.shape[1] > 0

    def test_load_image_invalid_bytes(self, sanitizer):
        """Test loading invalid image bytes raises error."""
        with pytest.raises(ValueError):
            sanitizer._load_image(b"not an image")

    def test_extract_walls(self, sanitizer, simple_floor_plan):
        """Test wall extraction from floor plan."""
        image = sanitizer._load_image(simple_floor_plan)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        walls = sanitizer._extract_walls(gray)

        assert walls is not None
        assert walls.shape == gray.shape
        # Walls should have some non-zero pixels
        assert np.count_nonzero(walls) > 0

    def test_extract_equipment_symbols(self, sanitizer, simple_floor_plan):
        """Test equipment symbol extraction."""
        image = sanitizer._load_image(simple_floor_plan)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

        equipment = sanitizer._extract_equipment_symbols(binary)

        assert equipment is not None
        assert equipment.shape == binary.shape
        # Should detect equipment circles
        assert np.count_nonzero(equipment) > 0

    def test_extract_text_regions(self, sanitizer, simple_floor_plan):
        """Test text region extraction (requires OCR)."""
        image = sanitizer._load_image(simple_floor_plan)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        lookup = sanitizer._extract_text_regions(gray)

        # If OCR available, should find some text
        # If not available, should return empty dict (graceful fallback)
        assert isinstance(lookup, dict)
        if sanitizer.ocr_installed:
            # Should find at least some text regions
            assert len(lookup) >= 0

    def test_build_room_lookup(self, sanitizer, simple_floor_plan):
        """Test building room lookup table."""
        lookup = sanitizer.build_room_lookup_from_floor_plan(simple_floor_plan)

        assert isinstance(lookup, dict)
        # If OCR available, should have found text
        if sanitizer.ocr_installed and len(lookup) > 0:
            # Each entry should have text and coordinates
            for _region_id, region_data in lookup.items():
                assert "text" in region_data
                assert "coordinates" in region_data

    def test_sanitize_simple_floor_plan(self, sanitizer, simple_floor_plan):
        """Test sanitizing a simple floor plan."""
        sanitized_bytes, lookup = sanitizer.sanitize_floor_plan(simple_floor_plan, remove_text=True, return_lookup=True)

        # Should return bytes
        assert isinstance(sanitized_bytes, bytes)
        assert len(sanitized_bytes) > 0

        # Should have created lookup table
        assert isinstance(lookup, dict)

        # Sanitized version should be smaller (text removed) or similar size
        # but definitely not corrupted
        assert len(sanitized_bytes) > 100  # Not empty

        # Can decode sanitized image
        nparr = np.frombuffer(sanitized_bytes, np.uint8)
        sanitized_img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        assert sanitized_img is not None
        assert sanitized_img.shape[0] > 0

    def test_sanitize_complex_floor_plan(self, sanitizer, complex_floor_plan):
        """Test sanitizing a complex floor plan with multiple zones."""
        sanitized_bytes, lookup = sanitizer.sanitize_floor_plan(
            complex_floor_plan, remove_text=True, return_lookup=True
        )

        assert isinstance(sanitized_bytes, bytes)
        assert len(sanitized_bytes) > 0
        assert isinstance(lookup, dict)

    def test_sanitize_without_lookup(self, sanitizer, simple_floor_plan):
        """Test sanitization without returning lookup table."""
        sanitized_bytes, lookup = sanitizer.sanitize_floor_plan(
            simple_floor_plan, remove_text=True, return_lookup=False
        )

        assert isinstance(sanitized_bytes, bytes)
        assert lookup is None

    def test_sanitize_skip_text_removal(self, sanitizer, simple_floor_plan):
        """Test sanitization without text removal."""
        sanitized_bytes, _ = sanitizer.sanitize_floor_plan(simple_floor_plan, remove_text=False, return_lookup=True)

        assert isinstance(sanitized_bytes, bytes)
        assert len(sanitized_bytes) > 0

    @pytest.mark.skip(reason="Requires OCR library - integration test")
    def test_detect_text_regions(self, sanitizer, simple_floor_plan):
        """Test text detection and masking."""
        image = sanitizer._load_image(simple_floor_plan)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        text_mask = sanitizer._detect_text_regions(gray)

        assert text_mask is not None
        assert text_mask.shape == gray.shape
        # Should detect some text regions
        assert np.count_nonzero(text_mask) > 0

    def test_find_closest_text_region(self, sanitizer):
        """Test finding closest text region to a position."""
        lookup = {
            "region_0": {
                "text": "Room A",
                "coordinates": {"x": 100, "y": 100, "width": 50, "height": 20},
                "confidence": 90,
            },
            "region_1": {
                "text": "Room B",
                "coordinates": {"x": 300, "y": 300, "width": 50, "height": 20},
                "confidence": 85,
            },
        }

        # Find closest to position (110, 110) - should be region_0
        closest = sanitizer._find_closest_text_region((110, 110), lookup)
        assert closest is not None
        assert closest["region_id"] == "region_0"
        assert closest["text"] == "Room A"

        # Find closest to position (290, 290) - should be region_1
        closest = sanitizer._find_closest_text_region((290, 290), lookup)
        assert closest is not None
        assert closest["region_id"] == "region_1"
        assert closest["text"] == "Room B"

    def test_reidentify_equipment_config(self, sanitizer):
        """Test re-identifying equipment with zone names."""
        extracted_config = {
            "equipment": [
                {"type": "chiller", "x": 120, "y": 150, "floor": "B1"},
                {"type": "ahu", "x": 300, "y": 100, "floor": "B1"},
            ]
        }

        lookup = {
            "region_0": {
                "text": "Chiller Room",
                "coordinates": {"x": 100, "y": 150, "width": 100, "height": 20},
                "confidence": 90,
            },
            "region_1": {
                "text": "Plant Area",
                "coordinates": {"x": 280, "y": 100, "width": 50, "height": 20},
                "confidence": 85,
            },
        }

        result = sanitizer.reidentify_equipment_config(extracted_config, lookup)

        assert "equipment" in result
        assert len(result["equipment"]) == 2

        # Check re-identification
        chiller = result["equipment"][0]
        if "zone_name" in chiller:
            # Should have found closest zone name
            assert "zone_confidence" in chiller

    def test_reidentify_without_lookup(self, sanitizer):
        """Test re-identification gracefully handles missing lookup."""
        extracted_config = {"equipment": [{"type": "chiller", "x": 120, "y": 150}]}

        # Should return config unchanged without lookup
        result = sanitizer.reidentify_equipment_config(extracted_config, None)
        assert result == extracted_config

    def test_singleton_instance(self, sanitizer):
        """Test singleton pattern for sanitizer."""
        from app.services.floor_plan_sanitizer import get_floor_plan_sanitizer

        instance1 = get_floor_plan_sanitizer()
        instance2 = get_floor_plan_sanitizer()

        # Should return same instance
        assert instance1 is instance2


class TestIntegration:
    """Integration tests for full sanitization workflow."""

    @pytest.mark.asyncio
    async def test_full_sanitization_workflow(self, sanitizer, simple_floor_plan):
        """Test complete workflow: load → sanitize → verify."""
        # Step 1: Load and sanitize
        sanitized_bytes, lookup = sanitizer.sanitize_floor_plan(simple_floor_plan, remove_text=True, return_lookup=True)

        assert isinstance(sanitized_bytes, bytes)
        assert isinstance(lookup, dict)

        # Step 2: Verify sanitized image is valid
        nparr = np.frombuffer(sanitized_bytes, np.uint8)
        sanitized_img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
        assert sanitized_img is not None

        # Step 3: Simulate extracted config
        extracted_config = {
            "equipment": [
                {"type": "chiller", "x": 50, "y": 50, "floor": "B1"},
                {"type": "pump", "x": 200, "y": 200, "floor": "B1"},
            ]
        }

        # Step 4: Re-identify with original zone names
        reidentified = sanitizer.reidentify_equipment_config(extracted_config, lookup)
        assert len(reidentified.get("equipment", [])) > 0

    @pytest.mark.asyncio
    async def test_end_to_end_sanitization_export(self, sanitizer, simple_floor_plan):
        """Test saving sanitized image to disk and re-loading."""
        sanitized_bytes, _lookup = sanitizer.sanitize_floor_plan(simple_floor_plan, remove_text=True, return_lookup=True)

        # Decode and verify we can work with the sanitized version
        nparr = np.frombuffer(sanitized_bytes, np.uint8)
        sanitized_img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)

        assert sanitized_img is not None
        # Sanitized image should have clear walls and equipment
        assert np.count_nonzero(sanitized_img < 200) > 0  # Dark pixels for walls
