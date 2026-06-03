"""KNX Discovery Service — gateway discovery, ETS import, group address scan.

SENTINEL workflow:
1. Discover KNXnet/IP gateways on the network (UDP broadcast on port 3671)
2. Upload ETS group address export XML → parse → device config
3. Scan group address range passively (GroupValueRead, non-intrusive)
4. Build SENTINEL Device objects from ETS data
"""

from __future__ import annotations

import asyncio
import logging
import socket
import xml.etree.ElementTree as ET
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gateway discovery
# ---------------------------------------------------------------------------

MULTICAST_ADDR = "224.0.23.12"
KNXNET_IP_PORT = 3671


async def discover_gateways(timeout_s: float = 5.0) -> list[dict[str, Any]]:
    """Send KNXnet/IP Search Request and return discovered gateways.

    Discovery is done via UDP multicast to 224.0.23.12:3671.
    Returns list of gateway descriptors with address, name, etc.
    """
    gateways = []

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout_s)

        # Build search request header (KNXnet/IP header + SEARCH_REQUEST)
        # Search Request: header + HPAI (control endpoint) + search endpoint
        header = bytes(
            [
                0x06,  # header length = 6
                0x10,  # protocol version 1.0
                0x02,
                0x01,  # search request (0x0201)
                0x00,
                0x00,  # total length (filled below)
            ]
        )

        # HPAI for discovery response destination
        hpai = bytes(
            [
                0x00,
                0x00,  # family = IP, port = 0 (auto)
                0x00,
                0x00,
                0x00,
                0x00,
            ]
        )  # IP = 0.0.0.0

        # Search endpoint
        search_ep = bytes(
            [
                0x00,
                0x00,  # family = IP
                0x0E,
                0x9C,  # port = 3676 (control port)
                0x00,
                0x00,
                0x00,
                0x00,
            ]
        )  # IP = 0.0.0.0

        packet = header + hpai + search_ep
        packet = packet[:6] + bytes([(len(packet) >> 8) & 0xFF, len(packet) & 0xFF]) + packet[8:]

        sock.sendto(packet, (MULTICAST_ADDR, KNXNET_IP_PORT))

        responses = []
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                responses.append((data, addr))
            except TimeoutError:
                break

        for data, addr in responses:
            if len(data) < 16:
                continue
            # Parse response — we only need the gateway address
            gateways.append(
                {
                    "host": addr[0],
                    "port": KNXNET_IP_PORT,
                    "name": f"KNX Gateway {addr[0]}",
                    "discovered_at": asyncio.get_event_loop().time(),
                }
            )

        sock.close()

    except Exception as e:
        logger.error("KNX gateway discovery failed: %s", e)

    return gateways


async def test_gateway_connectivity(host: str, port: int = 3671, timeout_s: float = 3.0) -> dict[str, Any]:
    """Test connectivity to a specific KNXnet/IP gateway.

    Returns: {status: "success"|"timeout"|"error", host, port, error?}
    """
    try:
        # Quick UDP ping to gateway
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout_s)

        # Send minimal search request
        header = bytes([0x06, 0x10, 0x02, 0x01, 0x00, 0x10])
        hpai = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        sock.sendto(header + hpai, (host, port))

        data, _ = sock.recvfrom(256)
        sock.close()

        if data and len(data) >= 6:
            return {"status": "success", "host": host, "port": port}

        return {"status": "error", "host": host, "port": port, "error": "Empty response"}

    except TimeoutError:
        return {"status": "timeout", "host": host, "port": port, "error": "Gateway not responding"}
    except Exception as e:
        return {"status": "error", "host": host, "port": port, "error": str(e)}


# ---------------------------------------------------------------------------
# ETS XML group address import
# ---------------------------------------------------------------------------

ETS_NAMESPACES = {
    "ets": "http://www.knx.org/Schema/ETS/GroupAddresses/v2",
    "ets5": "http://www.knx.org/Schema/ETS/GroupAddresses/v5",
}


def import_ets_group_addresses(xml_content: str) -> list[dict[str, Any]]:
    """Parse ETS group address export XML and return list of group address dicts.

    Supports ETS5 and ETS6 XML format.

    Returns list of:
        {
            "address": "1/1/1",          # group address string
            "name": "Zone 1 Temperature", # description
            "dpt": "9.001",             # DPT type
            "description": "",          # main line
        }
    """
    group_addresses = []

    try:
        root = ET.fromstring(xml_content)

        # Iterate all elements in tree (namespace-agnostic)
        for ga_elem in root.iter():
            # Handle both namespaced and non-namespaced tags
            tag_local = ga_elem.tag.split("}")[-1] if "}" in ga_elem.tag else ga_elem.tag
            if tag_local == "GroupAddress":
                # Address and Name may be attributes OR child elements — check both
                address = ga_elem.get("Address", "")
                name = ga_elem.get("Name", "")

                dpt = "9.001"  # default
                description = ""

                for child in ga_elem:
                    child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child_tag == "Address":
                        address = child.text or ""
                    elif child_tag == "Name":
                        name = child.text or ""
                    elif child_tag == "Description":
                        description = child.text or ""
                    elif child_tag == "DataType":
                        dpt = _normalize_dpt(child.text or "9.001")

                if address:
                    group_addresses.append(
                        {
                            "address": address,
                            "name": name,
                            "dpt": dpt,
                            "description": description,
                        }
                    )

        logger.info("ETS import: parsed %d group addresses", len(group_addresses))

    except ET.ParseError as e:
        logger.error("ETS XML parse error: %s", e)
        raise ValueError(f"Invalid ETS XML: {e}") from e

    return group_addresses


def _normalize_dpt(dpt_str: str) -> str:
    """Normalize DPT string to standard format (e.g., 'DPT-9.001' → '9.001')."""
    import re

    match = re.search(r"(\d+\.\d+)", dpt_str)
    if match:
        return match.group(1)
    return "9.001"


# ---------------------------------------------------------------------------
# Group address scanning
# ---------------------------------------------------------------------------


async def scan_group_addresses(
    gateway_host: str,
    start_address: str = "0/0/0",
    end_address: str = "15/7/255",
    timeout_s: float = 2.0,
) -> list[dict[str, Any]]:
    """Passively scan group address range by sending GroupValueRead telegrams.

    Addresses that respond indicate active devices on the bus.

    Args:
        gateway_host: KNXnet/IP gateway IP
        start_address: Start of range (e.g., "1/0/0")
        end_address: End of range (e.g., "1/7/255")

    Returns:
        List of responsive group addresses with their current values.
    """
    from app.services.knx.knx_client import get_knx_client

    client = get_knx_client(gateway_host)
    connected = await client.connect()
    if not connected:
        return []

    # Parse address range
    start_main, start_mid, start_sub = map(int, start_address.split("/"))
    end_main, end_mid, end_sub = map(int, end_address.split("/"))

    responsive = []

    try:
        for main in range(start_main, min(end_main + 1, 16)):
            for mid in range(start_mid, min(end_mid + 1, 8)):
                for sub in range(start_sub, min(end_sub + 1, 256)):
                    addr_str = f"{main}/{mid}/{sub}"

                    try:
                        value = await asyncio.wait_for(
                            client.read_group_address(addr_str, "9.001"),
                            timeout=timeout_s,
                        )
                        responsive.append(
                            {
                                "address": addr_str,
                                "value": value,
                                "main": main,
                                "mid": mid,
                                "sub": sub,
                            }
                        )
                    except Exception:
                        # Non-responsive address — expected for passive scan
                        pass

                    await asyncio.sleep(0.05)  # avoid flooding the bus

    except asyncio.CancelledError:
        pass

    logger.info("Group address scan: %d responsive out of range %s–%s", len(responsive), start_address, end_address)

    return responsive


# ---------------------------------------------------------------------------
# Build SENTINEL Device from ETS import
# ---------------------------------------------------------------------------


def build_device_from_ets(
    site_id: str,
    building_name: str,
    floor: str,
    ets_group_addresses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construct SENTINEL Device config from parsed ETS group address list.

    Groups addresses by main group to create logical devices
    (one device per main group, e.g., 1/0/0–1/7/255 = Lighting).

    Args:
        site_id: SENTINEL site ID (e.g., "site-002")
        building_name: Building name for device location
        floor: Floor designator (e.g., "FL1")
        ets_group_addresses: List from import_ets_group_addresses()

    Returns:
        Device config dict ready for DeviceManager.add_device()
    """

    # Group by main group number
    by_main: dict[int, list[dict]] = {}
    for ga in ets_group_addresses:
        addr = ga["address"]
        main = int(addr.split("/")[0])
        by_main.setdefault(main, []).append(ga)

    # Build one device per main group
    devices = []

    for main, addresses in sorted(by_main.items()):
        device_id = f"knx-m{main}-site-{site_id.replace('-', '')}"

        points = {}
        group_addresses = {}

        for ga in addresses:
            point_name = ga["name"] or ga["address"]
            point_name = point_name[:80]  # truncate long names

            dpt = ga["dpt"]
            writable = not _is_emergency_description(ga.get("description", ""))

            # Map DPT to PointType
            if dpt in {"1.001"}:
                point_type = "binary_input" if writable else "binary_output"
            elif dpt in {"5.001"}:
                point_type = "analog_output"
            else:
                point_type = "analog_input"

            # Build group address metadata per point
            group_addr_meta = {
                "read_address": ga["address"],
                "dpt": dpt,
                "description": ga.get("description", ""),
                "unit": _dpt_unit(dpt),
            }

            group_addresses[point_name] = group_addr_meta

            points[point_name] = {
                "point_type": point_type,
                "description": ga.get("description", ""),
                "dpt": dpt,
                "writable": writable,
                "unit": _dpt_unit(dpt),
            }

        device = {
            "id": device_id,
            "name": f"KNX Main Group {main}",
            "device_type": "lighting",
            "protocol": "knx",
            "site_id": site_id,
            "status": "online",
            "description": f"KNX lighting/controls from ETS main group {main}",
            "device_location": {
                "building": building_name,
                "floor": floor,
                "zone": f"M{main // 8 + 1}",
                "room": f"GA{main}",
                "description": f"KNX group {main}",
            },
            "equipment": {
                "manufacturer": "KNX",
                "model": "KNXnet/IP",
            },
            "metadata": {
                "gateway_host": "",  # filled in by operator
                "main_group": main,
            },
            "points": points,
        }

        # Embed group_addresses into metadata for the adapter
        device["metadata"]["group_addresses"] = group_addresses

        devices.append(device)

    return devices[0] if len(devices) == 1 else {"devices": devices}


def _is_emergency_description(desc: str) -> bool:
    desc = desc.lower()
    return any(p in desc for p in ("emergency", "fire", "alarm", "evacuation"))


def _dpt_unit(dpt: str) -> str:
    units = {
        "1.001": "",
        "5.001": "%",
        "5.010": "",
        "9.001": "°C",
        "9.007": "%RH",
        "9.020": "V",
        "14.019": "A",
        "14.056": "W",
        "14.068": "Wh",
    }
    return units.get(dpt, "")
