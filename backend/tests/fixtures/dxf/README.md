# DXF Test Fixtures

This directory contains DXF test files for validating the DXF parser service.

## Test Files

### sample_floor_plan.dxf (Not committed - generated dynamically)
Minimal test DXF file with:
- Layers: AR-WALL, AE-HVAC, EL-POWER
- Wall structure (100m x 80m)
- 5 HVAC equipment (chillers, AHUs)
- 5 Electrical equipment (generators, UPS, transformers)

**Use:** Basic unit tests, layer parsing validation

### site-002-real.dxf (Not committed - too large)
Real Sandton City floor plan from Siemens Desigo:
- 5 floors (B1, G, L1, L2, L3)
- 156 equipment total
- All HVAC, electrical, fire safety layers

**Use:** Integration testing, accuracy validation (requires manual upload)

## Creating Test DXF Files

### Minimal Test DXF

```python
import ezdxf
import io

doc = ezdxf.new('R2010')
msp = doc.modelspace()

# Add layers
doc.layers.new('AR-WALL')
doc.layers.new('AE-HVAC')
doc.layers.new('EL-POWER')

# Add walls
msp.add_line((0, 0), (100, 0), dxfattribs={'layer': 'AR-WALL'})
msp.add_line((100, 0), (100, 80), dxfattribs={'layer': 'AR-WALL'})
msp.add_line((100, 80), (0, 80), dxfattribs={'layer': 'AR-WALL'})
msp.add_line((0, 80), (0, 0), dxfattribs={'layer': 'AR-WALL'})

# Add equipment
msp.add_circle((50, 40, 0), radius=2, dxfattribs={'layer': 'AE-HVAC'})
msp.add_text('CH-1', dxfattribs={'layer': 'AE-HVAC', 'insert': (50, 40)})

doc.saveas('sample_floor_plan.dxf')
```

### Performance Test DXF

For performance testing with 100+ equipment, use the generator in `test_dxf_performance.py`:

```python
from tests.test_dxf_performance import TestDXFParserPerformance

dxf_bytes = TestDXFParserPerformance.generate_large_dxf(equipment_count=150)
```

## Supported DXF Versions

- AutoCAD R12 (1992)
- DXF R13-R14 (1994-1997)
- DXF 2000-2024

Older DXF versions (R10, R11) may not parse correctly.

## Layer Conventions

The DXF parser expects these layers:

| Layer Name | Content | Example |
|------------|---------|---------|
| AR-WALL    | Building structure, walls, doors | Lines, polylines |
| AE-HVAC    | HVAC equipment symbols | INSERT blocks, circles |
| EL-POWER   | Electrical equipment | INSERT blocks, symbols |
| FP-LIFE    | Fire/life safety equipment | Detectors, sprinklers |

## Equipment Naming

Equipment should be named according to these patterns:

```
{TYPE}-{FLOOR/LOCATION}-{ZONE/SEQUENCE}

Examples:
- CH-1          (Chiller 1)
- AHU-L1-01     (AHU on Level 1, sequence 01)
- FCU-L2-A      (FCU on Level 2, zone A)
- GEN-B1-001    (Generator in Basement 1, sequence 001)
- UPS-G-001     (UPS on Ground floor)
```

## Troubleshooting

### DXF won't parse
- Check DXF version is R12-2024
- Verify layer names match conventions exactly (case-sensitive)
- Try opening in AutoCAD or LibreOffice to validate structure

### Equipment not extracted
- Verify equipment is on correct layer (AR-WALL, AE-HVAC, EL-POWER, FP-LIFE)
- Check equipment names follow standard patterns (CH-1, AHU-L1, etc.)
- Ensure text labels are on same layer as equipment

### Coordinates incorrect
- Check DXF units (millimeters vs meters)
- Verify walls are on AR-WALL layer for bbox calculation
- Ensure AR-WALL defines complete floor perimeter

## Adding New Fixtures

To add a new test fixture:

1. Create DXF file in this directory
2. Add documentation here
3. Reference in test files (e.g., `test_dxf_parser.py`)
4. Add to `.gitignore` if >1MB

**Note:** Large DXF files (>5MB) should not be committed. Generate them dynamically in tests instead.
