# SENTINEL Occupancy Node Firmware

**Hardware:** NodeMCU-32S (ESP32) + HLK-LD2410C 24GHz mmWave
**Version:** 2.0.0
**Transport:** MQTT (PubSubClient) -> Mosquitto on SENTINEL edge appliance
**Source:** `firmware/sentinel_occupancy_node/sentinel_occupancy_node.ino`

## Architecture

```
[LD2410C] --UART--> [ESP32] --MQTT--> [Mosquitto on Jetson]
                                             |
                                      [SENTINEL backend]
                                  subscribes sentinel/node/+/radar
                                          and sentinel/node/+/config
                                          and sentinel/nodes/+/presence (legacy)
```

## Commissioning Workflow

1. Flash identical firmware to all nodes (only `NODE_ID`, `ZONE_ID`, WiFi differ in config.h)
2. Install sensor in ceiling
3. Open HLKRadarTool on phone, connect via Bluetooth to the LD2410C
4. Configure gate limits, sensitivity, resolution, unmanned duration for that room
5. Reboot the node (power cycle or OTA restart)
6. ESP32 reads the LD2410C config over UART, publishes as retained MQTT message
7. Server subscribes to `sentinel/node/+/config` and receives the commissioning baseline

No reflashing needed after Bluetooth configuration. The firmware reads the truth from the radar.

## Version History

| Version | Date       | Key Changes |
|---------|------------|-------------|
| 2.0.0   | 2026-03-14 | Read radar config from LD2410C at boot via UART command protocol; flash-once firmware; periodic config re-read (10 min) detects Bluetooth re-commissioning |
| 1.4.0   | 2026-03-14 | Radar profile moved to config.h (required reflash per node) |
| 1.3.8   | 2026-03-14 | Retained config topic, resolution-aware gate calc, UART stale timeout, OTA fix, frame parser fix |
| 1.3.0   | 2026-03-14 | distance_m, moving_gate/static_gate, 30s heartbeat, dual-topic, dual-WiFi, MQTT Last Will |
| 1.2.0   | 2026-03    | Full UART frame parser (256000 baud); OUT pin fallback; non-blocking LED; ArduinoOTA |

## Pinout

| Signal                | Pin              |
|-----------------------|------------------|
| LD2410C TX -> ESP32 RX | GPIO 16         |
| LD2410C RX <- ESP32 TX | GPIO 17         |
| LD2410C OUT (presence) | GPIO 4          |
| Status LED             | GPIO 2 (active LOW) |

**Note:** Confirm GPIO4 is physically wired on your specific dev board.

## LED Status Codes

| Pattern           | Meaning                    |
|-------------------|----------------------------|
| Fast blink (200ms) | Connecting to WiFi        |
| Slow blink (1s)   | Connected, no presence     |
| Solid ON          | Presence detected          |
| Double blink      | MQTT reconnected           |

## MQTT Topics

| Topic                                  | Retain | Purpose |
|----------------------------------------|--------|---------|
| sentinel/node/<NODE_ID>/radar          | No     | Live presence telemetry |
| sentinel/node/<NODE_ID>/config         | Yes    | Commissioned radar profile (read from LD2410C) |
| sentinel/node/<NODE_ID>/status         | Yes    | 30s heartbeat + Last Will (radar: "offline") |
| sentinel/nodes/<NODE_ID>/presence      | No     | Legacy dual-publish (backward compat) |

## Libraries Required

Install via Arduino Library Manager:
- PubSubClient by Nick O'Leary (MQTT)
- ArduinoJson v6

Built-in ESP32 Arduino core (no install needed):
- WiFi.h, ArduinoOTA.h

## Config

Copy `config_example.h` to `config.h` and fill in your values.
`config.h` is gitignored -- never commit credentials.

```cpp
#define WIFI_SSID       "your-ssid"
#define WIFI_PASSWORD   "your-password"
#define WIFI_SSID_2     ""              // Optional fallback
#define WIFI_PASSWORD_2 ""
#define MQTT_BROKER     "192.168.1.100" // Jetson LAN IP
#define MQTT_PORT       1883
#define MQTT_USER       "sentinel"
#define MQTT_PASSWORD   "changeme"
#define NODE_ID         "NODE-L2-001"
#define ZONE_ID         "L2-NORTH"
#define PUBLISH_INTERVAL_MS  5000UL
#define OTA_PASSWORD    "sentinel-ota"
```

No radar profile in config.h — it's read from the LD2410C sensor over UART.

## Provisioning

Flash firmware via Arduino IDE, write config.h values per node.
Only `NODE_ID` and `ZONE_ID` change per unit (WiFi/MQTT shared across site).

OTA updates (once node is on WiFi):
  Arduino IDE -> Tools -> Port -> sentinel-node-XXXX.local
  Password: value of OTA_PASSWORD in config.h

## LD2410C Command Protocol

The firmware uses the LD2410C UART command protocol to read configuration at boot. This is separate from the data frame protocol used during normal operation.

| Protocol | Header | Trailer | Purpose |
|----------|--------|---------|---------|
| Data frames | F4 F3 F2 F1 | F8 F7 F6 F5 | Live detection data (continuous) |
| Command frames | FD FC FB FA | 04 03 02 01 | Configuration read/write (on demand) |

### Commands used

| Command | Code | Purpose |
|---------|------|---------|
| Enter config mode | 0xFF | Required before any config commands |
| Read parameters | 0x61 | Returns gate limits, sensitivity arrays, unmanned duration |
| Read firmware version | 0xA0 | Returns radar firmware version string |
| Read distance resolution | 0xAB | Returns 0x0000 (0.75m) or 0x0001 (0.20m) |
| Exit config mode | 0xFE | Resumes data frame output |

### Boot sequence

1. Wait 1 second for radar boot
2. Drain any pending data frames
3. Enter config mode (retry up to 3 times)
4. Read gate parameters (command 0x61)
5. Read firmware version (command 0xA0)
6. Read distance resolution (command 0xAB)
7. Exit config mode (data frames resume)
8. Publish config as retained MQTT message

### Periodic re-read

Every 10 minutes, the firmware re-reads the radar config. This detects if someone re-configured the radar via Bluetooth while it was running. If the config changed, a new retained message is published.

## Config Payload (Retained)

Published to `sentinel/node/<NODE_ID>/config` — values read directly from the LD2410C:

```json
{
  "node_id": "NODE-L2-001",
  "zone": "L2-NORTH",
  "radar_model": "HLK-LD2410C",
  "radar_fw_version": "2.44.25070917",
  "node_fw_version": "2.0.0",
  "distance_resolution_m": 0.75,
  "moving_farthest_gate": 4,
  "static_farthest_gate": 4,
  "unmanned_duration_s": 15,
  "baud_rate": 256000,
  "moving_sensitivity": [50,50,40,30,20,15,15,15,15],
  "static_sensitivity": [0,0,40,40,30,30,20,20,20]
}
```

**Key distinction:** `moving_farthest_gate` (config) = gate limit set during commissioning. `moving_gate` (telemetry) = current detected target position. Not the same.

## Radar Telemetry Payload

Published at `PUBLISH_INTERVAL_MS` to both `radar` and `presence` (legacy) topics:

```json
{
  "node_id": "NODE-L2-001",
  "zone": "L2-NORTH",
  "presence": true,
  "moving": true,
  "stationary": false,
  "moving_distance_cm": 180,
  "stationary_distance_cm": 0,
  "moving_energy": 82,
  "stationary_energy": 0,
  "distance_m": 1.80,
  "moving_gate": 2,
  "static_gate": 0,
  "rssi": -62,
  "uptime_s": 3742,
  "ts": 3742,
  "fw_version": "2.0.0"
}
```

`distance_m` -- float in metres from active target (moving takes priority).
`moving_gate` / `static_gate` -- detected target gate, resolution-aware.

## Heartbeat Payload

Published every 30s to sentinel/node/<NODE_ID>/status:

```json
{
  "node_id": "NODE-L2-001",
  "wifi_rssi": -62,
  "uptime": 3742,
  "radar": "ok",
  "radar_config": "ok",
  "fw_version": "2.0.0"
}
```

`radar`: `"ok"` (UART valid), `"no_data"` (UART stale >2s, OUT fallback), `"offline"` (Last Will).
`radar_config`: `"ok"` (config read successfully), `"pending"` (will retry in 10 min).

## UART Data Frame Format

```
Offset  Bytes  Description
0-3     4      Header: F4 F3 F2 F1
4-5     2      Payload length (LE), typically 0x0D = 13
6-18    13     Payload (see below)
19-22   4      Trailer: F8 F7 F6 F5
```

Payload (13 bytes):
```
[0]     0x02   Data frame type
[1]     0xAA   Head marker
[2]     state  0=none, 1=moving, 2=static, 3=both
[3-4]   LE     Moving distance (cm)
[5]     u8     Moving energy (0-100)
[6-7]   LE     Stationary distance (cm)
[8]     u8     Stationary energy (0-100)
[9-10]  LE     Detection distance (cm)
[11]    0x55   Tail marker
[12]    0x00   Check byte
```

Total frame: 23 bytes.

## UART Stale Timeout

If no valid UART frame for 2 seconds, falls back to `digitalRead(PIN_LD2410_OUT)` for binary presence. Recovers automatically when UART resumes. Heartbeat reports `radar: "no_data"` during fallback.
