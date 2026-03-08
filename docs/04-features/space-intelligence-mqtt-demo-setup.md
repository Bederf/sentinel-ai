# Space Intelligence — 5-Room MQTT Demo Setup

> **Rev 1.0** | 2026-03-08 | Wemos D1 Mini + HLK-LD2410C + Mosquitto MQTT

## Overview

Clean setup for a 5-room SENTINEL occupancy demo using:

- **Wemos D1 Mini** (ESP8266)
- **HLK-LD2410C** mmWave radar
- **Arduino IDE 2**
- **MQTT** to Mosquitto broker
- **Digital OUT mode** on pin D4

> **Note:** The full 20-room deployment spec uses HTTP REST (`POST /api/space/occupancy-event`).
> This demo variant uses MQTT for lower latency and simpler device firmware.
> See [`space-intelligence-hardware-spec.md`](space-intelligence-hardware-spec.md) for the HTTP approach.

---

## 1. Wiring

Simple digital OUT setup — no UART needed.

| D1 Mini | LD2410C | Purpose |
|---------|---------|---------|
| 5V | VCC | Power |
| G | GND | Ground |
| D4 | OUT | Occupancy signal |

Leave TX and RX on the radar unconnected for this version.

---

## 2. Arduino IDE Setup

### Install

1. [Arduino IDE 2](https://www.arduino.cc/en/software)
2. In **File > Preferences**, add to Additional Boards Manager URLs:
   ```
   https://arduino.esp8266.com/stable/package_esp8266com_index.json
   ```
3. **Boards Manager** — search `esp8266`, install the ESP8266 core
4. **Library Manager** — install:
   - `PubSubClient` (standard Arduino MQTT client)
   - `ArduinoJson`

### Board Settings

In **Tools**:

| Setting | Value |
|---------|-------|
| Board | LOLIN(WEMOS) D1 R2 & mini |
| Upload Speed | 921600 or 115200 |
| CPU Frequency | 80 MHz |
| Flash Size | 4MB |
| Port | Your COM port |

For first pass, use a normal 4 MB layout. LittleFS not needed yet.

---

## 3. Mosquitto Broker Setup

If Docker is available on the SENTINEL server:

### Directory Structure

```
mosquitto/
  config/
    mosquitto.conf
  data/
  log/
```

### mosquitto.conf

```
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest stdout
```

### Docker Run

```bash
docker run -d \
  --name mosquitto \
  -p 1883:1883 \
  -v /path/to/mosquitto/config:/mosquitto/config \
  -v /path/to/mosquitto/data:/mosquitto/data \
  -v /path/to/mosquitto/log:/mosquitto/log \
  eclipse-mosquitto:2
```

---

## 4. MQTT Topic Structure

Use this convention — do not change mid-demo.

```
sentinel/rooms/{ROOM_CODE}/occupancy
sentinel/rooms/{ROOM_CODE}/status
sentinel/rooms/{ROOM_CODE}/rssi
```

Room codes for the 5-room demo:

- `MR01`, `MR02`, `MR03` (meeting rooms)
- `FR01`, `FR02` (focus rooms)

---

## 5. Room / IP Map

| Room | Client ID | Static IP |
|------|-----------|-----------|
| MR01 | sentinel_mr01 | 10.20.50.21 |
| MR02 | sentinel_mr02 | 10.20.50.22 |
| MR03 | sentinel_mr03 | 10.20.50.23 |
| FR01 | sentinel_fr01 | 10.20.50.31 |
| FR02 | sentinel_fr02 | 10.20.50.32 |

---

## 6. Firmware

One sketch per room. Change only `ROOM_CODE`, `MQTT_CLIENT_ID`, and static IP per device.

```cpp
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

#define RADAR_PIN D4

// ===== Room identity =====
const char* ROOM_CODE      = "MR01";
const char* MQTT_CLIENT_ID = "sentinel_mr01";

// ===== Wi-Fi =====
const char* WIFI_SSID = "FNB WIFI";
const char* WIFI_PASS = "fnbwifi123";

// Optional static IP - edit or disable if not needed
IPAddress local_IP(10, 20, 50, 21);
IPAddress gateway(10, 20, 50, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress dns1(8, 8, 8, 8);
IPAddress dns2(1, 1, 1, 1);

// ===== MQTT =====
const char* MQTT_HOST = "10.20.50.10";   // change to your Mosquitto server IP
const uint16_t MQTT_PORT = 1883;

// ===== Topics =====
String topicOccupancy;
String topicStatus;
String topicRssi;

// ===== State =====
WiFiClient espClient;
PubSubClient mqtt(espClient);

bool lastOccupied = false;
bool firstPublish = true;
unsigned long lastWifiCheck = 0;
unsigned long lastMqttReconnectAttempt = 0;
unsigned long lastRssiPublish = 0;

const unsigned long WIFI_CHECK_MS = 5000;
const unsigned long MQTT_RETRY_MS = 5000;
const unsigned long RSSI_PUBLISH_MS = 60000;

// ===== Fast reconnect cache =====
struct WifiCache {
  uint8_t marker;
  uint8_t channel;
  uint8_t bssid[6];
};

WifiCache rtcCache;

// ESP8266 RTC user memory helpers
bool loadRtcCache() {
  bool ok = ESP.rtcUserMemoryRead(0, (uint32_t*)&rtcCache, sizeof(rtcCache));
  return ok && rtcCache.marker == 0x42;
}

void saveRtcCache() {
  rtcCache.marker = 0x42;
  rtcCache.channel = WiFi.channel();
  memcpy(rtcCache.bssid, WiFi.BSSID(), 6);
  ESP.rtcUserMemoryWrite(0, (uint32_t*)&rtcCache, sizeof(rtcCache));
}

void publishJson(const String& topic, JsonDocument& doc, bool retained = true) {
  char buffer[256];
  size_t n = serializeJson(doc, buffer, sizeof(buffer));
  mqtt.publish(topic.c_str(), buffer, n, retained);
}

void publishStatus(const char* statusText) {
  JsonDocument doc;
  doc["room_code"] = ROOM_CODE;
  doc["sensor_id"] = MQTT_CLIENT_ID;
  doc["status"] = statusText;
  doc["ip"] = WiFi.localIP().toString();
  doc["rssi"] = WiFi.RSSI();
  publishJson(topicStatus, doc, true);
}

void publishOccupancy(bool occupied) {
  JsonDocument doc;
  doc["room_code"] = ROOM_CODE;
  doc["sensor_id"] = MQTT_CLIENT_ID;
  doc["occupied"] = occupied;
  doc["source"] = "ld2410c_out";
  doc["ts_ms"] = millis();
  publishJson(topicOccupancy, doc, true);
}

void publishRssi() {
  JsonDocument doc;
  doc["room_code"] = ROOM_CODE;
  doc["sensor_id"] = MQTT_CLIENT_ID;
  doc["rssi"] = WiFi.RSSI();
  publishJson(topicRssi, doc, false);
}

void connectWifi() {
  WiFi.mode(WIFI_STA);

  // Comment this out if you do not want static IP
  WiFi.config(local_IP, gateway, subnet, dns1, dns2);

  bool usedFastReconnect = false;

  if (loadRtcCache()) {
    WiFi.begin(WIFI_SSID, WIFI_PASS, rtcCache.channel, rtcCache.bssid, true);
    usedFastReconnect = true;
  } else {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
  }

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(250);
  }

  if (WiFi.status() == WL_CONNECTED) {
    saveRtcCache();
    Serial.print("WiFi connected. IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("Fast reconnect used: ");
    Serial.println(usedFastReconnect ? "yes" : "no");
  } else {
    Serial.println("WiFi connect failed");
  }
}

bool mqttConnect() {
  if (mqtt.connected()) return true;

  // Last Will
  JsonDocument lwtDoc;
  lwtDoc["room_code"] = ROOM_CODE;
  lwtDoc["sensor_id"] = MQTT_CLIENT_ID;
  lwtDoc["status"] = "offline";

  char lwtBuffer[128];
  size_t lwtLen = serializeJson(lwtDoc, lwtBuffer, sizeof(lwtBuffer));

  bool ok = mqtt.connect(
    MQTT_CLIENT_ID,
    nullptr, nullptr,
    topicStatus.c_str(),
    1,
    true,
    lwtBuffer
  );

  if (ok) {
    publishStatus("online");
    firstPublish = true;
  } else {
    Serial.print("MQTT connect failed, state=");
    Serial.println(mqtt.state());
  }

  return ok;
}

void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;

  unsigned long now = millis();
  if (now - lastWifiCheck < WIFI_CHECK_MS) return;
  lastWifiCheck = now;

  Serial.println("Reconnecting WiFi...");
  connectWifi();
}

void ensureMqtt() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (mqtt.connected()) return;

  unsigned long now = millis();
  if (now - lastMqttReconnectAttempt < MQTT_RETRY_MS) return;
  lastMqttReconnectAttempt = now;

  Serial.println("Reconnecting MQTT...");
  mqttConnect();
}

void setup() {
  Serial.begin(115200);
  delay(100);

  pinMode(RADAR_PIN, INPUT);

  topicOccupancy = "sentinel/rooms/" + String(ROOM_CODE) + "/occupancy";
  topicStatus    = "sentinel/rooms/" + String(ROOM_CODE) + "/status";
  topicRssi      = "sentinel/rooms/" + String(ROOM_CODE) + "/rssi";

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);

  connectWifi();
  mqttConnect();

  lastOccupied = digitalRead(RADAR_PIN) == HIGH;
  if (mqtt.connected()) {
    publishOccupancy(lastOccupied);
    publishRssi();
    firstPublish = false;
  }
}

void loop() {
  ensureWifi();
  ensureMqtt();

  if (mqtt.connected()) {
    mqtt.loop();
  }

  bool occupied = digitalRead(RADAR_PIN) == HIGH;

  if (firstPublish && mqtt.connected()) {
    publishOccupancy(occupied);
    publishRssi();
    firstPublish = false;
    lastOccupied = occupied;
  }

  if (occupied != lastOccupied && mqtt.connected()) {
    publishOccupancy(occupied);
    lastOccupied = occupied;
    Serial.print("Occupancy changed: ");
    Serial.println(occupied ? "true" : "false");
  }

  if (mqtt.connected() && millis() - lastRssiPublish > RSSI_PUBLISH_MS) {
    publishRssi();
    lastRssiPublish = millis();
  }

  delay(200);
}
```

---

## 7. Flash Process

1. Connect the D1 Mini by USB
2. In Arduino IDE choose the correct port
3. Paste the code
4. Change: `ROOM_CODE`, `MQTT_CLIENT_ID`, `MQTT_HOST`, static IP
5. Click **Upload**
6. Open **Serial Monitor** at 115200
7. Verify: WiFi connected, MQTT connected, occupancy state published

---

## 8. MQTT Payload Examples

### Occupancy

**Topic:** `sentinel/rooms/MR01/occupancy`

```json
{"room_code":"MR01","sensor_id":"sentinel_mr01","occupied":true,"source":"ld2410c_out","ts_ms":123456}
```

### Status

**Topic:** `sentinel/rooms/MR01/status`

```json
{"room_code":"MR01","sensor_id":"sentinel_mr01","status":"online","ip":"10.20.50.21","rssi":-61}
```

### RSSI

**Topic:** `sentinel/rooms/MR01/rssi`

```json
{"room_code":"MR01","sensor_id":"sentinel_mr01","rssi":-61}
```

---

## 9. HLKRadarTool Settings

For meeting rooms, start with:

| Setting | Value | Reason |
|---------|-------|--------|
| Unmanned Delay Time | 180 seconds | 3-min hold after last presence |
| Gate 1 moving | 0 | Suppress door bleed |
| Gate 2 moving | 0 | Suppress door bleed |
| Gate 1 stationary | 0 | Suppress door bleed |
| Gate 2 stationary | 0 | Suppress door bleed |

The LD2410C app tuning does the hard work. The node just relays clean occupancy.

---

## 10. First Test Checklist

For each room:

- [ ] Power node
- [ ] Confirm `status` topic shows `online`
- [ ] Walk into room
- [ ] Confirm `occupancy` becomes `true`
- [ ] Sit still
- [ ] Confirm room stays occupied
- [ ] Leave room
- [ ] Confirm `occupancy` becomes `false` after ~180 seconds

---

## 11. Design Decisions

| Decision | Rationale |
|----------|-----------|
| No UART parsing | Digital OUT is sufficient for presence detection |
| No firmware debounce | Radar handles this via HLKRadarTool gate config |
| No booking logic on device | Backend handles ghost detection and analytics |
| State-change only publishing | Reduces MQTT traffic; retained messages for late subscribers |
| Last Will `offline` status | Broker auto-publishes when device disconnects |
| Fast reconnect (RTC cache) | Sub-second WiFi reconnect after power cycle |
| Static IP | Deterministic addressing for troubleshooting |

---

## 12. WiFi Note

The target WiFi (`FNB WIFI`) is WPA2/WPA3-Personal. ESP8266 connects on the WPA2 side of mixed-mode networks. If IT has client isolation, MAC allowlisting, or LAN restrictions, MQTT traffic can fail even when WiFi association succeeds. That is network policy, not firmware.

---

---

## 13. NFC Tags for Device & Room Identification

Each sensor housing gets an **NTAG213** NFC sticker. The phone powers the passive chip through its magnetic field — no battery required, works for years.

### Use Cases

#### 1. Device commissioning

Stick one NFC tag inside the ceiling housing. Technician scans with phone, opens setup page:

```
https://sentinel.local/device/MR01
```

Shows: room code, sensor ID, IP address, firmware version, last seen time.

#### 2. Quick maintenance access

No dashboard login needed. Scan the tag:

```
Room: MR01
Device: sentinel_mr01
IP: 10.20.50.21
RSSI: -62
Last occupancy event: 09:01
```

#### 3. Reset / configuration trigger

NFC chip can hold a command URI:

```
sentinel://reconfigure/MR01
```

A mobile app could then connect to the device, update WiFi credentials, or trigger OTA firmware update.

#### 4. Physical room identification

Place an NFC tag near the meeting room door. Scanning opens the SENTINEL dashboard for that room:

```
https://sentinel.company/rooms/MR01
```

No typing — useful for facilities teams.

#### 5. Focus room session claim

Tap phone on the room NFC tag to **claim a focus room session**. This gives occupancy + user identity without cameras or badge systems. Pairs well with the 2-hour focus room limit.

### Tag Specification

| Spec | Value |
|------|-------|
| Chip | NTAG213 |
| Memory | 144 bytes |
| Compatibility | Android + iPhone |
| Cost | ~R2–R4 per tag (100 pcs) |
| Battery | None (passive, powered by phone NFC field) |
| Lifespan | Years |

### Demo NFC Content

| Room | NFC URL |
|------|---------|
| MR01 | `sentinel.local/room/MR01` |
| MR02 | `sentinel.local/room/MR02` |
| MR03 | `sentinel.local/room/MR03` |
| FR01 | `sentinel.local/room/FR01` |
| FR02 | `sentinel.local/room/FR02` |

---

## 14. Next Step

Build the **FastAPI MQTT listener** that subscribes to `sentinel/rooms/+/occupancy` and writes events into the `occupancy_events` table. See [`space-intelligence-data-model.md`](space-intelligence-data-model.md) for the schema.
