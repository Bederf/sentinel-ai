# SENTINEL Data Privacy & Security Architecture

**For IT Security Teams, CISOs, and Stakeholders**

---

## Executive Summary

SENTINEL is designed from the ground up to keep building data on-premise. The AI runs locally, data stays local, and cloud integration is optional and anonymised. This document explains exactly what data goes where, so IT security teams can make informed deployment decisions.

**Key Point:** SENTINEL processes building telemetry (temperatures, pressures, equipment status) — NOT personal information. This is operational technology data, not information technology data.

---

## The Core Truth: What Data Does SENTINEL Handle?

### What SENTINEL Processes

SENTINEL handles **building telemetry data** — machine-generated operational readings from building management systems:

- AHU supply temperature: 22.3°C
- Chiller run status: ON
- Energy meter reading: 145.7 kWh
- Fire zone 12: Normal
- Valve position: 65% open
- Filter pressure: 280 Pa
- Vibration readings: 1.8 mm/s
- Motor current: 145 A

### What SENTINEL Does NOT Process

- ❌ Personal information (names, IDs, contact details)
- ❌ Customer financial data
- ❌ Employee records
- ❌ Access control identity data (names, card numbers)
- ❌ CCTV footage
- ❌ Anything that falls under POPIA "personal information"

### Classification

| Data Type | POPIA Classification | SENTINEL Processing |
|-----------|-------------------|-------------------|
| Raw BMS point values | Operational data | Stored on-premise, never external |
| Equipment inventories | Operational data | Stored on-premise, never external |
| Alarm/event logs | Operational data | Stored on-premise, never external |
| Energy consumption | Operational data | Stored on-premise, never external |
| FM team chat messages | Personal info (names) | Stored locally, never external |
| Maintenance notes | May contain personal info | Stored locally, never external |

**Bottom Line:** A chiller temperature reading has no POPIA classification. It's operational technology data, not personal information.

---

## Deployment Options

### Option A: Fully Local (Default / Recommended)

**100% On-Premise — No Cloud Dependency**

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  CLIENT'S NETWORK / ON-PREMISE                              │
│  ─────────────────────────────                              │
│                                                             │
│  [Niagara BMS]                                               │
│       │                                                      │
│       │ BACnet/IP (building telemetry)                      │
│       ▼                                                      │
│  ┌──────────────────────────┐                                │
│  │   SENTINEL SERVER        │                                │
│  │                          │                                │
│  │   PostgreSQL ◄── data    │                                │
│  │   Ollama + Llama 3.2 ◄── AI brain                      │
│  │   Moltbot ◄── chat engine                                 │
│  │                          │                                │
│  │   EVERYTHING RUNS HERE   │                                │
│  │   Nothing leaves.        │                                │
│  └──────────┬───────────────┘                                │
│             │                                                │
│  ┌────────────┴──────────────┐                                │
│  │  FM Team Web UI           │                                │
│  │  (Internal network only)  │                                │
│  └───────────────────────────┘                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Data Flow:**
1. BMS telemetry → SENTINEL database (on-premise)
2. FM asks question via web UI (on-premise)
3. SENTINEL queries local database for building data
4. SENTINEL sends data + question to LOCAL Llama model
5. Llama generates answer LOCALLY on the GPU
6. Answer displayed in web UI
7. **Building data NEVER leaves the server**

**What Goes Over the Internet:** Nothing. Zero. Nada.

**What Never Leaves the Server:**
- Raw BMS point data
- Historical trend databases
- Equipment inventories
- Alarm logs
- Energy consumption records
- Full building model

---

### Option B: Hybrid (Local + Cloud API for Complex Queries)

**For clients wanting more powerful AI (Claude, GPT-4) for complex analysis, report generation, or advanced diagnostics.**

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  CLIENT'S NETWORK                                           │
│                                                             │
│  [Niagara BMS]                                               │
│       │                                                      │
│       │ BACnet/IP                                           │
│       ▼                                                      │
│  ┌──────────────────────────┐                                │
│  │   SENTINEL SERVER        │                                │
│  │                          │                                │
│  │   PostgreSQL ◄── data    │                                │
│  │   Ollama + Llama ◄── handles 90% of queries          │
│  │                          │                                │
│  │   For complex queries:   │──── API call ────┐        │
│  │   PREPARES ANONYMISED    │                  │        │
│  │   SUMMARY (not raw data)│                  │        │
│  └──────────────────────────┘                  │        │
│                                     │            │
│                                     ▼            │
│                     ┌─────────────────────────┐           │
│                     │  Claude API             │           │
│                     │  (Anthropic)            │           │
│                     └─────────────────────────┘           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**How Hybrid Works:**

1. FM asks: "Give me a monthly energy analysis report"
2. SENTINEL queries LOCAL database for all energy data
3. SENTINEL LOCALLY aggregates: totals, peaks, trends
4. SENTINEL creates an **ANONYMISED SUMMARY**:
   ```
   "Building X consumed 45,000 kWh this month.
    Peak demand was 210 kW on Tuesday 14:00.
    Baseline is 38,000 kWh. Variance +18%.
    3 AHUs running outside schedule detected."
   ```
5. This SUMMARY (not raw data) goes to Claude API
6. Claude generates a professional analysis report
7. Report comes back to SENTINEL
8. SENTINEL delivers to FM team

**Key Point:** The API never sees raw BMS data. It sees pre-processed, anonymised summaries. Like giving an analyst a spreadsheet summary, not access to your entire database.

---

## Data Classification Matrix

| Data Type | Stored On-Prem | Local AI (Llama) | Cloud API (Claude) |
|-----------|---------------|-----------------|---------------------|
| Raw BMS point values | ✅ Yes | ✅ Yes | ❌ Never |
| Historical trends | ✅ Yes | ✅ Yes | ❌ Never |
| Alarm event logs | ✅ Yes | ✅ Yes | ❌ Never |
| Equipment inventory | ✅ Yes | ✅ Yes | ❌ Never |
| Network topology | ✅ Yes | ✅ Yes | ❌ Never |
| IP addresses / VLANs | ✅ Yes | ✅ Yes | ❌ Never |
| Building names/locations | ✅ Yes | ✅ Yes | ❌ Never |
| User identities | ✅ Yes | ✅ Yes | ❌ Never |
| FM team chat messages | ✅ Yes | ✅ Yes | ❌ Never |
| **Anonymised summaries** | ✅ Yes | ✅ Yes | ✅ If opted-in |
| Generic technical queries | N/A | ✅ Yes | ✅ If opted-in |

**Summary:**
- Raw data: NEVER leaves the server
- Anonymised summaries: Only if client opts in to hybrid mode
- Generic technical questions: Can use cloud API (no client data)
- **Client chooses: 100% local or hybrid. Their decision.**

---

## Network Architecture

### Inbound Ports (to SENTINEL Server)

From BMS VLAN:
- TCP 47808 — BACnet/IP (from Niagara)
- TCP 502 — Modbus TCP (from meters/PLCs)
- TCP 1883 — MQTT (from IoT devices, if used)

From Internal Network:
- TCP 9095 — HTTP API (from web UI)
- TCP 9096 — HTTPS (if SSL enabled)

### Outbound Ports (from SENTINEL Server)

**Fully Local Deployment:**
- None (air-gapped capable)

**Hybrid Deployment:**
- TCP 443 — HTTPS to WhatsApp Business API (optional)
- TCP 443 — HTTPS to Telegram Bot API (optional)
- TCP 443 — HTTPS to Cloudflare Tunnel (optional, for remote support)
- TCP 443 — HTTPS to Claude API (optional, hybrid mode only)

### Air-Gapped Deployment

**Yes, SENTINEL can run completely air-gapped:**

- SENTINEL server on BMS VLAN only — no internet
- Local AI model — no cloud dependency
- Web dashboard accessible on internal network only
- No WhatsApp/Telegram (use internal web UI instead)
- Cloudflare Tunnel disabled
- **Everything runs without any external connectivity**

**Trade-off:** Sacrifices chat interface convenience for zero external data exposure.

---

## Local AI Model Details

**Model:** Meta Llama 3.2 (3B or 8B parameter)

**License:** Meta Community License (free for commercial use)

**Runtime:** Ollama (open-source model server)

**Location:** Model weights stored on SENTINEL server GPU/SSD

**Internet Required:** ONLY for initial download (one-time, ~5GB)

**After Installation:** Runs 100% offline, indefinitely

**Important:** The model is a static file. It doesn't "phone home." It doesn't send telemetry. It doesn't update itself. It processes text in → text out. Locally. That's it.

---

## Cloud API Details (Hybridid Mode - Optional)

**Provider:** Anthropic (Claude API)

**Endpoint:** api.anthropic.com

**Encryption:** TLS 1.3 in transit

**Data Retention:** Anthropic does NOT retain API inputs/outputs for model training (per their data policy)

**What Is Sent:** Anonymised, pre-processed summaries only

**What Is NOT Sent:**
- Raw BMS data
- IP addresses
- Building names
- Client identifiers
- User identities

**Control:** Client can disable cloud API entirely. It's a configuration toggle. Default = OFF (local only).

---

## IT Security Q&A

### Q: "Does our building data go to the cloud?"

**A:** "No. SENTINEL runs entirely on your infrastructure. The AI model runs locally on your server. Your BMS data stays in your database on your network. Nothing is sent to any cloud service."

---

### Q: "What about the AI? Doesn't it need the internet?"

**A:** "The AI model (Llama) runs locally on a GPU in your server room. It's the same technology as ChatGPT but running on your own hardware. It doesn't need internet access at all. The model weights are installed once and run offline permanently."

---

### Q: "Is our data used to train AI models?"

**A:** "Absolutely not. The local model is pre-trained and does not learn from your data. Your building data is used for real-time analysis only — it's never sent anywhere for training purposes. If we use a cloud API for optional enhanced analysis, those providers (Anthropic/OpenAI) do not train on API data either."

---

### Q: "What about POPIA compliance?"

**A:** "SENTINEL primarily handles building telemetry data — temperatures, pressures, energy readings, equipment status. This is operational technology data, not personal information as defined by POPIA. However, if the system touches any personal data (like FM team names in chat logs), those records are stored locally and processed according to POPIA requirements. We do not transfer personal data to any third party."

---

### Q: "What about WhatsApp? Isn't that sending data externally?"

**A:** "The WhatsApp/Telegram channel carries conversational messages — the same kind of messages your FM team already sends when they report a fault. For example: 'AHU-01 supply temp is 29°C, compressor fault detected.' This is operational information, not sensitive data. It's the same as a technician calling the help desk and saying 'the chiller has tripped.' WhatsApp messages are end-to-end encrypted by default. If the client requires even higher security, we can use Telegram with self-destructing messages, or Microsoft Teams which stays within the corporate Microsoft 365 tenant."

---

### Q: "Can you air-gap this completely?"

**A:** "Yes. In a fully air-gapped deployment:
- SENTINEL server on the BMS VLAN only — no internet
- Local AI model — no cloud dependency
- Web dashboard accessible on internal network only
- No WhatsApp/Telegram (use internal web UI instead)
- Cloudflare Tunnel disabled
- Everything runs without any external connectivity

This sacrifices the chat interface convenience but gives you zero external data exposure."

---

### Q: "What data do YOU (SENTINEL vendor) have access to?"

**A:** "By default, none. The system runs on your hardware. If you grant us remote support access (via Cloudflare Tunnel or VPN), we can access the SENTINEL admin interface for maintenance and troubleshooting. This access is:
- Revocable at any time by your IT team
- Logged with full audit trail
- Restricted to SENTINEL admin functions only
- Does not include access to your wider corporate network

We never extract, copy, or retain your building data."

---

## One-Liner for Different Audiences

### To the CISO

"SENTINEL runs a local AI model on your hardware. Building data stays in your database on your network. No cloud AI dependency. No data leaves your premises. Optional cloud API for enhanced analysis uses anonymised summaries only, with your explicit opt-in, and the provider doesn't train on your data."

### To the CTO

"Think of it as having a ChatGPT that runs on your own server, trained to understand buildings. It reads your BMS data locally, thinks locally, and answers locally. The internet is only used for the WhatsApp delivery channel — same as your FM team already uses WhatsApp to report faults."

### To the FM Director

"Your building data stays on your server. The AI brain is in your server room, not in the cloud. When your team asks a question on WhatsApp, the answer comes from your own system. Nobody else sees your building data."

### To Procurement / Legal

"SENTINEL processes operational technology data (temperatures, pressures, equipment status) — not personal information. The system runs on-premise with no mandatory cloud dependency. No personal data as defined by POPIA is processed externally. All data storage is within the client's infrastructure."

---

## Security Features

### Data Sovereignty

- All building data stored on client premises
- No mandatory cloud dependency
- Client retains full control and ownership

### Access Control

- Role-based access control (RBAC) for FM team
- Audit logging for all control actions
- Revocable remote support access

### Network Security

- Runs on isolated BMS VLAN
- No inbound internet access required
- Optional outbound HTTPS for chat APIs (client-controlled)

### AI Safety

- Local model cannot "leak" data to third parties
- No training on client data
- Static model weights (no automatic updates)

### Encryption

- HTTPS for all external API calls
- End-to-end encryption for WhatsApp/Telegram
- Database encryption at rest (PostgreSQL)

---

## Summary

**Privacy by Design:**
- Default deployment: 100% local, air-gapped capable
- Building data never leaves client premises
- Optional cloud API uses anonymised summaries only
- Client retains full control

**Security by Design:**
- Isolated BMS VLAN deployment
- No mandatory inbound internet access
- Role-based access control
- Full audit logging

**Compliance:**
- POPIA-compliant data handling
- No personal data processing without consent
- Data stored within client's jurisdiction

**The privacy objection becomes a selling point:** "Unlike cloud-only platforms, SENTINEL keeps your data on your premises."
