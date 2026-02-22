# HVAC + DALI + SENTINEL AI Integration Documentation

**Complete research and implementation guide for building system coordination**

---

## Research Documents

### 1. [HVAC_DALI_INTEGRATION.md](HVAC_DALI_INTEGRATION.md) - **Complete Technical Guide**
- **Length**: 18,000+ words
- **Time to read**: 45-60 minutes
- **Audience**: Engineers, integrators, systems architects

**Covers**:
- How traditional HVAC systems work (setpoints, comfort vs efficiency, energy consumption)
- Tridonic DALI lighting architecture (controllers, sensors, occupancy-aware control)
- Integration methods (BACnet communication, data exchange, thermal coordination)
- SENTINEL AI optimization (occupancy forecasting, pre-cooling, demand response)
- Energy comparisons (baseline, standalone, integrated, with AI)
- Real-world use cases (morning thermal comfort, peak demand response, evening setback)
- Implementation in SENTINEL (services, API endpoints, code examples)

**Key Sections**:
1. Traditional HVAC System (Section 1)
2. Tridonic DALI Lighting System (Section 2)
3. HVAC + Tridonic Integration (Section 3)
4. HVAC + DALI + Sentinel AI (Section 4)
5. Energy Consumption Comparisons (Section 5)
6. Real-World Use Cases (Section 6)
7. Implementation in SENTINEL (Section 7)

---

### 2. [HVAC_DALI_QUICKREF.md](HVAC_DALI_QUICKREF.md) - **Quick Reference**
- **Length**: 2,500 words
- **Time to read**: 5-10 minutes
- **Audience**: Facility managers, operators, developers needing quick overview

**Covers**:
- 1-page summaries of each system (HVAC, DALI, integration, AI)
- Key benefits table (energy savings, payback periods)
- Troubleshooting guide
- SENTINEL services quick reference
- Design decisions and security considerations

**Use this when you need**:
- Quick lookup of system capabilities
- Troubleshooting guidance
- Energy savings estimates
- Integration benefits summary

---

### 3. [HVAC_DALI_ARCHITECTURE.md](HVAC_DALI_ARCHITECTURE.md) - **Visual & Sequence Diagrams**
- **Length**: 3,000 words
- **Time to read**: 15-20 minutes (visual heavy, scan-friendly)
- **Audience**: Visual learners, architects, operators

**Covers**:
- System architecture overview (block diagram)
- Data flow sequence: Evening setback (6 PM) with full timeline
- Control architecture: Multi-module coordination
- Zone architecture: Single zone (Zone-101) detailed breakdown
- Energy decision tree: Peak demand response (1 PM)
- Occupancy forecast model: LSTM neural network workflow

**Use this when you need**:
- Visual understanding of how systems interact
- Data flow for debugging
- Timeline understanding of automation sequence
- Decision logic walkthrough

---

## Quick Navigation

### For Different Roles

**Facility Manager**:
1. Read: HVAC_DALI_QUICKREF.md (Section 1-3) - 5 min
2. Reference: Troubleshooting (Section 5) as needed
3. Monitor: Energy dashboard for savings tracking

**HVAC Technician**:
1. Read: HVAC_DALI_INTEGRATION.md (Sections 1, 3) - 20 min
2. Reference: Safety constraints, setpoint limits
3. Coordinate: With DALI team on occupancy data

**Lighting/DALI Technician**:
1. Read: HVAC_DALI_INTEGRATION.md (Section 2) - 10 min
2. Reference: Occupancy sensor calibration, PIR placement
3. Coordinate: With HVAC team on thermal stress signals

**Software Engineer**:
1. Read: HVAC_DALI_INTEGRATION.md (Sections 3, 4, 7) - 30 min
2. Study: HVAC_DALI_ARCHITECTURE.md (Section 2, 6) - 15 min
3. Reference: API endpoints, data models, implementation patterns

**System Architect**:
1. Read: All documents in order - 90 min comprehensive
2. Study: Energy comparisons (Section 5) for ROI analysis
3. Design: Custom configurations for different building types

**Facility Manager**:
1. Focus: Quick benefits summary + troubleshooting
2. Read: HVAC_DALI_QUICKREF.md (Sections 1-3, 5)
3. Monitor: Energy savings dashboard

---

## Key Takeaways by Document

### HVAC_DALI_INTEGRATION.md

**Main Learning**: How three separate systems (HVAC, DALI, AI) combine for 43% energy reduction

**Key Numbers**:
- HVAC alone: 88,176 kWh/year (€13,226)
- DALI alone: 25,350 kWh/year (€3,803) - 58% lighting reduction
- HVAC + DALI: 65,012 kWh/year (€9,752) - 26% HVAC reduction
- HVAC + DALI + AI: 81,000 kWh/year (€12,150) - 43% total reduction
- **Annual saving**: €10,293/year for 300-desk building
- **Payback**: 1.9 years for full system

**Critical Concepts**:
1. Setpoints control energy (1°C = 3-5% energy change)
2. DALI occupancy reduces lighting 58% (alone)
3. Integration adds 26% HVAC reduction (occupancy-triggered setback)
4. AI adds 17% additional reduction (pre-cooling optimization, demand response)
5. Multi-module coordination beats single-module optimization

---

### HVAC_DALI_QUICKREF.md

**Main Learning**: System capabilities and decision patterns in digestible form

**Quick Facts**:
- Evening setback: 4-hour delay (manual) → immediate (SENTINEL)
- Peak demand: 9.6 kW grid reduction possible at 1 PM
- Occupancy response: < 30 seconds for both HVAC and DALI
- AI accuracy: 85-90% occupancy forecasting
- Confidence: 95% on Mon-Thu, 75% on Friday

**Design Decisions**:
1. Why DALI integrated into HVAC: Real-time occupancy + thermal benefit
2. Why AI matters: Anticipatory control (pre-cool before occupancy)
3. Why forecasting helps: Weather-adaptive (clear vs cloudy day)
4. Why demand response: Grid support + cost optimization

---

### HVAC_DALI_ARCHITECTURE.md

**Main Learning**: Data flows, sequences, and decision trees in visual form

**Key Sequences**:
1. Evening Setback (Section 2): 45 seconds full automation
2. Peak Demand Response (Section 5): Multi-objective decision tree
3. LSTM Forecast (Section 6): 87% accuracy, continuously improving

**Visual Aids**:
- System block diagram (connections)
- Timeline sequence (6 PM setback, 45-second execution)
- Zone architecture (single room, all control points)
- Decision tree (peak hour optimization logic)
- LSTM model (forecast generation workflow)

---

## Energy Consumption Quick Reference

### Baseline Scenarios

| System | HVAC | Lighting | Total | Cost/Year | CO₂ |
|--------|------|----------|-------|-----------|-----|
| **HVAC Only (Manual)** | 88,176 | - | 88,176 | €13,226 | 35.3 T |
| **DALI Only (Smart Lighting)** | - | 25,350 | 25,350 | €3,803 | 10.1 T |
| **Baseline (Both Manual)** | 88,176 | 61,440 | 149,616 | €22,443 | 59.9 T |

### Optimized Scenarios

| System | HVAC | Lighting | Total | Cost/Year | CO₂ | Saving |
|--------|------|----------|-------|-----------|-----|--------|
| **HVAC + DALI Integrated** | 65,012 | 25,350 | 90,362 | €13,554 | 36.1 T | 40% |
| **+ SENTINEL AI** | 58,000 | 23,000 | 81,000 | €12,150 | 32.4 T | 46% |

### ROI Analysis

| Investment | Hardware Cost | Annual Saving | Payback |
|------------|---------------|---------------|---------|
| DALI System | €12,000 | €5,414 | 2.2 years |
| Full Integration (BACnet) | €20,000 | €10,293 | 1.9 years |

---

## Glossary

**HVAC**: Heating, Ventilation, Air Conditioning
- **Setpoint**: Target temperature (e.g., 22°C)
- **Chiller**: Cooling equipment (max 30 kW in example)
- **FCU**: Fan Coil Unit (local heating/cooling per zone)
- **VAV**: Variable Air Volume damper
- **Thermal Mass**: Building's ability to store/release heat (2.5 hours in example)

**DALI**: Digital Addressable Lighting Interface
- **Controller**: Master unit (Tridonic Luma Control 2)
- **Luminaire**: Smart light bulb/panel
- **PIR Sensor**: Motion detector (binary: yes/no occupancy)
- **Lux Sensor**: Daylight intensity (0-20,000 lux)
- **Scene**: Pre-configured brightness level

**SENTINEL Systems**:
- **DALIService**: Manages occupancy sensors + lighting control
- **SecurityOccupancyService**: Badge-based occupancy calculation
- **AIOptimizerService**: Forecasting + recommendations
- **DeviceManager**: Abstract device control (BACnet/Modbus)
- **SafetyEngine**: Validates changes against constraints

**Grid/Energy**:
- **TOU (Time-of-Use)**: Peak hours (1-3 PM, €0.35/kWh) vs off-peak (€0.15/kWh)
- **Demand Response**: Grid asks customers to reduce load during peaks
- **PV**: Photovoltaic (solar panels)
- **BESS**: Battery Energy Storage System
- **kW**: Power consumption
- **kWh**: Energy (power × time)

---

## Related Documents in SENTINEL

- **API Reference**: `/docs/03-api-reference/`
  - devices-api.md (batch endpoints for multi-device control)
  - hvac-api.md (zone control, chiller management)
  - dali-api.md (lighting control)

- **Architecture**: `/docs/02-architecture/`
  - device-abstraction.md (how BACnet/Modbus unified)
  - safety-interlocks.md (validation constraints)
  - approval-workflow.md (manual override process)

- **Features**: `/docs/04-features/`
  - predictive-maintenance.md (ML health models)
  - demand-aware-coordination.md (multi-module optimization)
  - occupancy-based-control.md (zone-level automation)

- **Codebase**:
  - `/backend/app/services/dali_service.py` - Occupancy + lighting
  - `/backend/app/services/security_occupancy_service.py` - Badge data
  - `/backend/app/services/ai_optimizer.py` - Forecasting
  - `/backend/app/api/hvac.py` - HVAC endpoints
  - `/backend/app/api/dali.py` - DALI endpoints

---

## FAQ

**Q: How much energy does this really save?**
A: 43% total reduction (€10,293/year for 300-desk building). Payback in 1.9 years. See Section 5, HVAC_DALI_INTEGRATION.md for detailed breakdown.

**Q: Can I use just DALI without HVAC integration?**
A: Yes. DALI alone saves 58% on lighting (€5,414/year, 2.2-year payback). HVAC integration adds only 26% more HVAC saving, so ROI is still positive even partial integration.

**Q: What if occupancy sensors fail?**
A: System falls back to fixed schedule (manual operator sets times). Not optimized, but building still functions. SENTINEL logs the failure and alerts facility manager.

**Q: How accurate is the occupancy forecasting?**
A: 85-90% on Mon-Thu, 75% on Friday. Confidence increases after 4 weeks of data. See Section 4.2, HVAC_DALI_INTEGRATION.md.

**Q: Is there any occupant discomfort?**
A: Minimal. Tests show 95% comfort satisfaction maintained. Evening setback to 25°C for low occupancy is imperceptible. Peak demand lighting reduction still provides 400+ lux (office standard).

**Q: How long does automation take?**
A: 45 seconds (Section 2, HVAC_DALI_ARCHITECTURE.md). Occupancy change detected → recommendation created → safety validated → executed. Much faster than 4-hour manual process.

**Q: Can I override SENTINEL automation?**
A: Yes. Facility manager can disable/pause automation anytime. Manual control always available. Approval workflow provides further safety check.

---

## Feedback & Updates

These documents are based on SENTINEL codebase as of February 2026.

For questions:
1. Check HVAC_DALI_QUICKREF.md troubleshooting (Section 5)
2. Review relevant HVAC_DALI_INTEGRATION.md section
3. Study HVAC_DALI_ARCHITECTURE.md sequence diagram for your scenario
4. Reference SENTINEL API endpoint documentation in `/docs/03-api-reference/`
5. Check codebase: `/backend/app/services/` and `/backend/app/api/`

---

## Document Versions

| Document | Version | Last Updated | Status |
|----------|---------|--------------|--------|
| HVAC_DALI_INTEGRATION.md | 1.0 | Feb 14, 2026 | Complete |
| HVAC_DALI_QUICKREF.md | 1.0 | Feb 14, 2026 | Complete |
| HVAC_DALI_ARCHITECTURE.md | 1.0 | Feb 14, 2026 | Complete |
| INDEX.md (this file) | 1.1 | Feb 22, 2026 | Complete |
| sentry-desk-complaint-agent-spec.md | 1.0 | Feb 22, 2026 | Complete |

---

## Agent Specifications

### [Sentry Desk Complaint Agent Spec](sentry-desk-complaint-agent-spec.md)
- **Length**: Full specification (14 sections)
- **Audience**: Developers, integrators, architects
- **Covers**: Goals, workflows, tools, data sources, complaint types, AI tier system, context/memory, events/state, error handling, metrics, open questions

See also: [AI Recommendation Agent Spec](../08-ai-ml/ai-recommendation-agent-spec.md) for the backend PARASITE autonomous recommendation system.
