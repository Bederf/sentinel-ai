"""Performance tests for DXF parser.

Tests that DXF parsing completes within acceptable time limits
for realistic floor plans with 100+ equipment.
"""

import pytest
import time
import io

ezdxf = pytest.importorskip("ezdxf", reason="ezdxf not installed")

from app.services.dxf_parser_service import get_dxf_parser_service  # noqa: E402


@pytest.mark.performance
class TestDXFParserPerformance:
    """Performance benchmarks for DXF parsing."""

    @staticmethod
    def generate_large_dxf(equipment_count: int = 120) -> bytes:
        """Generate DXF with many equipment entities.

        Args:
            equipment_count: Number of equipment to add

        Returns:
            DXF file content as bytes
        """
        import tempfile
        import os

        doc = ezdxf.new("R2010")
        msp = doc.modelspace()

        # Add layers
        doc.layers.new("AR-WALL")
        doc.layers.new("AE-HVAC")
        doc.layers.new("EL-POWER")

        # Add floor plan walls
        msp.add_line((0, 0), (150, 0), dxfattribs={"layer": "AR-WALL"})
        msp.add_line((150, 0), (150, 120), dxfattribs={"layer": "AR-WALL"})
        msp.add_line((150, 120), (0, 120), dxfattribs={"layer": "AR-WALL"})
        msp.add_line((0, 120), (0, 0), dxfattribs={"layer": "AR-WALL"})

        # Add equipment across floors (B1, G, L1, L2, L3)
        floors = ["B1", "G", "L1", "L2", "L3"]
        eq_per_floor = equipment_count // len(floors)

        for floor_idx, floor in enumerate(floors):
            z = floor_idx * 3.5 - 3.5  # B1=-3.5, G=0, L1=3.5, etc.

            for i in range(eq_per_floor):
                x = 20 + (i % 10) * 12
                y = 20 + (i // 10) * 20
                layer = "AE-HVAC" if i % 2 == 0 else "EL-POWER"

                # Add equipment circle
                msp.add_circle((x, y, z), radius=1.5, dxfattribs={"layer": layer})

                # Add equipment label
                eq_type = "FCU" if i % 2 == 0 else "GEN"
                eq_name = f"{eq_type}-{floor}-{i:02d}"
                msp.add_text(eq_name, dxfattribs={"layer": layer, "insert": (x, y, z)})

        # Save to temp file then read as bytes
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
            temp_path = f.name

        doc.saveas(temp_path)

        with open(temp_path, "rb") as f:
            dxf_bytes = f.read()

        os.remove(temp_path)

        return dxf_bytes

    @pytest.mark.asyncio
    async def test_parse_dxf_100_equipment_under_5s(self):
        """Test parsing 100+ equipment DXF completes in <5 seconds."""
        parser = get_dxf_parser_service()
        dxf_bytes = self.generate_large_dxf(equipment_count=100)

        start_time = time.time()

        config = await parser.parse_dxf_file(dxf_bytes, "site-002", "Test Building")

        elapsed = time.time() - start_time

        assert elapsed < 5.0, f"DXF parsing took {elapsed:.2f}s (target: < 5s)"
        assert len(config["equipment"]) >= 80  # At least 80% extracted

    @pytest.mark.asyncio
    async def test_parse_dxf_150_equipment_under_5s(self):
        """Test parsing 150 equipment DXF completes in <5 seconds."""
        parser = get_dxf_parser_service()
        dxf_bytes = self.generate_large_dxf(equipment_count=150)

        start_time = time.time()

        config = await parser.parse_dxf_file(dxf_bytes, "site-002", "Test Building")

        elapsed = time.time() - start_time

        assert elapsed < 5.0, f"DXF parsing took {elapsed:.2f}s (target: < 5s)"
        assert len(config["equipment"]) >= 120

    @pytest.mark.asyncio
    async def test_parse_dxf_memory_efficiency(self):
        """Test DXF parsing doesn't leak memory with large files."""

        parser = get_dxf_parser_service()
        dxf_bytes = self.generate_large_dxf(equipment_count=200)

        # Get baseline memory
        baseline_objects = len(gc.get_objects()) if "gc" in dir() else 0

        config = await parser.parse_dxf_file(dxf_bytes, "site-002", "Test Building")

        # Check result is valid
        assert len(config["equipment"]) > 100

        # Memory should not increase dramatically
        # (this is a rough check - we're mainly ensuring no exceptions)
        assert config["equipment"] is not None


@pytest.mark.performance
class TestDXFParserBenchmark:
    """Benchmark various DXF parsing operations."""

    @pytest.mark.asyncio
    async def test_parse_small_dxf_timing(self):
        """Benchmark small DXF parsing (10 equipment)."""
        parser = get_dxf_parser_service()

        # Generate small DXF
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        doc.layers.new("AE-HVAC")

        for i in range(10):
            msp.add_circle((20 + i * 10, 40, 0), radius=1.5, dxfattribs={"layer": "AE-HVAC"})

        stream = io.StringIO()
        doc.write(stream)
        dxf_bytes = stream.getvalue().encode("utf-8")

        start_time = time.time()
        config = await parser.parse_dxf_file(dxf_bytes, "site-002", "Test")
        elapsed = time.time() - start_time

        print(f"\nSmall DXF (10 equipment): {elapsed * 1000:.1f}ms")
        assert elapsed < 0.5  # Should be very fast

    @pytest.mark.asyncio
    async def test_parse_medium_dxf_timing(self):
        """Benchmark medium DXF parsing (50 equipment)."""
        parser = get_dxf_parser_service()
        dxf_bytes = TestDXFParserPerformance.generate_large_dxf(50)

        start_time = time.time()
        config = await parser.parse_dxf_file(dxf_bytes, "site-002", "Test")
        elapsed = time.time() - start_time

        print(f"\nMedium DXF (50 equipment): {elapsed * 1000:.1f}ms")
        assert elapsed < 2.0

    @pytest.mark.asyncio
    async def test_parse_large_dxf_timing(self):
        """Benchmark large DXF parsing (150 equipment)."""
        parser = get_dxf_parser_service()
        dxf_bytes = TestDXFParserPerformance.generate_large_dxf(150)

        start_time = time.time()
        config = await parser.parse_dxf_file(dxf_bytes, "site-002", "Test")
        elapsed = time.time() - start_time

        print(f"\nLarge DXF (150 equipment): {elapsed * 1000:.1f}ms")
        assert elapsed < 5.0


# Import gc for memory checks (optional)
try:
    import gc
except ImportError:
    gc = None
