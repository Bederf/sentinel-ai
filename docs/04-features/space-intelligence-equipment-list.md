# SENTINEL · Space Intelligence

## Room Occupancy Sensor — Equipment List

**Per Device · Rev 1.4 · Wemos D1 Mini + HLK-LD2410C · Above-Ceiling Install**
**Fairland 2 (FNB) · 20 Meeting Rooms · March 2026**

All components required to assemble and install one SENTINEL room occupancy sensor node. One node per meeting room, mounted above the acoustic ceiling tile on the ceiling grid bar. The Takachi PFF13-4-9W is the specified enclosure — flame-resistant ABS, PCB mounting bosses, sized to house the D1 Mini and LD2410C with clearance.

---

## Bill of Materials

| Qty | Component | Specification | Typical Part | Supplier | Unit Cost |
|-----|-----------|---------------|-------------|----------|-----------|
| 1 | ESP8266 Dev Board | Wemos D1 Mini, ESP8266, WiFi 2.4GHz, 4MB flash, 5V Micro-USB, 3.3V logic, CH340 USB-Serial | Wemos D1 Mini | Local / online | R80 |
| 1 | mmWave Sensor | HLK-LD2410C, 24GHz FMCW, OUT pin (digital GPIO), 5V–12V supply, 3.3V logic output, BT config via HLKRadarTool | HLK-LD2410C | PiShop (pishop.co.za) | R94.90 |
| 1 | Enclosure | Takachi PFF13-4-9W — flanged ABS UL94V-0, off-white, 149.3x125x40mm ext, 92.4x28.5x75.2mm int, IP40, PCB bosses | Takachi PFF13-4-9W | RS Components | ~R120 |
| 1 | USB Power Supply | 5V 1A Micro-USB wall adapter — routed to ceiling void power point | Any USB 5V 1A | — | R40 |
| 1 | USB Cable | Micro-USB, 1–2m, routed along ceiling grid bar to power point | Micro-USB 1–2m | — | R20 |
| 3 | Dupont Jumper Wires | Female-to-female, 15cm — 3 wires: VCC (5V), GND, OUT (D4/GPIO2) | Dupont F-F pack | — | R10 |
| 1 | Cable ties | Secure USB cable along ceiling grid bar | Generic | — | R5 |
| | **Total per device** | | | | **~R370** |
| | **Total — 20 rooms** | | | | **~R7,400** |

> Previous BOM used ESP32 DevKit V1 at R85 and LD2410C at R117.30 with 4 jumper wires (UART mode). D1 Mini + PiShop sourcing + OUT pin mode (3 wires) saves ~R65 per unit = ~R1,300 across 20 rooms.

---

## Enclosure — Takachi PFF13-4-9W

| Dimension | External | Internal |
|-----------|----------|----------|
| Width | 149.3mm | 92.4mm |
| Height | 40mm | 28.5mm |
| Depth | 85.3mm | 75.2mm |

| Property | Value |
|----------|-------|
| Material | ABS UL94V-0 |
| Colour | Off-white |
| IP Rating | IP40 |
| PCB bosses | Built-in — accommodates both boards |
| Mounting | Flanged base — screws to ceiling grid T-bar |
| End panels | 2x detachable — cable entry |

### Internal Fit Check

| Component | Size | Internal space | Result |
|-----------|------|---------------|--------|
| Wemos D1 Mini | 34 x 25mm | 92.4mm wide | Pass — much smaller than ESP32 |
| HLK-LD2410C | 22 x 16mm | ~50mm remaining | Pass |
| Combined width | ~56mm total | 92.4mm available | Pass — 36mm clearance |
| Height — USB connector | ~10mm | 28.5mm available | Pass — 18mm clearance |
| Cable entry | — | Detachable end panel | Pass |

> D1 Mini is significantly smaller than the ESP32 DevKit V1 (34x25mm vs 52x28mm), giving much more internal clearance.

---

## Wiring

Only 3 wires required. OUT pin mode — no UART connection needed.

| LD2410C Pin | D1 Mini Pin | Wire | Notes |
|-------------|-------------|------|-------|
| VCC | 5V | Red | Radar powered from USB 5V rail |
| GND | G | Black | Common ground |
| OUT | D4 (GPIO2) | Blue | HIGH=occupied, LOW=empty. 3.3V logic — safe for ESP8266 |

> **TX and RX on the LD2410C are not connected.** OUT pin provides all the information needed (presence/absence). UART is only needed for advanced telemetry which is not required for this application.

---

## Installation Notes

1. **Mounting:** Screw the PFF13-4-9W flanged base to the ceiling grid T-bar above the target tile. Two screws through the flange holes. Enclosure sits on the grid pointing downward.

2. **Sensor placement:** Mount 0.5–1m inside the room from the door edge. Not directly above the door. This reduces corridor bleed and simplifies gate tuning.

3. **LD2410C orientation:** Face the sensor toward the ceiling tile (downward). Radar cone is +/-60 degrees — one unit covers a standard meeting room from 2.4m mounting height.

4. **Cable routing:** Route the USB cable through the detachable end panel, along the grid bar to the nearest ceiling void power point. Secure with cable ties every 300-400mm.

5. **Tile replacement:** Replace the ceiling tile below. Device is fully hidden. Nothing visible in the meeting room.

6. **WiFi provisioning:** Power on — D1 Mini creates SENTINEL_SETUP hotspot. Connect phone, open 192.168.4.1, enter building WiFi credentials. Saved permanently.

7. **Sensor commissioning:** Use HLKRadarTool app (Android/iOS) over Bluetooth to configure LD2410C per room:
   - Set detection distance = 4.5m
   - Apply door bleed suppression profile (Gates 1–2 disabled, Gates 3–8 tuned)
   - Set Unmanned Delay Time = 180 seconds
   - No tile removal or reflashing required

8. **OTA updates:** Firmware updates pushed over WiFi via ArduinoOTA. Hostname set to room code (e.g. FA2-1Q1-MR-01) for identification.

9. **Visual indicator:** D4 is connected to the D1 Mini onboard LED. During commissioning, the LED mirrors occupancy state — free visual feedback without extra code.

---

**SENTINEL · Space Intelligence · Equipment List · Rev 1.4 · March 2026**
**Fairland 2 (FNB) · Wemos D1 Mini + HLK-LD2410C · Above-Ceiling Install · Confidential**
