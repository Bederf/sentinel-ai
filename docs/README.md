---
title: "SENTINEL Documentation"
type: "guide"
status: "approved"
version: "1.0.0"
created: "2026-01-30"
updated: "2026-01-30"
author: "Sentinel Development Team"
tags: ["documentation", "overview"]
domain: "general"
audience: "all"
complexity: "beginner"
estimated_read_time: 5
---

# SENTINEL Documentation

Comprehensive documentation for the SENTINEL BMS Intelligence Platform.

## Quick Navigation

### 🚀 Getting Started
- [Quick Start Guide](01-getting-started/quick-start.md) - 5-minute setup
- [Development Environment](01-getting-started/development-environment.md) - Full setup guide
- [Demo Guide](01-getting-started/demo-guide.md) - Demo walkthrough

### 🏗️ Architecture
- [System Overview](02-architecture/system-overview.md) - High-level architecture
- [Device Abstraction Layer](02-architecture/device-abstraction-layer.md) - Protocol-agnostic interface
- [Naming Conventions](02-architecture/naming-conventions.md) - Device ID and point naming

### 📚 API Reference
- [REST API Endpoints](03-api-reference/rest-api-endpoints.md) - Complete API reference
- [MCP Tools Reference](03-api-reference/mcp-tools-reference.md) - Model Context Protocol tools

### ✨ Features
- **[AI Operations & Monitoring](04-features/ai-operations-monitoring.md)** - Day-to-day AI monitoring & recommendations (control-aware)
- **[44-02: Explainable AI for ML Predictions](04-features/44-02-explainable-ai.md)** - Natural language explanations for AI predictions (Phase 44-02)
- **[Asset Baseline Assessment](04-features/44-asset-baseline-assessment.md)** - Asset condition scoring and maintenance cost modeling (Phase 44)
- **[Routine Inspection & Maintenance](04-features/45-routine-inspection-maintenance.md)** - Field inspection workflow with baseline tracking (Phase 45)
- **[Repair Effectiveness & ML Feedback Loop](04-features/46-repair-effectiveness-ml-feedback.md)** - Post-repair health updates and ML learning (Phase 46)
- [Technician Chat](04-features/technician-chat.md) - Guided fault diagnosis (Phase 19)
- [AI-Assisted Onboarding](04-features/ai-assisted-onboarding.md) - Import BMS data via MCP tools
- [41 - ML Knowledge Capture](04-features/41-ml-knowledge-capture-01.md) - OCR and data collection
- [42 - Data Collection & Storage](04-features/42-data-collection-storage.md) - InfluxDB integration
- [43 - ML Model Development](04-features/43-ml-model-development.md) - LSTM and Autoencoder models
- [18 - Fault Code Database](04-features/18-fault-code-database.md) - Equipment fault diagnosis

### 🏢 BMS Concepts
- [BMS Fundamentals](05-bms-concepts/bms-fundamentals.md) - BMS domain knowledge
- [HVAC Systems Guide](05-bms-concepts/hvac-systems.md) - Chiller, AHU, FCU, VAV with schematics (Technician/Operator reference)

### 🛡️ Safety & Compliance
- [Safety Interlocks Engine](06-safety-compliance/safety-interlocks-engine.md) - Safety validation

### 🔗 Integrations
- [DALI-HVAC Integration](07-integrations/dali-hvac-integration.md) - Cross-system comfort diagnosis
- [CAFM Schema](07-integrations/cafm-schema.md) - CAFM data model
- [Energy Centre](07-integrations/energy-centre.md) - Generators, ATS, power metering, UPS

### 📦 Modules
- [Module Registry](13-modules/module-registry.md) - Bolt-on module system architecture

### 🤖 AI & ML
- [Claude Integration](08-ai-ml/claude-integration.md) - Claude API usage
- [Hybrid AI Router](08-ai-ml/hybrid-ai-router.md) - Ollama/Claude routing
- **[RAG Integration Overview](08-ai-ml/rag-integration-overview.md)** - Vector database and semantic search (Phase 44-01)
- **[Explainable AI](08-ai-ml/explainable-ai.md)** - XAI for ML predictions and maintenance recommendations (Phase 44-02)

### 🔧 Development
- [Tool Use Best Practices](12-development/tool-use-best-practices.md) - Development workflow

### 🧪 Testing
- [Testing Strategy](11-testing/testing-strategy.md) - Test architecture
- [E2E Testing](11-testing/e2e-testing.md) - End-to-end tests
- [Test Data](11-testing/test-data.md) - Test data management

### 🌍 South Africa Context
- [Load Shedding Optimization](14-south-africa-context/load-shedding-optimization.md) - Eskom load shedding

## Documentation Structure

```
docs/
├── 01-getting-started/      # Onboarding, setup, quick start
├── 02-architecture/         # System design, patterns, data flow
├── 03-api-reference/        # REST API, MCP tools, SSE streams
├── 04-features/             # Feature specifications
├── 05-bms-concepts/         # BMS/HVAC domain knowledge
├── 06-safety-compliance/    # Safety interlocks, audit trails
├── 07-integrations/         # BACnet, Modbus, CAFM, BMS, DALI
├── 08-ai-ml/                # Claude, Ollama, predictions
├── 09-operations/           # Deployment, monitoring
├── 10-security/             # Auth, audit, API keys
├── 11-testing/              # Unit tests, integration tests
├── 12-development/          # Workflow, tooling, best practices
├── 13-modules/              # Bolt-on module system (Energy, HVAC, Security, Lighting)
├── 14-south-africa-context/ # Load shedding, Eskom
├── 15-troubleshooting/      # Common issues, diagnostics
├── 16-glossary/             # BMS terms, acronyms
├── 17-appendices/           # Migration scripts, references
└── _templates/              # Documentation templates and standards
```

## Documentation Standards

All documentation follows the [AimTheLaw-style standards](_templates/standards.md):

- **Frontmatter:** Required metadata on all documents
- **Markdown:** GitHub Flavored Markdown (GFM)
- **Diagrams:** Mermaid.js for architecture and flow diagrams
- **Code Examples:** Tested, syntactically correct, with comments
- **Audience:** Clearly defined (developers, operators, safety engineers, etc.)
- **Complexity:** Reading level indicated (beginner, intermediate, advanced)

## Frontmatter Schema

Every document must include frontmatter:

```yaml
---
title: "Document Title"
type: "architecture|guide|reference|spec|tutorial|audit|policy"
status: "draft|review|approved|deprecated"
version: "1.0.0"
created: "2026-01-30"
updated: "2026-01-30"
tags: ["tag1", "tag2"]
domain: "bms|hvac|lighting|security|water|solar|compliance|general"
audience: "developers|operators|product-managers|safety-engineers|all"
complexity: "beginner|intermediate|advanced"
estimated_read_time: 15
---
```

## Validation

Run validation before committing documentation:

```bash
# Validate frontmatter
python scripts/validate-frontmatter.py

# Check links (requires markdown-link-check)
npm install -g markdown-link-check
find docs -name "*.md" -exec markdown-link-check {} \;
```

## Contributing

When adding new documentation:

1. **Choose appropriate directory** based on content type
2. **Use templates** from `_templates/` directory
3. **Include frontmatter** with all required fields
4. **Test code examples** to ensure they work
5. **Add diagrams** using Mermaid.js where appropriate
6. **Validate** using validation scripts
7. **Link** from relevant sections in this README

## Reading Guide

### For New Developers
1. Start with [Quick Start Guide](01-getting-started/quick-start.md)
2. Read [Development Environment](01-getting-started/development-environment.md)
3. Review [System Overview](02-architecture/system-overview.md)
4. Study [Tool Use Best Practices](12-development/tool-use-best-practices.md)

### For BMS Operators
1. Start with [Quick Start Guide](01-getting-started/quick-start.md)
2. Review [Demo Guide](01-getting-started/demo-guide.md)
3. Understand [Safety Interlocks Engine](06-safety-compliance/safety-interlocks-engine.md)
4. Study [Load Shedding Optimization](14-south-africa-context/load-shedding-optimization.md)

### For Product Managers
1. Start with [System Overview](02-architecture/system-overview.md)
2. Review [Features](04-features/) for capability overview
3. Study [BMS Fundamentals](05-bms-concepts/bms-fundamentals.md) for domain knowledge

### For Safety Engineers
1. Start with [Safety Interlocks Engine](06-safety-compliance/safety-interlocks-engine.md)
2. Review [System Architecture](02-architecture/system-overview.md) for data flow
3. Study [Audit Trail](06-safety-compliance/audit-trail.md) for compliance

## Status

- **Total Directories:** 17
- **Total Documents:** 18 (in progress)
- **With Frontmatter:** 12
- **Target:** 25-30 core documents

## Next Actions

- [ ] Add frontmatter to migrated files
- [ ] Create Tier 1 critical documents (safety, database, API)
- [ ] Create Tier 2 domain-specific docs (BMS concepts, load shedding)
- [ ] Create Tier 3 feature specs
- [ ] Create Tier 4 troubleshooting and operations guides
- [x] Module Registry documentation (13-modules/module-registry.md)
- [x] Energy Centre integration (07-integrations/energy-centre.md)

## Related Resources

- [CLAUDE.md](../CLAUDE.md) - Claude Code project instructions
- [README_MCP_INTEGRATION.md](../backend/README_MCP_INTEGRATION.md) - MCP server guide
- [NAMING_CONVENTIONS.md](../NAMING_CONVENTIONS.md) - Device naming (moved to docs)
