# SENTINEL Occupancy Node — Firmware Architecture

**Rev 1.0 · ESP32 + LD2410C + MQTT · March 2026**

Reference architecture for stable room detection without false triggers from corridors or adjacent rooms.

---

## 1. Hardware Placement Rules

Ceiling mount works best. Detection cone is wide — the radar sees through thin walls and glass, so limiting detection distance is critical.

| Parameter | Value |
|-----------|-------|
| Height | 2.4–3.0 m |
| Angle | Flat down or slight tilt |
| Avoid | Pointing at doors, corridors, metal ducting |

---

## 2. Wiring (LD2410C → ESP32)

| Sensor Pin | ESP32 Pin |
|------------|-----------|
| VCC | 5V |
| GND | GND |
| TX | GPIO16 |
| RX | GPIO17 |
| OUT | GPIO27 (or any input) |

UART: 256000 baud, 8N1.

---

## 3. Firmware Architecture — Three Loops

### 3a. Radar Loop

Reads serial frames. Extracts:

- Presence (boolean)
- Moving target distance (m)
- Stationary target distance (m)
- Motion energy (0–100)
- Static energy (0–100)

### 3b. Occupancy Logic

Converts radar data to room state. Prevents flicker with delay timer.

```
if moving_distance < room_radius → occupied = true
if stationary_distance < room_radius → occupied = true
if no detection for delay_time → occupied = false
```

| Parameter | Recommended |
|-----------|-------------|
| room_radius | 4 m |
| delay_time | 15 s |

### 3c. MQTT Loop

Publishes only on state change to reduce network traffic.

**Topics:**

```
sentinel/node/<node_id>/presence    → { "presence": true/false, "moving": true/false, "stationary": true/false, "distance": 2.4 }
sentinel/node/<node_id>/motion      → motion energy values
sentinel/node/<node_id>/distance    → distance readings
sentinel/node/<node_id>/health      → heartbeat (see section 5)
```

---

## 4. Detection Gate Tuning

Starting configuration that prevents corridor triggers:

**Moving gates:**

```
50, 50, 45, 40, 35, 30, 20, 15
```

**Static gates:**

```
0, 10, 40, 40, 35, 30, 20, 15
```

**Farthest detection gate:**

| Type | Gate |
|------|------|
| Moving | 6 |
| Static | 5 |

**Unoccupied delay:** 10–20 seconds.

**Key trick — ignore far detections near doors:**

```
if distance > 4.5m → ignore detection
```

This removes most hallway false triggers.

---

## 5. MQTT Health Monitoring

Every node publishes heartbeat every 30 seconds.

**Topic:** `sentinel/node/<node_id>/status`

**Payload:**

```json
{
  "wifi_rssi": -42,
  "uptime": 12034,
  "radar": "ok"
}
```

SENTINEL uses missed heartbeats to detect dead nodes.

---

## 6. Scaling Architecture

```
LD2410C → ESP32 → WiFi → MQTT broker → SENTINEL ingestion → Timeseries DB → AI occupancy model
```

| Nodes | Message rate |
|-------|-------------|
| 50 | ~5 msg/sec |
| 200 | ~20 msg/sec |
| 1000 | ~100 msg/sec |

MQTT handles this easily.

---

## 7. Future Upgrades

| Addition | Purpose |
|----------|---------|
| Light sensor | Lighting automation based on ambient light |
| Temperature sensor | Room comfort detection |
| Multi-radar fusion | Two radars per room eliminate blind spots |

---

## Related Docs

- [Hardware Spec (Rev 1.5)](space-intelligence-hardware-spec.md)
- [MQTT Demo Setup](space-intelligence-mqtt-demo-setup.md)
- [Ceiling Placement Map](space-intelligence-ceiling-placement-map.md)
- [Equipment List](space-intelligence-equipment-list.md)
- [Data Model](../02-architecture/space-intelligence-data-model.md)
