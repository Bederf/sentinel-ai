#!/usr/bin/env python3
"""Generate realistic synthetic floor plans for site-002 demo building.

Creates floor plan images that match the demo building structure:
- 5 floors: B1 (basement), G (ground), L1-L3 (levels)
- Equipment placed according to demo config
- Text labels for sanitization testing
- Realistic walls, zones, and partitions

Output: PNG images for each floor in backend/app/data/demo_floor_plans/
"""

from pathlib import Path

from PIL import Image, ImageDraw

# Site-002 Demo Building Configuration
SITE_CONFIG = {
    "code": "site-002",
    "name": "Sandton City Tower - Demo",
    "floors": {
        "B1": {
            "level_name": "Basement Level 1",
            "height": 3.5,
            "width": 150,
            "depth": 120,
            "zones": {
                "Plant": {
                    "x": 10,
                    "y": 10,
                    "width": 130,
                    "height": 100,
                    "equipment": [
                        {"name": "CHILLER-B1-01", "type": "chiller", "x": 30, "y": 30},
                        {"name": "CHILLER-B1-02", "type": "chiller", "x": 70, "y": 30},
                        {"name": "AHU-G-01", "type": "ahu", "x": 30, "y": 70},
                        {"name": "GEN-B1-01", "type": "generator", "x": 100, "y": 30},
                        {"name": "UPS-B1-01", "type": "ups", "x": 100, "y": 70},
                    ],
                },
            },
        },
        "G": {
            "level_name": "Ground Floor",
            "height": 4.0,
            "width": 150,
            "depth": 120,
            "zones": {
                "Lobby": {"x": 10, "y": 10, "width": 40, "height": 100, "equipment": []},
                "Retail A": {
                    "x": 50,
                    "y": 10,
                    "width": 45,
                    "height": 50,
                    "equipment": [
                        {"name": "FCU-G-A", "type": "fcu", "x": 65, "y": 30},
                    ],
                },
                "Retail B": {
                    "x": 95,
                    "y": 10,
                    "width": 45,
                    "height": 50,
                    "equipment": [
                        {"name": "FCU-G-B", "type": "fcu", "x": 110, "y": 30},
                    ],
                },
            },
        },
        "L1": {
            "level_name": "Level 1 - Office",
            "height": 3.2,
            "width": 150,
            "depth": 120,
            "zones": {
                "Zone A": {
                    "x": 10,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L1-A", "type": "fcu", "x": 20, "y": 30},
                        {"name": "VAV-L1-01", "type": "vav", "x": 20, "y": 70},
                    ],
                },
                "Zone B": {
                    "x": 45,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L1-B", "type": "fcu", "x": 55, "y": 30},
                    ],
                },
                "Zone C": {
                    "x": 80,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L1-C", "type": "fcu", "x": 90, "y": 30},
                    ],
                },
                "Zone D": {
                    "x": 115,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L1-D", "type": "fcu", "x": 125, "y": 30},
                    ],
                },
            },
        },
        "L2": {
            "level_name": "Level 2 - Office",
            "height": 3.2,
            "width": 150,
            "depth": 120,
            "zones": {
                "Zone A": {
                    "x": 10,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L2-A", "type": "fcu", "x": 20, "y": 30},
                    ],
                },
                "Zone B": {
                    "x": 45,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L2-B", "type": "fcu", "x": 55, "y": 30},
                    ],
                },
                "Zone C": {
                    "x": 80,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L2-C", "type": "fcu", "x": 90, "y": 30},
                    ],
                },
                "Zone D": {
                    "x": 115,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L2-D", "type": "fcu", "x": 125, "y": 30},
                    ],
                },
            },
        },
        "L3": {
            "level_name": "Level 3 - Office",
            "height": 3.2,
            "width": 150,
            "depth": 120,
            "zones": {
                "Zone A": {
                    "x": 10,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L3-A", "type": "fcu", "x": 20, "y": 30},
                    ],
                },
                "Zone B": {
                    "x": 45,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L3-B", "type": "fcu", "x": 55, "y": 30},
                    ],
                },
                "Zone C": {
                    "x": 80,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L3-C", "type": "fcu", "x": 90, "y": 30},
                    ],
                },
                "Zone D": {
                    "x": 115,
                    "y": 10,
                    "width": 35,
                    "height": 100,
                    "equipment": [
                        {"name": "FCU-L3-D", "type": "fcu", "x": 125, "y": 30},
                    ],
                },
            },
        },
    },
}

# Equipment symbol styles (for drawing)
EQUIPMENT_SYMBOLS = {
    "chiller": {"color": (100, 150, 255), "shape": "circle", "size": 15},
    "ahu": {"color": (100, 200, 255), "shape": "circle", "size": 14},
    "fcu": {"color": (150, 200, 255), "shape": "circle", "size": 10},
    "vav": {"color": (120, 180, 255), "shape": "circle", "size": 12},
    "pump": {"color": (100, 150, 200), "shape": "circle", "size": 11},
    "generator": {"color": (255, 150, 100), "shape": "rect", "size": 16},
    "ups": {"color": (255, 180, 100), "shape": "rect", "size": 14},
}


def scale_coords(x, y, scale=2):
    """Scale coordinates for display (10m = scale pixels)."""
    return int(x * scale), int(y * scale)


def draw_equipment(draw, name, eq_type, x, y, scale=2):
    """Draw equipment symbol and label."""
    sx, sy = scale_coords(x, y, scale)

    symbol = EQUIPMENT_SYMBOLS.get(eq_type, EQUIPMENT_SYMBOLS["fcu"])
    color = symbol["color"]
    size = symbol["size"]

    # Draw equipment circle/rect
    if symbol["shape"] == "circle":
        draw.ellipse(
            [sx - size, sy - size, sx + size, sy + size],
            fill=color,
            outline="black",
            width=1,
        )
    else:  # rect
        draw.rectangle(
            [sx - size, sy - size, sx + size, sy + size],
            fill=color,
            outline="black",
            width=1,
        )

    # Draw label (small text)
    draw.text((sx + size + 5, sy - 10), name.split("-")[0], fill="black", font=None)


def draw_zone(draw, zone_name, x, y, width, height, scale=2):
    """Draw zone boundary and label."""
    x1, y1 = scale_coords(x, y, scale)
    x2, y2 = scale_coords(x + width, y + height, scale)

    # Draw zone boundary (light gray dashed-style)
    draw.rectangle([x1, y1, x2, y2], outline=(200, 200, 200), width=2)

    # Draw zone label
    draw.text((x1 + 5, y1 + 5), zone_name, fill=(100, 100, 100), font=None)


def generate_floor_plan(floor_code, floor_data, output_path):
    """Generate floor plan image for a single floor."""
    # Image size: 150m × 120m at 2px/m = 300×240 px, plus margins
    margin = 40
    scale = 2
    width = int(floor_data["width"] * scale) + 2 * margin
    height = int(floor_data["depth"] * scale) + 2 * margin

    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)

    # Draw border (building outline)
    border_x1 = margin
    border_y1 = margin
    border_x2 = width - margin
    border_y2 = height - margin
    draw.rectangle([border_x1, border_y1, border_x2, border_y2], outline="black", width=3)

    # Draw zones and equipment
    for zone_name, zone_data in floor_data["zones"].items():
        # Draw zone boundary
        draw_zone(
            draw,
            zone_name,
            zone_data["x"] + margin / scale,
            zone_data["y"] + margin / scale,
            zone_data["width"],
            zone_data["height"],
            scale,
        )

        # Draw equipment in zone
        for equipment in zone_data["equipment"]:
            eq_x = equipment["x"] + margin / scale
            eq_y = equipment["y"] + margin / scale
            draw_equipment(draw, equipment["name"], equipment["type"], eq_x, eq_y, scale)

    # Draw title
    title = f"{floor_code}: {floor_data['level_name']}"
    draw.text((margin, margin - 30), title, fill="black", font=None)

    # Draw scale info
    draw.text((margin, height - margin + 10), "Scale: 2px = 1m", fill=(100, 100, 100), font=None)

    return img


def generate_all_floor_plans():
    """Generate all floor plans for site-002."""
    output_dir = Path("backend/app/data/demo_floor_plans")
    output_dir.mkdir(parents=True, exist_ok=True)

    floor_images = {}

    for floor_code, floor_data in SITE_CONFIG["floors"].items():
        print(f"Generating floor plan: {floor_code}")

        img = generate_floor_plan(floor_code, floor_data, output_dir)
        output_path = output_dir / f"site-002-{floor_code}.png"

        img.save(output_path)
        print(f"  ✓ Saved to {output_path}")

        floor_images[floor_code] = img

    # Generate combined multi-page view
    print("\nGenerating combined 5-floor view...")
    combined_width = 300 * 2 + 60  # 2 columns + margins
    combined_height = 300 * 3 + 80  # 3 rows + margins
    combined = Image.new("RGB", (combined_width, combined_height), color="white")

    positions = [
        (20, 20, "B1"),
        (320, 20, "G"),
        (20, 300, "L1"),
        (320, 300, "L2"),
        (170, 580, "L3"),  # Center bottom
    ]

    for x, y, floor_code in positions:
        if floor_code in floor_images:
            floor_img = floor_images[floor_code].resize((280, 220))
            combined.paste(floor_img, (x, y))

    combined_path = output_dir / "site-002-all-floors.png"
    combined.save(combined_path)
    print(f"  ✓ Saved combined view to {combined_path}")

    print("\n" + "=" * 60)
    print(f"✓ Generated {len(floor_images)} floor plans for site-002")
    print(f"✓ Output directory: {output_dir}")
    print("=" * 60)

    return output_dir


if __name__ == "__main__":
    generate_all_floor_plans()
