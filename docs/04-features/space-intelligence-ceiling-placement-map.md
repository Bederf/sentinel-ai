---
title: "SENTINEL · Space Intelligence"
type: "spec"
status: "draft"
version: "1.0.0"
created: "2026-03-31"
updated: "2026-03-31"
tags: ["sentinel", "documentation"]
related: []
domain: "bms"
audience: "all"
complexity: "intermediate"
estimated_read_time: 10
---

# SENTINEL · Space Intelligence

## Ceiling Placement Map — mmWave LD2410C Occupancy Sensor

**Rev 1.0 · Technician Field Guide · March 2026**
**Fairland 2 (FNB) · 20 Meeting Rooms**

> **Audience:** Installation technicians. Print this document or load on phone for on-site reference.

---

## The One Rule

**Mount the sensor 0.8–1.5 m inside the room from the door, centred over the table axis.** The exact distance depends on room size. Never mount directly above or near the door.

---

## Room Layout 1: 6-Person Meeting Room

**Typical room size:** ~3 m x 3.5 m

```
  Corridor
     |
     | door
     v

+---------------------+
|                     |
|        O            |   O = SENTINEL radar node
|                     |
|      Meeting        |
|       Table         |
|                     |
|                     |
+---------------------+
```

| Parameter | Value |
|-----------|-------|
| Sensor offset from door | 0.8–1.0 m |
| Left-right position | Centred across table width |
| Ceiling height | 2.4–2.8 m ideal |
| Gate 1–2 | Suppressed (covers door zone) |
| Gate 3–5 | Active (covers table) |
| Gate 6–8 | Reduced or off (hits far wall) |

**Why this position:** Keeps Gate 1–2 outside the door opening. Corridor traffic does not trigger occupancy.

---

## Room Layout 2: 10-Person Meeting Room

**Typical room size:** ~4 m x 5 m

```
  Corridor
     |
     v

+---------------------------+
|                           |
|        O                  |   O = SENTINEL radar node
|                           |
|       Conference          |
|          Table            |
|                           |
|                           |
+---------------------------+
```

| Parameter | Value |
|-----------|-------|
| Sensor offset from door | 1.0–1.2 m |
| Left-right position | Centred across table width |
| Ceiling height | 2.4–2.8 m ideal |

**Gate coverage map:**

| Gate | Distance | Covers |
|------|----------|--------|
| Gate 1–2 | 0–1.5 m | Door area — **suppressed** |
| Gate 3–4 | 1.5–3.0 m | Table near side |
| Gate 5–6 | 3.0–4.5 m | Table centre |
| Gate 7–8 | 4.5–6.0 m | Table far side |

---

## Room Layout 3: 20-Person Boardroom

**Typical room size:** ~6 m x 8 m

```
  Corridor
     |
     v

+-------------------------------------+
|                                     |
|            O                        |   O = SENTINEL radar node
|                                     |
|        Large Boardroom Table        |
|                                     |
|                                     |
|                                     |
+-------------------------------------+
```

| Parameter | Value |
|-----------|-------|
| Sensor offset from door | 1.5 m |
| Left-right position | Centre of table axis |
| Ceiling height | 2.4–3.0 m |
| Gate 1–2 | Suppressed (door zone) |
| Gate 3–8 | All active — full table coverage needed |

> For very large boardrooms (>8 m deep), optionally deploy two nodes. Most standard boardrooms work with one.

---

## Radar Coverage Cone — Side View

```
        Ceiling (2.4-2.8m)
        =========[LD2410C]=========
                   |
              ___/ | \___
           __/    |60   \__         +/-60 deg detection cone
         /       deg       \
        /         |         \
       /          |          \
      /           |           \
-----+-----|------|------|-----+-----  Floor level
     |     |             |     |
     |<--->|<----------->|<--->|
     blind  detection zone  blind
     zone   (0.75-5m)      zone

     At 2.5m ceiling:
     Floor coverage radius = ~4.3m
     Floor coverage diameter = ~8.6m
```

**Key dimensions at typical ceiling heights:**

| Ceiling Height | Floor Coverage Radius | Floor Coverage Diameter |
|----------------|----------------------|------------------------|
| 2.4 m | ~4.2 m | ~8.4 m |
| 2.6 m | ~4.5 m | ~9.0 m |
| 2.8 m | ~4.8 m | ~9.7 m |
| 3.0 m | ~5.2 m | ~10.4 m |

> The LD2410C has a minimum detection distance of 0.75 m. There is a small blind cone directly below the sensor — this is fine because no one sits directly under the ceiling-mounted sensor.

---

## Radar Coverage Cone — Top View

```
                Door
                 |
                 v

         +-------+-------+
        /   Gate 1-2     \        <-- SUPPRESSED (door bleed zone)
       /    (0-1.5m)      \
      +--------------------+
     /     Gate 3-4         \
    /      (1.5-3m)          \    <-- Near table
   +--------------------------+
   |       Gate 5-6           |
   |       (3-4.5m)           |   <-- Table centre (max sensitivity)
   +--------------------------+
    \      Gate 7-8          /
     \     (4.5-6m)         /     <-- Far table
      +--------------------+

   Detection angle: +/-60 deg horizontal
   Full cone width at 4m: ~4.6m
```

---

## Mounting Orientation

```
  Ceiling Tile
  ==================
     Radar antenna
          |
     [ LD2410C ]      <-- antenna faces DOWN toward room

     [ D1 Mini ]      <-- USB port toward end panel

  ==================
     Enclosure base (flanged, screwed to T-bar)
```

**Rules:**
- Radar antenna faces the room (downward through tile)
- No metal directly below the antenna
- Keep 5–10 mm clearance between boards and enclosure lid
- USB cable exits through detachable end panel

---

## Corridor Suppression Strategy

Door bleed is handled by **two layers**:

1. **Physical placement** — Sensor mounted 0.8–1.5 m inside room, not above the door
2. **Gate configuration** — Gate 1 and Gate 2 sensitivity set to 0

Together these eliminate >95% of false triggers from corridor traffic.

```
  Corridor traffic -->  | door |  Gate 1-2 (OFF)  |  Gate 3+ (ON)  |
                                   ^                  ^
                                   |                  |
                              No detection      Active detection
                              (suppressed)      (table coverage)
```

---

## Installation Checklist

Complete for every room. Check each box on site.

- [ ] 1. Install enclosure above ceiling tile on T-bar, **0.8–1.5 m inside room from door**
- [ ] 2. Confirm radar antenna faces downward
- [ ] 3. Replace ceiling tile — device fully hidden
- [ ] 4. Power on via USB cable
- [ ] 5. Provision WiFi via WiFiManager (SENTINEL_SETUP hotspot → 192.168.4.1)
- [ ] 6. Open **HLKRadarTool** app on phone
- [ ] 7. Connect to sensor via Bluetooth
- [ ] 8. Set detection range = **4.5 m**
- [ ] 9. Apply gate sensitivity profile:
  - Gate 1 = **0**, Gate 2 = **0** (door suppression)
  - Gate 3–8 = per room layout table above
- [ ] 10. Set Unmanned Delay Time = **180 seconds**
- [ ] 11. Save settings to sensor
- [ ] 12. **Walk test:** Walk corridor outside room — confirm sensor does NOT trigger
- [ ] 13. **Sit test:** Sit motionless at meeting table for 2 minutes — confirm sensor stays HIGH
- [ ] 14. Verify SENTINEL dashboard shows occupancy events
- [ ] 15. Record final gate settings in room commissioning log

> **Adjust Gate 3 per room.** If corridor bleed persists, reduce Gate 3 sensitivity. If near-table occupants are missed, increase Gate 3. Gates 1–2 are always 0.

---

## Deployment Summary — Fairland 2

| Item | Value |
|------|-------|
| Rooms | 20 |
| Sensor | HLK-LD2410C (24GHz FMCW) |
| MCU | Wemos D1 Mini (ESP8266) |
| Detection mode | OUT pin (digital GPIO) |
| Delay | 180 seconds |
| Gate suppression | Gate 1–2 = 0 |
| Mount height | 2.2–2.8 m |
| Mount offset from door | 0.8–1.5 m (varies by room size) |
| Estimated hardware | ~R7,400 for entire floor |

---

**SENTINEL · Space Intelligence · Ceiling Placement Map · Rev 1.0 · March 2026**
**Fairland 2 (FNB) · Technician Field Guide · Confidential**
