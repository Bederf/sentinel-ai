---
title: "SENTINEL Data Philosophy & Architecture Manifesto"
type: "strategy"
status: "approved"
version: "1.0.0"
created: "2026-02-28"
author: "SENTINEL Architecture Team"
tags: ["architecture", "philosophy", "data-agnostic", "deployment"]
domain: "general"
audience: "developers"
complexity: "foundational"
---

# SENTINEL Data Philosophy & Architecture Manifesto

## SENTINEL Identity

SENTINEL is a **live, production-grade AI-powered building intelligence platform**. It is **data-agnostic** — it receives data, processes data, and outputs data. It does not care where the data comes from or where it goes. The platform behaves identically whether connected to:

- A physical BMS (Siemens Desigo, Schneider, Honeywell, etc.)
- The Site 002 lifecycle simulator
- Kamstrup smart meters
- eiEnterprise energy feeds
- Any future protocol or data source

**There is no "demo mode." There is no "mock mode." There is no distinction between "real" and "simulated" data inside SENTINEL.** SENTINEL is always live, always production. A data source is a data source.

---

## The SBC Deployment Rule

**A clean SENTINEL install with no data source configured must produce zero telemetry, zero alerts, zero dashboard data. The platform starts idle and activates only when a data source is connected. The Site 002 simulator is a separate, removable component — not a default.**

This is the litmus test:

1. Deploy SENTINEL on a fresh SBC with no BMS connected.
2. Start the platform.
3. **Expected:** An empty, waiting intelligence engine. No data flows, no dashboards populating, no alerts firing. Just like PostgreSQL doesn't generate its own rows on install, SENTINEL doesn't generate its own telemetry.
4. Connect a data source (real BMS, simulator, meter feed).
5. **Expected:** SENTINEL activates — telemetry flows, AI processes, dashboards populate, alerts fire.

If step 3 produces any telemetry, the architecture is broken. The simulator is entangled with the core platform.

### What This Means for Code

- **The simulator must be fully decoupled** — not just renamed, but architecturally separable. You must be able to delete the entire `bms_simulator/` directory and SENTINEL still starts, runs, and waits for a real BMS connection.
- **The device registry must be empty by default** — or populated by discovery from the connected BMS. Bundling simulated device definitions means a clean install thinks it has devices that don't physically exist.
- **No startup flag should trigger data generation** — `DEMO_MODE` or any equivalent must not cause SENTINEL itself to produce telemetry. If a flag activates a simulator, that simulator is a separate process/component that feeds data into SENTINEL through the standard ingestion pipeline.

---

## Terminology Rules — Strictly Enforced

**NEVER use the following terms when referring to SENTINEL's operations, data processing, UI, dashboards, APIs, or outputs:**

- "mock" / "mocked"
- "demo" / "demo mode"
- "fake" / "false"
- "simulated data" (when referring to what SENTINEL processes)
- "dummy"
- "placeholder" (for data or values that SENTINEL processes)
- "hardcoded sample data"
- "test data" (unless literally in a unit test context)
- "for demonstration purposes"
- "in a real environment this would..."
- "when connected to a real BMS..."

**The ONLY acceptable context for "simulator" or "simulation" is when referring specifically to the Site 002 Lifecycle Simulator itself as a named component — because that IS its name. It is a data source that produces building telemetry. SENTINEL consumes its output as production data.**

**USE these terms instead:**

- "data source" / "connected data source"
- "telemetry feed"
- "ingested data"
- "live data" (all data SENTINEL processes is live)
- "Site 002" (when referring to that specific source)
- "BMS feed" / "protocol feed"
- "sensor readings" / "meter readings"

---

## Code & Architecture Rules

**1. No conditional logic that distinguishes "real" vs "demo" data paths.**
SENTINEL has one data pipeline. Data comes in, gets processed by the rules engine, AI layer, and alerting system, and produces outputs. Never write code that branches based on whether a source is "real" or not.

**2. No hardcoded fallback data presented as SENTINEL output.**
If a data source is unavailable, SENTINEL should report that the source is unavailable — not fall back to hardcoded values and present them as if they're live readings. Error states are valid states.

**3. API responses are always structured the same way regardless of source.**
Whether the data originated from a physical chiller in Sandton or the Site 002 simulator, the API response schema, processing logic, and output format must be identical.

**4. UI components never display "demo," "sample," or "mock" labels.**
Dashboards, cards, charts, and alerts display the data they receive. No banners, badges, tooltips, or watermarks suggesting the data is anything other than what SENTINEL is actively processing.

**5. Comments and documentation follow the same standard.**
Code comments should not say things like `// TODO: replace with real data` or `// mock response for demo`. If you're writing a service that connects to Site 002, the comment should read something like `// Ingests telemetry from Site 002 data source` — because that's what it does.

**6. The Site 002 Lifecycle Simulator is a first-class data source.**
It is not a stopgap. It is not temporary scaffolding. It is a purpose-built data source that produces realistic building lifecycle telemetry. Code that interfaces with it should be written with the same quality, error handling, and structure as code that interfaces with any physical BMS.

---

## Mental Model

Think of SENTINEL like a database engine. PostgreSQL doesn't care if the data you insert is from a weather station, a financial trading system, or a video game. It stores it, indexes it, queries it, and returns it. The data source is irrelevant to the engine's operation.

SENTINEL is the same. It is an intelligence engine. Data flows in through connectors. The AI layer processes it. Rules fire. Alerts trigger. Dashboards render. Reports generate. The origin of the data is metadata — it's a label on the source, not a modifier on SENTINEL's behavior.

---

## When Writing New Features

Before committing any code, ask yourself:

1. Would this code behave differently if I swapped Site 002 for a live Siemens Desigo feed? **If yes, refactor.**
2. Does any UI element suggest to the user that what they're seeing isn't "real"? **If yes, remove it.**
3. Do any comments, variable names, or function names use "mock," "demo," "fake," or "dummy"? **If yes, rename them.**
4. Does the API response include any field that flags data as simulated? **If yes, remove it unless it's a source metadata field identifying which data source provided the reading.**
5. If I delete `bms_simulator/` entirely, does SENTINEL still start and wait for a data source? **If no, the simulator is entangled.**

---

## Summary

SENTINEL is a production platform. It is always on. It processes whatever data it receives with full AI intelligence, full rules engine evaluation, and full reporting capability. The coding standard reflects this reality — every line of code, every API response, every UI component, and every comment should treat SENTINEL as what it is: a live building intelligence system.
