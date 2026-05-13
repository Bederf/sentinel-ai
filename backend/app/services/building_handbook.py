"""Meeting rooms extracted from BUILDING_HANDBOOK.md markdown tables.

Used as fallback when room_registry has no data for a site.
"""

import re
from typing import Any


def parse_handbook_rooms(markdown: str) -> tuple[list[dict[str, Any]], str]:
    """Parse meeting rooms from BUILDING_HANDBOOK.md markdown table.

    Extracts rooms from a markdown table that has columns:
    | Room | Capacity | Floor | AV | Notes |

    Returns:
        Tuple of (rooms list, source="handbook")
    """
    rooms = []

    # Match the meeting rooms section header
    in_meeting_rooms = False
    for line in markdown.splitlines():
        line = line.rstrip()
        # Detect meeting rooms section (with or without emoji prefix)
        if re.match(r"(?:[^\w]*)?Meeting Rooms", line, re.IGNORECASE):
            in_meeting_rooms = True
            continue
        # Stop if we hit another section (non-table line after table)
        if in_meeting_rooms and line.startswith("#") and "Meeting" not in line:
            break
        if in_meeting_rooms and line.startswith("**Booking"):
            break

        if in_meeting_rooms and line.startswith("|"):
            # Skip header separator line (|---|---|...)
            if re.match(r"\|[-:\s|]+\|", line):
                continue
            parts = [p.strip() for p in line.split("|")]
            # parts[0] is empty (leading |), parts[1:] = [Room, Capacity, Floor, AV, Notes, ...]
            if len(parts) >= 5:
                room_name = parts[1]
                capacity_str = parts[2]
                floor = parts[3]
                av_raw = parts[4]
                notes = parts[5] if len(parts) > 5 else ""

                # Skip header row itself
                if room_name.lower() in ("room", "name"):
                    continue

                # Parse capacity
                try:
                    capacity = int(capacity_str) if capacity_str else None
                except ValueError:
                    capacity = None

                # AV: ✅ or Yes/True
                av = bool(re.search(r"(yes|true|✅|av)", av_raw, re.IGNORECASE))

                rooms.append({
                    "name": room_name,
                    "capacity": capacity,
                    "floor": floor,
                    "av": av,
                    "notes": notes,
                })

    return rooms, "handbook"
