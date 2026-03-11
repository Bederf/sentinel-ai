# SENTINEL · Space Intelligence

## Room Occupancy Sensor — Hardware Specification

**Rev 1.5 · ESP32 + HLK-LD2410C · Hidden Above-Ceiling Installation**
**Fairland 2 (FNB) · 20 Meeting Rooms · March 2026**

---

## Revision History

| Rev | Change | Detail |
|-----|--------|--------|
| 1.0 | Initial spec | HC-SR501 PIR sensor, hardcoded WiFi, generic ABS box, surface-ceiling mount |
| 1.1 | mmWave + WiFiManager + OTA | HLK-LD2410C replaces PIR. WiFiManager provisioning. ArduinoOTA. OKW EASYTEC 100 enclosure. |
| 1.2 | Hidden above-ceiling install | Sensor hidden above tile. Basic DIN clip box. Presence-only (no count). Pattern-based right-sizing. |
| 1.3 | Takachi PFF13-4-9W | Proper flanged enclosure specified. Dimensionally verified against ESP32 + LD2410C. Replaces generic DIN clip box. |
| 1.4 | Wemos D1 Mini + OUT pin mode | MCU changed to Wemos D1 Mini (ESP8266). OUT pin mode confirmed. D4 GPIO. Door bleed suppression profile. HLKRadarTool commissioning procedure. Sensor delay replaces firmware debounce. |
| 1.5 | ESP32 current design | MCU returns to ESP32. Presence events are published over MQTT into the SENTINEL space utilisation pipeline. |

---

## What This Hardware Enables

| Detection | Trigger | SENTINEL Action |
|-----------|---------|-----------------|
| Ghost booking | Room booked, occupied=false after 20-min grace | Concierge dispatched with two-tap verify link |
| Right-sizing — early vacate | Room occupied then empty >90 min before booking end | Notify concierge, offer room to waiting bookings |
| Right-sizing — brief occupation | Occupied <30 min in booking >60 min | Flag underuse, notify organiser |
| Right-sizing — sporadic use | Occupied <25% of booking duration | Flag speculative booking pattern |

The LD2410C detects **presence vs absence only** — not headcount. All logic uses presence/absence. No claims about number of people are made.

---

## Components

### NodeMCU-32S (ESP32)

| Spec | Value |
|------|-------|
| MCU | ESP32 |
| Supply voltage (VIN) | 5V via USB |
| Logic voltage | 3.3V |
| WiFi | 802.11 b/g/n 2.4GHz |
| Flash | 4MB typical |
| Dimensions | ~58 x 28mm |
| WiFi provisioning | Configured for building WiFi / FMB WiFi |
| OTA updates | ArduinoOTA |
| USB-Serial | CP2102 or CH340 depending on board variant |

### HLK-LD2410C mmWave Sensor

| Spec | Value |
|------|-------|
| Supply voltage | 5V–12V (connect to ESP32 5V/VIN pin as applicable) |
| Logic output | 3.3V — safe for ESP32 GPIO direct |
| Interface used | OUT pin (digital GPIO) |
| Detection range | 0.75m – 5m (configurable) |
| Detection angle | +/-60 degrees |
| Stationary detection | Yes — detects breathing, micro-movement |
| Frequency | 24GHz FMCW |
| Bluetooth config | HLKRadarTool app (Android/iOS) |
| Dimensions | 22 x 16mm |
| Supplier | PiShop (pishop.co.za) |
| Price | R94.90 inc VAT |

> **Why LD2410C and not LD2410B:** Only the C variant has Bluetooth. Bluetooth is required for field configuration via HLKRadarTool without reflashing firmware.

### Takachi PFF13-4-9W Enclosure

| Spec | Value |
|------|-------|
| Series | PFF — Flanged Network Plastic Box |
| Material | ABS UL94V-0 (flame-resistant) |
| Colour | Off-white |
| IP Rating | IP40 |
| Operating temp | -10C to +60C |
| External dimensions | 149.3 x 125 x 40mm (W x D x H) |
| Internal dimensions | 92.4 x 75.2 x 28.5mm (W x D x H) |
| PCB mounting | Built-in bosses |
| End panels | 2x detachable — cable entry |
| Fasteners | 4x self-tapping nickel-plated screws |
| Mounting | Flanged base screws to ceiling grid T-bar |
| Supplier | RS Components (Takachi Electric Industrial) |

---

## Wiring

Only 3 wires required. TX and RX pins on the LD2410C are left unconnected in OUT pin mode.

LD2410C OUT is a 3.3V logic signal — safe for ESP32 GPIO input. No level shifting required.

| LD2410C Pin | ESP32 Pin | Wire | Notes |
|-------------|-----------|------|-------|
| VCC | 5V / VIN | Red | Radar powered from board 5V rail |
| GND | GND | Black | Common ground |
| OUT | GPIO4 | Blue | Occupancy signal — HIGH=occupied, LOW=empty |
| TX | — | — | Not connected |
| RX | — | — | Not connected |

### OUT Pin Logic

| State | Voltage | Meaning |
|-------|---------|---------|
| HIGH | 3.3V | Person present (motion or stationary) |
| LOW | 0V | Room empty |

> **GPIO4 note:** GPIO4 is the standard OUT-pin occupancy input on the current ESP32 node design.

---

## Sensor Configuration — HLKRadarTool

The LD2410C is configured via Bluetooth using the HLKRadarTool app before installation. Settings are stored inside the radar module and persist through power loss.

**App:** Search "HLKRadarTool" on Google Play or Apple App Store.

### Door Bleed Suppression Profile

The primary tuning challenge in meeting rooms is **corridor bleed** — people walking past the door triggering occupancy. The solution is to disable the near gates (covering the door area) and concentrate sensitivity on the meeting table zone.

Ceiling view — sensor mounted 0.5–1m inside room from door:

```
  Corridor
     |
     | door
     v
+----------------------------------+
|  Gate 1-2 DISABLED               |
|  (door zone - no detection)      |
|                                  |
|  Gate 3-4   Gate 5               |
|                                  |
|       Meeting table              |
|                                  |
|  Gate 6-7   Gate 8               |
|                                  |
+----------------------------------+

Sensor on ceiling, 0.5-1m inside from door edge.
```

### Gate Reference

| Gate | Distance |
|------|----------|
| Gate 1 | 0 – 0.75m |
| Gate 2 | 0.75 – 1.5m |
| Gate 3 | 1.5 – 2.25m |
| Gate 4 | 2.25 – 3m |
| Gate 5 | 3 – 3.75m |
| Gate 6 | 3.75 – 4.5m |
| Gate 7 | 4.5 – 5.25m |
| Gate 8 | 5.25 – 6m |

### Moving Sensitivity (per gate)

| Gate | Sensitivity | Reason |
|------|-------------|--------|
| Gate 1 | 0 | Disabled — door zone |
| Gate 2 | 0 | Disabled — door zone |
| Gate 3 | 30 | Near-table transition |
| Gate 4 | 60 | Table edge |
| Gate 5 | 80 | Table centre |
| Gate 6 | 80 | Table centre |
| Gate 7 | 70 | Table far end |
| Gate 8 | 60 | Room far end |

### Stationary Sensitivity (per gate)

| Gate | Sensitivity | Reason |
|------|-------------|--------|
| Gate 1 | 0 | Disabled — door zone |
| Gate 2 | 0 | Disabled — door zone |
| Gate 3 | 50 | Near-table transition |
| Gate 4 | 80 | Table edge |
| Gate 5 | 100 | Table centre — must catch seated/still people |
| Gate 6 | 100 | Table centre |
| Gate 7 | 90 | Table far end |
| Gate 8 | 80 | Room far end |

### Delay Setting

**App parameter:** Unmanned Delay Time = **180 seconds**

```
Last detected presence
        |
        +------------ 180s hold -------------> OUT pin goes LOW (empty)
```

**Firmware implication:** The 180-second hold-off is handled entirely by the sensor. No debounce timer needed in firmware. `occupied = digitalRead(D4)` is sufficient.

---

## Firmware

### Core Logic

```c
const char* ROOM_CODE  = "FA2-1Q1-MR-01";          // <- change per unit
const char* SENSOR_ID  = "LD2410C-FA2-1Q1-MR-01";  // <- change per unit

#define RADAR_OUT_PIN D4

void loop() {
  bool occupied = digitalRead(RADAR_OUT_PIN);

  if (occupied != lastOccupied) {
    sendOccupancyEvent(occupied);
    lastOccupied = occupied;
  }
}
```

Only **ROOM_CODE** and **SENSOR_ID** change per unit. All other config (WiFi credentials, API endpoint, auth token) is identical across all 20 nodes.

### Toolchain

| Tool | Purpose |
|------|---------|
| Cursor IDE | Firmware editing |
| Arduino IDE 2 | Compile + initial flash (required for first flash per unit) |
| ArduinoOTA | All subsequent firmware updates over WiFi |
| Board package | esp32 by Espressif Systems |
| Board selection | NodeMCU-32S / ESP32 Dev Module |
| Libraries | WiFi, PubSubClient, ArduinoJson, ArduinoOTA |

**Board manager URL:** `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`

### SENTINEL API Endpoint

```
POST https://[PRODUCTION_DOMAIN]/api/space/occupancy-event

{
  "room_code": "FA2-1Q1-MR-01",
  "sensor_id": "LD2410C-FA2-1Q1-MR-01",
  "occupied": true,
  "source": "mmwave_ld2410c",
  "timestamp": "2026-03-09T09:05:00Z"
}

Auth: Bearer token (static site-level token)
```

---

## Installation

```
Concrete slab
--------------------------------------
  Ceiling grid T-bar
  [ D1 Mini | LD2410C (down) ] <- enclosure on T-bar
  0.5-1m inside room from door edge

         |  24GHz radar beam

======================================
  Acoustic mineral fibre ceiling tile
  (nothing visible below)

         |  signal passes through tile

         MEETING ROOM
         Detection cone: +/-60 deg
         Mounting height: 2.4-3m
```

**Sensor placement rule:** Mount 0.5–1m inside the room from the door edge. Not directly above the door. This reduces door bleed significantly and makes gate tuning easier.

### Through-Tile Notes

| Passes through | Does NOT pass through |
|----------------|----------------------|
| Acoustic mineral fibre tiles | Metal ceiling panels |
| Standard drywall | Foil-backed insulation |
| ABS enclosure walls | Thick reinforced concrete |

---

## Commissioning Checklist (per room)

Complete this procedure for every room after hardware installation.

- [ ] 1. Install node on ceiling grid T-bar, 0.5–1m inside room from door
- [ ] 2. Replace ceiling tile below
- [ ] 3. Power on via USB — WiFiManager creates SENTINEL_SETUP hotspot
- [ ] 4. Connect phone to SENTINEL_SETUP, open 192.168.4.1, enter building WiFi credentials
- [ ] 5. Open HLKRadarTool on phone, scan for sensor via Bluetooth
- [ ] 6. Set detection distance = 4.5m
- [ ] 7. Apply door bleed suppression gate profile (Gates 1–2 = 0, Gates 3–8 as per table)
- [ ] 8. Set Unmanned Delay Time = 180 seconds
- [ ] 9. Save configuration to device
- [ ] 10. Walk corridor outside room — confirm OUT pin does NOT trigger
- [ ] 11. Sit motionless at meeting table — confirm OUT pin stays HIGH
- [ ] 12. Verify SENTINEL receives occupancy events in dashboard
- [ ] 13. Record final gate settings in room log

> **Adjust gate profile per room.** Corridor width, door position, and room depth vary. Gates 1–2 suppression is standard; Gate 3 sensitivity may need tuning per site.

---

## Bill of Materials

| Qty | Component | Part | Supplier | Cost |
|-----|-----------|------|----------|------|
| 1 | ESP32 Dev Board | NodeMCU-32S | Local / online | R120 |
| 1 | mmWave Sensor | HLK-LD2410C | PiShop | R94.90 |
| 1 | Enclosure | Takachi PFF13-4-9W | RS Components | ~R120 |
| 1 | USB Power Supply | 5V 1A Micro-USB adapter | — | R40 |
| 1 | USB Cable | Micro-USB 1–2m | — | R20 |
| 3 | Dupont Jumper Wires | F-F 15cm (red, black, blue) | — | R10 |
| 1 | Cable ties | Generic | — | R5 |
| | **Total per device** | | | **~R370** |
| | **Total — 20 rooms** | | | **~R7,400** |

> Previous BOM used ESP32 DevKit at R85 and LD2410C at R117.30. D1 Mini + PiShop sourcing saves ~R65 per unit = ~R1,300 across 20 rooms.

---

## Deployment Plan — Fairland 2, 20 Rooms

| Step | Action |
|------|--------|
| 1 | Build prototype — FA2-1Q1-MR-01 |
| 2 | Flash firmware, provision WiFi via WiFiManager |
| 3 | Install above ceiling tile, 0.5–1m inside from door |
| 4 | Commission via HLKRadarTool — apply gate profile, set delay |
| 5 | Verify SENTINEL receives events for 2 days |
| 6 | Flash remaining 19 units — change ROOM_CODE + SENSOR_ID only |
| 7 | Deploy floor-wide — WiFiManager provisioning per unit |
| 8 | Future firmware updates via OTA — no physical access required |

---

**SENTINEL · Space Intelligence · Hardware Specification · Rev 1.4 · March 2026**
**Fairland 2 (FNB) · ESP32 + HLK-LD2410C · Above-Ceiling · Confidential**
