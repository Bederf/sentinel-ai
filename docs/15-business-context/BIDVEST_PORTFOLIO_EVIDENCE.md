---
title: "Portfolio Evidence: Enterprise AI Systems"
type: "guide"
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

# Portfolio Evidence: Enterprise AI Systems

## Two Production AI Platforms

You've built **two distinct production AI systems** demonstrating full-stack CTO capabilities:

---

## 1. SENTINEL - Building Management Intelligence

**Domain:** Facilities Management / Smart Buildings
**Status:** Production-ready demo
**Demo Site:** Sandton City Office Tower (3 floors, 156 equipment, 4,850 data points)

| Capability | Implementation |
|------------|----------------|
| **BMS/SCADA Integration** | Siemens Desigo CC V5.0 with 10 subsystems |
| **Predictive Maintenance** | LSTM/Autoencoder ML models |
| **Smart Building Integration** | BACnet/IP, Modbus TCP, DALI-2, OPC-UA, KNX |
| **Live Telemetry** | Temperature, CO2, occupancy, lighting, energy |
| **Conversational AI** | Claude + Ollama hybrid routing (40% cost savings) |
| **Real-time Alerts** | Telegram integration with slash commands |
| **Work Order Automation** | AI-generated with parts/skills |
| **Safety Interlocks** | Control validation layer |
| **Energy Management** | Load shedding, demand response, TOU tariffs |

**Equipment Monitored:**
- HVAC: 3 chillers, 3 AHU, 15 VAV, 15 FCU
- Lighting: 15 DALI zones, 15 luminaire groups
- Energy Centre: 4 generators (DSE8610), 2 UPS, 2 transformers
- Sensors: 60+ (temperature, CO2, daylight, occupancy)

**Relevance to Bidvest:** Direct FM industry experience with enterprise BMS

---

## 2. AimTheLaw - Legal Practice AI Platform

**Domain:** Legal Tech / Professional Services
**Status:** Live production (app.aimthelaw.co.za)

| Capability | Implementation |
|------------|----------------|
| **AI Agent Orchestration** | LangGraph multi-step workflows |
| **Document Processing** | OCR, embeddings, chronology extraction |
| **Voice AI** | ElevenLabs TTS + transcription |
| **Multi-LLM Support** | Claude, OpenAI, DeepSeek, Ollama |
| **Workflow Automation** | 16 N8N standardized workflows |
| **Monitoring & Drift Detection** | Prometheus, Grafana, Loki stack |
| **Email AI** | Auto-response with confidence scoring |
| **Video Generation** | Remotion for promotional videos |

**Infrastructure:**
- Docker Swarm + Kubernetes (K3s)
- Cloudflare Tunnel + Caddy
- GitHub Actions CI/CD
- Self-hosted Supabase (PostgreSQL)

---

## Skills Matrix: Both Platforms Combined

| CTO Competency | SENTINEL Evidence | AimTheLaw Evidence |
|----------------|-------------------|---------------------|
| **AI/ML Strategy** | Predictive maintenance models | LangGraph agent orchestration |
| **Multi-LLM Management** | Claude + Ollama hybrid | Claude, OpenAI, DeepSeek, Ollama |
| **Real-time Systems** | BMS telemetry, SSE streaming | Voice chat, email processing |
| **Document AI** | RAG for equipment manuals | Legal document OCR, embeddings |
| **Workflow Automation** | Work order generation | 16 N8N standardized workflows |
| **DevOps/Infrastructure** | FastAPI + React | Docker Swarm, K8s, CI/CD |
| **Monitoring** | Health dashboards | Prometheus, Grafana, AI drift detection |
| **Security** | Safety interlocks, RLS | Auth, RLS, POPIA compliance |
| **Production Operations** | Demo environment | Live production users |

---

## Technical Depth Demonstrated

### AI/ML Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Layer                                  │
├─────────────────────────────────────────────────────────────┤
│  SENTINEL                    │  AimTheLaw                   │
│  • LSTM time-series          │  • LangGraph agents          │
│  • Autoencoder anomaly       │  • RAG document search       │
│  • Hybrid routing (40% save) │  • Multi-model fallback      │
│  • Explainable AI (XAI)      │  • AI drift detection        │
│  • Safety validation         │  • Confidence scoring        │
└─────────────────────────────────────────────────────────────┘
```

### Production Infrastructure

```
┌─────────────────────────────────────────────────────────────┐
│                    Infrastructure                            │
├─────────────────────────────────────────────────────────────┤
│  SENTINEL                    │  AimTheLaw                   │
│  • FastAPI + React           │  • FastAPI + React           │
│  • Supabase PostgreSQL       │  • Self-hosted Supabase      │
│  • Systemd services          │  • Docker Swarm + K3s        │
│  • Telegram integration      │  • GitHub Actions CI/CD      │
│  • MCP protocol server       │  • Cloudflare + Caddy        │
└─────────────────────────────────────────────────────────────┘
```

---

## Interview Talking Points

### "Tell me about your AI experience"

> "I've built two production AI platforms. SENTINEL is an AI-powered BMS for facilities management - predictive maintenance, smart building integration, conversational AI. AimTheLaw is a legal practice management system with LangGraph agent orchestration, document AI, and voice chat. Both handle multi-LLM routing for cost optimization."

### "How do you handle production operations?"

> "AimTheLaw is live with real users. I've implemented Docker Swarm, Kubernetes for N8N workflows, GitHub Actions CI/CD, and a full monitoring stack with Prometheus, Grafana, and AI drift detection that alerts me if model quality degrades."

### "What about document processing?"

> "AimTheLaw processes legal documents at scale - OCR extraction, vector embeddings for semantic search, chronology extraction, and automatic task generation. SENTINEL applies similar RAG techniques to equipment manuals for technician support."

### "How do you ensure AI reliability?"

> "Multiple layers: AI drift detection compares daily metrics against 7-day baselines and alerts on regression. Confidence scoring gates automated actions. Safety interlocks prevent dangerous BMS commands. Human-in-the-loop for high-stakes decisions."

---

## Key Differentiators

| What Sets You Apart | Evidence |
|---------------------|----------|
| **Two production AI systems** | SENTINEL + AimTheLaw |
| **Domain diversity** | FM, Legal - transferable patterns |
| **Full-stack delivery** | From ML models to production deployment |
| **Cost optimization** | Hybrid AI routing, multi-LLM fallback |
| **Operational maturity** | Monitoring, drift detection, CI/CD |
| **SA-specific** | Load shedding (SENTINEL), POPIA compliance (AimTheLaw) |

---

## Closing Statement

> "I've built two complete AI platforms from architecture to production. SENTINEL is ready to deploy at Bidvest scale for facilities management. AimTheLaw proves I can operate production AI systems with real users. This isn't theoretical - it's working code that I can demonstrate."
