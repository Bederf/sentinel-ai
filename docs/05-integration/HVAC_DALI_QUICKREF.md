# HVAC + DALI Integration Quick Reference

**For**: Developers, integrators, facility managers
**Time to read**: 5 minutes (details in HVAC_DALI_INTEGRATION.md)

---

## 1. Traditional HVAC (Standalone)

### How It Works
- **Setpoint**: Target temperature (e.g., 22°C)
- **Control Loop**: Read current temp → Compare to setpoint → Adjust water valve every 2-5 min
- **Energy Cost**: Fixed, doesn't adapt to occupancy

### Challenges
```
6 AM: Pre-cool 1 hour (cost: €3)  →  Over-cooled empty zones
1 PM: Peak demand, can't cool enough  →  Thermal undershoot (24-25°C)
6 PM: Still cooling for absent people  →  Wasted 4 hours until manual setback
```

### Annual Energy
- **88,176 kWh/year** (€13,226 cost)
- 35.3 tonnes CO₂

---

## 2. Tridonic DALI Lighting (Standalone)

### How It Works
- **Controllers**: Master unit on DALI bus (2-wire, daisy-chain 64+ luminaires)
- **Sensors**: PIR (occupancy yes/no) + Lux (daylight 0-20,000)
- **Control**: Occupancy + Daylight → Brightness % (30-second loop)

### Benefits
```
Empty zone → 10% brightness (emergency lighting only)  →  94% energy savings (that zone)
Occupied + bright daylight → 40% brightness (dimming)  →  Sufficient light + energy saved
```

### Annual Energy
- **25,350 kWh/year** (€3,803 cost)
- 10.1 tonnes CO₂
- **58% reduction** vs always-on lighting

### Payback
- Hardware cost: ~€12,000 (controllers, sensors, luminaires)
- ROI: 2.2 years

---

## 3. HVAC + DALI Integration (Siemens BMS Coordination)

### How They Communicate
```
DALI Controller                    Siemens BMS                      HVAC System
│                                  │                                │
Occupancy 85% ────────────────────→ (receives occupancy data)      │
                                   │                                │
                    ◄─────────────  (sends: relax setpoint) ───────→ FCU valve closes
                                   │                                │
Daylight 400 lux ──────────────────→ (receives lux data)           │
                                   │                                │
                    ◄─────────────  (sends: thermal stress) ───────→ Reduce heat load
```

### What HVAC Gets from DALI
| Data | Source | Frequency | Use |
|------|--------|-----------|-----|
| Occupancy % | Badge reader | 30 sec | Adjust setpoint immediately |
| Daylight lux | Daylight sensor | 60 sec | Estimate solar load → pre-cool timing |
| Zone status | PIR sensors | Real-time | Detect unoccupied zones → relax cooling |

### What DALI Gets from HVAC
| Data | Source | Frequency | Use |
|------|--------|-----------|-----|
| Thermal stress | Chiller load | 30 sec | If > 75%, dim lights to reduce heat |
| Demand response | Grid signal | Peak hours | Reduce brightness, support grid |
| Time-of-use price | Energy market | Hourly | Optimize when to pre-cool |

### Real-World Benefit Examples

**Evening Setback (6 PM)**:
```
Without integration:
  Operator manually changes setpoint at 10 PM  → 4-hour energy waste (€4.80/night)

With integration:
  DALI detects occupancy drop → HVAC setpoint relaxed immediately  → Saves €4.80
  Multiplied across building → €1,200/year saved
```

**Peak Demand (1 PM)**:
```
Without integration:
  HVAC chiller runs 30 kW, room still too warm (24-25°C)

With integration:
  DALI dims lights 20%  → 4.6 kW less heat
  + Relax setpoint 0.5°C  → 3 kW chiller relief
  Result: Room achieves 23°C (comfort improved), chiller within capacity
```

### Annual Savings
- HVAC optimization: 26% reduction (€1,650/year)
- Lighting + HVAC synergy: €7,064/year combined
- System payback: 1.9 years

---

## 4. HVAC + DALI + SENTINEL AI

### AI Layers Added

#### Layer 1: Occupancy Forecasting
```
Historical data (4 weeks):
├── Monday-Friday: 85% typical occupancy by 8:00 AM
├── Friday: 60% (early departures)
└── Holidays: 5% (skeleton staff)

AI Model (LSTM Neural Net):
├── Input: Last 28 days occupancy patterns
├── Output: Tomorrow's hourly occupancy forecast
├── Accuracy: 85-90% (higher on weekdays)
└── Confidence: "92% probability Zone-101 has 50+ people by 8 AM"
```

#### Layer 2: Predictive Pre-Cooling
```
Traditional: Pre-cool at fixed 6:30 AM (wastes energy on cloudy days)

AI-Optimized:
├── 6:00 AM: Check weather forecast (clear vs cloudy)
├── Check occupancy prediction (holiday vs normal day)
├── Calculate: How much pre-cool needed?
│   └── Clear day, 90% occupancy → Pre-cool 1 hour (20 kWh)
│   └── Cloudy day, 60% occupancy → Pre-cool 0.5 hours (10 kWh)
└── Result: 5-10 kWh saved per day × 250 days = €187-€375/year
```

#### Layer 3: Demand Response Coordination
```
Peak hour trigger: Grid frequency < 49.9 Hz, price > €0.35/kWh

SENTINEL Decision:
├── Option A: Reduce lighting 20%  → 4.6 kW thermal relief
├── Option B: Relax HVAC setpoint 0.5°C  → 3 kW reduction
├── Option C: Discharge battery (if available)  → 2 kW offset
├── Optimal: All three  → 9.6 kW grid reduction
└── Benefit: €3.36 saved this hour × 100 peak hours = €336/year
```

#### Layer 4: Cross-System Optimization
```
Inputs: Occupancy forecast, weather (solar, temp), energy prices, comfort constraints
Objective: Minimize cost while maintaining 95% comfort satisfaction

Output: Coordinated setpoints across all modules
├── Pre-cool schedule (HVAC): 6:45 AM start, 1 hour
├── Morning ramp: Zone lights 100% by 8:30 AM
├── Midday: Dim lights if thermal stress detected
├── Afternoon: Adjust chiller based on solar gain forecast
└── Evening: Automatic setback when occupancy drops
```

### Annual Energy Reduction
- **HVAC**: 65,012 kWh (26% reduction)
- **Lighting**: 23,000 kWh (10% reduction from DALI baseline)
- **Total**: 88,012 kWh (vs 149,616 baseline all-manual)
- **Savings**: €10,293/year
- **Carbon avoided**: 27.5 tonnes CO₂
- **Payback period**: 1.9 years for full system

---

## 5. Quick Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Lighting doesn't dim at peak hours | DALI not receiving occupancy signal | Check badge reader integration, PIR sensor battery |
| HVAC setpoint not changing | Siemens BMS not receiving SENTINEL recommendation | Check BACnet connectivity, device status online |
| Evening setback still delayed | Recommendation not executed by scheduler | Check background job status, verify occupancy drop detected |
| Room temperature overshoots | Pre-cool overly aggressive | Reduce pre-cool duration by 15 minutes, let AI learn |
| Occupants complain "too cold in morning" | Pre-cool not activated | Check weather forecast API, verify chiller available |

---

## 6. Key SENTINEL Services

### Backend
```python
# Occupancy-aware lighting
from app.services.dali_service import get_dali_service
dali = get_dali_service()
dali.get_zone_occupancy('Zone-101')  # Returns: occupancy_percent, sensors, status

# Occupancy from security
from app.services.security_occupancy_service import get_security_occupancy_service
occ_service = get_security_occupancy_service()
occ_service.get_zone_occupancy('Zone-101')  # Returns: people count, badge data

# AI optimization
from app.services.ai_optimizer import AIOptimizerService
ai = AIOptimizerService()
recommendation = await ai.analyze_building('site-002')  # Returns: setpoints, forecast
```

### API Endpoints
```
# Get occupancy
GET /api/occupancy/zones/{zone_id}
  ← occupancy_percent, source (badge/PIR), confidence

# Apply HVAC setpoint
POST /api/hvac/zones/{zone_id}/setpoint
  ← {"setpoint": 25.0} → {success: true, old_setpoint: 22}

# Set lighting brightness
POST /api/dali/zones/{zone_id}/brightness
  ← {"level": 50} → {success: true, fade_time: 3}

# Get AI recommendations
GET /api/optimization/analysis/{site_id}
  ← {occupancy_forecast, solar_load, setpoint_recommendations, projected_savings}
```

---

## 7. Design Decisions in SENTINEL

### Why DALI is Integrated into HVAC Coordination
1. **Real-time occupancy data** - PIR sensors catch occupancy changes <30 sec
2. **Thermal benefit** - Lighting accounts for 23 kW heat (7-8% of HVAC load)
3. **Occupancy correlation** - Badge reader provides exact headcount (not just yes/no)
4. **Cost-effective** - DALI system pays for itself; HVAC coordination is "free" layer on top

### Why AI Forecasting Matters
1. **Anticipatory control** - Pre-cool 1 hour before occupancy (vs reactive post-arrival)
2. **Weather adaptation** - Solar load varies ±50% day-to-day; fixed schedule can't handle
3. **Grid support** - Respond to price/frequency signals 15+ minutes before peak (vs manual)
4. **Learning** - System improves over 4 weeks, becomes site-specific

### Security & Safety
- All HVAC changes validated against SafetyEngine (temperature limits, runtime constraints)
- DALI commands only execute if device online (no ghost control)
- Audit log: Every change logged with reason (occupancy %, AI confidence, cost saved)
- Manual override: Facility manager can disable automation anytime

---

## 8. Expansion: Solar + Battery (Multi-Module)

If building has roof PV + battery:

```
Morning (6-9 AM):
├── SENTINEL: Check solar forecast → Expect 20 kW generation
├── HVAC: Pre-cool uses solar (not grid)
├── DALI: Use solar power if available
└── Battery: Charge from solar surplus

Midday (11 AM - 3 PM):
├── PV peak: 45 kW generation
├── SENTINEL: Route solar to highest-priority load
│   ├── Priority 1: Essential (chiller, lighting, security)
│   ├── Priority 2: Flexible (water heating, EV charging)
│   └── Priority 3: Storage (charge battery if surplus)
└── Demand response: Use PV + battery to reduce grid draw during peak price

Evening (5-7 PM):
├── PV generation drops
├── SENTINEL: Discharge battery to cover peak demand
├── Cost: €0.35/kWh avoided by battery (profit per kWh discharged)
└── HVAC: Setback (low occupancy)
```

**Multi-Module Coordinator** (app/services/demand_aware_coordinator.py):
```
Coordinates: HVAC + DALI + Solar Inverter + Battery
Optimizes: Energy cost + Grid support + Comfort
Decides: Which loads to shift, which to reduce, which to source locally
```

---

## Next Steps

1. **For facility managers**:
   - Ensure DALI occupancy sensors (PIR) are installed and battery-checked monthly
   - Monitor energy dashboard for evening setback timing
   - Report if setback delayed (> 30 minutes after last occupancy)

2. **For engineers**:
   - Verify BACnet connectivity between Siemens BMS and DALI controllers
   - Configure setpoint limits in SafetyRulesRepository (18-28°C typical)
   - Test background scheduler runs every 30 seconds (check logs)

3. **For AI tuning**:
   - After 4 weeks of data, check occupancy forecast accuracy (aim for 85%+)
   - Adjust pre-cool start time if building consistently cold/warm at occupancy arrival
   - Monitor solar model accuracy vs actual chiller load (should track within ±10%)

---

## More Details

See full research document: `HVAC_DALI_INTEGRATION.md`

Key sections:
- Section 1: HVAC physics (how setpoints control energy)
- Section 2: DALI system architecture (PIR sensors, luminaires, controllers)
- Section 3: Integration methods (BACnet communication, data exchange)
- Section 4: AI optimization (forecasting, pre-cooling, demand response)
- Section 5: Energy comparisons (annual consumption, cost, carbon)
- Section 6: Real-world use cases (with timelines and cost impact)
- Section 7: SENTINEL implementation (services, API endpoints, code)
